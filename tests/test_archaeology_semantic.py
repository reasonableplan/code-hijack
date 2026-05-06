"""Tests for A2.2 — semantic matching (Jaccard-based evidence chain fallback).

All fixtures use fake CommitDecision instances — no real git repo needed.
Pattern: mirror test_commit_decisions.py fixture style.
"""
from __future__ import annotations

import pytest

from hijack.core.archaeology import (
    CommitDecision,
    CommitDecisions,
    _tokenize,
    find_semantic_candidates,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cd(
    subject: str,
    body_excerpt: str = "",
    sha: str = "aabbccdd1234",
    date: str = "2024-09-21 10:00:00 +0000",
    file_paths: list[str] | None = None,
) -> CommitDecision:
    return CommitDecision(
        sha=sha,
        subject=subject,
        date=date,
        body_excerpt=body_excerpt,
        matched_patterns=[],
        file_paths=file_paths or [],
    )


def _decisions(*commits: CommitDecision) -> CommitDecisions:
    return CommitDecisions(
        commits_scanned=len(commits),
        patterns=[],
        commits=list(commits),
    )


# ---------------------------------------------------------------------------
# TestTokenize — _tokenize helper
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_tokenize_handles_english_lowercase(self):
        result = _tokenize("Hello World")
        assert result == {"hello", "world"}

    def test_tokenize_handles_mixed_case(self):
        result = _tokenize("HTTP Transport Layer")
        assert "http" in result
        assert "transport" in result
        assert "layer" in result

    def test_tokenize_handles_korean_syllables(self):
        result = _tokenize("다중 라운드트립")
        assert "다중" in result
        assert "라운드트립" in result

    def test_tokenize_strips_stopwords_en(self):
        result = _tokenize("the cat sat on the mat")
        assert "cat" in result
        assert "sat" in result
        assert "mat" in result
        # Stopwords must be absent
        assert "the" not in result
        assert "on" not in result

    def test_tokenize_strips_stopwords_ko(self):
        # Korean stopwords are single characters like "을", "를", "이", etc.
        # They appear as standalone tokens only if the input has spaces between them.
        result = _tokenize("프로토콜 을 사용한다")
        assert "프로토콜" in result
        # "을" is a KO stopword — must be removed
        assert "을" not in result

    def test_tokenize_ignores_single_char_tokens(self):
        # Single-character tokens (length ≤ 1) are dropped regardless of language.
        result = _tokenize("a b c foo")
        assert "a" not in result
        assert "b" not in result
        assert "c" not in result
        assert "foo" in result

    def test_tokenize_empty_string(self):
        assert _tokenize("") == set()

    def test_tokenize_numbers_excluded(self):
        # Pure digits are excluded by the regex pattern [a-zA-Z가-힣]+
        result = _tokenize("version 3 is released")
        assert "3" not in result
        assert "version" in result


# ---------------------------------------------------------------------------
# TestJaccardScore — Jaccard correctness via find_semantic_candidates
# ---------------------------------------------------------------------------


class TestJaccardScore:
    def test_jaccard_score_basic(self):
        # rule_text tokens: {"generator", "protocol", "auth", "transport"}
        # commit tokens: {"generator", "protocol", "flow", "auth"}
        # intersection: {"generator", "protocol", "auth"} = 3
        # union: {"generator", "protocol", "auth", "transport", "flow"} = 5
        # jaccard = 3/5 = 0.60 >> 0.15 → must appear
        commit = _cd(
            subject="generator protocol flow auth",
            body_excerpt="",
            sha="aaa111222333",
        )
        decisions = _decisions(commit)
        rule_text = "generator protocol auth transport"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.15, top_k=3)
        assert len(results) == 1
        cd_out, score = results[0]
        assert cd_out.sha == "aaa111222333"
        assert score > 0.5

    def test_jaccard_perfect_overlap(self):
        commit = _cd(subject="cache invalidation strategy", sha="bbb222333444")
        decisions = _decisions(commit)
        rule_text = "cache invalidation strategy"
        results = find_semantic_candidates(rule_text, decisions)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(1.0)

    def test_jaccard_no_overlap(self):
        commit = _cd(subject="unrelated topic about routing", sha="ccc333444555")
        decisions = _decisions(commit)
        rule_text = "async database query optimization"
        results = find_semantic_candidates(rule_text, decisions)
        assert results == []


# ---------------------------------------------------------------------------
# TestFindSemanticCandidates — integration-level tests
# ---------------------------------------------------------------------------


class TestFindSemanticCandidates:
    def test_find_semantic_candidates_returns_top_k_descending(self):
        # 4 commits with varying relevance to the rule, top_k=2
        c1 = _cd("async caching layer invalidation", sha="sha000000001a")
        c2 = _cd("caching layer design", sha="sha000000002b")  # less overlap
        c3 = _cd("async invalidation cache", sha="sha000000003c")  # similar to c1
        c4 = _cd("unrelated database migration", sha="sha000000004d")

        decisions = _decisions(c1, c2, c3, c4)
        rule_text = "async caching layer invalidation strategy"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.10, top_k=2)

        assert len(results) == 2
        # Results must be descending by score
        scores = [s for _, s in results]
        assert scores[0] >= scores[1]

    def test_find_semantic_candidates_threshold_filter(self):
        # Commit shares no meaningful tokens with rule_text
        commit = _cd("completely unrelated XYZ topic", sha="sha111111111a")
        decisions = _decisions(commit)
        # Use a high threshold that nothing will pass
        rule_text = "database migration rollback policy"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.99, top_k=3)
        assert results == []

    def test_find_semantic_candidates_empty_input(self):
        decisions = CommitDecisions(commits_scanned=0, patterns=[], commits=[])
        results = find_semantic_candidates("any rule text", decisions)
        assert results == []

    def test_find_semantic_candidates_no_signal(self):
        # has_signal=False when both patterns and commits are empty
        decisions = CommitDecisions(commits_scanned=5, patterns=[], commits=[])
        results = find_semantic_candidates("any rule text", decisions)
        assert results == []

    def test_find_semantic_candidates_uses_body_excerpt(self):
        # Body excerpt should contribute tokens alongside subject
        commit = _cd(
            subject="refactor auth",
            body_excerpt="switched from callable to generator protocol for multi-round auth",
            sha="sha222222222b",
        )
        decisions = _decisions(commit)
        # Rule text shares tokens with body_excerpt
        rule_text = "generator protocol multi-round auth switched callable"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.15, top_k=3)
        assert len(results) == 1
        assert results[0][0].sha == "sha222222222b"

    def test_find_semantic_candidates_korean_english_mix(self):
        # Transport is an English loanword that can appear in Korean reasoning
        commit = _cd(
            subject="Transport 추상화 레이어 설계",
            body_excerpt="기존 방식 대신 Transport 프로토콜을 도입해 auth와 분리",
            sha="sha333333333c",
        )
        decisions = _decisions(commit)
        # Rule text mixes Korean and English
        rule_text = "Transport 프로토콜 추상화 auth 분리 설계"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.10, top_k=3)
        assert len(results) == 1
        cd_out, score = results[0]
        assert cd_out.sha == "sha333333333c"
        assert score >= 0.10

    def test_find_semantic_candidates_top_k_respected(self):
        commits = [
            _cd(f"async caching strategy commit {i}", sha=f"sha{i:012d}")
            for i in range(6)
        ]
        decisions = _decisions(*commits)
        rule_text = "async caching strategy design"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.05, top_k=3)
        assert len(results) <= 3

    def test_find_semantic_candidates_score_order_stable(self):
        # When scores differ, ensure descending order is maintained
        high = _cd("async caching layer invalidation strategy pattern", sha="sha_high_111")
        low = _cd("async caching", sha="sha_low_2222")
        decisions = _decisions(high, low)
        rule_text = "async caching layer invalidation strategy pattern design"
        results = find_semantic_candidates(rule_text, decisions, threshold=0.05, top_k=5)
        assert len(results) == 2
        assert results[0][1] >= results[1][1]
        # high-overlap commit must rank first
        assert results[0][0].sha == "sha_high_111"
