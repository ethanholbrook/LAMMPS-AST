---
name: lammps-ast-eval
description: Generate or validate a LAMMPS molecular dynamics input script using static parsing and execution testing. Make a reasonable attempt at a correct script (good physics and structure, without agonizing over exact syntax), then use the pipeline to catch and fix precise errors iteratively. Use this skill when the user wants to write, check, or fix a LAMMPS script.
---

# LAMMPS-AST Eval

Validate LAMMPS input scripts through a progressive pipeline: normalization → static parsing → execution testing. At each stage, structured feedback guides iterative repair.

This skill implements the evaluation procedure described in:
> Holbrook, Verduzco & Strachan. "Evaluating LLM-generated code for domain-specific languages: molecular dynamics with LAMMPS." arXiv:2603.20630 (2026).

## Setup

Before running any script, verify that `lammps-ast` is installed:

```bash
python -c "import lammps_ast" 2>/dev/null && echo "lammps-ast ready" || pip install lammps-ast
```

If that fails (common on HPC clusters due to permissions or no internet on compute nodes):

```bash
pip install --user lammps-ast          # install to home directory
# or, if using conda:
conda activate <your-env>
pip install lammps-ast
```

**HPC note:** Run installation on a login node, not a compute node. If you are inside a conda environment or virtualenv, activate it first — the skill scripts use `sys.executable` so they install into whichever Python is currently active.

All pipeline scripts are in the `scripts/` directory of this skill. Reference them by their full path when running.

## Workflow: single script

**Before running the pipeline, make a reasonable attempt at a correct script — get the physics and structure right, but don't agonize over exact syntax. The pipeline will catch precise errors; trust it to do that work.**

Before running any pipeline step:
1. Create a `tests/` folder in the current working directory (if it doesn't exist), and a dedicated eval subfolder inside it:

```bash
mkdir -p tests/<script_stem>_eval
```

2. If the user provided a method description or prompt, write it to `tests/<script_stem>_eval/<script_stem>_prompt.txt`.
3. If the script does not yet exist on disk, write it **directly into that subfolder** as `tests/<script_stem>_eval/<script_stem>.in` — never to the parent directory or to `/tmp/`. This keeps all eval sessions organized under `tests/` with no duplicates.

### Step 1 — Normalize and parse

```bash
python <skill_dir>/scripts/sanitize_and_parse.py tests/<script_stem>_eval/<script_stem>.in \
  --session-log tests/<script_stem>_eval/<script_stem>.session.jsonl \
  --prompt-file tests/<script_stem>_eval/<script_stem>_prompt.txt \
  --lammps-version 20240829
```

The `--prompt-file` flag is optional but recommended when a method description was provided — it embeds the description in the session log and report for full provenance. Omit it if no description is available.

The `--lammps-version` flag selects which LAMMPS grammar to parse against (e.g. `20240829`). Omit it to use the latest available. To list installed versions: `python -c "from lammps_ast import list_grammar_versions; print(list_grammar_versions())"`. The resolved version is recorded in the output JSON as `lammps_version`.

The output is JSON. Read the fields:
- `sanitized: false, sanitize_error: ...` → normalization raised an exception; see `sanitize_error`
- `sanitized: false, unresolved_variables: [...]` → normalization produced output with unresolvable variable references; the `unresolved_variables` list names each one
- `sanitized: true, parsed: false` → syntax error; see `errors` list (each entry has `line`, `column`, `token`, `text` — the offending line)
- `parsed: true` → proceed to Step 2

**If errors are found:** consult `REFERENCE.md` for the failure mode and fix pattern. Apply the fix to the script and re-run Step 1. Repeat until `parsed: true`.

### Step 2 — Execute (requires LAMMPS)

Only attempt this step if one of the following is true:
- The user explicitly asked to run or execute the script.
- The script passed Step 1 and the user's goal is to get it working end-to-end.
- `LAMMPS_EXE` is already set in the environment.

Do **not** ask the user for an executable path unprompted. If Step 1 already revealed errors, report those and stop — execution testing adds nothing until the script parses cleanly. If Step 1 passed and execution testing would be useful, note at the end of your response that it is available if the user provides a LAMMPS executable path.

To locate the executable:
```bash
echo $LAMMPS_EXE                              # check env var first
which lmp lmp_serial lmp_mpi 2>/dev/null      # check PATH
```

If neither works, LAMMPS may need to be loaded via the module system (common on HPC clusters):
```bash
module spider lammps          # list available LAMMPS versions
module load lammps/<version>  # load the chosen version
which lmp                     # should now resolve
```

Once the executable is found or the module is loaded, run with:
```bash
# Explicit path
python <skill_dir>/scripts/run_lammps.py tests/<script_stem>_eval/<script_stem>.in \
  --lammps-exe <path_to_lammps> \
  --session-log tests/<script_stem>_eval/<script_stem>.session.jsonl

# Or rely on the environment variable
export LAMMPS_EXE=$(which lmp)
python <skill_dir>/scripts/run_lammps.py tests/<script_stem>_eval/<script_stem>.in \
  --session-log tests/<script_stem>_eval/<script_stem>.session.jsonl
```

Pass the same `--session-log` file used in Step 1 so the execution result is appended to the same session.

If the user is on an HPC cluster and has not loaded a LAMMPS module, suggest they run `module spider lammps` to see what is available before asking for an explicit path.

The script runs LAMMPS with all `run` statements shortened to 10 steps. Read the output:

- `executed: true` → script runs successfully
- `executed: false, psz_applied: true, psz_executed: true` → pair_style is the isolated problem; the rest of the script is structurally sound. Fix only the `pair_style`/`pair_coeff` lines (see REFERENCE.md §1).
- `executed: false, psz_executed: false` → deeper structural error; read `psz_log_tail` for the LAMMPS error message. Consult REFERENCE.md and fix, then re-run from Step 1.

## Iterative repair loop

When fixing a script, always restart from Step 1 after each edit — a fix at the execution stage can uncover a previously hidden parse issue.

The canonical repair order is:
1. Fix normalization errors (variable expressions, loop constructs)
2. Fix parser errors (invalid commands, wrong argument types)
3. Fix pair_style/pair_coeff (most common execution failure)
4. Fix deeper execution errors (ordering, geometry, unit conversions)

Consult `REFERENCE.md` for concrete fix patterns for each failure mode.

### Step 3 — Domain review

After the script passes Step 1 (and Step 2 if attempted), compare the final normalized script against the original method description and flag any physical correctness issues the pipeline cannot detect. Perform this step even if no prompt file was provided — analyze the script on its own merits.

Check each of the following:
- **Unit conversions** (metal units): velocity in Å/ps, time in ps, temperature in K, energy in eV. Flag values that appear to be in SI or other unit systems.
- **Geometry**: box dimensions, region boundaries, and implied atom counts match the described system size.
- **Boundary conditions**: match the physics (e.g., free surfaces along the shock direction for spall, periodic for bulk NPT).
- **Potential**: the chosen `pair_style` and potential file are appropriate for the described material and reference.
- **Equilibration**: thermostat/barostat damping constants are physically reasonable (0.1 ps for temperature, 1.0 ps for pressure in metal units).
- **Run length**: timestep × steps produces the described simulation time.
- **Velocities**: initial or impact velocities are correctly converted and applied to the correct groups.

Write the review as a short paragraph or bulleted list. Prefix each issue with `[WARNING]` (physically wrong) or `[NOTE]` (minor concern). If no issues are found, say so explicitly.

Log the review to the session:

```bash
python <skill_dir>/scripts/log_review.py \
  tests/<script_stem>_eval/<script_stem>.session.jsonl \
  --text "Your review text here"
```

If the review is long, write it to a file first:

```bash
python <skill_dir>/scripts/log_review.py \
  tests/<script_stem>_eval/<script_stem>.session.jsonl \
  --file tests/<script_stem>_eval/<script_stem>_review.txt
```

## Generating a report

If a session log was collected, generate a human-readable HTML report into the same eval folder:

```bash
python <skill_dir>/scripts/generate_report.py \
  tests/<script_stem>_eval/<script_stem>.session.jsonl \
  --output tests/<script_stem>_eval/<script_stem>_report.html
```

The report shows each repair round with per-stage pass/fail status, error details, execution log output, and the final normalized script.

To produce a PDF instead:
```bash
python <skill_dir>/scripts/generate_report.py <script>.session.jsonl --pdf
```

This requires `weasyprint` (`pip install weasyprint`). If weasyprint is not installed, the script falls back to HTML and prints instructions for printing to PDF from a browser.

Offer to generate the report at the end of any session where a session log was used.

## Notes

- Potential files (`.potential`, `.eam`, `.alloy`, `.fs`) should be in the same directory as the script or referenced by absolute path.
- The parser covers ~62 LAMMPS command types. An error on an otherwise valid command may indicate it is outside the current grammar — check REFERENCE.md before attempting a fix.
- Execution uses a 10-step run. A script that passes execution at 10 steps may still fail at full run length, but this catches the majority of structural and potential-related errors cheaply.
