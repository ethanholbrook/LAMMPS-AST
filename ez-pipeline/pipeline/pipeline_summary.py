from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import pipeline_config as cfg
from pipeline_accuracy import compute_accuracy_metrics, get_accuracy_df


COL_SPEC = {
    "Correct_Acc": lambda metrics: metrics.get("accuracy_to_correct", 0),
    "Failure_Acc": lambda metrics: metrics.get("accuracy_to_failure", 0),
    "Correct_PSZ": lambda metrics: metrics.get("pair_accuracy_to_correct", 0),
    "Failure_PSZ": lambda metrics: max(
        0,
        metrics.get("execution_to_accuracy_after_pairstyle", 0)
        - metrics.get("pair_accuracy_to_correct", 0),
    ),
    "Failure_PSZ_Exec": lambda metrics: max(
        0,
        metrics.get("execution_to_pairstylecheck", 0)
        - metrics.get("execution_to_accuracy_after_pairstyle", 0),
    ),
    "Failure_parser": lambda metrics: metrics.get("parser_to_failure", 0),
    "Failure_sanitizer": lambda metrics: metrics.get("sanitizer_to_failure", 0),
}


def build_summary_table_grouped_by_model(master_df: pd.DataFrame) -> pd.DataFrame:
    prompt_order = ["prompt1", "prompt2", "prompt3"]
    model_order = list(cfg.MODEL_DISPLAY.keys())
    grand_totals = {key: 0 for key in COL_SPEC}
    model_totals = {model: {key: 0 for key in COL_SPEC} for model in model_order}
    rows: list[dict[str, object]] = []

    for model_name in model_order:
        model_label = cfg.MODEL_DISPLAY.get(model_name, model_name)
        for prompt_name in prompt_order:
            if model_name not in cfg.PROMPT_MODEL_MAP[prompt_name]:
                continue
            combo_df = get_accuracy_df(prompt_name, model_name, master_df)
            metrics = compute_accuracy_metrics(combo_df)
            row_values = {column: int(spec(metrics)) for column, spec in COL_SPEC.items()}
            for column, value in row_values.items():
                grand_totals[column] += value
                model_totals[model_name][column] += value
            rows.append(
                {
                    "Model": model_label,
                    "Prompt": prompt_name.replace("prompt", "P"),
                    **row_values,
                }
            )

    out_rows = [
        {
            "Model": "",
            "Prompt": f"FULL {len(master_df)}",
            **grand_totals,
        }
    ]

    detail_df = pd.DataFrame(rows).set_index(["Model", "Prompt"])
    for model_name in model_order:
        model_label = cfg.MODEL_DISPLAY.get(model_name, model_name)
        out_rows.append(
            {
                "Model": model_label,
                "Prompt": "TOTAL",
                **model_totals[model_name],
            }
        )
        for prompt_name in prompt_order:
            prompt_label = prompt_name.replace("prompt", "P")
            if (model_label, prompt_label) in detail_df.index:
                out_rows.append(
                    {
                        "Model": model_label,
                        "Prompt": prompt_label,
                        **detail_df.loc[(model_label, prompt_label)].to_dict(),
                    }
                )

    summary_df = pd.DataFrame(out_rows).set_index(["Model", "Prompt"])
    return summary_df[
        [
            "Correct_Acc",
            "Failure_Acc",
            "Correct_PSZ",
            "Failure_PSZ",
            "Failure_PSZ_Exec",
            "Failure_parser",
            "Failure_sanitizer",
        ]
    ]


def make_sankey_figure(metrics: dict[str, int]) -> go.Figure:
    return go.Figure(
        go.Sankey(
            node=dict(
                pad=15,
                thickness=40,
                label=[
                    "Normalization",
                    "Parser",
                    "Execution",
                    "Accuracy",
                    "Correct",
                    "PSZ",
                    "Accuracy",
                    "Fail",
                    "Fail",
                    "Fail",
                    "Fail",
                    "Fail",
                    "Correct",
                ],
                x=[0.0, 0.2, 0.4, 0.75, 0.95, 0.6, 0.75, 0.1, 0.3, 0.7, 0.85, 0.9, 0.9],
                y=[0.5, 0.4, 0.4, 0.15, 0.15, 0.6, 0.5, 0.9, 0.9, 0.9, 0.3, 0.7, 0.5],
                color=["black"] * 13,
            ),
            link=dict(
                source=[0, 0, 1, 1, 2, 2, 5, 5, 3, 3, 6, 6],
                target=[1, 7, 2, 8, 3, 5, 6, 9, 4, 10, 12, 11],
                value=[
                    metrics["sanitizer_to_parser"],
                    metrics["sanitizer_to_failure"],
                    metrics["parser_to_execution"],
                    metrics["parser_to_failure"],
                    metrics["execution_to_accuracy"],
                    metrics["execution_to_pairstylecheck"],
                    metrics["execution_to_accuracy_after_pairstyle"],
                    metrics["execution_to_pairstylecheck"] - metrics["execution_to_accuracy_after_pairstyle"],
                    metrics["accuracy_to_correct"],
                    metrics["accuracy_to_failure"],
                    metrics["pair_accuracy_to_correct"],
                    metrics["execution_to_accuracy_after_pairstyle"] - metrics["pair_accuracy_to_correct"],
                ],
                color=[
                    "rgba(34, 139, 34, 0.4)",
                    "rgba(178, 34, 34, 0.4)",
                    "rgba(34, 139, 34, 0.4)",
                    "rgba(178, 34, 34, 0.4)",
                    "rgba(34, 139, 34, 0.4)",
                    "rgba(218, 165, 32, 0.4)",
                    "rgba(34, 139, 34, 0.4)",
                    "rgba(178, 34, 34, 0.4)",
                    "rgba(34, 139, 34, 0.4)",
                    "rgba(178, 34, 34, 0.4)",
                    "rgba(126, 152, 33, 0.4)",
                    "rgba(178, 34, 34, 0.4)",
                ],
            ),
        )
    ).update_layout(
        title="LAMMPS Evaluation Pipeline Flow",
        font=dict(size=14),
        width=1200,
        height=700,
    )


def run_summary_stage() -> tuple[pd.DataFrame, dict[str, int]]:
    accuracy_df = pd.read_pickle(cfg.ACCURACY_DF_PATH)
    summary_df = build_summary_table_grouped_by_model(accuracy_df)
    summary_df.to_csv(cfg.SUMMARY_CSV_PATH)
    try:
        summary_text = summary_df.to_markdown()
    except Exception:
        summary_text = summary_df.to_string()
    cfg.SUMMARY_MD_PATH.write_text(summary_text, encoding="utf-8")

    metrics = compute_accuracy_metrics(accuracy_df)
    sankey = make_sankey_figure(metrics)
    sankey.write_html(cfg.SANKEY_HTML_PATH)
    try:
        sankey.write_image(cfg.SANKEY_PNG_PATH)
    except Exception:
        pass

    return summary_df, metrics


def cli_summarize() -> None:
    summary_df, metrics = run_summary_stage()
    print(summary_df)
    print(metrics)
    print(f"Saved summary table to {cfg.SUMMARY_CSV_PATH} and Sankey plot to {cfg.SANKEY_HTML_PATH}.")
