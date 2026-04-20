from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Iterable

import pandas as pd

import pipeline_config as cfg
from pipeline_common import append_stage_error, ensure_directories, format_counts, print_model_lines, print_sample_status, reset_stage_error_log


def discover_lammps_executable() -> str:
    if cfg.DEFAULT_LAMMPS_EXECUTABLE and Path(cfg.DEFAULT_LAMMPS_EXECUTABLE).exists():
        return cfg.DEFAULT_LAMMPS_EXECUTABLE

    result = subprocess.run(
        ["bash", "-lc", "module load lammps/20240829 >/dev/null 2>&1 && which lmp"],
        capture_output=True,
        text=True,
        check=False,
    )
    executable = result.stdout.strip()
    if executable and Path(executable).exists():
        return executable
    raise FileNotFoundError("Could not resolve a working LAMMPS executable.")


def modify_run_lines(file_path: Path, output_path: Path, prompt_name: str) -> None:
    lines = file_path.read_text(encoding="utf-8").splitlines(True)
    modified_lines: list[str] = []

    for line in lines:
        stripped_line = line.strip()
        if re.match(r"^run\b", stripped_line):
            words = line.split()
            if len(words) > 1:
                words[1] = "10"
                line = " ".join(words) + "\n"

        if stripped_line.startswith("pair_coeff"):
            words = line.split()
            if len(words) > 3:
                words[3] = str(cfg.POTENTIALS_DIR / f"{prompt_name}.potential")
                line = " ".join(words) + "\n"

        modified_lines.append(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(modified_lines), encoding="utf-8")


def modify_for_short_runs() -> None:
    for prompt_name, models in cfg.PROMPT_MODEL_MAP.items():
        for model_name in models:
            for trial in range(cfg.TRIALS):
                script_name = f"{prompt_name}-{model_name}-T{trial}.in"
                input_path = cfg.GENERATED_SCRIPTS_DIR / prompt_name / model_name / script_name
                output_path = cfg.SHORT_RUN_SCRIPTS_DIR / prompt_name / model_name / script_name
                modify_run_lines(input_path, output_path, prompt_name)


def run_lammps(lmp_exec: str, input_file: Path, log_file: Path) -> None:
    shell_cmd = (
        "module load lammps/20240829 >/dev/null 2>&1 && "
        f"{lmp_exec} -in {str(input_file)!r} -log {str(log_file)!r}"
    )
    result = subprocess.run(
        ["bash", "-lc", shell_cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err_msg = extract_lammps_error_lines(log_file=log_file, stdout=result.stdout, stderr=result.stderr)
        raise RuntimeError(err_msg)


def _filter_mpi_warning_lines(lines: Iterable[str]) -> list[str]:
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "mca_base_component_repository_open" in lowered and "libhcoll.so.1" in lowered:
            continue
        filtered.append(stripped)
    return filtered


def extract_lammps_error_lines(log_file: Path, stdout: str, stderr: str) -> list[str]:
    if log_file.exists():
        log_lines = _filter_mpi_warning_lines(log_file.read_text(encoding="utf-8", errors="replace").splitlines())
        error_idx = next((idx for idx, line in enumerate(log_lines) if line.startswith("ERROR")), None)
        if error_idx is not None:
            selected = [log_lines[error_idx]]
            if error_idx + 1 < len(log_lines) and log_lines[error_idx + 1].startswith("Last command:"):
                selected.append(log_lines[error_idx + 1])
            return selected
        if log_lines:
            return log_lines[-2:]

    stderr_lines = _filter_mpi_warning_lines(stderr.splitlines())
    if stderr_lines:
        return stderr_lines[-2:]

    stdout_lines = _filter_mpi_warning_lines(stdout.splitlines())
    if stdout_lines:
        return stdout_lines[-2:]

    return ["unknown LAMMPS execution failure"]


def do_runs(parsing_df: pd.DataFrame, lmp_exec: str) -> pd.DataFrame:
    df = parsing_df.copy()
    df["run"] = pd.Series("", index=df.index, dtype=object)

    for prompt_name, models in cfg.PROMPT_MODEL_MAP.items():
        for model_name in models:
            out_dir = cfg.LOGS_DIR / prompt_name / model_name
            out_dir.mkdir(parents=True, exist_ok=True)
            for trial in range(cfg.TRIALS):
                mask = (
                    (df["prompt"] == prompt_name)
                    & (df["model"] == model_name)
                    & (df["trial"] == trial)
                )

                if (df.loc[mask, "parsed"] != True).any():
                    df.loc[mask, "run"] = "not parsed"
                    print_sample_status("Execute", prompt_name, model_name, trial, "SKIP", "not parsed")
                    continue

                script_name = f"{prompt_name}-{model_name}-T{trial}.in"
                input_path = cfg.SHORT_RUN_SCRIPTS_DIR / prompt_name / model_name / script_name
                log_path = out_dir / f"lmmp-{prompt_name}-{model_name}-{trial}.log"

                try:
                    run_lammps(lmp_exec=lmp_exec, input_file=input_path, log_file=log_path)
                    status: object = True
                    print_sample_status("Execute", prompt_name, model_name, trial, "OK")
                except Exception as exc:
                    status = str(exc)
                    append_stage_error("execute", prompt_name, model_name, trial, status)
                    print_sample_status("Execute", prompt_name, model_name, trial, "FAIL", status)
                df.loc[mask, "run"] = status

    return df


def modify_pair_style(file_path: Path, output_path: Path) -> None:
    lines = file_path.read_text(encoding="utf-8").splitlines(True)
    modified_lines: list[str] = []

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("pair"):
            if stripped_line.startswith("pair_style"):
                line = "\n"
            else:
                line = "pair_style zero 10.0\npair_coeff * *\nmass 1 27\n"
        modified_lines.append(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(modified_lines), encoding="utf-8")


def pair_style_change(run_df: pd.DataFrame, lmp_exec: str) -> pd.DataFrame:
    df = run_df.copy()
    df["pair_run"] = pd.Series("n/a", index=df.index, dtype=object)

    for prompt_name, models in cfg.PROMPT_MODEL_MAP.items():
        for model_name in models:
            out_dir = cfg.PAIR_CHANGE_DIR / prompt_name / model_name
            log_dir = cfg.PAIR_CHANGE_LOGS_DIR / prompt_name / model_name
            out_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)

            for trial in range(cfg.TRIALS):
                mask = (
                    (df["prompt"] == prompt_name)
                    & (df["model"] == model_name)
                    & (df["trial"] == trial)
                )
                run_value = df.loc[mask, "run"].iloc[0]
                if run_value != True and run_value != "not parsed":
                    error_lines = ast.literal_eval(run_value)
                    if error_lines[1].startswith("Last command: pair"):
                        script_name = f"{prompt_name}-{model_name}-T{trial}.in"
                        input_path = cfg.SHORT_RUN_SCRIPTS_DIR / prompt_name / model_name / script_name
                        out_path = out_dir / script_name
                        log_path = log_dir / f"lmmp-{prompt_name}-{model_name}-{trial}.log"
                        modify_pair_style(input_path, out_path)
                        try:
                            run_lammps(lmp_exec=lmp_exec, input_file=out_path, log_file=log_path)
                            status: object = True
                            print_sample_status("PairRetry", prompt_name, model_name, trial, "OK")
                        except Exception as exc:
                            status = str(exc)
                            append_stage_error("execute", prompt_name, model_name, trial, f"pair_retry={status}")
                            print_sample_status("PairRetry", prompt_name, model_name, trial, "FAIL", status)
                        df.loc[mask, "pair_run"] = status
                    else:
                        df.loc[mask, "pair_run"] = False
                else:
                    df.loc[mask, "pair_run"] = "n/a"

    return df


def run_execution_stage() -> pd.DataFrame:
    reset_stage_error_log("execute")
    parsing_df = pd.read_pickle(cfg.PARSING_DF_PATH)
    modify_for_short_runs()
    lmp_exec = discover_lammps_executable()
    run_df = do_runs(parsing_df, lmp_exec=lmp_exec)
    pair_df = pair_style_change(run_df, lmp_exec=lmp_exec)
    pair_df.to_pickle(cfg.FINAL_PAIR_DF_PATH)
    return pair_df


def cli_execute() -> None:
    df = run_execution_stage()
    print(f"Saved execution results with {len(df)} rows to {cfg.FINAL_PAIR_DF_PATH}.")
    print(
        format_counts(
            "Execution summary",
            [
                ("run_true", int((df["run"] == True).sum())),
                ("run_not_parsed", int((df["run"] == "not parsed").sum())),
                ("run_failures", int(((df["run"] != True) & (df["run"] != "not parsed")).sum())),
                ("pair_run_true", int((df["pair_run"] == True).sum())),
            ],
        )
    )
    print_model_lines(
        df,
        "Execution",
        lambda model_df: [
            ("run_ok", int((model_df["run"] == True).sum())),
            ("not_parsed", int((model_df["run"] == "not parsed").sum())),
            ("run_fail", int(((model_df["run"] != True) & (model_df["run"] != "not parsed")).sum())),
            ("pair_ok", int((model_df["pair_run"] == True).sum())),
        ],
    )
