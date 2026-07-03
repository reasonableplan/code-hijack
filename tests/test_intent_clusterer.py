"""Tests for R7 phase 1 intent_clusterer.

The clusterer is a dumb bucketer — these tests protect:
  - intent_kind mapping mirrors prompts.py / SKILL.md (no drift)
  - primary_path resolution prefers source over test files
  - bucketing groups same (kind, path) and splits on either differing
  - cluster ordering: size DESC, then intent priority
"""
from __future__ import annotations

from hijack.core.archaeology import CommitDecision
from hijack.core.intent_clusterer import (
    IntentCluster,
    PRIntentCluster,
    classify_intent_kind,
    cluster_commits,
    cluster_pr_decisions,
)
from hijack.core.pr_archaeology import PRDecision


def _commit(
    sha: str,
    matched_patterns: list[str],
    file_paths: list[str],
    subject: str = "fix: stuff",
    body: str = "body",
) -> CommitDecision:
    return CommitDecision(
        sha=sha,
        subject=subject,
        date="2024-01-01 00:00:00 +0000",
        body_excerpt=body,
        matched_patterns=sorted(matched_patterns),
        file_paths=sorted(file_paths),
    )


# ---------------------------------------------------------------------------
# classify_intent_kind — protects the prompts.py / SKILL.md mapping mirror
# ---------------------------------------------------------------------------


class TestClassifyIntentKind:
    def test_rejection_patterns(self) -> None:
        assert classify_intent_kind(["rejected"]) == "rejection"
        assert classify_intent_kind(["abandoned"]) == "rejection"
        assert classify_intent_kind(["switched from"]) == "rejection"

    def test_incident_patterns(self) -> None:
        assert classify_intent_kind(["regression"]) == "incident"
        assert classify_intent_kind(["reverted because"]) == "incident"

    def test_preference_patterns(self) -> None:
        for p in [
            "instead of", "rather than", "decided to", "to avoid",
            "to prevent", "as opposed to", "switched to",
        ]:
            assert classify_intent_kind([p]) == "preference", p

    def test_constraint_patterns(self) -> None:
        assert classify_intent_kind(["due to"]) == "constraint"
        assert classify_intent_kind(["motivated by"]) == "constraint"

    def test_priority_rejection_over_preference(self) -> None:
        # "rejected" + "instead of" → rejection wins
        assert classify_intent_kind(["instead of", "rejected"]) == "rejection"

    def test_priority_incident_over_preference(self) -> None:
        assert classify_intent_kind(["regression", "to avoid"]) == "incident"

    def test_priority_preference_over_constraint(self) -> None:
        # An anyio-integration-style commit hits both 'due to' and 'instead of'.
        # preference (internal philosophy) wins over constraint (external).
        assert classify_intent_kind(["due to", "instead of"]) == "preference"

    def test_unknown_pattern_returns_none(self) -> None:
        # Defensive: if archaeology pattern set drifts and adds a new pattern
        # that this mirror doesn't know about, we get None instead of raising.
        assert classify_intent_kind(["fictional new pattern"]) is None

    def test_empty_patterns_returns_none(self) -> None:
        assert classify_intent_kind([]) is None


# ---------------------------------------------------------------------------
# cluster_commits — bucketing + ordering
# ---------------------------------------------------------------------------


class TestClusterCommits:
    def test_single_commit_single_cluster(self) -> None:
        c = _commit("a" * 12, ["instead of"], ["lib/foo.py"])
        clusters = cluster_commits([c])
        assert len(clusters) == 1
        assert clusters[0].intent_kind == "preference"
        assert clusters[0].primary_path == "lib/foo.py"
        assert clusters[0].commits == (c,)

    def test_two_commits_same_kind_same_path_merge(self) -> None:
        # 3 CORS-style commits all touching the same source file.
        cors = [
            _commit("c" + "0" * 11, ["instead of"], ["lib/cors.py", "tests/test_cors.py"]),
            _commit("c" + "1" * 11, ["rather than"], ["lib/cors.py"]),
            _commit("c" + "2" * 11, ["as opposed to"], ["lib/cors.py", "tests/test_cors.py"]),
        ]
        clusters = cluster_commits(cors)
        assert len(clusters) == 1
        assert clusters[0].size == 3
        assert clusters[0].primary_path == "lib/cors.py"

    def test_different_intent_kind_splits(self) -> None:
        a = _commit("a" * 12, ["regression"], ["lib/foo.py"])
        b = _commit("b" * 12, ["instead of"], ["lib/foo.py"])
        clusters = cluster_commits([a, b])
        assert len(clusters) == 2

    def test_different_primary_path_splits(self) -> None:
        a = _commit("a" * 12, ["instead of"], ["lib/foo.py"])
        b = _commit("b" * 12, ["instead of"], ["lib/bar.py"])
        clusters = cluster_commits([a, b])
        assert len(clusters) == 2

    def test_test_only_paths_dont_dominate_primary(self) -> None:
        # Commit touches both source and test — primary should be source.
        c = _commit(
            "a" * 12, ["instead of"],
            ["lib/foo.py", "tests/test_foo.py"],
        )
        clusters = cluster_commits([c])
        assert clusters[0].primary_path == "lib/foo.py"

    def test_test_only_commit_clusters_on_test_path(self) -> None:
        # When every touched file is under tests/, fall back to the first.
        c = _commit("a" * 12, ["instead of"], ["tests/conftest.py", "tests/test_x.py"])
        clusters = cluster_commits([c])
        assert clusters[0].primary_path == "tests/conftest.py"

    def test_cluster_ordering_by_size_desc(self) -> None:
        # Big cluster (3) should come before small cluster (1).
        big = [
            _commit("c" + str(i) * 11, ["instead of"], ["lib/big.py"])
            for i in range(3)
        ]
        small = _commit("d" * 12, ["instead of"], ["lib/small.py"])
        clusters = cluster_commits([*big, small])
        assert clusters[0].size == 3
        assert clusters[1].size == 1

    def test_cluster_ordering_intent_priority_tiebreak(self) -> None:
        # Same size — rejection should rank before preference.
        rej = _commit("r" * 12, ["rejected"], ["lib/a.py"])
        pref = _commit("p" * 12, ["instead of"], ["lib/b.py"])
        clusters = cluster_commits([pref, rej])
        assert clusters[0].intent_kind == "rejection"
        assert clusters[1].intent_kind == "preference"

    def test_unclassified_kind_clusters_separately(self) -> None:
        # A commit with an unknown matched_pattern still gets clustered (kind=None).
        bad = _commit("x" * 12, ["fictional pattern"], ["lib/foo.py"])
        good = _commit("y" * 12, ["instead of"], ["lib/foo.py"])
        clusters = cluster_commits([bad, good])
        # Same primary_path, different kinds → 2 clusters.
        assert len(clusters) == 2

    def test_empty_input_returns_empty(self) -> None:
        assert cluster_commits([]) == []

    def test_intent_cluster_immutable(self) -> None:
        # IntentCluster is a frozen dataclass — assignment to fields raises.
        # (Not testing hashability — commits tuple contains CommitDecision
        # records which are mutable dataclasses, so the cluster isn't usable
        # as a dict key. Immutability of the cluster's own fields is enough.)
        from dataclasses import FrozenInstanceError
        c = _commit("a" * 12, ["instead of"], ["lib/foo.py"])
        cl = cluster_commits([c])[0]
        assert isinstance(cl, IntentCluster)
        try:
            cl.intent_kind = "rejection"  # type: ignore[misc]
        except FrozenInstanceError:
            return
        raise AssertionError("expected FrozenInstanceError")


# ---------------------------------------------------------------------------
# cluster_pr_decisions — R7 probe (PR mining supplies intent_kind directly)
# ---------------------------------------------------------------------------


def _prd(ref: str, intent_kind: str, diff_excerpt: str = "") -> PRDecision:
    return PRDecision(
        ref=ref,
        title="t",
        date="2024-01-01 00:00:00 +0000",
        body_excerpt="b",
        matched_patterns=[],
        maintainer_comment="",
        intent_kind=intent_kind,
        diff_excerpt=diff_excerpt,
    )


class TestClusterPRDecisions:
    def test_diff_header_anchors_primary_path(self) -> None:
        d = _prd("PR#1", "rejection", diff_excerpt="--- src/cors.py\n@@ -1 +1 @@\n-a\n+b")
        clusters = cluster_pr_decisions([d])
        assert len(clusters) == 1
        assert clusters[0].intent_kind == "rejection"
        assert clusters[0].primary_path == "src/cors.py"
        assert clusters[0].decisions == (d,)

    def test_same_kind_same_file_merge(self) -> None:
        # Two rejection PRs touching the same source file — the multi-item
        # cluster that is R7's leverage case, and the incident/rejection axis
        # commit mining never populated.
        a = _prd("PR#1", "rejection", diff_excerpt="--- src/cors.py\n+x")
        b = _prd("PR#2", "rejection", diff_excerpt="--- src/cors.py\n+y")
        clusters = cluster_pr_decisions([a, b])
        assert len(clusters) == 1
        assert clusters[0].size == 2
        assert clusters[0].primary_path == "src/cors.py"

    def test_empty_diff_falls_back_to_ref(self) -> None:
        # preference PRs carry no diff — each anchors on its ref, so they stay
        # separate rather than collapsing into one intent-only mega-bucket.
        a = _prd("PR#1", "preference")
        b = _prd("PR#2", "preference")
        clusters = cluster_pr_decisions([a, b])
        assert len(clusters) == 2
        assert {c.primary_path for c in clusters} == {"PR#1", "PR#2"}

    def test_different_intent_kind_splits(self) -> None:
        a = _prd("PR#1", "incident", diff_excerpt="--- src/foo.py\n+x")
        b = _prd("PR#2", "rejection", diff_excerpt="--- src/foo.py\n+y")
        clusters = cluster_pr_decisions([a, b])
        assert len(clusters) == 2

    def test_ordering_size_desc_then_intent_priority(self) -> None:
        big = [
            _prd(f"PR#{i}", "preference", diff_excerpt="--- src/big.py\n+x")
            for i in range(2)
        ]
        rej = _prd("PR#9", "rejection", diff_excerpt="--- src/a.py\n+x")
        clusters = cluster_pr_decisions([rej, *big])
        assert clusters[0].size == 2                    # size wins first
        assert clusters[1].intent_kind == "rejection"   # then intent priority

    def test_empty_input_returns_empty(self) -> None:
        assert cluster_pr_decisions([]) == []

    def test_cluster_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        cl = cluster_pr_decisions([_prd("PR#1", "rejection", "--- a.py\n+x")])[0]
        assert isinstance(cl, PRIntentCluster)
        try:
            cl.intent_kind = "incident"  # type: ignore[misc]
        except FrozenInstanceError:
            return
        raise AssertionError("expected FrozenInstanceError")
