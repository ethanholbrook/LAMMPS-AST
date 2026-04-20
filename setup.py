from pathlib import Path
import re

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
INIT_TEXT = (ROOT / "lammps_ast" / "__init__.py").read_text(encoding="utf-8")
VERSION_MATCH = re.search(r'^__version__\s*=\s*"([^"]+)"', INIT_TEXT, re.MULTILINE)
if VERSION_MATCH is None:
    raise RuntimeError("Could not determine package version from lammps_ast/__init__.py")

setup(
    name="lammps_ast",
    version=VERSION_MATCH.group(1),
    author="Juan C. Verduzco, Ethan W. Holbrook",
    author_email="holbrooe@purdue.edu",
    description="A LAMMPS script parser and sanitizer using Lark",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/ethanholbrook/LAMMPS-AST",
    packages=find_packages(include=["lammps_ast", "lammps_ast.*"]),
    include_package_data=True,
    package_data={
        "lammps_ast": ["grammar/*.lark"],
    },
    install_requires=[
        "lark-parser>=0.12.0",
        "colorama",
        "graphviz",
        "zss", 
        "pydot",
        "simpleeval" 
    ],
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Intended Audience :: Science/Research",
    ],
)
