# lammps_parser/__init__.py

from .parser import parse_to_AST
from .sanitizer import find_unresolved_variables, sanitize

__version__ = "0.1.91"
__author__ = "Juan C. Verduzco, Ethan W. Holbrook"
