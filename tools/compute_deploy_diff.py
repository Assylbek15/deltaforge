#!/usr/bin/env python3
"""
tools/compute_deploy_diff.py

Compute the net deployment diff by chaining multiple CHANGED_FILES.jar archives.

Given a sequence of CHANGED_FILES.jar files ordered oldest-to-newest, collapses
them into a single net set: files to apply and paths to delete. This lets a
deploy pipeline bring an environment from any past release to any future release
by downloading only the small incremental JARs — never ALL_FILES.jar.

Merge rules applied in order (oldest release first):
  ADDED or MODIFIED  → net APPLY  (latest content wins)
  DELETED            → net DELETE (removed from apply set)
  Deleted then re-added → net APPLY (add wins, content from re-add)

Output:
  <output-dir>/          — files to apply, preserving original directory structure
  <output-manifest>      — JSON summary of net changes and chained releases

Usage:
    python tools/compute_deploy_diff.py \\
        --jars v1.1.0/CHANGED_FILES.jar v1.2.0/CHANGED_FILES.jar v1.3.0/CHANGED_FILES.jar \\
        --output-dir deploy/to_apply \\
        --output-manifest deploy/net_manifest.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def load_manifest(zf: zipfile.ZipFile, jar_path: Path) -> dict:
    try:
        return json.loads(zf.read("manifest.json"))
    except KeyError:
        print(
            f"[ERROR] {jar_path} is missing manifest.json.\n"
            f"        This JAR was built before manifest support was added.\n"
            f"        Re-run the release workflow for that tag to rebuild it.",
            file=sys.stderr,
        )
        sys.exit(1)


def merge(jar_paths: list[Path]) -> tuple[dict[str, bytes], set[str], list[dict]]:
    """
    Merge ordered CHANGED_FILES.jar archives into a net deployment set.

    Returns:
        files_to_apply  — {posix_path: file_bytes} of files to write
        paths_to_delete — set of posix paths to remove from target
        manifests       — list of per-release manifests, oldest first
    """
    files_to_apply: dict[str, bytes] = {}
    paths_to_delete: set[str] = set()
    manifests: list[dict] = []

    for jar_path in jar_paths:
        with zipfile.ZipFile(jar_path) as zf:
            manifest = load_manifest(zf, jar_path)
            manifests.append(manifest)

            changes = manifest.get("changes", {})

            for path in changes.get("added", []) + changes.get("modified", []):
                files_to_apply[path] = zf.read(path)
                paths_to_delete.discard(path)

            for path in changes.get("deleted", []):
                paths_to_delete.add(path)
                files_to_apply.pop(path, None)

    return files_to_apply, paths_to_delete, manifests


def write_output(
    files_to_apply: dict[str, bytes],
    paths_to_delete: set[str],
    manifests: list[dict],
    output_dir: Path,
    manifest_path: Path,
) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    for rel_path, content in sorted(files_to_apply.items()):
        out_file = output_dir / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(content)

    first = manifests[0] if manifests else {}
    last = manifests[-1] if manifests else {}

    net_manifest = {
        "from_release": first.get("previous_release", "unknown"),
        "to_release": last.get("release", "unknown"),
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "releases_chained": [m.get("release") for m in manifests],
        "net_changes": {
            "apply": sorted(files_to_apply),
            "delete": sorted(paths_to_delete),
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(net_manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute net deploy diff from chained CHANGED_FILES.jar archives."
    )
    parser.add_argument(
        "--jars",
        nargs="+",
        required=True,
        metavar="JAR",
        help="CHANGED_FILES.jar paths in chronological order (oldest first).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write the net files to apply.",
    )
    parser.add_argument(
        "--output-manifest",
        required=True,
        help="Path to write the net deployment manifest JSON.",
    )
    args = parser.parse_args()

    jar_paths = [Path(j) for j in args.jars]
    missing = [p for p in jar_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[ERROR] JAR not found: {p}", file=sys.stderr)
        sys.exit(1)

    print(f"Chaining {len(jar_paths)} CHANGED_FILES.jar(s):")
    for p in jar_paths:
        print(f"  {p}")

    files_to_apply, paths_to_delete, manifests = merge(jar_paths)

    write_output(
        files_to_apply,
        paths_to_delete,
        manifests,
        output_dir=Path(args.output_dir),
        manifest_path=Path(args.output_manifest),
    )

    print(f"\nNet result ({manifests[0].get('previous_release')} -> {manifests[-1].get('release')}):")
    for path in sorted(files_to_apply):
        print(f"  [apply]  {path}")
    for path in sorted(paths_to_delete):
        print(f"  [delete] {path}")
    print(f"\n  apply : {len(files_to_apply)} file(s)")
    print(f"  delete: {len(paths_to_delete)} file(s)")
    print(f"\nManifest written to {args.output_manifest}")


if __name__ == "__main__":
    main()
