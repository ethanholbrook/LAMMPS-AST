from __future__ import annotations

import json
import pickle
import sys

import pandas as pd

import pipeline_config as cfg
from pipeline_common import append_stage_error, build_trial_dataframe, ensure_directories, format_counts, print_model_lines, print_sample_status, reset_stage_error_log


if str(cfg.EVAL_ROOT) not in sys.path:
    sys.path.insert(0, str(cfg.EVAL_ROOT))

from lammps_ast import find_unresolved_variables, parse_to_AST, sanitize  # noqa: E402


def parse_and_save_results() -> pd.DataFrame:
    ensure_directories()
    reset_stage_error_log("parse")
    df = build_trial_dataframe().set_index(["prompt", "model", "trial"])
    df["sanitized"] = pd.Series("n/a", index=df.index, dtype=object)
    df["parsed"] = pd.Series("Not Run", index=df.index, dtype=object)
    df["ast_path"] = pd.Series(None, index=df.index, dtype=object)

    for prompt_name, models in cfg.PROMPT_MODEL_MAP.items():
        for model_name in models:
            script_dir = cfg.GENERATED_SCRIPTS_DIR / prompt_name / model_name
            for trial in range(cfg.TRIALS):
                key = (prompt_name, model_name, trial)
                script_path = script_dir / f"{prompt_name}-{model_name}-T{trial}.in"
                if not script_path.exists():
                    append_stage_error("parse", prompt_name, model_name, trial, f"Missing generated script: {script_path}")
                    raise FileNotFoundError(f"Missing generated script: {script_path}")

                source = script_path.read_text(encoding="utf-8")
                sanitized = sanitize(source)

                sanitized_path = cfg.SANITIZED_SCRIPTS_DIR / prompt_name / model_name / script_path.name
                sanitized_path.parent.mkdir(parents=True, exist_ok=True)
                sanitized_path.write_text(sanitized, encoding="utf-8")

                ast_obj, errors = parse_to_AST(sanitized, lint=True, max_errors=10, lammps_version=cfg.LAMMPS_GRAMMAR_VERSION)
                if ast_obj is not None and len(errors) == 0:
                    # Parse success: sanitization succeeded and an AST was produced.
                    parsed_result: object = True
                    sanitized_flag = True
                    ast_path = cfg.ASTS_DIR / prompt_name / model_name / script_path.with_suffix(".ast.pkl").name
                    ast_path.parent.mkdir(parents=True, exist_ok=True)
                    with ast_path.open("wb") as handle:
                        pickle.dump(ast_obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    df.loc[key, "ast_path"] = str(ast_path)
                    print_sample_status("Parse", prompt_name, model_name, trial, "OK")
                else:
                    unresolved = find_unresolved_variables(sanitized)
                    if unresolved:
                        # Sanitization failure: unresolved placeholders remain, so parsing is not meaningful.
                        sanitized_flag = False
                        parsed_result = "n/a"
                        unresolved_text = ", ".join(unresolved)
                        detail = f"sanitized={sanitized_flag}, parsed={parsed_result}, unresolved={unresolved_text}"
                    else:
                        # Parse failure after successful sanitization: record parser errors for debugging.
                        sanitized_flag = True
                        parsed_result = json.dumps([err.__dict__ for err in errors])
                        detail = f"sanitized={sanitized_flag}, parsed={parsed_result}"
                    append_stage_error("parse", prompt_name, model_name, trial, detail)
                    print_sample_status("Parse", prompt_name, model_name, trial, "FAIL", detail)

                df.loc[key, "sanitized"] = sanitized_flag
                df.loc[key, "parsed"] = parsed_result

    output_df = df.reset_index()
    output_df.to_pickle(cfg.PARSING_DF_PATH)
    return output_df


def cli_parse() -> None:
    df = parse_and_save_results()
    print(f"Saved parsing results with {len(df)} rows to {cfg.PARSING_DF_PATH}.")
    print(
        format_counts(
            "Parse summary",
            [
                ("sanitized_true", int((df["sanitized"] == True).sum())),
                ("sanitized_false", int((df["sanitized"] == False).sum())),
                ("parsed_true", int((df["parsed"] == True).sum())),
                ("parsed_nontrue", int((df["parsed"] != True).sum())),
                ("asts_written", int(df["ast_path"].notna().sum())),
            ],
        )
    )
    print_model_lines(
        df,
        "Parse",
        lambda model_df: [
            ("sanitized_ok", int((model_df["sanitized"] == True).sum())),
            ("sanitized_fail", int((model_df["sanitized"] == False).sum())),
            ("parsed_ok", int((model_df["parsed"] == True).sum())),
            ("parsed_fail", int((model_df["parsed"] != True).sum())),
        ],
    )
