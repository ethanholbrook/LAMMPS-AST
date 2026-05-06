# Script Evaluation Pipeline Example

This folder contains a notebook-based example of the LAMMPS script evaluation pipeline used with `lammps_ast`. The notebooks walk through the full workflow used to evaluate large language model outputs for LAMMPS input generation:

1. Generate candidate scripts from model responses
2. Sanitize and parse the scripts into ASTs
3. Execute shortened versions of the scripts in LAMMPS (and PSZ)
4. Apply prompt-specific accuracy checks
5. Summarize outcomes with tables and Sankey plots

The notebooks are designed as an example of the parser in use and reflects the approach used in our paper entitled 'Evaluating LLM-generated code for domain-specific languages: molecular dynamics with LAMMPS'. The main repository focuses on the parser itself, while this folder shows how it can be used in an end-to-end benchmark pipeline.

## Folder Contents

- `1_Script_Generation.ipynb`: calls model APIs and writes generated LAMMPS scripts to `generated_scripts/`
- `2_Sanitizer_and_Parsing.ipynb`: sanitizes scripts, parses them with `lammps_ast`, writes sanitized scripts and ASTs, and saves `parsing_df.pkl`
- `3_Execution.ipynb`: creates shortened execution scripts, runs LAMMPS, performs the pair-style neutralization pass, and saves `final_pair_df.pkl`
- `4_Accuracy.ipynb`: evaluates prompt-specific correctness from ASTs and execution results, and saves `accuracy_df_trees.pkl`
- `Sankey_simple_modified.ipynb`: loads `accuracy_df_trees.pkl` and produces summary tables and Sankey-style visualizations
- `potentials/`: prompt-specific potential files used by the example scripts
- `generated_scripts_paper/`: example generated scripts corresponding to the paper dataset
- `generated_scripts.zip`: archived generated scripts

## Recommended Use

There are two practical ways to use this folder.

### Option 1: Run the full pipeline

Use this when you want to generate fresh model outputs and evaluate them from start to finish.

Run the notebooks in this order:

1. `1_Script_Generation.ipynb`
2. `2_Sanitizer_and_Parsing.ipynb`
3. `3_Execution.ipynb`
4. `4_Accuracy.ipynb`
5. `Summarization_and_Visualization.ipynb`

### Option 2: Start from included example scripts

Use this when you want to demonstrate the parser and evaluation flow without regenerating scripts from APIs.

In this case, point the later notebooks to an existing script directory such as `generated_scripts_paper/`, then run:

1. `2_Sanitizer_and_Parsing.ipynb`
2. `3_Execution.ipynb`
3. `4_Accuracy.ipynb`
4. `Summarization_and_Visualization.ipynb`

This is the better path for readers who want to inspect the evaluation pipeline without needing API access. It does require changing the promp_model_map and trial loop values. 

## Expected Inputs and Outputs by Stage

### 1. Script generation

Input:

- prompt text embedded in the notebook
- model configuration embedded in the notebook
- API credentials from environment variables (store in .env file)

Output:

- `generated_scripts/<prompt>/<model>/<prompt>-<model>-T<trial>.in`

### 2. Sanitization and parsing

Input:

- generated scripts from `generated_scripts/` or another compatible script directory

Output:

- `sanitized_scripts/<prompt>/<model>/...`
- `asts/<prompt>/<model>/*.ast.pkl`
- `parsing_df.pkl`

### 3. Execution

Input:

- `parsing_df.pkl`
- prompt potential files in `potentials/`
- a working LAMMPS executable

Output:

- `short_run_scripts/<prompt>/<model>/...`
- `logs2/<prompt>/<model>/...`
- `pair_change2/<prompt>/<model>/...`
- `pair_change_logs2/<prompt>/<model>/...`
- `final_pair_df.pkl`

### 4. Accuracy

Input:

- `final_pair_df.pkl`
- AST files written during parsing

Output:

- `accuracy_df_trees.pkl`

### 5. Summary and visualization

Input:

- `accuracy_df_trees.pkl`

Output:

- notebook tables and Sankey plots for pipeline-level interpretation

## Typical Workflow

### A. Generate new scripts

Open `1_Script_Generation.ipynb` and configure:

- the prompts to evaluate
- the model identifiers to query
- the number of trials
- the output script directory

Run the generation cells to create `.in` files in `generated_scripts/`.

### B. Parse the scripts

Open `2_Sanitizer_and_Parsing.ipynb`, confirm the script directory, and run the notebook. This stage sanitizes each input, attempts parsing, writes AST files for successful parses, and saves the stage summary to `parsing_df.pkl`.

### C. Execute shortened runs

Open `3_Execution.ipynb` and set the LAMMPS executable path if needed. This notebook constructs shortened versions of the scripts for fast testing, executes them, and records whether each script runs successfully. It also performs an auxiliary pair-style neutralization pass for certain execution failures. The final stage output is `final_pair_df.pkl`.

### D. Apply accuracy checks

Open `4_Accuracy.ipynb` and run the prompt-specific AST-based checks. This notebook evaluates whether each script matches the intended simulation setup for each benchmark prompt and saves the result as `accuracy_df_trees.pkl`.

### E. Build figures and tables

Open `Sankey_simple_modified.ipynb` to load the final accuracy dataframe, compute summary metrics, and produce the Sankey visualizations and aggregate tables.

## Environment Notes

To run the full pipeline, the environment should provide:

- Python with Jupyter support
- the `lammps_ast` package available in the environment
- the notebook dependencies used in the code cells, such as `pandas`, `numpy`, `lark`, and `python-dotenv`
- API access for any model providers used in `1_Script_Generation.ipynb`
- a working LAMMPS executable for `3_Execution.ipynb`

If your goal is only to inspect the pipeline structure, parser outputs, or downstream analysis, you can skip API-based generation and start from the included example scripts.

## Notes for Readers

- The notebooks are intended to be run sequentially because each stage writes artifacts used by the next stage.
- The pickle files are the main handoff objects between stages:
  - `parsing_df.pkl`
  - `final_pair_df.pkl`
  - `accuracy_df_trees.pkl`
- The `generated_scripts_paper/` directory is useful when you want a fixed set of example scripts instead of generating new ones.

## Citation Context

This folder is included as a supplementary example of how `lammps_ast` can be used in an LLM evaluation workflow for LAMMPS script generation. The parser itself lives in the main repository code; these notebooks demonstrate one applied evaluation pipeline built on top of it.
