"""Retrofit G1 exemplars.md + G2 invariants onto an existing hijack session.

Pure post-processing: fetches source, runs AST exemplar selector + style
fingerprint, writes exemplars.md AND appends a "Codebase Invariants" section
to each existing layer .md (backend.md, db.md, shared.md, ...). No LLM.

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
from hijack.core.style_fingerprint import (
    extract_style,
    render_layer_invariants_md,
)

_LAYER_FILE_NAMES = {
    "frontend": "frontend.md",
    "backend": "backend.md",
    "db": "database.md",
    "devops": "devops.md",
    "shared": "shared.md",
}

_INVARIANTS_HEADING = "## Codebase Invariants"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    target, integrated_dir = sys.argv[1], Path(sys.argv[2])
    if not integrated_dir.is_dir():
        print(f"error: integrated dir not found: {integrated_dir}")
        return 1

    print(f"[1/4] fetching source from {target} ...")
    files, repo_root = fetch_source(target)
    print(f"  → {len(files)} files (root: {repo_root.as_posix()})")

    print("[2/4] selecting exemplars (AST-based, no LLM) ...")
    exemplars = select_exemplars(files, repo_root=repo_root)
    print(f"  → {len(exemplars)} exemplars selected")
    for ex in exemplars:
        print(f"    - {ex.file_path}:{ex.line_range[0]}-{ex.line_range[1]} "
              f"({ex.layer}/{ex.role}) {ex.name}")

    if exemplars:
        md = render_exemplars_md(exemplars, source_target=target)
        out = integrated_dir / "exemplars.md"
        out.write_text(md, encoding="utf-8")
        print(f"  → wrote {out.as_posix()} ({len(md)} chars)")

    print("[3/4] computing per-layer style fingerprints (G2) ...")
    fingerprints = extract_style(files)
    for layer, fp in fingerprints.items():
        print(
            f"  - {layer}: {fp.file_count} files, "
            f"{len(fp.negative_space)} negative-space, "
            f"{len(fp.substitutions)} substitution checks"
        )

    print("[4/4] appending 'Codebase Invariants' to each layer .md ...")
    for layer, fp in fingerprints.items():
        fname = _LAYER_FILE_NAMES.get(layer, f"{layer}.md")
        layer_md_path = integrated_dir / fname
        if not layer_md_path.exists():
            print(f"  - skipping {fname} (file not present)")
            continue
        invariants_md = render_layer_invariants_md(fp)
        if not invariants_md:
            continue
        existing = layer_md_path.read_text(encoding="utf-8")
        # Idempotency: replace any prior Codebase Invariants section.
        marker_idx = existing.find(_INVARIANTS_HEADING)
        if marker_idx != -1:
            existing = existing[:marker_idx].rstrip() + "\n"
        layer_md_path.write_text(existing + invariants_md, encoding="utf-8")
        print(f"  → updated {fname} (+ {len(invariants_md)} chars)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
