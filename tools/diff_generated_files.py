#!/usr/bin/env python3
"""
tools/diff_generated_files.py

Compare artifacts/current/ against artifacts/previous/ and copy only
changed files into artifacts/changed/.

Comparison is based exclusively on SHA-256 content hashes.
File timestamps are intentionally ignored.

Classification:
- ADDED: present in current, absent in previous
- MODIFIED: present in both, but content differs
- UNCHANGED: present in both, and content is identical
- DELETED: present in previous, absent in current

Behavior:
- If artifacts/previous/ is missing or empty, all current files are treated
  as ADDED (first-release behavior).
- artifacts/changed/ is reset on every run.
- ADDED and MODIFIED files are copied into artifacts/changed/.
- DELETED paths are recorded in manifest.json but not materialized as files.
- manifest.json is always written to artifacts/changed/ so downstream tools
  (compute_deploy_diff.py) can chain releases without downloading ALL_FILES.jar.

Exit codes:
- 0: success
- 1: unrecoverable error (for example, artifacts/current/ missing or empty)

Usage:
    VERSION=v1.1.0 PREVIOUS_VERSION=v1.0.0 python tools/diff_generated_files.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path


CURRENT_DIR = Path("artifacts/current")
PREVIOUS_DIR = Path("artifacts/previous")
CHANGED_DIR = Path("artifacts/changed")

HASH_BUFFER_SIZE = 64 * 1024  # 64 KB


class FileStatus(Enum):
    ADDED = auto()
    MODIFIED = auto()
    UNCHANGED = auto()
    DELETED = auto()


@dataclass(frozen=True)
class FileDiff:
    relative_path: Path
    status: FileStatus


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def ensure_directory_if_present(path: Path) -> None:
    if path.exists() and not path.is_dir():
        fail(f"{path} exists but is not a directory.")


def has_any_files(directory: Path) -> bool:
    return any(path.is_file() for path in directory.rglob("*"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        while chunk := file_obj.read(HASH_BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def index_directory(directory: Path) -> dict[Path, str]:
    if not directory.exists():
        return {}

    ensure_directory_if_present(directory)

    return {
        file_path.relative_to(directory): sha256(file_path)
        for file_path in sorted(path for path in directory.rglob("*") if path.is_file())
    }


def compute_diff(
    current_index: dict[Path, str],
    previous_index: dict[Path, str],
) -> list[FileDiff]:
    diffs: list[FileDiff] = []

    current_paths = set(current_index)
    previous_paths = set(previous_index)

    for relative_path in sorted(current_paths | previous_paths):
        in_current = relative_path in current_paths
        in_previous = relative_path in previous_paths

        if in_current and not in_previous:
            status = FileStatus.ADDED
        elif in_previous and not in_current:
            status = FileStatus.DELETED
        elif current_index[relative_path] != previous_index[relative_path]:
            status = FileStatus.MODIFIED
        else:
            status = FileStatus.UNCHANGED

        diffs.append(FileDiff(relative_path=relative_path, status=status))

    return diffs


def reset_changed_dir() -> None:
    if CHANGED_DIR.exists():
        shutil.rmtree(CHANGED_DIR)
    CHANGED_DIR.mkdir(parents=True, exist_ok=True)


def materialize_changed_files(diffs: list[FileDiff]) -> None:
    for diff in diffs:
        if diff.status not in {FileStatus.ADDED, FileStatus.MODIFIED}:
            continue

        source_path = CURRENT_DIR / diff.relative_path
        destination_path = CHANGED_DIR / diff.relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def posix_path(p: Path) -> str:
    return p.as_posix()


def write_manifest(diffs: list[FileDiff], release: str, previous_release: str) -> None:
    """
    Write manifest.json into artifacts/changed/ recording every change category.

    Deletions are stored here even though no file is materialized — this is
    what compute_deploy_diff.py reads to chain releases without ALL_FILES.jar.
    """
    by_status: dict[FileStatus, list[str]] = {s: [] for s in FileStatus}
    for diff in diffs:
        by_status[diff.status].append(posix_path(diff.relative_path))

    manifest = {
        "release": release,
        "previous_release": previous_release,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "changes": {
            "added": sorted(by_status[FileStatus.ADDED]),
            "modified": sorted(by_status[FileStatus.MODIFIED]),
            "deleted": sorted(by_status[FileStatus.DELETED]),
        },
    }

    manifest_path = CHANGED_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  manifest written to {manifest_path}")


_STATUS_LABELS: dict[FileStatus, str] = {
    FileStatus.ADDED: "ADDED    ",
    FileStatus.MODIFIED: "MODIFIED ",
    FileStatus.UNCHANGED: "UNCHANGED",
    FileStatus.DELETED: "DELETED  ",
}


def print_summary(diffs: list[FileDiff], first_release: bool) -> None:
    counts = {status: 0 for status in FileStatus}
    for diff in diffs:
        counts[diff.status] += 1

    print("\nDiff summary:")
    if first_release:
        print("  [NOTE] No previous release found — treating all files as changed.")

    for diff in diffs:
        print(f"  {_STATUS_LABELS[diff.status]}  {diff.relative_path}")

    changed_count = counts[FileStatus.ADDED] + counts[FileStatus.MODIFIED]

    print(
        f"\n"
        f"  total     : {len(diffs)}\n"
        f"  added     : {counts[FileStatus.ADDED]}\n"
        f"  modified  : {counts[FileStatus.MODIFIED]}\n"
        f"  deleted   : {counts[FileStatus.DELETED]}\n"
        f"  unchanged : {counts[FileStatus.UNCHANGED]}\n"
        f"  materialized: {changed_count}"
    )

    if changed_count == 0 and not first_release:
        print("\n  [NOTE] Nothing changed — CHANGED_FILES.jar will be empty.")


def main() -> None:
    ensure_directory_if_present(CURRENT_DIR)
    ensure_directory_if_present(PREVIOUS_DIR)
    ensure_directory_if_present(CHANGED_DIR)

    if not CURRENT_DIR.exists() or not has_any_files(CURRENT_DIR):
        fail(f"{CURRENT_DIR}/ is missing or contains no files. Run fetch_deps.py first.")

    release = os.environ.get("VERSION", "unknown")
    previous_release = os.environ.get("PREVIOUS_VERSION", "unknown")

    print(f"Indexing {CURRENT_DIR}/...")
    current_index = index_directory(CURRENT_DIR)

    print(f"Indexing {PREVIOUS_DIR}/...")
    previous_index = index_directory(PREVIOUS_DIR)

    first_release = len(previous_index) == 0

    if first_release:
        diffs = [
            FileDiff(relative_path=relative_path, status=FileStatus.ADDED)
            for relative_path in sorted(current_index)
        ]
    else:
        diffs = compute_diff(current_index=current_index, previous_index=previous_index)

    reset_changed_dir()
    materialize_changed_files(diffs)
    write_manifest(diffs, release=release, previous_release=previous_release)
    print_summary(diffs, first_release)

    print(f"\nChanged files written to {CHANGED_DIR}/")


if __name__ == "__main__":
    main()
