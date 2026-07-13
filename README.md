# LAMMPS-AST

`LAMMPS-AST` is a Python package for sanitizing and parsing LAMMPS input scripts into abstract syntax trees (ASTs). It is built on [Lark](https://github.com/lark-parser/lark) and is intended for structural analysis, validation, comparison, and downstream workflows around LAMMPS input files.

## What It Provides

- script sanitization before parsing
- parsing of LAMMPS input scripts into ASTs
- AST transformation and comparison utilities
- repository examples showing how the parser can be used in notebook and pipeline workflows

## Install

Install from PyPI:

```bash
pip install lammps_ast
```

If you need the optional visualization tooling used in some example workflows, you may also want a local Graphviz install.

## Minimal Usage

```python
from lammps_ast.sanitizer import sanitize
from lammps_ast.parser import parse_to_AST

script = """
units metal
atom_style atomic
boundary p p p
"""

sanitized = sanitize(script)
tree, errors = parse_to_AST(sanitized, lint=True)
```

`parse_to_AST(..., lint=True)` returns a parse tree plus collected parse errors. With `lint=False`, it behaves like a direct parser call and returns either a tree or an exception object.

## Repository Layout

- `lammps_ast/`: package source, including parser, sanitizer, grammar, and AST utilities
- `examples/`: small examples of using the parser directly
- `publication/`: notebook-based workflow used for the publication-oriented evaluation example
- `ez-pipeline/`: script-oriented evaluation pipeline built on top of `lammps_ast`

The PyPI distribution is focused on the `lammps_ast` package itself. The notebook and pipeline folders are repository examples and supporting workflows.

## Development Install

To work from a local clone:

```bash
pip install -e .
```

## Citation

If you use `LAMMPS-AST` or the evaluation workflow in academic work, please cite the associated publication.

```bibtex
@article{holbrook2026evaluating,
  title        = {Evaluating LLM-generated code for domain-specific languages: Molecular dynamics with LAMMPS},
  author       = {Holbrook, Ethan W. and Verduzco, Juan C. and Strachan, Alejandro},
  journal      = {Computational Materials Science},
  year         = {2026},
  volume       = {272},
  pages        = {114839},
  doi          = {10.1016/j.commatsci.2026.114839},
  url          = {https://doi.org/10.1016/j.commatsci.2026.114839}
}
```
