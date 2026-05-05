"""Smoke-test Phase B (test_decisions) against a real remote repo.

Fetches the repo, runs extract_test_decisions, and prints a summary.

Usage:
    python scripts/check_test_decisions.py <target>

Example:
    python scripts/check_test_decisions.py https://github.com/pydantic/pydantic
    python scripts/check_test_decisions.py https://github.com/sqlalchemy/sqlalchemy
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.fetcher import fetch_source
from hijack.core.test_decisions import extract_test_decisions, render_tests_distilled_md


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    target = sys.argv[1]
    print(f"[1/2] fetching {target} ...")
    files, repo_root = fetch_source(target)
    print(f"  → {len(files)} files (root: {repo_root.as_posix()})")

    print("[2/2] extracting test decisions ...")
    decisions = extract_test_decisions(files)

    print()
    print("=" * 60)
    print(f"Results for: {target}")
    print("=" * 60)
    print(f"  Test files scanned: {decisions.test_file_count}")
    print(f"  Edge cases found:   {len(decisions.edge_cases)}")
    print(f"  Name themes found:  {len(decisions.name_themes)}")
    print(f"  Raises groups found:{len(decisions.raises_groups)}")
    print()

    if decisions.raises_groups:
        print("Top 3 raises exceptions:")
        for rg in decisions.raises_groups[:3]:
            print(f"  - {rg.exception} ({rg.count} occurrences)")
            for t in rg.triggers[:2]:
                print(f"      trigger: {t}")
        print()

    if decisions.name_themes:
        print("Top 5 name themes:")
        for nt in decisions.name_themes[:5]:
            print(f"  - {nt.verb}_{nt.subject} ({nt.count} tests)")
            for ex in nt.examples[:2]:
                print(f"      example: {ex}")
        print()

    if decisions.edge_cases:
        print("A few interesting edge cases:")
        for ec in decisions.edge_cases[:5]:
            print(f"  - {ec.test_file}::{ec.test_name} -- {ec.case_repr} ({ec.why})")
        print()

    if decisions.has_signal:
        md = render_tests_distilled_md(decisions, source_target=target)
        out_path = Path(f"test_decisions_smoke_{target.split('/')[-1]}.md")
        out_path.write_text(md, encoding="utf-8")
        print(f"  → wrote {out_path} ({len(md)} chars)")
    else:
        print("  (no signal — nothing written)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
