"""Dump top-N exemplar candidates with scores so we can see what's getting filtered.

Usage: python scripts/diagnose_exemplar_scores.py <target> [N]
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.exemplars import _extract_candidates
from hijack.core.fetcher import fetch_source


def main() -> int:
    target = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    files, _root = fetch_source(target)
    print(f"fetched {len(files)} source files")

    cands: list = []
    for sf in files:
        cands.extend(_extract_candidates(sf))
    cands.sort(key=lambda c: c.score, reverse=True)

    print(f"\nTop {n} of {len(cands)} candidates above _MIN_SCORE:")
    print(f"{'score':>6}  {'layer':<10}  {'role':<10}  path:lines  name")
    for c in cands[:n]:
        print(
            f"{c.score:>6.3f}  {c.layer:<10}  {c.role:<10}  "
            f"{c.file_path}:{c.start_line}-{c.end_line}  {c.name}"
        )

    print(f"\nLayer distribution (above MIN_SCORE):")
    layers: dict[str, int] = {}
    for c in cands:
        layers[c.layer] = layers.get(c.layer, 0) + 1
    for layer, count in sorted(layers.items(), key=lambda kv: -kv[1]):
        print(f"  {layer}: {count}")

    # Spot-check security/* candidates specifically
    sec_cands = [c for c in cands if "security/" in c.file_path]
    print(f"\nsecurity/* candidates: {len(sec_cands)}")
    for c in sec_cands[:10]:
        print(f"  {c.score:>6.3f}  {c.file_path}:{c.start_line}-{c.end_line}  {c.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
