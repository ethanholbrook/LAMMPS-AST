from __future__ import annotations
import ast
import shlex
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import pandas as pd

import pipeline_config as cfg
from pipeline_common import append_stage_error, ensure_directories, format_counts, print_model_lines, print_sample_status, reset_stage_error_log


LAMMPS_OUTPUT_GLOB_PATTERNS = (
    "*.lammpstrj",
    "*.dump",
    "*.data",
    "log.*",
    "*.restart",
    "*.restart.*",
)


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
    screen_file = log_file.with_suffix(".screen")
    child_cmd = (
        f"{shlex.quote(lmp_exec)} -nonbuf -echo both "
        f"-in {shlex.quote(str(input_file))} -log {shlex.quote(str(log_file))}"
    )
    shell_cmd = (
        "module load lammps/20240829 >/dev/null 2>&1 && "
        f"script -q -e -f -c {shlex.quote(child_cmd)} {shlex.quote(str(screen_file))}"
    )
    result = subprocess.run(
        ["bash", "-lc", shell_cmd],
        capture_output=True,
        text=True,
        cwd=str(cfg.PIPELINE_DIR),
    )
    if result.returncode != 0:
        err_msg = extract_lammps_error_lines(
            log_file=log_file,
            screen_file=screen_file,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        raise RuntimeError(err_msg)


def sweep_lammps_generated_files() -> list[tuple[Path, Path]]:
    moved_files: list[tuple[Path, Path]] = []
    seen_sources: set[Path] = set()

    for pattern in LAMMPS_OUTPUT_GLOB_PATTERNS:
        for source_path in cfg.PIPELINE_DIR.rglob(pattern):
            if not source_path.is_file():
                continue
            if source_path in seen_sources:
                continue

            seen_sources.add(source_path)
            relative_path = source_path.relative_to(cfg.PIPELINE_DIR)
            destination_path = cfg.LAMMPS_GENERATED_FILES_DIR / relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)

            if destination_path.exists():
                destination_path.unlink()

            shutil.move(str(source_path), str(destination_path))
            moved_files.append((source_path, destination_path))

    return sorted(moved_files, key=lambda pair: str(pair[0]))


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


def _filter_terminal_wrapper_lines(lines: Iterable[str]) -> list[str]:
    filtered: list[str] = []
    skip_phrases = (
        "script started on",
        "script done on",
        "mpi_abort was invoked on rank",
        "note: invoking mpi_abort causes open mpi to kill all mpi processes.",
        "you may or may not see output from other processes",
        "mpirun detected that one or more processes exited",
        "primary job terminated normally, but",
        "an error occurred in mpi_init",
        "local abort before mpi_init completed",
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if stripped.startswith("-") and len(stripped) >= 10:
            continue
        if any(phrase in lowered for phrase in skip_phrases):
            continue
        filtered.append(stripped)
    return filtered


def _extract_structured_lammps_error(lines: list[str]) -> list[str]:
    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if line.startswith("ERROR"):
            selected = [line]
            if idx + 1 < len(lines) and lines[idx + 1].startswith("Last command:"):
                selected.append(lines[idx + 1])
            return selected

    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if line.startswith("Last command:"):
            start = max(0, idx - 1)
            return lines[start : idx + 1]

    return []


def _prepare_candidate_lines(lines: Iterable[str]) -> list[str]:
    return _filter_terminal_wrapper_lines(_filter_mpi_warning_lines(lines))


def _extract_last_command_from_run_value(run_value: object) -> str:
    if isinstance(run_value, list):
        error_lines = run_value
    elif isinstance(run_value, str):
        try:
            parsed_value = ast.literal_eval(run_value)
        except (SyntaxError, ValueError):
            parsed_value = run_value
        error_lines = parsed_value if isinstance(parsed_value, list) else [str(parsed_value)]
    else:
        error_lines = [str(run_value)]

    for line in error_lines:
        if isinstance(line, str) and line.startswith("Last command:"):
            return line
    return ""


def extract_lammps_error_lines(log_file: Path, screen_file: Path, stdout: str, stderr: str) -> list[str]:
    if screen_file.exists():
        screen_lines = _prepare_candidate_lines(screen_file.read_text(encoding="utf-8", errors="replace").splitlines())
        selected = _extract_structured_lammps_error(screen_lines)
        if selected:
            return selected
        if screen_lines:
            return screen_lines[-2:]

    stderr_lines = _prepare_candidate_lines(stderr.splitlines())
    selected = _extract_structured_lammps_error(stderr_lines)
    if selected:
        return selected

    stdout_lines = _prepare_candidate_lines(stdout.splitlines())
    selected = _extract_structured_lammps_error(stdout_lines)
    if selected:
        return selected

    if log_file.exists():
        log_lines = _prepare_candidate_lines(log_file.read_text(encoding="utf-8", errors="replace").splitlines())
        selected = _extract_structured_lammps_error(log_lines)
        if selected:
            return selected
        if log_lines:
            return log_lines[-2:]

    if stderr_lines:
        return stderr_lines[-2:]

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
                    last_command_line = _extract_last_command_from_run_value(run_value)
                    if last_command_line.startswith("Last command: pair"):
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
    moved_files = sweep_lammps_generated_files()
    pair_df.to_pickle(cfg.FINAL_PAIR_DF_PATH)
    if moved_files:
        print(
            f"Swept {len(moved_files)} LAMMPS-generated files to {cfg.LAMMPS_GENERATED_FILES_DIR}."
        )
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
