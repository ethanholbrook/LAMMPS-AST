from __future__ import annotations

import ast
import math
import pickle
from pathlib import Path
from typing import Iterable

import pandas as pd
from lark import Token, Tree

import pipeline_config as cfg
from pipeline_common import append_stage_error, format_counts, print_model_lines, print_sample_status, reset_stage_error_log


def _tokens_under(node: Tree) -> list[Token]:
    return [value for value in node.scan_values(lambda candidate: isinstance(candidate, Token))]


def _iter_statement_nodes(ast_tree: Tree) -> Iterable[tuple[str, list[str]]]:
    for subtree in ast_tree.iter_subtrees():
        if isinstance(subtree, Tree) and str(subtree.data).endswith("_statement"):
            tokens = _tokens_under(subtree)
            parts = [token.value for token in tokens if token.value is not None]
            if parts:
                yield str(subtree.data), parts


def _cmd_map_from_ast(ast_tree: Tree) -> dict[str, list[list[str]]]:
    cmd_map: dict[str, list[list[str]]] = {}
    for _, parts in _iter_statement_nodes(ast_tree):
        command = parts[0].lower()
        cmd_map.setdefault(command, []).append(parts)
    return cmd_map


def accuracy_from_ast_row_prompt1(
    row: pd.Series,
    expected_lattice: float = 4.05,
    lattice_tol: float = 0.1,
    expected_timestep: float = 0.001,
    timestep_tol: float = 1e-6,
    expected_run: int = 500000,
    run_tol: int = 0,
    expected_total_time: float | None = None,
    total_time_tol: float = 1e-4,
    expected_pair_style: str = "eam/alloy",
) -> object:
    issues: list[str] = []

    if row.get("run") != True and row.get("pair_run") == True:
        issues.append("PSZ")
    if row.get("run") != True and row.get("pair_run") != True and row.get("run") != "not parsed":
        error_list = ast.literal_eval(row.get("run"))
        if error_list[0].startswith("ERROR: Thermo_style command before"):
            issues.append("bad thermo order")
        elif error_list[0].startswith("ERROR on proc 0: Neighbor list overflow"):
            issues.append("lost atoms")
        elif error_list[0].startswith("ERROR: Incorrect args for pair coefficients"):
            pass
        else:
            issues.append("unknown error")

    ast_path = row.get("ast_path")
    if pd.isna(ast_path) or not ast_path or not Path(str(ast_path)).exists():
        return "no AST generated"

    expected_fix = {
        "temp_start": 300.0,
        "temp_end": 300.0,
        "temp_damp": 0.1,
        "pressure_start": 1.0,
        "pressure_end": 1.0,
        "pressure_damp": 1.0,
    }
    fix_tolerances = {
        "temp_start": 1e-4,
        "temp_end": 1e-4,
        "temp_damp": 1e-4,
        "pressure_start": 0.2,
        "pressure_end": 0.2,
        "pressure_damp": 1e-4,
    }
    if expected_total_time is None:
        expected_total_time = expected_timestep * expected_run

    with Path(str(ast_path)).open("rb") as handle:
        lammps_ast = pickle.load(handle)
    cmd_map = _cmd_map_from_ast(lammps_ast)

    timestep_val = expected_timestep
    if "timestep" in cmd_map:
        try:
            timestep_val = float(cmd_map["timestep"][0][1])
            if abs(timestep_val - expected_timestep) > timestep_tol:
                issues.append("timestep inaccurate")
        except Exception:
            issues.append("timestep parsing error")

    run_val = None
    if "run" in cmd_map:
        try:
            run_val = int(cmd_map["run"][0][1])
            if abs(run_val - expected_run) > run_tol:
                issues.append("run inaccurate")
        except Exception:
            issues.append("run parsing error")
    else:
        issues.append("run missing")

    if "pair_style" in cmd_map:
        pair_style = cmd_map["pair_style"][0]
        if len(pair_style) < 2 or pair_style[1] != expected_pair_style:
            issues.append("pair_style inaccurate")
    else:
        issues.append("pair_style missing")

    if "lattice" in cmd_map:
        lattice = cmd_map["lattice"][0]
        if len(lattice) < 3 or lattice[1].lower() != "fcc":
            issues.append("lattice type inaccurate")
        try:
            lattice_value = float(lattice[2])
            if abs(lattice_value - expected_lattice) > lattice_tol:
                issues.append("lattice_param inaccurate")
        except Exception:
            issues.append("lattice_param parsing error")
    else:
        issues.append("lattice missing")

    npt_line = None
    for parts in cmd_map.get("fix", []):
        lowered = [part.lower() for part in parts]
        if "npt" in lowered and "temp" in lowered:
            npt_line = parts
            break

    if npt_line is None:
        issues.append("fix missing")
    else:
        try:
            lowered = [part.lower() for part in npt_line]
            i_temp = lowered.index("temp")
            i_iso = lowered.index("iso")
            parsed_fix = {
                "temp_start": float(npt_line[i_temp + 1]),
                "temp_end": float(npt_line[i_temp + 2]),
                "temp_damp": float(npt_line[i_temp + 3]),
                "pressure_start": float(npt_line[i_iso + 1]),
                "pressure_end": float(npt_line[i_iso + 2]),
                "pressure_damp": float(npt_line[i_iso + 3]),
            }
            for key in expected_fix:
                if abs(parsed_fix[key] - expected_fix[key]) > fix_tolerances[key]:
                    issues.append(key)
        except Exception:
            issues.append("fix_parse")

    region_dims = None
    replicate_vals = None
    if "region" in cmd_map:
        for region in cmd_map["region"]:
            try:
                if len(region) >= 9 and region[2].lower() == "block":
                    region_dims = (float(region[4]), float(region[6]), float(region[8]))
                    break
            except Exception:
                issues.append("size_parse")

    if "replicate" in cmd_map:
        replicate = cmd_map["replicate"][0]
        try:
            if len(replicate) >= 4:
                replicate_vals = (int(replicate[1]), int(replicate[2]), int(replicate[3]))
        except Exception:
            issues.append("replicate_parse")

    if region_dims is not None:
        if region_dims == (1.0, 1.0, 1.0):
            if replicate_vals != (5, 5, 5):
                issues.append("size")
        elif region_dims == (5.0, 5.0, 5.0):
            if replicate_vals not in [None, (1, 1, 1)]:
                issues.append("size")
        else:
            issues.append("size")
    else:
        issues.append("size_missing")

    if timestep_val is not None and run_val is not None:
        total_time = timestep_val * run_val
        if abs(total_time - expected_total_time) > total_time_tol:
            issues.append("total_time")
    else:
        issues.append("total_time_incomplete")

    return True if not issues else ", ".join(sorted(set(issues)))


def accuracy_from_ast_row_prompt2(
    row: pd.Series,
    expected_lattice: float = 3.52,
    lattice_tol: float = 0.1,
    expected_timestep: float = 0.001,
    timestep_tol: float = 1e-6,
    expected_run: int = 220000,
    run_tol: int = 0,
    expected_total_time: float | None = None,
    total_time_tol: float = 1e-4,
    expected_pair_style: str = "eam/alloy",
    expected_velocity_temp: float = 600.0,
    velocity_tol: float = 1e-6,
    rate_k_per_ps: float = 10.0,
    rate_tol: float = 0.25,
) -> object:
    issues: list[str] = []

    if row.get("run") != True and row.get("pair_run") == True:
        issues.append("PSZ")
    if row.get("run") != True and row.get("pair_run") != True and row.get("run") != "not parsed":
        error_list = ast.literal_eval(row.get("run"))
        if error_list[0].startswith("ERROR: Thermo_style command before"):
            issues.append("bad thermo order")
        elif error_list[0].startswith("ERROR on proc 0: Neighbor list overflow"):
            issues.append("lost atoms")
        elif error_list[0].startswith("ERROR: Incorrect args for pair coefficients"):
            pass
        elif error_list[0].startswith("ERROR on proc 0: Not a valid integer number:"):
            pass
        else:
            issues.append("unknown error")

    ast_path = row.get("ast_path")
    if pd.isna(ast_path) or not ast_path or not Path(str(ast_path)).exists():
        return "no AST generated"

    expected_fix = {
        "temp_start": 300.0,
        "temp_end": 2500.0,
        "temp_damp": 0.1,
        "pressure_start": 1.0,
        "pressure_end": 1.0,
        "pressure_damp": 1.0,
    }
    fix_tolerances = {
        "temp_start": 1e-4,
        "temp_end": 1e-4,
        "temp_damp": 1,
        "pressure_start": 0.2,
        "pressure_end": 0.2,
        "pressure_damp": 10,
    }
    if expected_total_time is None:
        expected_total_time = expected_timestep * expected_run

    with Path(str(ast_path)).open("rb") as handle:
        lammps_ast = pickle.load(handle)
    cmd_map = _cmd_map_from_ast(lammps_ast)

    if "units" in cmd_map and cmd_map["units"][0][1] != "metal":
        issues.append("units")

    timestep_val = expected_timestep
    if "timestep" in cmd_map:
        try:
            timestep_val = float(cmd_map["timestep"][0][1])
            if abs(timestep_val - expected_timestep) > timestep_tol:
                issues.append("timestep inaccurate")
        except Exception:
            issues.append("timestep parsing error")

    run_val = None
    if "run" in cmd_map:
        try:
            run_val = int(cmd_map["run"][0][1])
            if abs(run_val - expected_run) > run_tol:
                issues.append("run num inaccurate")
        except Exception:
            issues.append("run parsing error")
    else:
        issues.append("run missing")

    if "pair_style" in cmd_map:
        pair_style = cmd_map["pair_style"][0]
        if len(pair_style) < 2 or pair_style[1] != expected_pair_style:
            issues.append("pair_style inaccurate")
    else:
        issues.append("pair_style missing")

    if "lattice" in cmd_map:
        lattice = cmd_map["lattice"][0]
        if len(lattice) < 3 or lattice[1].lower() != "fcc":
            issues.append("lattice type inaccurate")
        try:
            lattice_value = float(lattice[2])
            if abs(lattice_value - expected_lattice) > lattice_tol:
                issues.append("lattice_param inaccurate")
        except Exception:
            issues.append("lattice_param parsing error")
    else:
        issues.append("lattice missing")

    npt_line = None
    for parts in cmd_map.get("fix", []):
        lowered = [part.lower() for part in parts]
        if "npt" in lowered and "temp" in lowered:
            npt_line = parts
            break

    parsed_fix = None
    if npt_line is None:
        issues.append("fix missing")
    else:
        try:
            lowered = [part.lower() for part in npt_line]
            i_temp = lowered.index("temp")
            i_iso = lowered.index("iso")
            parsed_fix = {
                "temp_start": float(npt_line[i_temp + 1]),
                "temp_end": float(npt_line[i_temp + 2]),
                "temp_damp": float(npt_line[i_temp + 3]),
                "pressure_start": float(npt_line[i_iso + 1]),
                "pressure_end": float(npt_line[i_iso + 2]),
                "pressure_damp": float(npt_line[i_iso + 3]),
            }
            for key in expected_fix:
                if abs(parsed_fix[key] - expected_fix[key]) > fix_tolerances[key]:
                    issues.append(key)
        except Exception:
            issues.append("fix_parse")

    vel_line = None
    for parts in cmd_map.get("velocity", []):
        lowered = [part.lower() for part in parts]
        if len(lowered) >= 5 and lowered[1] == "all" and lowered[2] == "create":
            vel_line = parts
            break

    if vel_line is None:
        issues.append("velocity missing")
    else:
        try:
            velocity_temperature = float(vel_line[3])
            if abs(velocity_temperature - expected_velocity_temp) > velocity_tol:
                issues.append("velocity_temp inaccurate")
        except Exception:
            issues.append("velocity parsing error")

    region_dims = None
    replicate_vals = None
    if "region" in cmd_map:
        for region in cmd_map["region"]:
            try:
                if len(region) >= 9 and region[2].lower() == "block":
                    region_dims = (float(region[4]), float(region[6]), float(region[8]))
                    break
            except Exception:
                issues.append("size_parse")

    if "replicate" in cmd_map:
        replicate = cmd_map["replicate"][0]
        try:
            if len(replicate) >= 4:
                replicate_vals = (int(replicate[1]), int(replicate[2]), int(replicate[3]))
        except Exception:
            issues.append("replicate_parse")

    if region_dims is not None:
        if region_dims == (1.0, 1.0, 1.0):
            if replicate_vals != (10, 10, 10):
                issues.append("size")
        elif region_dims == (10.0, 10.0, 10.0):
            if replicate_vals not in [None, (1, 1, 1)]:
                issues.append("size")
        else:
            issues.append("size")
    else:
        issues.append("size_missing")

    if timestep_val is not None and run_val is not None:
        total_time = timestep_val * run_val
        if abs(total_time - expected_total_time) > total_time_tol:
            issues.append("sim time inaccurate")
        if parsed_fix:
            delta_t = parsed_fix["temp_end"] - parsed_fix["temp_start"]
            rate = delta_t / total_time if total_time > 0 else float("inf")
            if not math.isclose(rate, rate_k_per_ps, rel_tol=0, abs_tol=rate_tol):
                issues.append("heating_rate")
    else:
        issues.append("total_time_incomplete")

    return True if not issues else ", ".join(sorted(set(issues)))


def accuracy_from_ast_row_prompt3(
    row: pd.Series,
    expected_lattice: float = 3.3,
    lattice_tol: float = 0.1,
    expected_timestep: float = 0.001,
    timestep_tol: float = 1e-6,
    expected_run1: int = 100000,
    run_tol1: int = 0,
    expected_total_time1: float = 100,
    total_time_tol1: float = 1e-4,
    expected_pair_style: str = "eam/alloy",
    expected_velocity_temp: float = 300,
    velocity_tol: float = 1e-6,
    velocity_add_magnitude: float = 2,
) -> object:
    km_s_to_a_ps = 10.0
    expected_rel_speed_a_ps = velocity_add_magnitude * km_s_to_a_ps
    issues: list[str] = []

    if row.get("run") != True and row.get("pair_run") == True:
        issues.append("PSZ")
    if row.get("run") != True and row.get("pair_run") != True and row.get("run") != "not parsed":
        error_list = ast.literal_eval(row.get("run"))
        if error_list[0].startswith("ERROR: Thermo_style command before"):
            issues.append("bad thermo order")
        elif error_list[0].startswith("ERROR on proc 0: Neighbor list overflow"):
            issues.append("lost atoms")
        elif error_list[0].startswith("ERROR: Incorrect args for pair coefficients"):
            pass
        elif error_list[0].startswith("ERROR on proc 0: Not a valid integer number:"):
            pass
        else:
            issues.append("unknown error")

    ast_path = row.get("ast_path")
    if pd.isna(ast_path) or not ast_path or not Path(str(ast_path)).exists():
        return "no AST generated"

    with Path(str(ast_path)).open("rb") as handle:
        lammps_ast = pickle.load(handle)
    cmd_map = _cmd_map_from_ast(lammps_ast)

    if "units" in cmd_map and cmd_map["units"][0][1] != "metal":
        issues.append("units")

    timestep_val = expected_timestep
    if "timestep" in cmd_map:
        try:
            timestep_val = float(cmd_map["timestep"][0][1])
            if abs(timestep_val - expected_timestep) > timestep_tol:
                issues.append("timestep inaccurate")
        except Exception:
            issues.append("timestep parsing error")

    run_val = None
    if "run" in cmd_map:
        try:
            run_val = int(cmd_map["run"][0][1])
            if abs(run_val - expected_run1) > run_tol1:
                issues.append("run num inaccurate")
        except Exception:
            issues.append("run parsing error")
        if len(cmd_map["run"]) != 2:
            issues.append("not 2 runs")
    else:
        issues.append("run missing")

    if "pair_style" in cmd_map:
        pair_style = cmd_map["pair_style"][0]
        if len(pair_style) < 2 or pair_style[1] != expected_pair_style:
            issues.append("pair_style inaccurate")
    else:
        issues.append("pair_style missing")

    if "lattice" in cmd_map:
        lattice = cmd_map["lattice"][0]
        if len(lattice) < 3 or lattice[1].lower() != "bcc":
            issues.append("lattice type inaccurate")
        try:
            lattice_value = float(lattice[2])
            if abs(lattice_value - expected_lattice) > lattice_tol:
                issues.append("lattice_param inaccurate")
        except Exception:
            issues.append("lattice_param parsing error")
    else:
        issues.append("lattice missing")

    expected_fix = {
        "temp_start": 300.0,
        "temp_end": 300.0,
        "temp_damp": 0.1,
    }
    fix_tolerances = {
        "temp_start": 1e-4,
        "temp_end": 1e-4,
        "temp_damp": 1,
    }

    nvt_line = None
    nve_line = None
    for parts in cmd_map.get("fix", []):
        lowered = [part.lower() for part in parts]
        if "nvt" in lowered:
            nvt_line = parts
        elif "nve" in lowered:
            nve_line = parts

    if nvt_line is None:
        issues.append("nvt fix missing")
    else:
        try:
            lowered = [part.lower() for part in nvt_line]
            i_temp = lowered.index("temp")
            parsed_fix = {
                "temp_start": float(nvt_line[i_temp + 1]),
                "temp_end": float(nvt_line[i_temp + 2]),
                "temp_damp": float(nvt_line[i_temp + 3]),
            }
            for key in expected_fix:
                if abs(parsed_fix[key] - expected_fix[key]) > fix_tolerances[key]:
                    issues.append(key)
        except Exception:
            issues.append("fix_parse")

    if nve_line is None:
        issues.append("nve fix missing")

    vel_init_line = None
    vel_add_line = None
    vel_any_line = None
    for parts in cmd_map.get("velocity", []):
        lowered = [part.lower() for part in parts]
        if len(lowered) >= 5 and lowered[1] == "all" and lowered[2] == "create":
            vel_init_line = parts
        elif len(lowered) >= 5 and lowered[2] == "set":
            vel_add_line = parts
        else:
            vel_any_line = parts
            issues.append("extra_vel")
        if "add" in lowered:
            issues.append("vel_add")

    if vel_init_line is None and vel_add_line is None and vel_any_line is None:
        issues.append("velocity missing")
    if vel_init_line is not None:
        try:
            velocity_temperature = float(vel_init_line[3])
            if abs(velocity_temperature - expected_velocity_temp) > velocity_tol:
                issues.append("velocity_temp inaccurate")
        except Exception:
            issues.append("velocity parsing error")
    if vel_add_line is not None:
        if abs(float(vel_add_line[5])) != expected_rel_speed_a_ps:
            issues.append("v_set_speed")
        if float(vel_add_line[5]) > 0:
            issues.append("v_set_direction")

    size_tol_lat = 1e-6
    lat_angstrom = expected_lattice
    if "lattice" in cmd_map and len(cmd_map["lattice"]) >= 1:
        try:
            lat_angstrom = float(cmd_map["lattice"][0][2])
        except Exception:
            issues.append("size_lattice_parse")

    projectile_cells = 20.0
    target_cells = 40.0
    gap_angstrom = 15.0

    if lat_angstrom == 0.0:
        issues.append("size_lattice_zero")
        gap_cells = None
    else:
        gap_cells = gap_angstrom / lat_angstrom

    box_bounds = None
    target_bounds = None
    projectile_bounds = None
    block_regions: dict[str, tuple[float, float, float, float, float, float]] = {}
    if "region" in cmd_map:
        for region in cmd_map["region"]:
            try:
                if len(region) >= 9 and region[2].lower() == "block":
                    name = region[1].lower()
                    bounds = (
                        float(region[3]),
                        float(region[4]),
                        float(region[5]),
                        float(region[6]),
                        float(region[7]),
                        float(region[8]),
                    )
                    block_regions[name] = bounds
                    if name == "box":
                        box_bounds = bounds
                    elif name == "target":
                        target_bounds = bounds
                    elif name == "projectile":
                        projectile_bounds = bounds
            except Exception:
                issues.append("size_parse")

    if box_bounds is None and "create_box" in cmd_map and len(cmd_map["create_box"]) >= 1:
        try:
            create_box_cmd = cmd_map["create_box"][0]
            if len(create_box_cmd) >= 3:
                create_box_region = create_box_cmd[2].lower()
                box_bounds = block_regions.get(create_box_region)
        except Exception:
            issues.append("box_region_parse")

    if box_bounds is None:
        issues.append("box_region_missing")
    if target_bounds is None:
        issues.append("target_region_missing")
    if projectile_bounds is None:
        issues.append("projectile_region_missing")

    if gap_cells is not None:
        total_z_cells = target_cells + gap_cells + projectile_cells
        expected_box = (0.0, 20.0, 0.0, 20.0, 0.0, total_z_cells)
        expected_target = (0.0, 20.0, 0.0, 20.0, 0.0, target_cells)
        expected_projectile = (0.0, 20.0, 0.0, 20.0, target_cells + gap_cells, total_z_cells)

        if box_bounds is not None:
            for got, expected in zip(box_bounds, expected_box):
                if abs(got - expected) > size_tol_lat:
                    issues.append("box_region_size")
                    break
        if target_bounds is not None:
            for got, expected in zip(target_bounds, expected_target):
                if abs(got - expected) > size_tol_lat:
                    issues.append("target_region_size")
                    break
        if projectile_bounds is not None:
            for got, expected in zip(projectile_bounds, expected_projectile):
                if abs(got - expected) > size_tol_lat:
                    issues.append("projectile_region_size")
                    break
        if target_bounds is not None and projectile_bounds is not None:
            gap_got = projectile_bounds[4] - target_bounds[5]
            if abs(gap_got - gap_cells) > size_tol_lat:
                issues.append("gap_size")
    else:
        issues.append("size_incomplete")

    if "replicate" in cmd_map:
        issues.append("replicate_unexpected")

    if "boundary" in cmd_map:
        bound_cond = cmd_map["boundary"][0][1:4]
        if bound_cond == ["p", "p", "s"]:
            pass
        elif bound_cond == ["p", "p", "f"]:
            issues.append("fixed bounds")
        else:
            issues.append("other bounds")

    if timestep_val is not None and run_val is not None:
        total_time = timestep_val * run_val
        if abs(total_time - expected_total_time1) > total_time_tol1:
            issues.append("sim time1 inaccurate")
    else:
        issues.append("total_time_incomplete")

    return True if not issues else ", ".join(sorted(set(issues)))


def run_accuracy_stage() -> pd.DataFrame:
    reset_stage_error_log("accuracy")
    pair_df = pd.read_pickle(cfg.FINAL_PAIR_DF_PATH)
    prompt1_df = pair_df[pair_df["prompt"] == "prompt1"].copy()
    prompt1_df["accurate"] = prompt1_df.apply(accuracy_from_ast_row_prompt1, axis=1)

    prompt2_df = pair_df[pair_df["prompt"] == "prompt2"].copy()
    prompt2_df["accurate"] = prompt2_df.apply(accuracy_from_ast_row_prompt2, axis=1)

    prompt3_df = pair_df[pair_df["prompt"] == "prompt3"].copy()
    prompt3_df["accurate"] = prompt3_df.apply(accuracy_from_ast_row_prompt3, axis=1)

    accuracy_df = pd.concat([prompt1_df, prompt2_df, prompt3_df], axis=0, ignore_index=True)
    for _, row in accuracy_df.iterrows():
        if row["accurate"] == True:
            print_sample_status("Accuracy", row["prompt"], row["model"], int(row["trial"]), "OK")
        else:
            append_stage_error("accuracy", row["prompt"], row["model"], int(row["trial"]), row["accurate"])
            print_sample_status("Accuracy", row["prompt"], row["model"], int(row["trial"]), "FAIL", row["accurate"])
    accuracy_df.to_pickle(cfg.ACCURACY_DF_PATH)
    return accuracy_df


def compute_accuracy_metrics(accuracy_df: pd.DataFrame) -> dict[str, int]:
    def vc_get(series: pd.Series, key: object) -> int:
        return int(series.value_counts(dropna=False).get(key, 0))

    total_scripts = int(len(accuracy_df))
    sanitizer_to_parser = vc_get(accuracy_df["sanitized"], True)
    sanitizer_to_failure = total_scripts - sanitizer_to_parser

    parser_to_execution = vc_get(accuracy_df["parsed"], True)
    parser_to_failure = total_scripts - parser_to_execution - int((accuracy_df["sanitized"] != True).sum())

    execution_to_accuracy = vc_get(accuracy_df["run"], True)

    if "pair_run" in accuracy_df.columns:
        # Mirror the execution notebook semantics:
        # every parsed execution failure enters the pair-style-zero stage and is
        # recorded in pair_run as True / False / retry-error-string, while rows
        # that never enter that stage remain "n/a".
        pair_run = accuracy_df["pair_run"]
        execution_to_pairstylecheck = int((pair_run != "n/a").sum())
        execution_to_accuracy_after_pairstyle = vc_get(pair_run, True)
        pair_df = accuracy_df[pair_run == True].copy()
    else:
        execution_to_pairstylecheck = 0
        execution_to_accuracy_after_pairstyle = 0
        pair_df = accuracy_df.iloc[0:0].copy()

    execution_to_failure = (
        total_scripts
        - execution_to_accuracy
        - execution_to_pairstylecheck
        - parser_to_failure
    )

    if "accurate" in accuracy_df.columns:
        accuracy_to_correct = vc_get(accuracy_df.loc[accuracy_df["run"] == True, "accurate"], True)
    else:
        accuracy_to_correct = 0
    accuracy_to_failure = execution_to_accuracy - accuracy_to_correct

    allowed = {"PSZ", "pair_style inaccurate"}
    if not pair_df.empty and "accurate" in pair_df.columns:
        col = pair_df["accurate"].astype(str)
        mask_has_disallowed = col.apply(
            lambda entry: any(
                token not in allowed
                for token in map(str.strip, entry.split(","))
                if token.strip()
            )
        )
        pair_to_accuracy_total = int(len(pair_df))
        pair_accuracy_to_failure = int(mask_has_disallowed.sum())
        pair_accuracy_to_correct = pair_to_accuracy_total - pair_accuracy_to_failure
    else:
        pair_accuracy_to_failure = 0
        pair_accuracy_to_correct = 0

    return {
        "total_scripts": total_scripts,
        "sanitizer_to_parser": int(sanitizer_to_parser),
        "sanitizer_to_failure": int(sanitizer_to_failure),
        "parser_to_execution": int(parser_to_execution),
        "parser_to_failure": int(parser_to_failure),
        "execution_to_accuracy": int(execution_to_accuracy),
        "execution_to_pairstylecheck": int(execution_to_pairstylecheck),
        "execution_to_accuracy_after_pairstyle": int(execution_to_accuracy_after_pairstyle),
        "execution_to_failure": int(execution_to_failure),
        "accuracy_to_correct": int(accuracy_to_correct),
        "accuracy_to_failure": int(accuracy_to_failure),
        "pair_accuracy_to_correct": int(pair_accuracy_to_correct),
        "pair_accuracy_to_failure": int(pair_accuracy_to_failure),
    }


def get_accuracy_df(prompt_name: str, model_name: str, master_df: pd.DataFrame) -> pd.DataFrame:
    mask = (master_df["prompt"] == prompt_name) & (master_df["model"] == model_name)
    return master_df.loc[mask, ["sanitized", "parsed", "run", "pair_run", "accurate"]].copy()


def cli_accuracy() -> None:
    df = run_accuracy_stage()
    print(f"Saved accuracy results with {len(df)} rows to {cfg.ACCURACY_DF_PATH}.")
    print(
        format_counts(
            "Accuracy summary",
            [
                ("accurate_true", int((df["accurate"] == True).sum())),
                ("accurate_nontrue", int((df["accurate"] != True).sum())),
                ("no_ast_generated", int((df["accurate"] == "no AST generated").sum())),
            ],
        )
    )
    print_model_lines(
        df,
        "Accuracy",
        lambda model_df: [
            ("accurate_ok", int((model_df["accurate"] == True).sum())),
            ("accurate_fail", int((model_df["accurate"] != True).sum())),
            ("no_ast", int((model_df["accurate"] == "no AST generated").sum())),
        ],
    )
