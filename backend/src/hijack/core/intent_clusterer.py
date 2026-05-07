"""R7 Phase 1 — cluster commit_decisions by (intent_kind, primary_path).

Forward pipeline (current) writes rules first, then hunts commits as evidence.
R7 inversion derives rules from commit clusters — evidence is the origin.
This module is the first scaffolding piece: a dumb bucketer that groups
CommitDecision records by intent_kind plus a primary path anchor.

Algorithm is intentionally simple — no k-means, no embeddings. Group by
(intent_kind, primary_path), order by cluster size desc.

NOT integrated into analyzer yet (R7 phase 2+ work). Standalone module so the
phase 1 smoke run can eyeball the clustering quality before committing further.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from hijack.core.archaeology import CommitDecision

# Intent kind mapping mirrors prompts.py:218-224 / SKILL.md step 3.5 mapping.
# Single source of truth lives there (LLM-facing); this is a code-side mirror.
# When prompts.py mapping changes, update this set too.
_REJECTION_PATTERNS: frozenset[str] = frozenset({
    "rejected", "abandoned", "switched from",
})
_INCIDENT_PATTERNS: frozenset[str] = frozenset({
    "reverted because", "regression",
})
_PREFERENCE_PATTERNS: frozenset[str] = frozenset({
    "instead of", "rather than", "decided to", "decided not to",
    "tried", "considered", "switched to", "originally...now",
    "to avoid", "to prevent", "as opposed to",
})
_CONSTRAINT_PATTERNS: frozenset[str] = frozenset({
    "due to", "motivated by",
})

# Priority: rejection > incident > preference > constraint.
# Matches the priority chain in prompts.py:224 ("rejection > incident > preference").
# Constraint added at end — tied to "external requirement" semantics, lower
# narrative weight than internal preference.
_INTENT_PRIORITY: tuple[tuple[str, frozenset[str]], ...] = (
    ("rejection", _REJECTION_PATTERNS),
    ("incident", _INCIDENT_PATTERNS),
    ("preference", _PREFERENCE_PATTERNS),
    ("constraint", _CONSTRAINT_PATTERNS),
)


def classify_intent_kind(matched_patterns: list[str]) -> str | None:
    """Map a CommitDecision's matched_patterns to a single intent_kind.

    Walks priority order and returns the first kind whose pattern set
    intersects matched_patterns. Returns None if no patterns match — this
    can happen if archaeology pattern set drifts from this mirror.
    """
    pattern_set = set(matched_patterns)
    for kind, patterns in _INTENT_PRIORITY:
        if pattern_set & patterns:
            return kind
    return None


def _resolve_primary_path(file_paths: list[str]) -> str:
    """Pick the file_path that anchors the commit's semantic.

    Heuristic: first non-test file in the (already-sorted) file_paths list.
    If every touched file lives under tests/, fall back to the first one —
    test-only commits do exist (fixture refactors, test infra) and should
    cluster on the test path itself.

    Caller guarantees file_paths is non-empty (CommitDecision invariant).
    """
    for fp in file_paths:
        if not fp.startswith("tests/") and "/tests/" not in fp:
            return fp
    return file_paths[0]


@dataclass(frozen=True)
class IntentCluster:
    """A group of commits sharing intent_kind and primary_path.

    Phase 1 output unit. Phase 2 will feed each cluster to the LLM with a
    "what rule do these commits jointly establish?" prompt.
    """
    intent_kind: str | None
    primary_path: str
    commits: tuple[CommitDecision, ...] = field(default_factory=tuple)

    @property
    def size(self) -> int:
        return len(self.commits)


# Ordering key for cluster sort: larger clusters first (evidence weight),
# then intent priority (rejection beats preference as tie-breaker).
_INTENT_SORT_RANK: dict[str | None, int] = {
    "rejection": 0,
    "incident": 1,
    "preference": 2,
    "constraint": 3,
    None: 4,
}


def cluster_commits(commits: list[CommitDecision]) -> list[IntentCluster]:
    """Bucket commits by (intent_kind, primary_path) and return ordered clusters.

    Sort order:
      1. Cluster size DESC (multi-commit clusters carry more evidence weight)
      2. Intent priority (rejection < incident < preference < constraint < None)
      3. primary_path ASC (deterministic for ties)
    """
    buckets: dict[tuple[str | None, str], list[CommitDecision]] = defaultdict(list)
    for c in commits:
        if not c.file_paths:  # defensive — extract_commit_decisions never emits this
            continue
        kind = classify_intent_kind(c.matched_patterns)
        path = _resolve_primary_path(c.file_paths)
        buckets[(kind, path)].append(c)

    clusters = [
        IntentCluster(intent_kind=kind, primary_path=path, commits=tuple(cs))
        for (kind, path), cs in buckets.items()
    ]
    clusters.sort(
        key=lambda cl: (
            -cl.size,
            _INTENT_SORT_RANK.get(cl.intent_kind, 99),
            cl.primary_path,
        )
    )
    return clusters
