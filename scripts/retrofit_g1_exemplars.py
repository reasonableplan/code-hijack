"""Retrofit G1 exemplars.md onto an existing pre-G1 hijack session.

Pure post-processing: fetches source, runs AST-based selector, writes
exemplars.md into the integrated/ dir. No LLM calls.

Usage:
    python scripts/retrofit_g1_exemplars.py <target> <integrated_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the in-tree package is importable when running from repo root
_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.exemplars import render_exemplars_md, select_exemplars
from hijack.core.fetcher import fetch_source


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    target, integrated_dir = sys.argv[1], Path(sys.argv[2])
    if not integrated_dir.is_dir():
        print(f"error: integrated dir not found: {integrated_dir}")
        return 1

    print(f"[1/3] fetching source from {target} ...")
    files, repo_root = fetch_source(target)
    print(f"  → {len(files)} files (root: {repo_root.as_posix()})")

    print("[2/3] selecting exemplars (AST-based, no LLM) ...")
    exemplars = select_exemplars(files, repo_root=repo_root)
    print(f"  → {len(exemplars)} exemplars selected")
    for ex in exemplars:
        print(f"    - {ex.file_path}:{ex.line_range[0]}-{ex.line_range[1]} "
              f"({ex.layer}/{ex.role}) {ex.name}")

    if not exemplars:
        print("error: no exemplars met the quality threshold")
        return 1

    print("[3/3] rendering exemplars.md ...")
    md = render_exemplars_md(exemplars, source_target=target)
    out = integrated_dir / "exemplars.md"
    out.write_text(md, encoding="utf-8")
    print(f"  → wrote {out.as_posix()} ({len(md)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
