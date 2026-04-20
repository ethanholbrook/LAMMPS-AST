from __future__ import annotations

import json
import pickle
import re
import sys

import pandas as pd

import pipeline_config as cfg
from pipeline_common import append_stage_error, build_trial_dataframe, ensure_directories, format_counts, print_model_lines, print_sample_status, reset_stage_error_log


if str(cfg.REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(cfg.REPO_ROOT))

from lammps_ast import parse_to_AST  # noqa: E402
from pipeline_sanitizer import sanitize_script


def find_unresolved_variables(script: str) -> list[str]:
    unresolved: set[str] = set()

    for match in re.findall(r"\${([a-zA-Z_]\w*)}", script):
        unresolved.add(f"${{{match}}}")

    for match in re.findall(r"\bv_([a-zA-Z_]\w*)\b", script):
        unresolved.add(f"v_{match}")

    return sorted(unresolved)


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
                sanitized = sanitize_script(source)

                sanitized_path = cfg.SANITIZED_SCRIPTS_DIR / prompt_name / model_name / script_path.name
                sanitized_path.parent.mkdir(parents=True, exist_ok=True)
                sanitized_path.write_text(sanitized, encoding="utf-8")

                ast_obj, errors = parse_to_AST(sanitized, lint=True, max_errors=10)
                if ast_obj is not None and len(errors) == 0:
                    parsed_result: object = True
                    flag = True
                    ast_path = cfg.ASTS_DIR / prompt_name / model_name / script_path.with_suffix(".ast.pkl").name
                    ast_path.parent.mkdir(parents=True, exist_ok=True)
                    with ast_path.open("wb") as handle:
                        pickle.dump(ast_obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    df.loc[key, "ast_path"] = str(ast_path)
                    print_sample_status("Parse", prompt_name, model_name, trial, "OK")
                else:
                    parsed_result = json.dumps([err.__dict__ for err in errors])
                    first = errors[0] if errors else None
                    if first is not None and first.text is not None:
                        tokens = first.text.split()
                        flag = not any(token.startswith(("v_", "$")) for token in tokens)
                        if not flag:
                            unresolved = find_unresolved_variables(sanitized)
                            parsed_result = "n/a"
                            unresolved_text = ", ".join(unresolved) if unresolved else "unknown"
                            detail = f"sanitized={flag}, parsed={parsed_result}, unresolved={unresolved_text}"
                        else:
                            detail = f"sanitized={flag}, parsed={parsed_result}"
                    else:
                        flag = False
                        parsed_result = "n/a"
                        unresolved = find_unresolved_variables(sanitized)
                        unresolved_text = ", ".join(unresolved) if unresolved else "unknown"
                        detail = f"sanitized={flag}, parsed={parsed_result}, unresolved={unresolved_text}"
                    append_stage_error("parse", prompt_name, model_name, trial, detail)
                    print_sample_status("Parse", prompt_name, model_name, trial, "FAIL", detail)

                df.loc[key, "sanitized"] = flag
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
