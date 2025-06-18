import os
from lark import Lark
from colorama import Fore, Style
from .transformer import RemoveNewlines
from .error_handler import missing_arg_error_handler

#####################
# Get the current working directory (useful in Jupyter/IPython)
current_dir = os.getcwd()

# Move to the correct path assuming we are inside LAMMPS-AST or a subdirectory
repo_root = os.path.abspath(os.path.join(current_dir, ".."))  # Go one level up
GRAMMAR_PATH = os.path.join(repo_root, "lammps_ast", "grammar", "lammps_grammar.lark")

# GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar", "lammps_grammar.lark")
#####################


# Ensure the grammar file exists before loading
if not os.path.exists(GRAMMAR_PATH):
    raise FileNotFoundError(f"Critical error: Default grammar file not found at {GRAMMAR_PATH}")

# Load the built-in grammar
with open(GRAMMAR_PATH, "r") as f:
    LAMMPS_GRAMMAR = f.read()

# Initialize the parser using the built-in grammar
parser = Lark(LAMMPS_GRAMMAR, parser="lalr", keep_all_tokens=True)

def parse_to_AST(sanitized_script):
    
    try:
        parse_tree = parser.parse(sanitized_script)
        parse_tree = RemoveNewlines().transform(parse_tree)
    except Exception as e:
        print(f""" \t {Fore.RED}🟥 Critical Parse Error:{Style.RESET_ALL}.
            Unexpected token {repr(e.token)} at line {e.line}, column {e.column}.
            Expected one of: {e.expected}.
            Previous token: {e.token_history}""")


        return None, e

    return parse_tree, None