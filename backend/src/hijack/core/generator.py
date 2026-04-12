"""출력 생성기 — 분석 결과를 다중 형식 문서로 변환한다."""

from __future__ import annotations

from pathlib import Path

from hijack.core.models import CategoryResult, SessionResult


def generate_claude_md(session: SessionResult) -> str:
    """CLAUDE.md 생성 — AI 에이전트가 가장 먼저 읽는 핵심 규칙 파일."""
    lines = [
        f"# 코드 스타일 규칙 — {session.target}에서 추출\n",
        f"> code-hijack이 {session.timestamp[:10]}에 생성",
        f"> 모델: {session.model}",
        f"> 분석 파일: {len(session.selected_files)}개\n",
        "---\n",
    ]

    # 전체 카테고리에서 MUST/SHOULD 규칙 수집
    must_rules: list[tuple[str, str, list[str]]] = []
    should_rules: list[tuple[str, str, list[str]]] = []
    all_checklist: list[str] = []

    for cat in session.categories:
        for rule in cat.rules:
            entry = (cat.category, rule.rule, rule.ref_files)
            if rule.priority == "MUST":
                must_rules.append(entry)
            else:
                should_rules.append(entry)
        all_checklist.extend(cat.checklist)

    # 필수 규칙
    if must_rules:
        lines.append("## 필수 규칙 (MUST)\n")
        for i, (cat, rule, refs) in enumerate(must_rules, 1):
            lines.append(f"{i}. **[{cat}]** {rule}")
            if refs:
                lines.append(f"   - 📁 참조: {', '.join(refs)}")
        lines.append("")

    # 권장 규칙
    if should_rules:
        lines.append("## 권장 규칙 (SHOULD)\n")
        for i, (cat, rule, refs) in enumerate(should_rules, 1):
            lines.append(f"{i}. **[{cat}]** {rule}")
            if refs:
                lines.append(f"   - 📁 참조: {', '.join(refs)}")
        lines.append("")

    # 참조 파일 맵
    ref_map: dict[str, list[str]] = {}
    for cat in session.categories:
        for rule in cat.rules:
            for ref in rule.ref_files:
                ref_map.setdefault(ref, []).append(rule.rule[:60])
    if ref_map:
        lines.append("## 참조 파일 맵\n")
        lines.append("코드 작성 전 관련 파일을 먼저 읽어라:\n")
        for ref, rules in sorted(ref_map.items()):
            lines.append(f"- **{ref}**")
            for r in rules[:3]:
                lines.append(f"  - {r}")
        lines.append("")

    # 체크리스트
    if all_checklist:
        lines.append("## 코드 제출 전 체크리스트\n")
        for item in all_checklist:
            lines.append(f"- [ ] {item}")
        lines.append("")

    return "\n".join(lines)


def generate_system_prompt(session: SessionResult) -> str:
    """system-prompt.md 생성 — AI 에이전트용 시스템 프롬프트."""
    lines = [
        f"# 시스템 프롬프트 — {session.target} 스타일\n",
        f"> code-hijack이 {session.timestamp[:10]}에 생성\n",
        "---\n",
        "너는 이 프로젝트의 시니어 개발자다. "
        "기존 코드베이스의 스타일, 아키텍처, 설계 철학을 정확히 따라서 코드를 짠다.\n",
        "## 프로젝트 스타일 규칙\n",
    ]

    for cat in session.categories:
        lines.append(f"### {cat.category}\n")
        if cat.design_intent:
            lines.append(f"**설계 의도:** {cat.design_intent}\n")

        for rule in cat.rules:
            lines.append(f"- **[{rule.priority}]** {rule.rule}")
            if rule.good_example:
                lines.append("  ✅ 올바른 예시:")
                lines.append(f"  ```\n  {rule.good_example}\n  ```")
            if rule.bad_example:
                lines.append("  ❌ 이렇게 하지 마라:")
                lines.append(f"  ```\n  {rule.bad_example}\n  ```")
        lines.append("")

    return "\n".join(lines)


def generate_session_meta(session: SessionResult) -> str:
    """세션 메타데이터 파일을 생성한다."""
    lines = [
        f"# 분석 세션 — {session.session_id}\n",
        f"- **대상**: {session.target}",
        f"- **시간**: {session.timestamp}",
        f"- **모델**: {session.model}",
        f"- **소요 시간**: {session.analysis_duration_seconds:.1f}초",
        f"- **분석 파일**: {len(session.selected_files)}개\n",
        "## 선별된 파일\n",
    ]
    for f in session.selected_files:
        lines.append(f"- {f}")
    lines.append("")

    lines.append("## 분석 카테고리\n")
    for cat in session.categories:
        lines.append(
            f"- **{cat.category}**: 규칙 {len(cat.rules)}개, "
            f"체크리스트 {len(cat.checklist)}개"
        )
    lines.append("")

    return "\n".join(lines)


def write_output(session: SessionResult, output_dir: Path) -> list[Path]:
    """모든 출력 파일을 디스크에 기록한다.

    Args:
        session: 전체 분석 결과.
        output_dir: 기본 출력 디렉토리 (예: target_project/docs/hijacked/).

    Returns:
        생성된 파일 경로 목록.
    """
    created: list[Path] = []

    # 세션 디렉토리
    session_dir = output_dir / session.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # 메타 파일
    meta_path = session_dir / "meta.md"
    meta_path.write_text(generate_session_meta(session), encoding="utf-8")
    created.append(meta_path)

    # 카테고리별 raw 결과
    for cat in session.categories:
        cat_path = session_dir / f"{cat.category}.md"
        cat_path.write_text(cat.raw_llm_output, encoding="utf-8")
        created.append(cat_path)

    # 세션 JSON
    json_path = session_dir / "session.json"
    json_path.write_text(session.to_json(), encoding="utf-8")
    created.append(json_path)

    # 통합 디렉토리
    integrated_dir = output_dir / "integrated"
    integrated_dir.mkdir(parents=True, exist_ok=True)

    claude_path = integrated_dir / "CLAUDE.md"
    claude_path.write_text(generate_claude_md(session), encoding="utf-8")
    created.append(claude_path)

    prompt_path = integrated_dir / "system-prompt.md"
    prompt_path.write_text(generate_system_prompt(session), encoding="utf-8")
    created.append(prompt_path)

    return created
