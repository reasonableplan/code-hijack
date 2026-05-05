"""Smoke-test Phase A1 (pr_decisions) against a real remote GitHub repo.

Fetches PR history, runs extract_pr_decisions, and prints a summary.

Usage:
    python scripts/check_pr_decisions.py <target> <cache_dir>

Examples:
    python scripts/check_pr_decisions.py https://github.com/pydantic/pydantic /tmp/pr_cache
    python scripts/check_pr_decisions.py https://github.com/sqlalchemy/sqlalchemy /tmp/pr_cache

Requires:
    gh CLI authenticated (gh auth login) OR GH_TOKEN / GITHUB_TOKEN env var set.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.pr_decisions import extract_pr_decisions, render_pr_decisions_md


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    target = sys.argv[1]
    cache_dir = Path(sys.argv[2])
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] Mining PR decisions for {target} ...")
    print(f"      Cache: {cache_dir.as_posix()}")
    decisions = extract_pr_decisions(target, None, cache_dir)

    if decisions is None:
        print("\n[SKIPPED] Target is not a GitHub repo, or no auth available.")
        print("  Set GH_TOKEN env var or run: gh auth login")
        return 1

    print()
    print("=" * 60)
    print(f"Results for: {target}")
    print("=" * 60)
    print(f"  Repo slug:           {decisions.repo_slug}")
    print(f"  Total PRs scanned:   {decisions.total_prs_scanned}")
    print(f"  Vocab clusters:      {len(decisions.vocabulary_clusters)}")
    print(f"  Notable PRs:         {len(decisions.notable_prs)}")
    print(f"  Rejected PRs:        {len(decisions.rejected_prs)}")
    print(f"  Label categories:    {len(decisions.label_counts)}")
    print()

    if decisions.vocabulary_clusters:
        print("Top vocab clusters:")
        for vc in decisions.vocabulary_clusters[:3]:
            print(f"  - {vc.theme} ({vc.count} mentions): {', '.join(vc.matched_keywords[:3])}")
        print()

    if decisions.notable_prs:
        print("Top 3 most-discussed merged PRs:")
        for pr in decisions.notable_prs[:3]:
            print(f"  - #{pr.number}: {pr.title!r} ({pr.comment_count} comments)")
        print()

    if decisions.rejected_prs:
        print("Top 3 rejected PRs:")
        for pr in decisions.rejected_prs[:3]:
            print(f"  - #{pr.number}: {pr.title!r} (closed {pr.closed_at[:10]})")
        print()

    if decisions.label_counts:
        print("Top 5 labels:")
        for lc in decisions.label_counts[:5]:
            print(f"  - {lc.label!r}: {lc.count}")
        print()

    if decisions.has_signal:
        md = render_pr_decisions_md(decisions, source_target=target)
        repo_name = target.rstrip("/").split("/")[-1]
        out_path = cache_dir.parent / f"pr_decisions_{repo_name}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"  → wrote {out_path.as_posix()} ({len(md)} chars)")
    else:
        print("  (no signal — nothing written)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
