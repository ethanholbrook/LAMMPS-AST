#!/usr/bin/env python3
"""
Execute a normalized LAMMPS input script with a shortened run (10 steps).
If execution fails, automatically retries with pair_style zero (PSZ) substitution.

LAMMPS is always run from the script's own directory so that relative paths to
potential files, geometry files, and other dependencies resolve correctly.

Usage:
    python run_lammps.py <script.in> --lammps-exe /path/to/lammps [--output-dir DIR]

Exit codes:
    0  execution succeeded (original or PSZ)
    1  execution failed even after PSZ substitution
    2  bad arguments or missing files
"""

import sys
import json
import argparse
import datetime
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple


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
    parse_count = sum(1 for e in entries if e.get("stage") == "parse")
    iteration = parse_count if parse_count else 1
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "iteration": iteration,
        "stage": stage,
        "result": result,
    }
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


RUN_STEPS = 10


def shorten_run_lines(text: str) -> str:
    lines = text.splitlines(keepends=True)
    modified = []
    for line in lines:
        if re.match(r"^run\b", line.strip()):
            words = line.split()
            if len(words) > 1:
                words[1] = str(RUN_STEPS)
                line = " ".join(words) + "\n"
        modified.append(line)
    return "".join(modified)


def apply_psz(text: str) -> str:
    """Replace pair_style/pair_coeff with pair_style zero 10.0 / pair_coeff * *."""
    lines = text.splitlines(keepends=True)
    out = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"pair_style\s+", stripped):
            out.append("\n")  # blank out the original pair_style line
        elif re.match(r"pair_coeff\s+", stripped):
            if not inserted:
                out.append("pair_style zero 10.0\n")
                out.append("pair_coeff * *\n")
                out.append("mass 1 27\n")
                inserted = True
            # drop any additional pair_coeff lines
        else:
            out.append(line)
    return "".join(out)


def run_lammps(script_text: str, lammps_exe: Path, work_dir: Path) -> Tuple[bool, str]:
    # Write temp input file into the script's directory so relative paths resolve
    tmp_name = f"._lammps_eval_{uuid.uuid4().hex[:8]}.in"
    tmp_input = work_dir / tmp_name
    tmp_input.write_text(script_text)

    try:
        result = subprocess.run(
            [str(lammps_exe), "-in", tmp_name],
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=120
        )
        success = result.returncode == 0
        log_output = (result.stdout + result.stderr).strip()
        last_lines = "\n".join(log_output.splitlines()[-10:]) if log_output else ""
        return success, last_lines
    except subprocess.TimeoutExpired:
        return False, "LAMMPS execution timed out after 120 seconds."
    except Exception as e:
        return False, str(e)
    finally:
        tmp_input.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path, help="Path to normalized LAMMPS input script")
    parser.add_argument("--lammps-exe", type=Path, default=None,
                        help="Path to LAMMPS executable (overrides LAMMPS_EXE env var)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory to write modified scripts (optional)")
    parser.add_argument("--session-log", type=Path, default=None,
                        help="JSONL file to append this result to (for report generation)")
    args = parser.parse_args()

    # Resolve executable: flag > env var > error
    lammps_exe = args.lammps_exe
    if lammps_exe is None:
        env_exe = os.environ.get("LAMMPS_EXE")
        if env_exe:
            lammps_exe = Path(env_exe)
        else:
            print(json.dumps({
                "error": "No LAMMPS executable provided.",
                "hint": "Pass --lammps-exe /path/to/lmp or set the LAMMPS_EXE environment variable."
            }))
            sys.exit(2)

    if not args.script.exists():
        print(json.dumps({"error": f"File not found: {args.script}"}))
        sys.exit(2)
    if not lammps_exe.exists():
        print(json.dumps({"error": f"LAMMPS executable not found: {lammps_exe}"}))
        sys.exit(2)

    script_text = args.script.read_text()
    work_dir = args.script.resolve().parent
    shortened = shorten_run_lines(script_text)

    success, log_tail = run_lammps(shortened, lammps_exe, work_dir)

    psz_applied = False
    psz_success = None
    psz_log_tail = None

    if not success:
        psz_text = apply_psz(shortened)
        psz_applied = True
        psz_success, psz_log_tail = run_lammps(psz_text, lammps_exe, work_dir)

        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / f"{args.script.stem}_psz.in").write_text(psz_text)

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / f"{args.script.stem}_short.in").write_text(shortened)

    result = {
        "script": str(args.script),
        "executed": success,
        "log_tail": log_tail,
        "psz_applied": psz_applied,
        "psz_executed": psz_success,
        "psz_log_tail": psz_log_tail
    }
    if args.session_log:
        append_to_log(args.session_log, "execute", result)
    print(json.dumps(result, indent=2))
    overall_success = success or (psz_applied and psz_success)
    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
