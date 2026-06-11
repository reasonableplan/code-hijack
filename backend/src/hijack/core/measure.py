"""measure.py — T-037: session metrics, foresight scoring, measurement.json I/O.

Pure functions: calc_session_metrics, diff_sessions, score_foresight,
                format_measurement_summary
I/O function:   write_measurement
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hijack.core.models import ForesightCard, SessionResult


@dataclass
class MeasurementResult:
    """단일 세션 측정 결과."""

    session_id: str
    cited_ratio: float
    must_ratio: float
    tier_distribution: dict[str, int]
    intent_kind_distribution: dict[str, int]
    foresight_scores: list[dict[str, str]]

    def to_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cited_ratio": self.cited_ratio,
            "must_ratio": self.must_ratio,
            "tier_distribution": self.tier_distribution,
            "intent_kind_distribution": self.intent_kind_distribution,
            "foresight_scores": self.foresight_scores,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MeasurementResult:
        return cls(
            session_id=data["session_id"],
            cited_ratio=data["cited_ratio"],
            must_ratio=data["must_ratio"],
            tier_distribution=data["tier_distribution"],
            intent_kind_distribution=data["intent_kind_distribution"],
            foresight_scores=data["foresight_scores"],
        )


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def calc_session_metrics(
    session: SessionResult,
    pr_decisions: Any | None = None,
) -> MeasurementResult:
    """SessionResult 에서 지표를 산출한다. pr_decisions 는 선택적 보강 소스.

    pr_decisions 는 pr_archaeology.PRDecisions 와 duck-type 호환.
    (decisions: list[...] where each item has .intent_kind: str)
    """
    rules = [rule for cat in session.categories for rule in cat.rules]
    total = len(rules)

    cited_count = sum(1 for r in rules if r.rationale_tier == "cited")
    must_count = sum(1 for r in rules if r.priority == "MUST")

    cited_ratio = cited_count / total if total > 0 else 0.0
    must_ratio = must_count / total if total > 0 else 0.0

    tier_distribution: dict[str, int] = {
        "cited": sum(1 for r in rules if r.rationale_tier == "cited"),
        "corroborated": sum(1 for r in rules if r.rationale_tier == "corroborated"),
        "speculative": sum(1 for r in rules if r.rationale_tier == "speculative"),
    }

    intent_kind_distribution: dict[str, int] = {
        "rejection": 0,
        "incident": 0,
        "preference": 0,
    }
    if pr_decisions is not None:
        for decision in getattr(pr_decisions, "decisions", []):
            kind = getattr(decision, "intent_kind", "")
            if kind in intent_kind_distribution:
                intent_kind_distribution[kind] += 1

    return MeasurementResult(
        session_id=session.session_id,
        cited_ratio=cited_ratio,
        must_ratio=must_ratio,
        tier_distribution=tier_distribution,
        intent_kind_distribution=intent_kind_distribution,
        foresight_scores=[],
    )


def diff_sessions(
    m1: MeasurementResult,
    m2: MeasurementResult,
) -> dict[str, Any]:
    """두 MeasurementResult 간 지표 차이 딕셔너리를 반환한다.

    m2 - m1 기준 (after - before).
    """
    tier_delta: dict[str, int] = {
        key: m2.tier_distribution.get(key, 0) - m1.tier_distribution.get(key, 0)
        for key in set(m1.tier_distribution) | set(m2.tier_distribution)
    }
    intent_delta: dict[str, int] = {
        key: m2.intent_kind_distribution.get(key, 0) - m1.intent_kind_distribution.get(key, 0)
        for key in set(m1.intent_kind_distribution) | set(m2.intent_kind_distribution)
    }
    return {
        "session_id_before": m1.session_id,
        "session_id_after": m2.session_id,
        "cited_ratio_delta": round(m2.cited_ratio - m1.cited_ratio, 10),
        "must_ratio_delta": round(m2.must_ratio - m1.must_ratio, 10),
        "tier_distribution_delta": tier_delta,
        "intent_kind_distribution_delta": intent_delta,
    }


def score_foresight(
    cards: list[ForesightCard],
    repo_docs: str,
    pr_decisions: Any | None,
) -> list[dict[str, str]]:
    """카드별 결정론 채점을 수행한다. LLM 판단 없이 키워드 매칭 기반.

    채점 기준:
    - signals 중 하나라도 repo_docs 에서 키워드 매칭 → "confirmed"
    - pr_decisions 의 rejection 결정에서 signals 키워드 매칭 → "confirmed"
    - 매칭 없음 → "unconfirmed"

    "refuted" 는 LLM 판단 영역이므로 결정론 채점에서는 반환하지 않는다.
    """
    docs_lower = repo_docs.lower()

    # Collect rejection text from pr_decisions for matching
    rejection_texts: list[str] = []
    if pr_decisions is not None:
        for decision in getattr(pr_decisions, "decisions", []):
            if getattr(decision, "intent_kind", "") == "rejection":
                title = getattr(decision, "title", "").lower()
                body = getattr(decision, "body_excerpt", "").lower()
                if title:
                    rejection_texts.append(title)
                if body:
                    rejection_texts.append(body)

    results: list[dict[str, str]] = []
    for card in cards:
        verdict = "unconfirmed"

        # Extract keywords from hypothesis + signals
        keywords: list[str] = []
        for signal in card.signals:
            # Split signal into meaningful tokens (words ≥ 4 chars)
            tokens = [w.lower() for w in signal.split() if len(w) >= 4]
            keywords.extend(tokens)

        # Also include hypothesis keywords
        hyp_tokens = [w.lower() for w in card.hypothesis.split() if len(w) >= 4]
        keywords.extend(hyp_tokens)

        if keywords and (
            (docs_lower and any(kw in docs_lower for kw in keywords))
            or (rejection_texts and any(
                kw in text for kw in keywords for text in rejection_texts
            ))
        ):
            verdict = "confirmed"

        results.append({"hypothesis": card.hypothesis, "verdict": verdict})

    return results


def format_measurement_summary(result: MeasurementResult) -> str:
    """사람이 읽는 측정 요약 문자열을 반환한다 (cli.py 에서 click.echo 로 출력)."""
    lines: list[str] = [
        f"Session: {result.session_id}",
        f"  cited_ratio : {result.cited_ratio:.1%}",
        f"  must_ratio  : {result.must_ratio:.1%}",
        "  tier distribution:",
    ]
    for tier, count in result.tier_distribution.items():
        lines.append(f"    {tier}: {count}")
    lines.append("  intent_kind distribution:")
    for kind, count in result.intent_kind_distribution.items():
        lines.append(f"    {kind}: {count}")
    if result.foresight_scores:
        lines.append(f"  foresight scores: {len(result.foresight_scores)} cards")
        for score in result.foresight_scores:
            lines.append(f"    [{score['verdict']}] {score['hypothesis'][:60]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O function
# ---------------------------------------------------------------------------

def write_measurement(result: MeasurementResult, session_dir: Path) -> None:
    """MeasurementResult 를 session_dir/measurement.json 에 저장한다.

    session.json 스키마 재확장 금지. stdout 저장 금지.
    """
    out_path = session_dir / "measurement.json"
    out_path.write_text(
        json.dumps(result.to_json(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
