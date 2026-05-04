#!/usr/bin/env python3
"""
Append a domain review entry to a lammps-ast-eval session log.

Usage:
    python log_review.py <session.jsonl> --text "Review text..."
    python log_review.py <session.jsonl> --file review.txt
    echo "Review text" | python log_review.py <session.jsonl>

Exit codes:
    0  review logged successfully
    1  log file path missing or review text empty
"""

import sys
import json
import argparse
import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Append a domain review entry to a lammps-ast-eval session log."
    )
    parser.add_argument("log", type=Path, help="Session log file (.jsonl)")
    parser.add_argument("--text", type=str, default=None,
                        help="Review text (inline string)")
    parser.add_argument("--file", type=Path, default=None,
                        help="File containing the review text")
    args = parser.parse_args()

    if args.text:
        text = args.text
    elif args.file:
        if not args.file.exists():
            print(f"Error: review file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        text = args.file.read_text()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("Error: provide review text via --text, --file, or stdin.", file=sys.stderr)
        sys.exit(1)

    text = text.strip()
    if not text:
        print("Error: review text is empty.", file=sys.stderr)
        sys.exit(1)

    entries = []
    if args.log.exists():
        for line in args.log.read_text().splitlines():
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
        "stage": "review",
        "result": {"text": text},
    }
    with args.log.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Review logged to {args.log}")


if __name__ == "__main__":
    main()
