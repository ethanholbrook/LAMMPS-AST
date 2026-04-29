# EZ Pipeline

A repo-friendly evaluation pipeline for assessing LLM-generated LAMMPS molecular dynamics scripts. Supports:

- `gpt-5.4`
- `claude-opus-4-7`

The shared control file is [pipeline/pipeline_config.py](pipeline/pipeline_config.py). It holds the prompts, model choices, output locations, potential path, and the default LAMMPS executable. Parsing and sanitization are provided by the repo package `lammps_ast`; this pipeline does not carry local copies of those functions.

## Structure

- [pipeline/pipeline_config.py](pipeline/pipeline_config.py): central control file
- [pipeline/pipeline_lib.py](pipeline/pipeline_lib.py): compatibility facade and stage orchestration
- [pipeline/pipeline_common.py](pipeline/pipeline_common.py): shared helpers
- [pipeline/pipeline_generate.py](pipeline/pipeline_generate.py): generation stage implementation
- [pipeline/pipeline_parse.py](pipeline/pipeline_parse.py): parse stage implementation
- [pipeline/pipeline_execute.py](pipeline/pipeline_execute.py): execution stage implementation
- [pipeline/pipeline_accuracy.py](pipeline/pipeline_accuracy.py): accuracy stage implementation
- [pipeline/pipeline_summary.py](pipeline/pipeline_summary.py): summary stage implementation
- [pipeline/run_pipeline.py](pipeline/run_pipeline.py): main driver with stage selection

## Main Driver

List the available stages:

```bash
cd ez-pipeline
./.venv/bin/python pipeline/run_pipeline.py --list-stages
```

Run the full workflow:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage all
```

Run only generation:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage generate
```

Run several stages explicitly:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage parse execute accuracy summarize
```

Skip generation and continue from existing scripts:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage all --skip-generation
```

Force regeneration even if script outputs already exist:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage generate --force-generate
```

## Stage Invocation

Use the single driver and choose stages with `--stage`:

```bash
./.venv/bin/python pipeline/run_pipeline.py --stage generate
./.venv/bin/python pipeline/run_pipeline.py --stage parse
./.venv/bin/python pipeline/run_pipeline.py --stage execute
./.venv/bin/python pipeline/run_pipeline.py --stage accuracy
./.venv/bin/python pipeline/run_pipeline.py --stage summarize
```

## Saved Outputs

- `pipeline/` contains the pipeline code and stage entrypoints
- `generated_scripts/` stays at the top level for generated LAMMPS inputs
- `pipeline_generated_files/` contains run-created artifact folders such as `raw_responses/`, `sanitized_scripts/`, `asts/`, `short_run_scripts/`, `logs/`, `pair_change/`, `pair_change_logs/`, `errors/`, and `lammps_generated_files/`
- `data/` contains checkpoint pickles such as `parsing_df.pkl`, `final_pair_df.pkl`, and `accuracy_df_trees.pkl`
- `results/` contains summary tables and plots such as [results/summary_table.csv](results/summary_table.csv), [results/summary_table.md](results/summary_table.md), and [results/final_sankey.html](results/final_sankey.html)

## Environment Notes

- The `.env` is loaded automatically from this directory.
- `LAMMPS_PIPELINE_TRIALS` controls how many scripts are generated per prompt/model pair.
- `OPENAI_MODEL` and `ANTHROPIC_MODEL` can override the default model choices.
- `LAMMPS_EXECUTABLE` can override the default `lmp` path if you want to use another install.
