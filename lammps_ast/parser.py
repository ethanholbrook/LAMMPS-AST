from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from colorama import Fore, Style
from lark import Lark

from .transformer import RemoveNewlines
from .error_handler import missing_arg_error_handler


_GRAMMAR_DIR = files("lammps_ast.grammar")
_parser_cache: dict[str, Lark] = {}


def list_grammar_versions() -> list[str]:
    """Return sorted list of available LAMMPS grammar versions."""
    versions = []
    for entry in _GRAMMAR_DIR.iterdir():
        name = entry.name
        if name.startswith("lammps_grammar_") and name.endswith(".lark"):
            versions.append(name[len("lammps_grammar_"):-len(".lark")])
    return sorted(versions)


def _get_parser(version: str | None) -> Lark:
    if version is None:
        available = list_grammar_versions()
        if not available:
            raise FileNotFoundError("No grammar files found in lammps_ast.grammar.")
        version = available[-1]

    if version in _parser_cache:
        return _parser_cache[version]

    grammar_file = f"lammps_grammar_{version}.lark"
    try:
        path = _GRAMMAR_DIR.joinpath(grammar_file)
        with open(path) as f:
            grammar_text = f.read()
    except FileNotFoundError:
        available = list_grammar_versions()
        raise FileNotFoundError(
            f"Grammar version '{version}' not found. "
            f"Available versions: {available}"
        )

    lark_parser = Lark(grammar_text, parser="lalr", keep_all_tokens=True)
    _parser_cache[version] = lark_parser
    return lark_parser


@dataclass
class ParseErrorInfo:
    line: int
    column: int
    token: str
    text: str


def parse_to_AST(sanitized_script, *, lint=False, max_errors=10, verbose=False, lammps_version=None):
    """
    Parse a sanitized LAMMPS script and return (tree, errors).

    lammps_version: LAMMPS release date string (e.g. '20240829'). Defaults to
                    the latest available grammar. Pass None to use the latest.

    If lint=False (default):
        returns (parse_tree, None) on success
        returns (None, err) on failure

    If lint=True:
        returns (parse_tree_or_None, [ParseErrorInfo, ...])
        - parse_tree_or_None is a valid tree only if parsing eventually succeeds
        - errors contains up to max_errors items
    """
    parser = _get_parser(lammps_version)

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

    lines = sanitized_script.splitlines(True)
    errors = []

    for _ in range(max_errors):
        try:
            parse_tree = parser.parse("".join(lines))
            parse_tree = RemoveNewlines().transform(parse_tree)
            return parse_tree, errors
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

            if not (0 <= line_idx < len(lines)):
                break

            lines[line_idx] = "\n" if lines[line_idx].endswith("\n") else ""

            if len(errors) >= 2 and errors[-1].line == errors[-2].line and errors[-1].column == errors[-2].column:
                break

    return None, errors
