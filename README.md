# LAMMPS-AST

**LAMMPS-AST** is a toolset for parsing, analyzing, and processing LAMMPS scripts using an Abstract Syntax Tree (AST) representation. It utilizes [Lark](https://github.com/lark-parser/lark) for parsing LAMMPS input files and provides scripts that leverage Large Language Models (LLMs) for interpreting, modifying, and generating LAMMPS scripts. It is designed to support structural analysis of LAMMPS scripts and to enable downstream workflows such as validation, comparison, transformation, and evaluation of LLM-generated simulation inputs.

`LAMMPS-AST` is a Python package for sanitizing and parsing LAMMPS input scripts into abstract syntax trees (ASTs). 

## Repository Structure

- `lammps_ast/`: core parser, sanitizer, grammar, and AST utilities
- `EvaluationPipelineExample/`: notebook-based example pipeline for script generation, parsing, execution, accuracy checking, and visualization
- `examples/`: small usage examples
- `setup.py`: package metadata and installation configuration

## Features

- Sanitization of LAMMPS input scripts prior to parsing
- Parsing of LAMMPS scripts into AST representations using Lark
- Utilities for AST transformation and comparison
- Support for evaluating generated LAMMPS scripts in downstream workflows
- Example notebooks demonstrating an end-to-end LLM evaluation pipeline

## Installation

### Clone the Repository

```bash
conda create -n Last_env python=3.11

pip install lammps_ast
conda install graphviz


## Citation

If you use `LAMMPS-AST` or the evaluation pipeline in academic work, please cite the associated publication.

```bibtex
@misc{lammps_ast_paper,
  title        = {Evaluating LLM-generated code for domain-specific languages: molecular dynamics with LAMMPS},
  author       = {Holbrook, Ethan W. and Verduzco, Juan C. and Strachan, Alejandro},
  year         = {2026},
  note         = {Manuscript in preparation}
}



