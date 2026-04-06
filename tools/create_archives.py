"""
tools/create_archives.py

Creates JAR (ZIP) archives for release:

- dist/ALL_FILES.jar     — all files from artifacts/current/
- dist/CHANGED_FILES.jar — files from artifacts/changed/ (optional)

Structure is preserved relative to source root.

Requirements:
- artifacts/current must exist and contain files
- artifacts/changed may be missing or empty (creates empty JAR)

Usage:
    python tools/create_archives.py
"""

from __future__ import annotations

import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


CURRENT_DIR = Path("artifacts/current")
CHANGED_DIR = Path("artifacts/changed")
DIST_DIR = Path("dist")

ALL_FILES_JAR = DIST_DIR / "ALL_FILES.jar"
CHANGED_FILES_JAR = DIST_DIR / "CHANGED_FILES.jar"


@dataclass(frozen=True)
class ArchiveSpec:
    name: str
    source_dir: Path
    output_path: Path
    required: bool


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def collect_files(source_dir: Path) -> list[Path]:
    """
    Return all regular files under source_dir in deterministic order.
    """
    return sorted(path for path in source_dir.rglob("*") if path.is_file())


def ensure_dist_dir() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def remove_existing_output(path: Path) -> None:
    if path.exists():
        path.unlink()


def write_empty_archive(path: Path) -> None:
    """
    Create a valid empty ZIP/JAR archive.
    """
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED):
        pass


def build_archive(spec: ArchiveSpec) -> int:
    """
    Build a JAR archive from spec.source_dir into spec.output_path.

    Returns the number of files written to the archive.
    Exits with an error if a required source directory is missing or empty.
    """
    remove_existing_output(spec.output_path)

    if not spec.source_dir.exists():
        if spec.required:
            fail(f"{spec.source_dir}/ does not exist.")
        print(f"[WARN] {spec.source_dir}/ not found. Creating empty archive: {spec.output_path.name}")
        write_empty_archive(spec.output_path)
        return 0

    if not spec.source_dir.is_dir():
        fail(f"{spec.source_dir} exists but is not a directory.")

    files = collect_files(spec.source_dir)

    if not files:
        if spec.required:
            fail(f"{spec.source_dir}/ is empty.")
        print(f"[WARN] {spec.source_dir}/ is empty. Creating empty archive: {spec.output_path.name}")
        write_empty_archive(spec.output_path)
        return 0

    with zipfile.ZipFile(spec.output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive_name = file_path.relative_to(spec.source_dir)
            archive.write(file_path, arcname=archive_name)
            print(f"    packed: {archive_name}")

    return len(files)


def print_summary(archive_path: Path, file_count: int) -> None:
    size_kb = archive_path.stat().st_size / 1024
    print(f"  => {archive_path} ({file_count} file(s), {size_kb:.1f} KB)")


def main() -> None:
    ensure_dist_dir()

    archive_specs = [
        ArchiveSpec(
            name="ALL_FILES",
            source_dir=CURRENT_DIR,
            output_path=ALL_FILES_JAR,
            required=True,
        ),
        ArchiveSpec(
            name="CHANGED_FILES",
            source_dir=CHANGED_DIR,
            output_path=CHANGED_FILES_JAR,
            required=False,
        ),
    ]

    for spec in archive_specs:
        print(f"\nBuilding {spec.output_path.name} from {spec.source_dir}/")
        file_count = build_archive(spec)
        print_summary(spec.output_path, file_count)

    print("\nArchives ready:")
    for spec in archive_specs:
        print(f"  {spec.output_path}")


if __name__ == "__main__":
    main()