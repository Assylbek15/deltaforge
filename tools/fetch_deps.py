#!/usr/bin/env python3
"""
Fetch each dependency at its pinned version and run its generator.

Resolution order per dependency:
  1. local_path (if set and exists) — used in local development
  2. GitHub clone at pinned tag     — used in CI

Output lands in artifacts/current/<dep-name>/.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEPS_FILE = REPO_ROOT / "deps.json"
ARTIFACTS_CURRENT = REPO_ROOT / "artifacts" / "current"
DEPS_CACHE = REPO_ROOT / ".deps"


def clone(repo: str, tag: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        [
            "git", "clone",
            "--branch", tag,
            "--depth", "1",
            f"https://github.com/{repo}.git",
            str(dest),
        ],
        check=True,
    )


def resolve_dep_dir(dep: dict) -> Path:
    local_path = dep.get("local_path")
    if local_path:
        candidate = (REPO_ROOT / local_path).resolve()
        if candidate.exists():
            print(f"  using local path: {local_path}")
            return candidate

    DEPS_CACHE.mkdir(exist_ok=True)
    dest = DEPS_CACHE / dep["name"]
    print(f"  cloning {dep['repo']}@{dep['tag']}")
    clone(dep["repo"], dep["tag"], dest)
    return dest


def get_commit_hash(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_generator(
    dep_dir: Path,
    output_dir: Path,
    dep_tag: str,
    source_commit: str,
    release_version: str,
) -> None:
    # Metadata is passed via env vars so older generators that predate
    # traceability can still run without argument errors.
    subprocess.run(
        [
            sys.executable,
            str(dep_dir / "generate.py"),
            "--output-dir", str(output_dir),
            "--version", dep_tag,
        ],
        check=True,
        env={
            **os.environ,
            "VERSION": dep_tag,
            "PYTHONIOENCODING": "utf-8",
            "SOURCE_COMMIT": source_commit,
            "RELEASE_VERSION": release_version,
        },
    )


def main() -> None:
    release_version = os.environ.get("VERSION", "unknown")
    deps = json.loads(DEPS_FILE.read_text(encoding="utf-8"))["dependencies"]

    if ARTIFACTS_CURRENT.exists():
        shutil.rmtree(ARTIFACTS_CURRENT)
    ARTIFACTS_CURRENT.mkdir(parents=True)

    for dep in deps:
        name, tag = dep["name"], dep["tag"]
        print(f"\n[{name}] version={tag}")

        dep_dir = resolve_dep_dir(dep)
        commit_hash = get_commit_hash(dep_dir)
        print(f"  commit: {commit_hash}")

        output_dir = ARTIFACTS_CURRENT / name
        print(f"  generating into artifacts/current/{name}/")
        run_generator(dep_dir, output_dir, tag, commit_hash, release_version)

    print("\nAll artifacts written to artifacts/current/")


if __name__ == "__main__":
    main()
