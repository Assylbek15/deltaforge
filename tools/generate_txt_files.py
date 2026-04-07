#!/usr/bin/env python3
"""
Generate deterministic .txt files for release artifact testing.

Writes a controlled set of files into artifacts/current/ to simulate
release-to-release differences, including:
- UNCHANGED (same content)
- MODIFIED (content changed)
- ADDED (new files)
- DELETED (missing files)

The generator intentionally models several release versions so diff logic
can be validated across multiple transitions, not just a single baseline
comparison.

Version plan:
- v0.1.0: baseline
- v0.2.0: adds features/new_module.txt
- v0.3.0: modifies features/new_module.txt
- v0.4.0: removes legacy/old_format.txt
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


OUTPUT_DIR = Path("artifacts/current")
SUPPORTED_VERSIONS = {"v0.1.0", "v0.2.0", "v0.3.0", "v0.4.0"}


def get_version() -> str:
    version = os.environ.get("VERSION", "").strip()
    if not version:
        print("ERROR: VERSION environment variable is required.", file=sys.stderr)
        print("Usage: VERSION=v0.1.0 python tools/generate_txt_files.py", file=sys.stderr)
        sys.exit(1)
    return version


def reset_output_dir() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def write_file(relative_path: str, content: str) -> None:
    target_path = OUTPUT_DIR / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [+] {relative_path}")


def ensure_output_not_empty() -> None:
    generated_files = list(OUTPUT_DIR.rglob("*.txt"))
    if not generated_files:
        print("ERROR: generator produced zero .txt files.", file=sys.stderr)
        sys.exit(1)


def version_at_least(current: str, minimum: str) -> bool:
    ordered_versions = ["v0.1.0", "v0.2.0", "v0.3.0", "v0.4.0"]
    return ordered_versions.index(current) >= ordered_versions.index(minimum)


def write_unchanged_files() -> None:
    """
    Files with static content across all releases.
    These should only appear in CHANGED_FILES.jar on the very first release.
    """
    write_file(
        "config/constants.txt",
        "\n".join(
            [
                "MAX_RETRIES=3",
                "TIMEOUT_SECONDS=30",
                "ENCODING=utf-8",
                "LOG_LEVEL=INFO",
                "",
            ]
        ),
    )

    write_file(
        "schema/field_types.txt",
        "\n".join(
            [
                "id:uuid",
                "name:string",
                "value:integer",
                "active:boolean",
                "created_at:timestamp",
                "",
            ]
        ),
    )


def write_modified_files(version: str) -> None:
    """
    Files whose content changes as VERSION changes.
    These simulate normal modified files between releases.
    """
    write_file(
        "manifest.txt",
        "\n".join(
            [
                f"version={version}",
                "generator=tools/generate_txt_files.py",
                "artifact_type=full",
                "",
            ]
        ),
    )

    write_file(
        "config/settings.txt",
        "\n".join(
            [
                "env=production",
                f"version={version}",
                "debug=false",
                "feature_flag_release_assets=true",
                "",
            ]
        ),
    )

    write_file(
        "reports/summary.txt",
        "\n".join(
            [
                "Release Summary",
                "---------------",
                f"version: {version}",
                "status: generated",
                "scope: release-artifacts",
                "",
            ]
        ),
    )


def write_legacy_file(version: str) -> None:
    """
    File present through v0.3.0 and removed in v0.4.0.
    This creates a deletion scenario for the v0.3.0 -> v0.4.0 transition.
    """
    if version == "v0.4.0":
        return

    write_file(
        "legacy/old_format.txt",
        "\n".join(
            [
                "format=v1",
                "deprecated=true",
                "removal_target=v0.4.0",
                "",
            ]
        ),
    )


def write_new_module_file(version: str) -> None:
    """
    File introduced in v0.2.0 and modified again in v0.3.0+.
    This creates both add and modify scenarios across releases.
    """
    if not version_at_least(version, "v0.2.0"):
        return

    if version == "v0.2.0":
        content = "\n".join(
            [
                "module=new_module",
                "status=active",
                "revision=1",
                "introduced_in=v0.2.0",
                "",
            ]
        )
    else:
        content = "\n".join(
            [
                "module=new_module",
                "status=active",
                "revision=2",
                "introduced_in=v0.2.0",
                f"updated_in={version}",
                "",
            ]
        )

    write_file("features/new_module.txt", content)


def main() -> None:
    version = get_version()

    print(f"Generating files for version: {version}")
    print(f"Output directory: {OUTPUT_DIR}")

    reset_output_dir()

    write_unchanged_files()
    write_modified_files(version)
    write_legacy_file(version)
    write_new_module_file(version)

    ensure_output_not_empty()

    total_files = sum(1 for _ in OUTPUT_DIR.rglob("*.txt"))
    print(f"\nDone. {total_files} file(s) written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
