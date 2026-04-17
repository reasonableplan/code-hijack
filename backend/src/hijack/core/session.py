from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

from hijack.core.models import AnalysisRule, SessionResult

_COMPARED_FIELDS = ("priority", "confidence", "layer", "reason", "ref_files")


def create_session_id(target: str) -> str:
    """'YYYY-MM-DD_<repo_name>' 형식 세션 ID를 반환한다."""
    date_str = datetime.date.today().strftime("%Y-%m-%d")

    if re.match(r"^(https?://|git@)", target):
        segment = target.rstrip("/").split("/")[-1]
        repo_name = re.sub(r"\.git$", "", segment)
    else:
        repo_name = Path(target).name

    if not repo_name:
        repo_name = "unknown"

    return f"{date_str}_{repo_name}"


def get_output_dir(base_dir: Path, session_id: str) -> Path:
    """세션 출력 디렉토리 Path를 반환한다. 디렉토리를 생성한다."""
    output_dir = base_dir / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_integrated_dir(base_dir: Path) -> Path:
    """통합 출력 디렉토리 Path를 반환한다. 디렉토리를 생성하지 않는다."""
    return base_dir / "integrated"


@dataclass
class RuleChange:
    """동일한 rule 텍스트를 가지지만 속성이 달라진 규칙."""

    rule: str
    old: AnalysisRule
    new: AnalysisRule
    changed_fields: list[str]


@dataclass
class SessionDiff:
    """두 세션 간 규칙 변경사항."""

    added: list[AnalysisRule] = field(default_factory=list)
    removed: list[AnalysisRule] = field(default_factory=list)
    changed: list[RuleChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.removed and not self.changed

    @classmethod
    def compare(cls, old: SessionResult, new: SessionResult) -> SessionDiff:
        """두 SessionResult 의 모든 규칙을 비교해 diff를 반환한다.

        규칙 동일성 기준: `rule` 텍스트 (대소문자 민감).
        비교 속성: priority, confidence, layer, reason, ref_files.
        """
        old_rules = _index_rules(old)
        new_rules = _index_rules(new)

        old_keys = set(old_rules)
        new_keys = set(new_rules)

        added = [new_rules[k] for k in sorted(new_keys - old_keys)]
        removed = [old_rules[k] for k in sorted(old_keys - new_keys)]

        changed: list[RuleChange] = []
        for key in sorted(old_keys & new_keys):
            diff_fields = _diff_fields(old_rules[key], new_rules[key])
            if diff_fields:
                changed.append(
                    RuleChange(
                        rule=key,
                        old=old_rules[key],
                        new=new_rules[key],
                        changed_fields=diff_fields,
                    )
                )

        return cls(added=added, removed=removed, changed=changed)

    def to_markdown(self) -> str:
        """diff 를 마크다운 형식으로 반환한다."""
        if self.is_empty:
            return "No changes between sessions."

        lines: list[str] = []
        if self.added:
            lines += [f"## Added ({len(self.added)})", ""]
            for r in self.added:
                lines.append(f"- [{r.priority}/{r.layer}] {r.rule}")
            lines.append("")

        if self.removed:
            lines += [f"## Removed ({len(self.removed)})", ""]
            for r in self.removed:
                lines.append(f"- [{r.priority}/{r.layer}] {r.rule}")
            lines.append("")

        if self.changed:
            lines += [f"## Changed ({len(self.changed)})", ""]
            for c in self.changed:
                lines.append(f"- {c.rule}")
                lines.append(f"  Changed fields: {', '.join(c.changed_fields)}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _index_rules(session: SessionResult) -> dict[str, AnalysisRule]:
    """SessionResult 의 모든 규칙을 rule 텍스트 키로 인덱싱한다."""
    index: dict[str, AnalysisRule] = {}
    for cat in session.categories:
        for rule in cat.rules:
            index[rule.rule] = rule
    return index


def _diff_fields(old: AnalysisRule, new: AnalysisRule) -> list[str]:
    """두 규칙 사이에서 달라진 필드 이름 목록을 반환한다."""
    return [f for f in _COMPARED_FIELDS if getattr(old, f) != getattr(new, f)]
