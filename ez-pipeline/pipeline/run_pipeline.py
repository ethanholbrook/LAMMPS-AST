from __future__ import annotations

import argparse

import pipeline_config as cfg
from pipeline_lib import run_selected_stages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run selected stages of the ez-pipeline LAMMPS evaluation pipeline."
    )
    parser.add_argument(
        "--stage",
        nargs="+",
        default=["all"],
        choices=["all", *cfg.STAGE_ORDER],
        help="Stage or stages to run. Use 'all' for the full pipeline.",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip generation and start from existing generated scripts.",
    )
    parser.add_argument(
        "--force-generate",
        action="store_true",
        help="Regenerate scripts even if generation outputs already exist.",
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="Print the available stages and exit.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_stages:
        print("Available stages:")
        for stage in cfg.STAGE_ORDER:
            print(f"- {stage}")
        return

    run_selected_stages(
        args.stage,
        skip_generation=args.skip_generation,
        force_generate=args.force_generate,
    )


if __name__ == "__main__":
    main()
