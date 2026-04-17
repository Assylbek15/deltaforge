#!/usr/bin/env python3
"""
Resolve the ordered list of releases to chain when deploying an environment
from its current release to a target release.

Outputs one release tag per line (oldest first). Feed the output directly
to compute_deploy_diff.py as --jars arguments after downloading each JAR.

Exit codes:
  0 — chain printed (may be empty if already up to date)
  1 — unrecoverable error (target not found, API failure, etc.)

Usage:
    python tools/resolve_deploy_chain.py \
        --from-release v1.0.0 \
        --to-release v1.2.0 \
        --repo Assylbek15/deltaforge
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def list_releases(repo: str) -> list[str]:
    """Return all non-draft release tags in chronological order (oldest first)."""
    result = subprocess.run(
        [
            "gh", "release", "list",
            "--repo", repo,
            "--json", "tagName,isDraft,createdAt",
            "--limit", "200",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    releases = json.loads(result.stdout)
    non_drafts = [r for r in releases if not r["isDraft"]]
    ordered = sorted(non_drafts, key=lambda r: r["createdAt"])
    return [r["tagName"] for r in ordered]


def resolve_chain(from_tag: str, to_tag: str, ordered_tags: list[str]) -> list[str]:
    """
    Return tags strictly between from_tag (exclusive) and to_tag (inclusive),
    in chronological order.

    If from_tag is 'none' or not in the release list, treat the environment as
    never deployed and return only [to_tag] (first-deploy behavior).
    Returns an empty list if the environment is already at or past to_tag.
    """
    if to_tag not in ordered_tags:
        print(f"[ERROR] Target release '{to_tag}' not found in the release list.", file=sys.stderr)
        sys.exit(1)

    to_idx = ordered_tags.index(to_tag)

    if from_tag == "none" or from_tag not in ordered_tags:
        return [to_tag]

    from_idx = ordered_tags.index(from_tag)

    if from_idx >= to_idx:
        return []

    return ordered_tags[from_idx + 1 : to_idx + 1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve the release chain needed to deploy an environment."
    )
    parser.add_argument(
        "--from-release",
        required=True,
        help="Current release on the environment, or 'none' for first deploy.",
    )
    parser.add_argument(
        "--to-release",
        required=True,
        help="Target release to deploy.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in owner/name format.",
    )
    args = parser.parse_args()

    ordered_tags = list_releases(args.repo)
    chain = resolve_chain(args.from_release, args.to_release, ordered_tags)

    if not chain:
        print(
            f"[INFO] Environment is already at or past '{args.to_release}'. Nothing to deploy.",
            file=sys.stderr,
        )

    for tag in chain:
        print(tag)


if __name__ == "__main__":
    main()
