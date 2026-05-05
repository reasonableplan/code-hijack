"""Smoke-test Phase C (commit_decisions) against a real remote repo.

Fetches the repo (which loads git history into SourceFile.history), runs
extract_commit_decisions, and prints a summary.

Usage:
    python scripts/check_commit_decisions.py <target> [out_dir]

Example:
    python scripts/check_commit_decisions.py https://github.com/pydantic/pydantic
    python scripts/check_commit_decisions.py https://github.com/sqlalchemy/sqlalchemy /tmp/out
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.archaeology import extract_commit_decisions, render_commit_decisions_md
from hijack.core.fetcher import fetch_source


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    target = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] fetching {target} (history included) ...")
    files, repo_root = fetch_source(target)
    print(f"  → {len(files)} files (root: {repo_root.as_posix()})")

    print("[2/2] extracting commit decisions ...")
    decisions = extract_commit_decisions(files)

    print()
    print("=" * 60)
    print(f"Results for: {target}")
    print("=" * 60)
    print(f"  Commits scanned:       {decisions.commits_scanned}")
    print(f"  Patterns found:        {len(decisions.patterns)}")
    print(f"  Matching commits:      {len(decisions.commits)}")
    print()

    if decisions.patterns:
        print("Top 5 patterns (by occurrence):")
        for dp in decisions.patterns[:5]:
            print(f"  - {dp.pattern!r} ({dp.count} commits)")
            for ex in dp.examples[:2]:
                print(f"      \"{ex}\"")
        print()

    if decisions.commits:
        print("Top 3 matching commits (most recent):")
        for cd in decisions.commits[:3]:
            date_short = cd.date[:10] if cd.date else "?"
            print(f"  - {cd.sha} ({date_short}) {cd.subject}")
            print(f"    patterns: {', '.join(cd.matched_patterns)}")
            print(f"    paths:    {', '.join(cd.file_paths[:3])}")
            if cd.body_excerpt:
                excerpt = cd.body_excerpt[:100]
                print(f"    > {excerpt}")
        print()

    if decisions.has_signal:
        md = render_commit_decisions_md(decisions, source_target=target)
        slug = target.rstrip("/").split("/")[-1]
        out_path = out_dir / f"commit_decisions_{slug}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"  → wrote {out_path} ({len(md)} chars)")
    else:
        print("  (no signal — nothing written)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
