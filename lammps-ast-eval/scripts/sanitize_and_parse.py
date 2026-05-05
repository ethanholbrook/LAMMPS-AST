#!/usr/bin/env python3
"""
Normalize and parse a LAMMPS input script, reporting errors as structured JSON.

Usage:
    python sanitize_and_parse.py <script.in> [--output-dir DIR]

Exit codes:
    0  parse succeeded
    1  parse failed (errors in JSON output)
    2  dependency missing
"""

import sys
import json
import argparse
import io
import datetime
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional


def append_to_log(log_path: Path, stage: str, result: dict):
    entries = []
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    iteration = sum(1 for e in entries if e.get("stage") == "parse") + 1
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "iteration": iteration,
        "stage": stage,
        "result": result,
    }
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def ensure_dependency():
    try:
        import lammps_ast  # noqa: F401
        return
    except ImportError:
        pass

    import subprocess

    # Try standard install first, then --user fallback (common on HPC)
    for extra in ([], ["--user"]):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *extra, "lammps-ast"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return

    print(json.dumps({
        "error": "lammps-ast not found and installation failed.",
        "hint": (
            "On HPC clusters, activate your conda environment or virtualenv first "
            "(e.g. 'conda activate <env>'), then re-run. "
            "Installation must be done on a login node with internet access, "
            "not on a compute node."
        ),
        "details": result.stderr.strip()
    }))
    sys.exit(2)


def run(script_path: Path, output_dir: Optional[Path], session_log: Optional[Path], lammps_version: Optional[str] = None):
    from lammps_ast.sanitizer import sanitize
    from lammps_ast.parser import parse_to_AST
    try:
        from lammps_ast import find_unresolved_variables as _find_unresolved, list_grammar_versions as _list_versions
    except ImportError:
        _find_unresolved = None
        _list_versions = None

    # Resolve None → actual version string so logs record what was used
    if lammps_version is None and _list_versions is not None:
        versions = _list_versions()
        if versions:
            lammps_version = versions[-1]

    raw = script_path.read_text()

    sanitized_text = None
    sanitize_error = None
    try:
        sanitized_text = sanitize(raw)
    except Exception as e:
        sanitize_error = str(e)

    if sanitize_error:
        result = {
            "script": str(script_path),
            "sanitized": False,
            "parsed": False,
            "sanitize_error": sanitize_error,
            "errors": []
        }
        if session_log:
            append_to_log(session_log, "parse", result)
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # lint=True is available in newer versions of lammps-ast; fall back gracefully.
    # The older PyPI version always prints to stdout on failure, so we suppress it.
    try:
        tree, errors = parse_to_AST(sanitized_text, lint=True, lammps_version=lammps_version)
        if errors and not isinstance(errors, list):
            errors = [errors]
    except TypeError:
        with redirect_stdout(io.StringIO()):
            tree, err = parse_to_AST(sanitized_text)
        errors = [err] if err is not None else []

    parsed = tree is not None and not errors

    # sanitize() does not always raise on unresolved variables — it may leave them
    # in the output and let the parser fail. Check explicitly so the caller gets a
    # clear error instead of an opaque parse error pointing at the wrong fix.
    unresolved = []
    if not parsed and _find_unresolved is not None and sanitized_text:
        unresolved = list(_find_unresolved(sanitized_text) or [])

    error_list = []
    for e in errors:
        if e is None:
            continue
        error_list.append({
            "line": getattr(e, "line", None),
            "column": getattr(e, "column", None),
            "token": str(getattr(e, "token", "")),
            "text": getattr(e, "text", (e.args[0] if e.args else "") if hasattr(e, "args") else "")
        })

    if output_dir and sanitized_text:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / script_path.name
        out_path.write_text(sanitized_text)

    result = {
        "script": str(script_path),
        "sanitized": len(unresolved) == 0,
        "parsed": parsed,
        "errors": error_list,
        "sanitized_script": sanitized_text,
        "lammps_version": lammps_version,
    }
    if unresolved:
        result["unresolved_variables"] = unresolved
    if session_log:
        append_to_log(session_log, "parse", result)
    print(json.dumps(result, indent=2))
    sys.exit(0 if parsed else 1)


def log_prompt(session_log: Path, prompt_text: str):
    """Write the user's method description as the first entry in the session log."""
    existing = []
    if session_log.exists():
        for line in session_log.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if any(e.get("stage") == "prompt" for e in existing):
        return  # already recorded
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "iteration": 0,
        "stage": "prompt",
        "result": {"text": prompt_text.strip()},
    }
    with session_log.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path, help="Path to LAMMPS input script")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory to write normalized script (optional)")
    parser.add_argument("--session-log", type=Path, default=None,
                        help="JSONL file to append this result to (for report generation)")
    parser.add_argument("--prompt-file", type=Path, default=None,
                        help="Text file containing the method description / user prompt")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Method description / user prompt (inline string)")
    parser.add_argument("--lammps-version", type=str, default=None,
                        help="LAMMPS grammar version to use (e.g. '20240829'). Defaults to latest available.")
    args = parser.parse_args()

    if not args.script.exists():
        print(json.dumps({"error": f"File not found: {args.script}"}))
        sys.exit(2)

    if args.session_log:
        prompt_text = None
        if args.prompt_file:
            if not args.prompt_file.exists():
                print(json.dumps({"error": f"Prompt file not found: {args.prompt_file}"}))
                sys.exit(2)
            prompt_text = args.prompt_file.read_text()
        elif args.prompt:
            prompt_text = args.prompt
        if prompt_text:
            log_prompt(args.session_log, prompt_text)

    ensure_dependency()
    run(args.script, args.output_dir, args.session_log, lammps_version=args.lammps_version)


if __name__ == "__main__":
    main()
