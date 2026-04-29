from __future__ import annotations

import argparse

import pipeline_config as cfg
from pipeline_accuracy import (
    accuracy_from_ast_row_prompt1,
    accuracy_from_ast_row_prompt2,
    accuracy_from_ast_row_prompt3,
    cli_accuracy,
    compute_accuracy_metrics,
    get_accuracy_df,
    run_accuracy_stage,
)
from pipeline_common import (
    append_stage_error as _append_stage_error,
    build_trial_dataframe,
    ensure_directories,
    format_counts as _format_counts,
    print_model_lines as _print_model_lines,
    print_sample_status as _print_sample_status,
    reset_stage_error_log as _reset_stage_error_log,
)
from pipeline_execute import (
    _filter_mpi_warning_lines,
    cli_execute,
    discover_lammps_executable,
    do_runs,
    extract_lammps_error_lines,
    modify_for_short_runs,
    modify_pair_style,
    modify_run_lines,
    pair_style_change,
    run_execution_stage,
    run_lammps,
)
from pipeline_generate import (
    cli_generate,
    extract_lammps_script,
    generate_anthropic_response,
    generate_openai_response,
    generate_scripts,
    write_script_file,
)
from pipeline_parse import cli_parse, find_unresolved_variables, parse_and_save_results
from pipeline_summary import COL_SPEC, build_summary_table_grouped_by_model, make_sankey_figure, run_summary_stage, cli_summarize


def run_selected_stages(
    stage_names: list[str],
    *,
    skip_generation: bool = False,
    force_generate: bool = False,
) -> None:
    ensure_directories()

    normalized = list(stage_names)
    if not normalized or "all" in normalized:
        normalized = list(cfg.STAGE_ORDER)

    if skip_generation:
        normalized = [stage for stage in normalized if stage != "generate"]

    def run_generate() -> None:
        written = generate_scripts(force=force_generate)
        action = "Generated" if force_generate else "Wrote or reused"
        print(f"{action} {len(written)} generated scripts.")

    stage_functions = {
        "generate": run_generate,
        "parse": cli_parse,
        "execute": cli_execute,
        "accuracy": cli_accuracy,
        "summarize": cli_summarize,
    }

    unknown = [stage for stage in normalized if stage not in stage_functions]
    if unknown:
        raise ValueError(f"Unknown stages requested: {unknown}")

    for stage in normalized:
        print(f"\n=== Running stage: {stage} ===")
        stage_functions[stage]()


def cli_full_pipeline() -> None:
    parser = argparse.ArgumentParser(description="Run the full evaluation pipeline.")
    parser.add_argument("--skip-generation", action="store_true", help="Assume generated scripts already exist.")
    parser.add_argument("--force-generate", action="store_true", help="Regenerate scripts even if outputs already exist.")
    args = parser.parse_args()

    run_selected_stages(
        ["all"],
        skip_generation=args.skip_generation,
        force_generate=args.force_generate,
    )
