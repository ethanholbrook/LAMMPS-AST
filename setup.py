from setuptools import setup, find_packages

setup(
    name="lammps-ast",
    version="0.0.3",
    author="Juan C. Verduzco, Ethan W. Holbrook",
    author_email="eholbrooe@purdue.edu",
    description="A LAMMPS script parser and sanitizer using Lark",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ethanholbrook/LAMMPS-AST",
    packages=find_packages(include=["lammps_ast", "lammps_ast.*"]),
    include_package_data=True,
    package_data={
        "lammps_parser": ["grammar/*.lark"],
    },
    install_requires=[
        "lark-parser>=0.12.0",
        "colorama",
        "graphviz",
        "zss",  
    ],
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Intended Audience :: Science/Research",
    ],
    entry_points={
        "console_scripts": [
            "lammps-parse=lammps_parser.parser:parse_to_AST",
        ],
    },
)
