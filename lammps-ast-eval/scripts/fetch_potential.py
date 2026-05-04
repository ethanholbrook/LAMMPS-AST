#!/usr/bin/env python3
"""
Fetch a LAMMPS potential file with interactive user sign-off and provenance logging.

Accepts an OpenKIM model ID, an OpenKIM DOI, or a user-provided local file.
Always asks for explicit confirmation before downloading or copying.
Records full provenance (source, SHA256, timestamp) in the session log.

Usage:
    # From OpenKIM by model ID:
    python fetch_potential.py \
        --model-id EAM_Dynamo_FellingerParkWilkins_2010_Nb__MO_483655865867_005 \
        --dest-dir tests/nb_spall_impact_eval \
        --session-log tests/nb_spall_impact_eval/nb_spall_impact.session.jsonl

    # From OpenKIM by DOI:
    python fetch_potential.py \
        --doi https://doi.org/10.25950/befb2eea \
        --dest-dir tests/nb_spall_impact_eval \
        --session-log tests/nb_spall_impact_eval/nb_spall_impact.session.jsonl

    # User-provided local file:
    python fetch_potential.py \
        --file /path/to/Nb.eam.fs \
        --dest-dir tests/nb_spall_impact_eval \
        --session-log tests/nb_spall_impact_eval/nb_spall_impact.session.jsonl

    # Skip interactive prompt (e.g. when called from a script after prior sign-off):
    python fetch_potential.py --doi ... --dest-dir ... --session-log ... --yes

Exit codes:
    0  potential file ready, provenance logged
    1  error (network, file not found, user aborted)
"""

import sys
import json
import hashlib
import shutil
import tarfile
import tempfile
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError


OPENKIM_DOWNLOAD_URL = "https://openkim.org/download/{model_id}.txz"

# Files to skip during extraction (not potential parameter data)
SKIP_NAMES = {
    "CMakeLists.txt", "LICENSE", "LICENSE.CDDL", "README", "README.md",
    "README.txt", ".travis.yml",
}
SKIP_SUFFIXES = {".cmake", ".cpp", ".c", ".h", ".f", ".f90", ".py", ".sh"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_doi(doi: str) -> str:
    """Follow a DOI redirect and return the final URL."""
    if not doi.startswith("http"):
        doi = "https://doi.org/" + doi.lstrip("/")
    req = Request(doi, headers={"User-Agent": "lammps-ast-eval/1.0"})
    try:
        resp = urlopen(req, timeout=15)
        return resp.url
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"Could not resolve DOI {doi}: {e}")


def extract_model_id(url: str) -> str:
    """Pull the OpenKIM model ID out of a resolved URL."""
    segment = urlparse(url).path.rstrip("/").split("/")[-1]
    # OpenKIM model IDs always contain __MO_ or __MD_
    if "__MO_" not in segment and "__MD_" not in segment:
        raise RuntimeError(
            f"Could not identify an OpenKIM model ID in URL: {url}\n"
            f"  (extracted segment: '{segment}')\n"
            f"  Please supply --model-id directly."
        )
    return segment


def download_openkim(model_id: str, dest_dir: Path) -> List[Path]:
    """Download OpenKIM model tarball, extract parameter files, return saved paths."""
    url = OPENKIM_DOWNLOAD_URL.format(model_id=model_id)
    print(f"  Downloading {url} ...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = Path(tmpdir) / f"{model_id}.txz"

        req = Request(url, headers={"User-Agent": "lammps-ast-eval/1.0"})
        try:
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                received = 0
                with open(tarball, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        if total:
                            print(
                                f"\r  {received // 1024} / {total // 1024} KB"
                                f"  ({received * 100 // total}%)",
                                end="", flush=True,
                            )
            print()
        except (URLError, HTTPError) as e:
            raise RuntimeError(
                f"Download failed: {e}\n"
                f"  You can download the file manually from:\n"
                f"  https://openkim.org/id/{model_id}"
            )

        saved: List[Path] = []
        try:
            with tarfile.open(tarball, mode="r:*") as tf:
                for member in tf.getmembers():
                    name = Path(member.name).name
                    if not member.isfile():
                        continue
                    if name in SKIP_NAMES:
                        continue
                    if Path(name).suffix in SKIP_SUFFIXES:
                        continue
                    if name.startswith("."):
                        continue
                    fobj = tf.extractfile(member)
                    if fobj is None:
                        continue
                    dest_file = dest_dir / name
                    dest_file.write_bytes(fobj.read())
                    saved.append(dest_file)
                    print(f"  Extracted: {name}")
        except tarfile.TarError as e:
            raise RuntimeError(f"Could not read tarball: {e}")

    if not saved:
        raise RuntimeError(
            "No parameter files found in the downloaded archive.\n"
            f"  Please download manually from https://openkim.org/id/{model_id}"
        )
    return saved


def append_log(log_path: Path, entry: dict) -> None:
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a LAMMPS potential file with user sign-off and provenance logging."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--model-id", metavar="ID",
                     help="OpenKIM model ID (e.g. EAM_Dynamo_...)")
    src.add_argument("--doi", metavar="DOI",
                     help="OpenKIM DOI or URL (e.g. https://doi.org/10.25950/...)")
    src.add_argument("--file", metavar="PATH",
                     help="Path to a user-provided potential file")
    parser.add_argument("--dest-dir", required=True, metavar="DIR",
                        help="Directory to save the potential file (usually the eval folder)")
    parser.add_argument("--session-log", metavar="JSONL",
                        help="Session log to append the provenance entry to")
    parser.add_argument("--yes", action="store_true",
                        help="Skip interactive confirmation (use only after prior sign-off)")
    args = parser.parse_args()

    dest_dir = Path(args.dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # --- Resolve source ---
    source_type: str
    model_id: Optional[str] = None
    doi: Optional[str] = None
    original_path: Optional[Path] = None

    if args.model_id:
        source_type = "openkim"
        model_id = args.model_id

    elif args.doi:
        source_type = "openkim"
        doi = args.doi
        print(f"Resolving DOI: {doi}")
        try:
            final_url = resolve_doi(doi)
            model_id = extract_model_id(final_url)
            print(f"  → Model ID: {model_id}")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:  # --file
        source_type = "user_provided"
        original_path = Path(args.file).resolve()
        if not original_path.exists():
            print(f"Error: file not found: {original_path}", file=sys.stderr)
            sys.exit(1)

    # --- Print sign-off summary ---
    print()
    print("=" * 60)
    print("  POTENTIAL FILE — SIGN-OFF REQUIRED")
    print("=" * 60)
    if source_type == "openkim":
        download_url = OPENKIM_DOWNLOAD_URL.format(model_id=model_id)
        print(f"  Source   : OpenKIM")
        print(f"  Model ID : {model_id}")
        if doi:
            print(f"  DOI      : {doi}")
        print(f"  Download : {download_url}")
    else:
        print(f"  Source   : User-provided file")
        print(f"  File     : {original_path}")
    print(f"  Save to  : {dest_dir}/")
    print("=" * 60)
    print()

    if args.yes:
        print("  --yes flag set: proceeding without interactive prompt.")
    else:
        answer = input("  Proceed? [y/N]: ").strip().lower()
        if answer != "y":
            print("\nAborted — no files downloaded, no log entry written.")
            sys.exit(1)

    print()

    # --- Fetch / copy ---
    timestamp = datetime.now(timezone.utc).isoformat()
    fetched: List[Path] = []

    if source_type == "openkim":
        try:
            fetched = download_openkim(model_id, dest_dir)
        except RuntimeError as e:
            print(f"\nError: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        dest_file = dest_dir / original_path.name
        if dest_file.resolve() == original_path:
            print(f"  File already in destination — recording in-place: {original_path.name}")
        else:
            shutil.copy2(original_path, dest_file)
            print(f"  Copied: {original_path.name} → {dest_dir}/")
        fetched = [dest_file]

    # --- SHA256 ---
    print()
    file_records = []
    for f in fetched:
        digest = sha256_file(f)
        short = digest[:16] + "..."
        print(f"  {f.name}")
        print(f"    SHA256 : {digest}")
        file_records.append({"filename": f.name, "dest_path": str(f), "sha256": digest})

    # --- Build sign-off text ---
    files_str = ", ".join(r["filename"] for r in file_records)
    if source_type == "openkim":
        src_desc = f"OpenKIM model {model_id}"
        if doi:
            src_desc += f" (DOI: {doi})"
    else:
        src_desc = f"user-provided file at {original_path}"
    signoff_text = f"Use {files_str}, from {src_desc}"

    print()
    print(f"  Human sign-off: {signoff_text}")

    # --- Append to session log ---
    if args.session_log:
        log_path = Path(args.session_log)
        entry = {
            "timestamp": timestamp,
            "iteration": 0,
            "stage": "potential",
            "result": {
                "source": source_type,
                "model_id": model_id,
                "doi": doi,
                "original_path": str(original_path) if original_path else None,
                "files": file_records,
                "signoff_text": signoff_text,
                "download_timestamp": timestamp,
            },
        }
        append_log(log_path, entry)
        print(f"\n  Provenance logged to: {log_path}")

    print()
    if len(fetched) > 1:
        print("Note: multiple files extracted — update pair_coeff in your script")
        print("to reference the correct filename from the list above.")
    else:
        print(f"Ready. Use '{fetched[0].name}' in your pair_coeff line.")
    print()


if __name__ == "__main__":
    main()
