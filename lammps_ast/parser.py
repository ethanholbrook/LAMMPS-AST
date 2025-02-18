import os
from lark import Lark
from colorama import Fore, Style
from .sanitizer import sanitize
from .transformer import RemoveNewlinesAndUnsupported
from .error_handler import missing_arg_error_handler

# +
GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar", "lammps_grammar.lark")

# Ensure the grammar file exists before loading
if not os.path.exists(GRAMMAR_PATH):
    raise FileNotFoundError(f"Critical error: Default grammar file not found at {GRAMMAR_PATH}")

# Load the built-in grammar
with open(GRAMMAR_PATH, "r") as f:
    LAMMPS_GRAMMAR = f.read()

# Initialize the parser using the built-in grammar
parser = Lark(LAMMPS_GRAMMAR, parser="lalr", keep_all_tokens=True)


# -

def parse_to_AST(filename):

    with open(filename, "r") as file:
        script = file.read()

    try:
        sanitized_script = sanitize(script)
        parse_tree = parser.parse(sanitized_script, on_error=missing_arg_error_handler)
        parse_tree = RemoveNewlinesAndUnsupported().transform(parse_tree)
    except Exception as e:
        print(f" \t {Fore.RED}Critical Parse Error:{Style.RESET_ALL} {e}")
        return None

    return parse_tree
