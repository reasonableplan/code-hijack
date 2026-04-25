from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import click

from hijack import __version__
from hijack.core.analyzer import run_full_analysis
from hijack.core.fetcher import fetch_source
from hijack.core.generator import write_output
from hijack.core.harness_export import export_session
from hijack.core.models import SessionResult
from hijack.core.prompts import MVP_CATEGORIES
from hijack.core.session import SessionDiff
from hijack.errors import LLM_001, OUTPUT_001, LLMError, OutputError
from hijack.llm.api import DEFAULT_MODEL, ClaudeAPIClient
from hijack.llm.base import BaseLLM

_COST_PER_TOKEN = 3e-6
_AVG_TOKENS_PER_FILE = 600
_TOKENS_PER_ANALYSIS_CALL = 4000


def _estimate_cost(file_count: int, category_count: int) -> float:
    input_tokens = file_count * _AVG_TOKENS_PER_FILE + category_count * _TOKENS_PER_ANALYSIS_CALL
    output_tokens = category_count * 2000
    return (input_tokens + output_tokens) * _COST_PER_TOKEN


def _load_session_json(path_str: str) -> SessionResult:
    """session.json 또는 세션 디렉토리에서 SessionResult를 로드한다."""
    p = Path(path_str)
    if p.is_dir():
        candidate = p / "session.json"
        if not candidate.exists():
            raise click.BadParameter(f"session.json not found in {p.as_posix()!r}")
        p = candidate
    if not p.exists():
        raise click.BadParameter(f"파일이 없습니다: {p.as_posix()!r}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"session.json 파싱 실패 ({p.as_posix()!r}): {e.msg}") from e
    try:
        return SessionResult.from_json(data)
    except (KeyError, TypeError) as e:
        raise click.BadParameter(f"session.json 스키마 오류 ({p.as_posix()!r}): {e}") from e


def _completed_categories(session: SessionResult) -> list[str]:
    """성공적으로 완료된 카테고리 목록을 반환한다."""
    return [cat.category for cat in session.categories if cat.error is None]


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="code-hijack")
def cli() -> None:
    """시니어 코드베이스를 LLM으로 분석해 AI 에이전트용 규칙을 추출한다."""


@cli.command("analyze")
@click.argument("target")
@click.option("--model", "-m", default=DEFAULT_MODEL, show_default=True, help="LLM 모델 ID")
@click.option("--path", "-p", "subpath", default=None, help="모노레포 서브디렉토리")
@click.option(
    "--categories",
    default=",".join(MVP_CATEGORIES),
    show_default=True,
    help="분석 카테고리 (콤마 구분)",
)
@click.option("--output", "-o", "output_dir", default=None, help="출력 디렉토리")
@click.option("--resume", default=None, metavar="SESSION_JSON",
              help="이전 세션 session.json (완료된 카테고리 스킵)")
@click.option("--dry-run", is_flag=True, help="LLM 호출 없이 예상 비용만 출력")
@click.option("--critic/--no-critic", default=True,
              help="Critic 레이어로 중복/MUST 인플레 재평가 (기본 on, +1 LLM 호출)")
@click.option("--verbose", "-v", is_flag=True, help="상세 로그")
@click.option("--quiet", "-q", is_flag=True, help="진행 메시지 억제")
def analyze(
    target: str,
    model: str,
    subpath: str | None,
    categories: str,
    output_dir: str | None,
    resume: str | None,
    dry_run: bool,
    critic: bool,
    verbose: bool,
    quiet: bool,
) -> None:
    """TARGET 레포를 분석해 규칙 문서를 생성한다.

    TARGET: GitHub URL 또는 로컬 경로
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)

    category_list = [c.strip() for c in categories.split(",") if c.strip()]

    if resume:
        prev = _load_session_json(resume)
        done = _completed_categories(prev)
        skipped = [c for c in category_list if c in done]
        category_list = [c for c in category_list if c not in done]
        if skipped and not quiet:
            click.echo(f"[resume] 스킵: {', '.join(skipped)}")
        if not category_list:
            click.echo("[resume] 모든 카테고리가 이미 완료됐습니다.")
            return

    _run(
        target=target,
        model=model,
        subpath=subpath,
        category_list=category_list,
        output_dir=output_dir,
        dry_run=dry_run,
        critic=critic,
        quiet=quiet,
    )


@cli.command("diff")
@click.argument("session1")
@click.argument("session2")
@click.option("--output", "-o", default=None, metavar="FILE",
              help="diff 결과를 파일로 저장 (기본: stdout)")
def diff_cmd(session1: str, session2: str, output: str | None) -> None:
    """두 세션의 규칙 변경사항을 비교한다.

    SESSION1: 이전 세션 (session.json 또는 세션 디렉토리)
    SESSION2: 최신 세션 (session.json 또는 세션 디렉토리)
    """
    old = _load_session_json(session1)
    new = _load_session_json(session2)
    diff = SessionDiff.compare(old, new)
    md = diff.to_markdown()

    if output:
        Path(output).write_text(md, encoding="utf-8")
        click.echo(f"diff 저장: {output}")
    else:
        click.echo(md)


@cli.command("harness-export")
@click.argument("session")
@click.option("--output", "-o", "output_dir", required=True,
              metavar="DIR",
              help="HarnessAI docs 디렉토리 (conventions.md / guidelines/ 출력 루트)")
def harness_export_cmd(session: str, output_dir: str) -> None:
    """code-hijack 세션을 HarnessAI conventions/guidelines 형식으로 변환한다.

    SESSION: session.json 또는 세션 디렉토리 (raw 분석 결과)

    cross_project scope 의 규칙만 자동 적용. framework_internal 은 제외,
    domain_specific 은 shared-lessons-candidates.md 로 분리.
    """
    session_result = _load_session_json(session)
    output_path = Path(output_dir)
    summary = export_session(session_result, output_path)

    click.echo(f"\n[harness-export] 완료 → {summary.output_dir.as_posix()}")
    click.echo(f"  conventions.md: {summary.conventions_path.relative_to(output_path).as_posix()}")
    click.echo(f"  guidelines: {len(summary.guideline_paths)} files")
    if summary.lesson_candidates_path:
        click.echo(
            f"  lessons (candidate): "
            f"{summary.lesson_candidates_path.relative_to(output_path).as_posix()}"
        )
    click.echo("")
    click.echo(
        f"  scope — cross_project: {summary.cross_project_count}, "
        f"framework_internal: {summary.framework_internal_count} (제외), "
        f"domain_specific: {summary.domain_specific_count} (lesson 후보)"
    )
    click.echo(f"  anti-patterns: {summary.anti_pattern_count}")
    click.echo("")
    click.echo("다음 단계: 출력 파일을 검토 후 HarnessAI 프로젝트의 docs/ 로 복사하세요.")


# ---------------------------------------------------------------------------
# Backward-compat alias — skill.py 및 기존 임포트용
# ---------------------------------------------------------------------------

main = cli


# ---------------------------------------------------------------------------
# Internal analysis runner
# ---------------------------------------------------------------------------

def _run(
    *,
    target: str,
    model: str,
    subpath: str | None,
    category_list: list[str],
    output_dir: str | None,
    dry_run: bool,
    critic: bool,
    quiet: bool,
) -> None:
    if not quiet:
        click.echo(f"\n{'━' * 50}")
        click.echo(f" code-hijack  →  {target}")
        click.echo(f"{'━' * 50}\n")

    if not quiet:
        click.echo("[1/4] 파일 수집 중...")
    files, repo_root = fetch_source(target, subpath=subpath)
    if not quiet:
        click.echo(f"  → {len(files)}개 파일 수집 완료")

    cost = _estimate_cost(len(files), len(category_list))
    if not quiet:
        click.echo("\n[2/4] 비용 추정")
        click.echo(f"  → 예상 비용: ~${cost:.2f} ({model})")
        click.echo(f"  → 카테고리: {', '.join(category_list)}")

    if dry_run:
        click.echo("\n[dry-run] LLM 호출 없이 종료합니다.")
        return

    if not quiet:
        confirmed = click.confirm("\n분석을 시작할까요?", default=True)
        if not confirmed:
            click.echo("취소되었습니다.")
            return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError(LLM_001, "ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    llm: BaseLLM = ClaudeAPIClient(api_key=api_key)

    if not quiet:
        click.echo("\n[3/4] LLM 분석 중...")

    result = asyncio.run(
        run_full_analysis(
            files,
            repo_root,
            categories=category_list,
            llm=llm,
            model=model,
            target=target,
            critic=critic,
        )
    )

    base = Path(output_dir) if output_dir else repo_root / "docs" / "hijacked"
    integrated = base / "integrated"
    if integrated.exists() and not quiet:
        prompt = f"\n기존 통합 파일({integrated.as_posix()})을 덮어쓸까요?"
        if not click.confirm(prompt, default=True):
            raise OutputError(OUTPUT_001, f"덮어쓰기 거부됨: {integrated.as_posix()}")
    write_output(result, base)

    if not quiet:
        click.echo("\n[4/4] 완료!")
        click.echo(f"\n세션 파일: {(base / result.session_id).as_posix()}")
        click.echo(f"통합 파일: {(base / 'integrated').as_posix()}")
        failed = [c.category for c in result.categories if c.error]
        if failed:
            click.echo(f"\n⚠️  실패한 카테고리: {', '.join(failed)}", err=True)
