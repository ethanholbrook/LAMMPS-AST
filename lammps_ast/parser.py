import os
from lark import Lark
from colorama import Fore, Style
from .transformer import RemoveNewlines
from .error_handler import missing_arg_error_handler
from importlib.resources import files

#####################
# Get the current working directory (useful in Jupyter/IPython)
current_dir = os.getcwd()

# Move to the correct path assuming we are inside LAMMPS-AST or a subdirectory
repo_root = os.path.abspath(os.path.join(current_dir, ".."))  # Go one level up

# Ensure the grammar file exists before loading
try: 
    GRAMMAR_PATH = files("lammps_ast.grammar").joinpath("lammps_grammar.lark")
    with open(GRAMMAR_PATH, "r") as f:
        LAMMPS_GRAMMAR = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"Critical error: Grammar file not found at {GRAMMAR_PATH}")

# Initialize the parser using the built-in grammar
parser = Lark(LAMMPS_GRAMMAR, parser="lalr", keep_all_tokens=True)

from dataclasses import dataclass

@dataclass
class ParseErrorInfo:
    line: int
    column: int
    token: str
    text: str
    
def parse_to_AST(sanitized_script, *, lint=False, max_errors=10, verbose=False):
    """
    If lint=False (default):
        returns (parse_tree, None) on success
        returns (None, err) on failure

    If lint=True:
        returns (parse_tree_or_None, [ParseErrorInfo, ...])
        - parse_tree_or_None is a valid tree only if parsing eventually succeeds
        - errors contains up to max_errors items
    """
    # --- Parser-only mode (your current behavior, but optionally quiet) ---
    if not lint:
        try:
            parse_tree = parser.parse(sanitized_script)
            parse_tree = RemoveNewlines().transform(parse_tree)
            return parse_tree, None
        except Exception as e:
            if verbose:
                print(f""" \t {Fore.RED}🟥 Critical Parse Error:{Style.RESET_ALL}.
                    Unexpected token {repr(e.token)} at line {e.line}, column {e.column}.
                    Expected one of: {e.expected}.
                    Previous token: {e.token_history}""")
            return None, e

    # --- Linter mode (collect multiple errors) ---
    lines = sanitized_script.splitlines(True)  # preserve newlines
    errors = []

    for _ in range(max_errors):
        try:
            parse_tree = parser.parse("".join(lines))
            parse_tree = RemoveNewlines().transform(parse_tree)
            return parse_tree, errors  # success with collected errors (possibly empty)
        except Exception as e:
            line_idx = e.line - 1
            bad_line = lines[line_idx].rstrip("\n") if 0 <= line_idx < len(lines) else ""

            err_info = ParseErrorInfo(
                line=getattr(e, "line", None),
                column=getattr(e, "column", None),
                token=repr(getattr(e, "token", None)),
                text=bad_line
            )
            errors.append(err_info)

            if verbose:
                print(f""" \t {Fore.RED}🟥 Parse Error:{Style.RESET_ALL}.
                    Unexpected token {repr(getattr(e,'token',None))} at line {getattr(e,'line',None)}, column {getattr(e,'column',None)}.
                    Expected one of: {getattr(e,'expected',None)}.
                    Previous token: {getattr(e,'token_history',None)}
                    Line: {bad_line}""")

            # Prevent infinite loops / out-of-range
            if not (0 <= line_idx < len(lines)):
                break

            # Neutralize the offending line but keep line numbering
            newline = "\n" if lines[line_idx].endswith("\n") else ""
            lines[line_idx] = "\n" if lines[line_idx].endswith("\n") else ""

            # If we keep hitting the same spot, stop
            if len(errors) >= 2 and errors[-1].line == errors[-2].line and errors[-1].column == errors[-2].column:
                break

    return None, errors


