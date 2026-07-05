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
    # SATD comment-citation metrics (W2 strengthening). satd_supplied_count is
    # how many SATD items the miner surfaced; comment_cited_rule_count /
    # comment_cited_ref_count count how many of those were actually cited by
    # rules as kind="comment" evidence; satd_citation_ratio is the yield.
    satd_supplied_count: int = 0
    comment_cited_rule_count: int = 0
    comment_cited_ref_count: int = 0
    satd_citation_ratio: float = 0.0
    # W4a exemplar verbatim-ratio metrics. exemplar_checked_count is how many
    # rules had exemplar_verbatim computed (good_example non-empty);
    # exemplar_verbatim_ratio is the fraction of those that were True.
    exemplar_checked_count: int = 0
    exemplar_verbatim_ratio: float = 0.0
    # Behavioral-probe metrics. probed_rule_count is how many rules carry a
    # ProbeRecord (regardless of verdict); probe_discriminated_count is how
    # many of those verdicts are "discriminated".
    probed_rule_count: int = 0
    probe_discriminated_count: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cited_ratio": self.cited_ratio,
            "must_ratio": self.must_ratio,
            "tier_distribution": self.tier_distribution,
            "intent_kind_distribution": self.intent_kind_distribution,
            "foresight_scores": self.foresight_scores,
            "satd_supplied_count": self.satd_supplied_count,
            "comment_cited_rule_count": self.comment_cited_rule_count,
            "comment_cited_ref_count": self.comment_cited_ref_count,
            "satd_citation_ratio": self.satd_citation_ratio,
            "exemplar_checked_count": self.exemplar_checked_count,
            "exemplar_verbatim_ratio": self.exemplar_verbatim_ratio,
            "probed_rule_count": self.probed_rule_count,
            "probe_discriminated_count": self.probe_discriminated_count,
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
            satd_supplied_count=data.get("satd_supplied_count", 0),
            comment_cited_rule_count=data.get("comment_cited_rule_count", 0),
            comment_cited_ref_count=data.get("comment_cited_ref_count", 0),
            satd_citation_ratio=data.get("satd_citation_ratio", 0.0),
            exemplar_checked_count=data.get("exemplar_checked_count", 0),
            exemplar_verbatim_ratio=data.get("exemplar_verbatim_ratio", 0.0),
            probed_rule_count=data.get("probed_rule_count", 0),
            probe_discriminated_count=data.get("probe_discriminated_count", 0),
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
    # 969e3d2 이후 세션이 pr_decisions 를 직접 들고 있다 — 인자 미전달 시
    # 세션 것을 쓴다 (measure CLI 가 세션만으로 자급하도록).
    if pr_decisions is None:
        pr_decisions = session.pr_decisions
    if pr_decisions is not None:
        raw_decisions = (
            pr_decisions.get("decisions", [])
            if isinstance(pr_decisions, dict)
            else getattr(pr_decisions, "decisions", [])
        )
        for decision in raw_decisions:
            kind = (
                decision.get("intent_kind", "")
                if isinstance(decision, dict)
                else getattr(decision, "intent_kind", "")
            )
            if kind in intent_kind_distribution:
                intent_kind_distribution[kind] += 1

    satd_supplied_count = _satd_supplied_count(session)
    comment_cited_rule_count = 0
    comment_refs: set[str] = set()
    for r in rules:
        rule_has_comment = False
        for e in r.evidence:
            if e.kind == "comment":
                rule_has_comment = True
                if e.ref:
                    comment_refs.add(e.ref)
        if rule_has_comment:
            comment_cited_rule_count += 1
    comment_cited_ref_count = len(comment_refs)
    satd_citation_ratio = (
        comment_cited_ref_count / satd_supplied_count if satd_supplied_count > 0 else 0.0
    )

    checked = [r for r in rules if r.exemplar_verbatim is not None]
    exemplar_checked_count = len(checked)
    exemplar_verbatim_ratio = (
        sum(1 for r in checked if r.exemplar_verbatim) / exemplar_checked_count
        if exemplar_checked_count > 0
        else 0.0
    )

    probed_rules = [r for r in rules if r.probe is not None]
    probed_rule_count = len(probed_rules)
    probe_discriminated_count = sum(
        1 for r in probed_rules if r.probe.verdict == "discriminated"
    )

    return MeasurementResult(
        session_id=session.session_id,
        cited_ratio=cited_ratio,
        must_ratio=must_ratio,
        tier_distribution=tier_distribution,
        intent_kind_distribution=intent_kind_distribution,
        foresight_scores=[],
        satd_supplied_count=satd_supplied_count,
        comment_cited_rule_count=comment_cited_rule_count,
        comment_cited_ref_count=comment_cited_ref_count,
        satd_citation_ratio=satd_citation_ratio,
        exemplar_checked_count=exemplar_checked_count,
        exemplar_verbatim_ratio=exemplar_verbatim_ratio,
        probed_rule_count=probed_rule_count,
        probe_discriminated_count=probe_discriminated_count,
    )


def _satd_supplied_count(session: SessionResult) -> int:
    """Count of session.satd_items entries — 0 when absent.

    `session.satd_items` is duck-typed: a satd.SatdItems dataclass (`.items`)
    or a raw dict from session.json (`["items"]`), same defensive pattern as
    evidence._valid_comment_refs_from_session.
    """
    satd_items = session.satd_items
    if not satd_items:
        return 0
    if isinstance(satd_items, dict):
        return len(satd_items.get("items", []))
    return len(getattr(satd_items, "items", []))


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
        "satd_citation_ratio_delta": round(m2.satd_citation_ratio - m1.satd_citation_ratio, 10),
        "exemplar_verbatim_ratio_delta": round(
            m2.exemplar_verbatim_ratio - m1.exemplar_verbatim_ratio, 10
        ),
        "probed_rule_count_delta": m2.probed_rule_count - m1.probed_rule_count,
        "probe_discriminated_count_delta": (
            m2.probe_discriminated_count - m1.probe_discriminated_count
        ),
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
    lines.append(
        f"  satd_citation_ratio: {result.satd_citation_ratio:.1%} "
        f"({result.comment_cited_ref_count}/{result.satd_supplied_count} refs, "
        f"{result.comment_cited_rule_count} rules)"
    )
    lines.append(
        f"  exemplar_verbatim_ratio: {result.exemplar_verbatim_ratio:.1%} "
        f"({result.exemplar_checked_count} checked)"
    )
    lines.append(
        f"  probes: {result.probe_discriminated_count}/{result.probed_rule_count} discriminated"
    )
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
