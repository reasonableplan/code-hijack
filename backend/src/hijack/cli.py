"""CLI 진입점 — Claude API를 사용하는 독립 실행 모드."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import time
from pathlib import Path

import click

from hijack.core.analyzer import run_full_analysis
from hijack.core.fetcher import fetch_source
from hijack.core.generator import write_output
from hijack.core.models import SessionResult
from hijack.core.preprocessor import build_file_summary_for_llm, preprocess
from hijack.core.prompts import MVP_CATEGORIES
from hijack.core.session import create_session_id, get_output_dir
from hijack.llm.api import ClaudeAPIClient

logger = logging.getLogger("hijack")


async def _run(
    target: str,
    model: str,
    output: str | None,
    categories: list[str],
    dry_run: bool,
) -> None:
    click.echo("━" * 50)
    click.echo(f" code-hijack — {target}")
    click.echo("━" * 50)
    click.echo()

    # 1단계: 파일 수집
    click.echo("[1/4] 파일 수집 중...")
    temp_dir = None
    try:
        files, structure_map, temp_dir = fetch_source(target)
    except RuntimeError as exc:
        click.echo(f"오류: {exc}", err=True)
        sys.exit(1)

    if not files:
        click.echo("오류: Python 또는 TypeScript 파일을 찾을 수 없습니다.", err=True)
        sys.exit(1)

    py_count = sum(1 for f in files if f.language == "python")
    ts_count = sum(1 for f in files if f.language == "typescript")
    click.echo(f"  {len(files)}개 파일 발견 (Python {py_count}개, TypeScript {ts_count}개)")

    # 2단계: 핵심 파일 선별
    click.echo("\n[2/4] 핵심 파일 선별 중...")
    prep = preprocess(files, structure_map)
    click.echo(f"  휴리스틱 후보: {len(prep.classified)}개 파일")
    click.echo(f"  예상 LLM 호출: {len(categories) + 1}회")

    if dry_run:
        click.echo("\n[DRY RUN] 분석 대상 카테고리:")
        for cat in categories:
            click.echo(f"  - {cat}")
        summary = build_file_summary_for_llm(prep)
        click.echo(f"\n파일 요약:\n{summary}")
        return

    if not click.confirm("\n  분석을 계속할까요?", default=True):
        click.echo("중단됨.")
        return

    # 3단계: 카테고리별 분석
    click.echo(f"\n[3/4] {len(categories)}개 카테고리 분석 중...")
    llm = ClaudeAPIClient(model=model)

    start = time.time()
    results = await run_full_analysis(llm, prep, categories)
    duration = time.time() - start

    for result in results:
        click.echo(
            f"\n  ✓ {result.category}: "
            f"규칙 {len(result.rules)}개, 체크리스트 {len(result.checklist)}개"
        )

    # 4단계: 출력 생성
    click.echo("\n[4/4] 출력 파일 생성 중...")

    session_id = create_session_id(target)
    local_path = Path(target) if Path(target).is_dir() else Path(".")
    output_dir = Path(output) if output else get_output_dir(local_path)

    session = SessionResult(
        session_id=session_id,
        target=target,
        model=model,
        selected_files=[str(cf.file.path) for cf in prep.classified],
        categories=results,
        analysis_duration_seconds=duration,
        project_structure=structure_map,
    )

    created = write_output(session, output_dir)

    click.echo(f"\n✅ 분석 완료! ({duration:.1f}초)")
    click.echo("\n출력 파일:")
    for path in created:
        click.echo(f"  {path}")

    # 정리
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)


@click.command()
@click.argument("target")
@click.option("--model", "-m", default="claude-sonnet-4-6", help="사용할 LLM 모델.")
@click.option("--output", "-o", default=None, help="출력 디렉토리.")
@click.option(
    "--categories", "-c",
    default=None,
    help="분석할 카테고리 (콤마 구분, 기본: architecture,coding_style,api_design).",
)
@click.option("--dry-run", is_flag=True, help="비용 추정만 하고 실행하지 않음.")
@click.option("--verbose", "-v", is_flag=True, help="상세 로그.")
def main(
    target: str,
    model: str,
    output: str | None,
    categories: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """TARGET의 코드 스타일을 분석하여 AI 에이전트용 규칙을 생성한다.

    TARGET은 로컬 디렉토리 경로 또는 GitHub URL.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    cats = categories.split(",") if categories else MVP_CATEGORIES
    asyncio.run(_run(target, model, output, cats, dry_run))


if __name__ == "__main__":
    main()
