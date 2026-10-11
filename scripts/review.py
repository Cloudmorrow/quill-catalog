#!/usr/bin/env python3
"""The review of a pull request somebody opened: run by check.yml on pull requests.

Compares the pull request's catalog.toml with main's: every Quill whose ref
changed, and every new one, is fetched at both releases and reviewed by the
rules in policy.py. Prints the review for each, and fails when a rule is
broken, so the pull request cannot be merged by mistake; what to look
closely at is printed for the person reviewing.

    python scripts/review.py --base origin/main [--catalog catalog.toml]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import policy
import tomllib
from follow import Checker, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--catalog", default="catalog.toml", type=Path)
    args = parser.parse_args()
    after = tomllib.loads(args.catalog.read_text(encoding="utf-8"))
    base_text = subprocess.run(
        ["git", "show", f"{args.base}:{args.catalog.as_posix()}"], check=True, capture_output=True, text=True,
    ).stdout
    before = tomllib.loads(base_text)
    was = {e["id"]: e for e in before.get("quills", [])}
    changed = [e for e in after.get("quills", []) if e.get("ref") != (was.get(e["id"]) or {}).get("ref")
               or e.get("repo") != (was.get(e["id"]) or {}).get("repo")]
    if not changed:
        print("No Quill changes its release here; nothing to review.")
        return 0
    refused_any = False
    with tempfile.TemporaryDirectory(prefix="quill-review-") as tmp:
        checker = Checker(Path(tmp))
        now = checker.run(after)
        then = checker.run(before) if any(e["id"] in was for e in changed) else {}
        for entry in changed:
            quill_id = entry["id"]
            old = was.get(quill_id)
            print(f"\n## {entry.get('name') or quill_id} at {entry.get('ref')}")
            refused: list[str] = []
            if old and old.get("repo") != entry.get("repo"):
                refused.append(f"its repository changed from {old.get('repo')} to {entry.get('repo')}; a Quill that "
                               f"moves is a pull request that says why, from the publisher")
            mine = now.get(quill_id) or {}
            if not mine.get("ok"):
                print(f"✗ the check fails: {mine.get('error')}")
                refused_any = True
                continue
            more, look = policy.review((then.get(quill_id) or {}).get("plan"), mine["plan"], str(entry.get("ref", "")),
                                       listed=old is not None)
            refused += more
            print(policy.said(refused, look))
            refused_any = refused_any or bool(refused)
        bad = {k: v for k, v in failures(now).items() if k not in {e["id"] for e in changed}}
        for k, v in bad.items():
            print(f"✗ {k} does not check out: {v}")
    return 1 if refused_any else 0


if __name__ == "__main__":
    sys.exit(main())
