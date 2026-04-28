from __future__ import annotations

from pathlib import Path

import pandas as pd

import pipeline_config as cfg


def ensure_directories() -> None:
    for path in [
        cfg.DATA_DIR,
        cfg.RESULTS_DIR,
        cfg.GENERATED_SCRIPTS_DIR,
        cfg.PIPELINE_GENERATED_FILES_DIR,
        cfg.RAW_RESPONSES_DIR,
        cfg.SANITIZED_SCRIPTS_DIR,
        cfg.ASTS_DIR,
        cfg.SHORT_RUN_SCRIPTS_DIR,
        cfg.LOGS_DIR,
        cfg.PAIR_CHANGE_DIR,
        cfg.PAIR_CHANGE_LOGS_DIR,
        cfg.ERRORS_DIR,
        cfg.LAMMPS_GENERATED_FILES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _stage_error_log_path(stage: str) -> Path:
    return cfg.ERRORS_DIR / f"{stage}_errors.txt"


def reset_stage_error_log(stage: str) -> Path:
    path = _stage_error_log_path(stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{stage} errors\n", encoding="utf-8")
    return path


def append_stage_error(stage: str, prompt_name: str, model_name: str, trial: int, message: object) -> None:
    path = _stage_error_log_path(stage)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prompt_name}\t{model_name}\tT{trial}\t{message}\n")


def print_sample_status(
    stage: str,
    prompt_name: str,
    model_name: str,
    trial: int,
    status: str,
    detail: object | None = None,
) -> None:
    line = f"{stage} {status} {prompt_name}/{model_name}/T{trial}"
    if detail not in (None, "", True):
        line += f" :: {detail}"
    print(line)


def build_trial_dataframe() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for prompt_name, models in cfg.PROMPT_MODEL_MAP.items():
        for model_name in models:
            for trial in range(cfg.TRIALS):
                rows.append({"prompt": prompt_name, "model": model_name, "trial": trial})
    return pd.DataFrame(rows)


def format_counts(title: str, counts: list[tuple[str, object]]) -> str:
    parts = [f"{label}={value}" for label, value in counts]
    return f"{title}: " + ", ".join(parts)


def print_model_lines(df: pd.DataFrame, stage: str, metric_builder) -> None:
    for model_name, model_df in df.groupby("model", sort=True):
        model_label = cfg.MODEL_DISPLAY.get(model_name, model_name)
        counts = metric_builder(model_df)
        print(format_counts(f"{stage} [{model_label}]", counts))
