#!/usr/bin/env python3
"""
Generate a human-readable HTML (or PDF) evaluation report from a lammps-ast-eval session log.

Usage:
    python generate_report.py <session.jsonl> [--output report.html] [--pdf]

The session log is a JSONL file produced by passing --session-log to
sanitize_and_parse.py and run_lammps.py during an evaluation session.

Exit codes:
    0  report written successfully
    1  log file missing or empty
"""

import sys
import json
import argparse
import difflib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, sans-serif;
    font-size: 14px; line-height: 1.65; color: #1a1a1a; background: #fff;
    max-width: 1280px; margin: 0 auto; padding: 2rem 2rem 0;
}
.page-header { margin-bottom: 1.5rem; }
h1 { font-size: 1.45rem; font-weight: 700; margin-bottom: 0.2rem; }
h2 {
    font-size: 1rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: #6b7280;
    margin: 2rem 0 0.85rem;
    border-bottom: 1px solid #e5e7eb; padding-bottom: 0.3rem;
}
h3 { font-size: 0.95rem; font-weight: 600; color: #374151; margin-bottom: 0.5rem; }
h4 { font-size: 0.875rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; }
.meta { color: #6b7280; font-size: 0.8rem; margin-bottom: 0.5rem; }
.meta span { margin-right: 1.75rem; }
.outcome { font-size: 0.95rem; font-weight: 600; margin: 0.75rem 0 0; }
.badge {
    display: inline-block; padding: 0.15rem 0.55rem;
    border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    vertical-align: middle; white-space: nowrap;
}
.badge.pass  { background: #dcfce7; color: #166534; }
.badge.fail  { background: #fee2e2; color: #991b1b; }
.badge.warn  { background: #fef9c3; color: #854d0e; }
.badge.skip  { background: #f3f4f6; color: #6b7280; }
/* Three-column layout */
.columns {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 2rem;
    align-items: start;
}
.col-left { min-width: 0; }
.col-mid { min-width: 0; }
.col-right { min-width: 0; }
.script-panel {
    position: sticky;
    top: 1.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    overflow: hidden;
}
.script-panel-header {
    padding: 0.5rem 1rem;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: #6b7280;
}
.script-panel pre {
    margin: 0; border: none; border-radius: 0;
    max-height: calc(100vh - 8rem);
    overflow-y: auto;
    font-size: 0.75rem;
}
.review-panel {
    border: 1px solid #e5e7eb; border-radius: 0.5rem;
    margin-top: 1rem; overflow: hidden;
}
.review-panel-header {
    padding: 0.5rem 1rem;
    background: #fffbeb;
    border-bottom: 1px solid #fde68a;
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: #92400e;
}
.review-panel-body {
    padding: 0.75rem 1rem;
    font-size: 0.82rem; line-height: 1.6; color: #374151;
    white-space: pre-wrap; word-break: break-word;
}
.round {
    border: 1px solid #e5e7eb; border-radius: 0.5rem;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
}
.round-header {
    display: flex; align-items: center; gap: 0.65rem;
    margin-bottom: 0.85rem; flex-wrap: wrap;
}
.round-header h3 { margin: 0; flex-shrink: 0; }
.stage {
    margin-bottom: 0.75rem; padding: 0.6rem 0.85rem;
    border-left: 3px solid #e5e7eb; border-radius: 0 0.25rem 0.25rem 0;
    background: #fafafa;
}
.stage:last-child { margin-bottom: 0; }
.stage.pass { border-color: #86efac; background: #f0fdf4; }
.stage.fail { border-color: #fca5a5; background: #fff1f2; }
.stage.skip { border-color: #d1d5db; }
.stage p { margin-top: 0.35rem; font-size: 0.85rem; color: #374151; }
ul { margin: 0.4rem 0 0.2rem 1.1rem; }
li { margin-bottom: 0.25rem; font-size: 0.85rem; }
code {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    font-size: 0.82em; background: #f1f5f9;
    padding: 0.1em 0.4em; border-radius: 3px;
}
pre {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    font-size: 0.78rem; background: #f8fafc; color: #1e293b;
    border: 1px solid #e2e8f0; border-radius: 0.375rem;
    padding: 1rem 1.1rem; overflow-x: auto;
    white-space: pre-wrap; word-break: break-word;
    line-height: 1.5;
}
pre.log { font-size: 0.72rem; color: #64748b; margin-top: 0.5rem; }
.diff { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.75rem;
         border: 1px solid #e2e8f0; border-radius: 0.375rem; overflow-x: auto;
         margin-top: 0; line-height: 1.5; }
.changes {
    border: 1px solid #bfdbfe; border-radius: 0.5rem;
    padding: 0.75rem 1.25rem; margin-bottom: 1rem; background: #eff6ff;
}
.changes-header {
    display: flex; align-items: center; gap: 0.65rem; margin-bottom: 0.5rem;
}
.changes-header h3 { margin: 0; color: #1d4ed8; font-size: 0.875rem; }
.diff table { border-collapse: collapse; width: 100%; }
.diff td { padding: 0 0.6rem; white-space: pre; vertical-align: top; }
.diff td:first-child { color: #9ca3af; user-select: none; text-align: right;
                       border-right: 1px solid #e2e8f0; min-width: 2.5rem; padding-right: 0.4rem; }
.diff tr.add td { background: #f0fdf4; }
.diff tr.add td:last-child { color: #166534; }
.diff tr.rem td { background: #fff1f2; }
.diff tr.rem td:last-child { color: #991b1b; }
.diff tr.hdr td { background: #f1f5f9; color: #64748b; font-style: italic; }
blockquote {
    border-left: 3px solid #d1d5db; margin: 0.5rem 0;
    padding: 0.4rem 1rem; color: #374151;
    font-size: 0.875rem; background: #f9fafb;
    border-radius: 0 0.25rem 0.25rem 0;
}
footer {
    margin-top: 3rem; padding: 1rem 0;
    border-top: 1px solid #e5e7eb;
    font-size: 0.72rem; color: #9ca3af;
}
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
@media (max-width: 900px) {
    .columns { grid-template-columns: 1fr; }
    .script-panel { position: static; }
    .script-panel pre { max-height: 60vh; }
}
@media print {
    body { padding: 1rem; max-width: 100%; }
    .columns { grid-template-columns: 1fr 1fr 1fr; }
    .script-panel { position: static; }
    .round { break-inside: avoid; }
}
"""


def load_entries(log_path: Path) -> List[Dict[str, Any]]:
    entries = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def group_rounds(entries: List[Dict]) -> List[Dict]:
    rounds: Dict[int, Dict] = {}
    for e in entries:
        i = e["iteration"]
        if i not in rounds:
            rounds[i] = {"iteration": i, "parse": None, "execute": None, "timestamp": e["timestamp"]}
        rounds[i][e["stage"]] = e
    return [rounds[i] for i in sorted(rounds)]


def fmt_errors(errors: List[Dict]) -> str:
    if not errors:
        return ""
    items = []
    for e in errors:
        line = e.get("line", "?")
        col = e.get("column", "?")
        token = e.get("token", "")
        text = e.get("text", "")
        tok_html = f" &mdash; <code>{token}</code>" if token else ""
        items.append(f"<li>Line {line}, col {col}{tok_html}: {text}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def render_diff(before: str, after: str) -> str:
    """Render a unified diff between two normalized scripts as an HTML table."""
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    rows = []
    lnum_a = lnum_b = 0
    for group in difflib.SequenceMatcher(None, a, b).get_grouped_opcodes(3):
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in a[i1:i2]:
                    lnum_a += 1; lnum_b += 1
                    rows.append(f'<tr><td>{lnum_a}</td><td>{lnum_b}</td><td>{line.rstrip()}</td></tr>')
            if tag in ("replace", "delete"):
                for line in a[i1:i2]:
                    lnum_a += 1
                    rows.append(f'<tr class="rem"><td>{lnum_a}</td><td></td><td>− {line.rstrip()}</td></tr>')
            if tag in ("replace", "insert"):
                for line in b[j1:j2]:
                    lnum_b += 1
                    rows.append(f'<tr class="add"><td></td><td>{lnum_b}</td><td>+ {line.rstrip()}</td></tr>')
    if not rows:
        return ""
    return ('<div class="diff"><table><colgroup><col style="width:3rem"><col style="width:3rem"><col></colgroup>'
            + "".join(rows) + "</table></div>")


def render_changes(prev_script: str, current_script: str) -> str:
    diff_html = render_diff(prev_script, current_script)
    if not diff_html:
        return ""
    return "\n".join([
        '<div class="changes">',
        '<div class="changes-header"><h3>Changes</h3></div>',
        diff_html,
        '</div>',
    ])


def render_round(r: Dict) -> str:
    i = r["iteration"]
    p = r["parse"]
    ex = r["execute"]

    try:
        ts = datetime.fromisoformat(r["timestamp"]).strftime("%H:%M:%S")
    except Exception:
        ts = r["timestamp"]

    # Summary badges for the round header
    badges = []
    if p:
        parsed = p["result"].get("parsed", False)
        sanitized = p["result"].get("sanitized", True)
        if not sanitized:
            badges.append('<span class="badge fail">Normalize ✗</span>')
        else:
            badges.append(f'<span class="badge {"pass" if parsed else "fail"}">Parse {"✓" if parsed else "✗"}</span>')
    if ex:
        executed = ex["result"].get("executed", False)
        psz_ok = ex["result"].get("psz_executed", False)
        overall = executed or psz_ok
        badges.append(f'<span class="badge {"pass" if overall else "warn" if psz_ok else "fail"}">Execute {"✓" if executed else "PSZ ✓" if psz_ok else "✗"}</span>')

    parts = [
        '<div class="round">',
        '<div class="round-header">',
        f'<h3>Round {i}</h3>',
        *badges,
        f'<span style="font-size:0.75rem;color:#9ca3af;margin-left:auto">{ts}</span>',
        '</div>',
    ]

    # Parse / normalize stage
    if p:
        result = p["result"]
        sanitized = result.get("sanitized", True)
        parsed = result.get("parsed", False)

        if not sanitized:
            cls = "fail"
            parts.append(f'<div class="stage {cls}">')
            parts.append(f'<h4>Normalization <span class="badge fail">✗ Failed</span></h4>')
            err = result.get("sanitize_error", "")
            parts.append(f'<p>{err}</p>')
            parts.append('</div>')
        else:
            cls = "pass" if parsed else "fail"
            parts.append(f'<div class="stage {cls}">')
            parts.append(f'<h4>Normalization &amp; Parse <span class="badge {cls}">{"✓ Passed" if parsed else "✗ Failed"}</span></h4>')
            if not parsed:
                errors = result.get("errors", [])
                parts.append(f'<p>{len(errors)} error(s) found:</p>')
                parts.append(fmt_errors(errors))
            else:
                parts.append('<p>Script parsed successfully.</p>')
            parts.append('</div>')

    # Execute stage
    if ex:
        result = ex["result"]
        executed = result.get("executed", False)
        psz_applied = result.get("psz_applied", False)
        psz_executed = result.get("psz_executed")
        overall = executed or (psz_applied and psz_executed)

        if executed:
            cls = "pass"
        elif psz_applied and psz_executed:
            cls = "warn"
        else:
            cls = "fail"

        parts.append(f'<div class="stage {cls}">')
        if executed:
            parts.append('<h4>Execution <span class="badge pass">✓ Passed</span></h4>')
            parts.append('<p>Script ran successfully (10-step run).</p>')
        elif psz_applied and psz_executed:
            parts.append('<h4>Execution <span class="badge warn">PSZ ✓ — pair_style isolated</span></h4>')
            parts.append('<p>Direct execution failed; PSZ substitution succeeded — <strong>pair_style/pair_coeff</strong> is the isolated source of error.</p>')
            log = result.get("log_tail", "")
            if log:
                parts.append(f'<pre class="log">{log}</pre>')
        else:
            parts.append('<h4>Execution <span class="badge fail">✗ Failed</span></h4>')
            log = result.get("psz_log_tail") or result.get("log_tail", "")
            if log:
                parts.append(f'<p>LAMMPS error output:</p><pre class="log">{log}</pre>')
            else:
                parts.append('<p>Execution failed with no output captured.</p>')
        parts.append('</div>')
    elif p and p["result"].get("parsed"):
        parts.append('<div class="stage skip"><h4>Execution <span class="badge skip">Not attempted</span></h4></div>')

    parts.append('</div>')
    return "\n".join(parts)


def build_html(entries: List[Dict], log_path: Path) -> str:
    prompt_entry = next((e for e in entries if e.get("stage") == "prompt"), None)
    review_entry = next((e for e in reversed(entries) if e.get("stage") == "review"), None)
    eval_entries = [e for e in entries if e.get("stage") not in ("prompt", "review")]
    rounds = group_rounds(eval_entries)

    # Script name
    script_name = "unknown"
    for e in entries:
        s = e.get("result", {}).get("script")
        if s:
            script_name = Path(s).name
            break

    # Date
    try:
        date_str = datetime.fromisoformat(entries[0]["timestamp"]).strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_str = ""

    # Prompt section
    prompt_html = ""
    if prompt_entry:
        text = prompt_entry["result"].get("text", "").replace("\n", "<br>")
        prompt_html = f"\n<h2>Method Description</h2>\n<blockquote>{text}</blockquote>"

    # Final outcome
    last = rounds[-1] if rounds else {}
    final_exec = last.get("execute", {}) or {}
    final_parse = last.get("parse", {}) or {}
    fe_result = final_exec.get("result", {}) if final_exec else {}
    fp_result = final_parse.get("result", {}) if final_parse else {}

    if fe_result:
        passed = fe_result.get("executed") or (fe_result.get("psz_applied") and fe_result.get("psz_executed"))
    else:
        passed = fp_result.get("parsed", False)

    outcome_badge = f'<span class="badge {"pass" if passed else "fail"}">{"✓ Passed" if passed else "✗ Failed"}</span>'

    # Final normalized script
    final_script = fp_result.get("sanitized_script", "")

    round_htmls = []
    prev_script: Optional[str] = None
    for r in rounds:
        current_script = r["parse"]["result"].get("sanitized_script", "") if r.get("parse") else ""
        if prev_script is not None and current_script and current_script != prev_script:
            changes_html = render_changes(prev_script, current_script)
            if changes_html:
                round_htmls.append(changes_html)
        round_htmls.append(render_round(r))
        if current_script:
            prev_script = current_script
    rounds_html = "\n".join(round_htmls) if round_htmls else ""

    script_panel_html = ""
    if final_script:
        script_panel_html = f"""<div class="script-panel">
  <div class="script-panel-header">Final Script (Normalized)</div>
  <pre>{final_script.strip()}</pre>
</div>"""
    else:
        script_panel_html = '<div class="script-panel"><div class="script-panel-header">Final Script</div><pre style="color:#9ca3af;font-style:italic">No normalized script available.</pre></div>'

    review_panel_html = ""
    if review_entry:
        review_text = review_entry["result"].get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        review_panel_html = f"""<div class="review-panel">
  <div class="review-panel-header">Domain Review</div>
  <div class="review-panel-body">{review_text}</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LAMMPS Eval Report — {script_name}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page-header">
  <h1>LAMMPS Script Evaluation Report</h1>
  <div class="meta">
    <span><strong>Script:</strong> {script_name}</span>
    <span><strong>Date:</strong> {date_str}</span>
    <span><strong>Repair rounds:</strong> {len(rounds)}</span>
  </div>
  <p class="outcome">Final outcome: {outcome_badge}</p>
  {prompt_html}
</div>
<div class="columns">
  <div class="col-left">
    <h2>Evaluation History</h2>
    {rounds_html}
  </div>
  <div class="col-mid">
    {script_panel_html}
  </div>
  <div class="col-right">
    {review_panel_html}
  </div>
</div>
<footer>
  Generated by <strong>lammps-ast-eval</strong> &middot;
  <a href="https://arxiv.org/abs/2603.20630">Holbrook, Verduzco &amp; Strachan, arXiv:2603.20630</a>
</footer>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate an HTML (or PDF) report from a lammps-ast-eval session log."
    )
    parser.add_argument("log", type=Path, help="Session log file (.jsonl)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output file (default: <log_stem>_report.html or .pdf)")
    parser.add_argument("--pdf", action="store_true",
                        help="Produce a PDF via weasyprint (falls back to HTML if not installed)")
    args = parser.parse_args()

    if not args.log.exists():
        print(f"Error: log file not found: {args.log}", file=sys.stderr)
        sys.exit(1)

    entries = load_entries(args.log)
    if not entries:
        print("Error: session log is empty.", file=sys.stderr)
        sys.exit(1)

    html = build_html(entries, args.log)

    suffix = ".pdf" if args.pdf else ".html"
    output = args.output or args.log.with_name(args.log.stem + "_report").with_suffix(suffix)

    if args.pdf:
        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(str(output))
            print(f"PDF report written to {output}")
        except ImportError:
            html_out = output.with_suffix(".html")
            html_out.write_text(html)
            print(f"weasyprint not installed — HTML report saved to {html_out}")
            print("Install weasyprint with: pip install weasyprint")
            print("Or open the HTML file in a browser and use File → Print → Save as PDF.")
    else:
        output.write_text(html)
        print(f"Report written to {output}")


if __name__ == "__main__":
    main()
