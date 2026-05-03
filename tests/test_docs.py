"""Tests for hijack.core.docs — repo-level rationale doc collection."""

from __future__ import annotations

from pathlib import Path

from hijack.core.docs import (
    RepoDoc,
    collect_repo_docs,
    render_repo_context,
)


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level filename allowlist
# ---------------------------------------------------------------------------

class TestFilenameAllowlist:
    def test_readme_md_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# Project")
        docs = collect_repo_docs(tmp_path)
        assert [d.path for d in docs] == ["README.md"]

    def test_architecture_md_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "ARCHITECTURE.md", "# Why dataclasses")
        docs = collect_repo_docs(tmp_path)
        assert any(d.path == "ARCHITECTURE.md" for d in docs)

    def test_contributing_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "CONTRIBUTING.md", "# How to PR")
        docs = collect_repo_docs(tmp_path)
        assert any(d.path == "CONTRIBUTING.md" for d in docs)

    def test_localized_readme_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.ko.md", "# 한국어")
        docs = collect_repo_docs(tmp_path)
        assert any(d.path == "README.ko.md" for d in docs)

    def test_unrelated_md_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "CHANGELOG.md", "# 1.0")
        _write(tmp_path, "RELEASE_NOTES.md", "# notes")
        docs = collect_repo_docs(tmp_path)
        assert docs == []

    def test_non_doc_extension_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.py", "# this is python, not docs")
        docs = collect_repo_docs(tmp_path)
        assert docs == []

    def test_empty_file_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "   \n  ")
        assert collect_repo_docs(tmp_path) == []


# ---------------------------------------------------------------------------
# ADR / design-note directories
# ---------------------------------------------------------------------------

class TestDocDirectories:
    def test_adr_dir_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "docs/adr/0001-init.md", "# ADR 0001\nWhy we chose X.")
        _write(tmp_path, "docs/adr/0002-auth.md", "# ADR 0002\nOAuth choice.")
        docs = collect_repo_docs(tmp_path)
        paths = [d.path for d in docs]
        assert "docs/adr/0001-init.md" in paths
        assert "docs/adr/0002-auth.md" in paths

    def test_root_adr_dir_collected(self, tmp_path: Path) -> None:
        _write(tmp_path, "adr/0001-foo.md", "# ADR")
        docs = collect_repo_docs(tmp_path)
        assert any(d.path == "adr/0001-foo.md" for d in docs)

    def test_node_modules_skipped(self, tmp_path: Path) -> None:
        # ADRs that happen to live inside node_modules don't count.
        _write(tmp_path, "node_modules/somelib/docs/adr/0001.md", "# bogus")
        docs = collect_repo_docs(tmp_path)
        assert docs == []


# ---------------------------------------------------------------------------
# Truncation / budget
# ---------------------------------------------------------------------------

class TestTruncation:
    def test_long_doc_marked_truncated(self, tmp_path: Path) -> None:
        # Per-doc cap is 2000.
        long_content = "x" * 5000
        _write(tmp_path, "README.md", long_content)
        docs = collect_repo_docs(tmp_path)
        assert len(docs) == 1
        assert "[...truncated]" in docs[0].content
        assert len(docs[0].content) <= 2000 + len("\n[...truncated]") + 5

    def test_total_cap_stops_collection(self, tmp_path: Path) -> None:
        # 5000-char total cap; three 2000-char docs would be 6000 → last one
        # truncates / drops to fit.
        for i in range(3):
            _write(tmp_path, f"docs/adr/000{i}.md", "y" * 2000)
        _write(tmp_path, "README.md", "z" * 2000)

        docs = collect_repo_docs(tmp_path)
        total = sum(len(d.content) for d in docs)
        # Allow for "[...truncated]" suffix overshoot — bounded.
        assert total <= 5000 + 50


# ---------------------------------------------------------------------------
# render_repo_context
# ---------------------------------------------------------------------------

class TestRenderRepoContext:
    def test_empty_returns_empty_string(self) -> None:
        assert render_repo_context([]) == ""

    def test_renders_with_path_headers(self) -> None:
        docs = [
            RepoDoc(path="README.md", content="# Project\nWe use dataclasses."),
            RepoDoc(path="docs/adr/0001.md", content="# ADR 0001\nDrop pydantic."),
        ]
        out = render_repo_context(docs)
        assert out.startswith("<repo_context>")
        assert out.endswith("</repo_context>")
        assert "### README.md" in out
        assert "### docs/adr/0001.md" in out
        assert "Drop pydantic" in out
