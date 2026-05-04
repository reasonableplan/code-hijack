"""Fresh G1+G2 retrofit on a target repo with no prior session.

Runs the mechanical part of code-hijack — exemplar selection (G1) and style
fingerprint (G2) — against a freshly-fetched senior repo and writes outputs
to a clean integrated dir. Skips the LLM-driven rules layer, so this is the
right entry point for cross-repo generalization tests where we only care
whether G1+G2 work on a different codebase.

Usage:
    python scripts/fresh_g1g2_retrofit.py <target> <integrated_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
sys.path.insert(0, str(_BACKEND_SRC))

from hijack.core.exemplars import render_exemplars_md, select_exemplars
from hijack.core.fetcher import fetch_source
from hijack.core.style_fingerprint import (
    extract_style,
    render_layer_invariants_md,
)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    target = sys.argv[1]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] fetching {target} ...")
    files, repo_root = fetch_source(target)
    print(f"  → {len(files)} files (root: {repo_root.as_posix()})")

    print("[2/3] G1 exemplar selection ...")
    exemplars = select_exemplars(files, repo_root=repo_root)
    print(f"  → {len(exemplars)} exemplars")
    for ex in exemplars:
        print(
            f"    - {ex.file_path}:{ex.line_range[0]}-{ex.line_range[1]} "
            f"({ex.layer}/{ex.role}) {ex.name}"
        )

    if exemplars:
        md = render_exemplars_md(exemplars, source_target=target)
        (out_dir / "exemplars.md").write_text(md, encoding="utf-8")
        print(f"  → wrote exemplars.md ({len(md)} chars)")

    print("[3/3] G2 style fingerprint per layer ...")
    fingerprints = extract_style(files)
    for layer, fp in fingerprints.items():
        md = render_layer_invariants_md(fp)
        if not md:
            continue
        layer_path = out_dir / f"{layer}-invariants.md"
        # Wrap with a layer header so the file stands alone
        wrapped = f"# {layer.title()} Codebase Invariants\n{md}"
        layer_path.write_text(wrapped, encoding="utf-8")
        print(
            f"  - {layer}: {fp.file_count} files, "
            f"{len(fp.negative_space)} neg, "
            f"{len(fp.substitutions)} subs → wrote {layer_path.name}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
