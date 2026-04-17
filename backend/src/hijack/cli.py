from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click

from hijack import __version__
from hijack.core.analyzer import run_full_analysis
from hijack.core.fetcher import fetch_source
from hijack.core.generator import write_output
from hijack.errors import LLM_001, OUTPUT_001, LLMError, OutputError
from hijack.llm.api import DEFAULT_MODEL, ClaudeAPIClient
from hijack.llm.base import BaseLLM

_MVP_CATEGORIES = ["architecture", "coding_style", "api_design"]
_COST_PER_TOKEN = 3e-6  # claude-sonnet-4-6 approximate blended $/token
_AVG_TOKENS_PER_FILE = 600
_TOKENS_PER_ANALYSIS_CALL = 4000  # prompt overhead per category


def _estimate_cost(file_count: int, category_count: int) -> float:
    input_tokens = file_count * _AVG_TOKENS_PER_FILE + category_count * _TOKENS_PER_ANALYSIS_CALL
    output_tokens = category_count * 2000
    return (input_tokens + output_tokens) * _COST_PER_TOKEN


@click.command()
@click.argument("target")
@click.option("--model", "-m", default=DEFAULT_MODEL, show_default=True, help="LLM 모델 ID")
@click.option("--path", "-p", "subpath", default=None, help="모노레포 서브디렉토리")
@click.option(
    "--categories",
    default=",".join(_MVP_CATEGORIES),
    show_default=True,
    help="분석 카테고리 (콤마 구분)",
)
@click.option("--output", "-o", "output_dir", default=None, help="출력 디렉토리")
@click.option("--dry-run", is_flag=True, help="LLM 호출 없이 예상 비용만 출력")
@click.option("--verbose", "-v", is_flag=True, help="상세 로그")
@click.option("--quiet", "-q", is_flag=True, help="진행 메시지 억제")
@click.version_option(__version__, prog_name="code-hijack")
@click.pass_context
def main(
    ctx: click.Context,
    target: str,
    model: str,
    subpath: str | None,
    categories: str,
    output_dir: str | None,
    dry_run: bool,
    verbose: bool,
    quiet: bool,
) -> None:
    """시니어 코드베이스를 LLM으로 분석해 AI 에이전트용 규칙을 추출한다.

    TARGET: GitHub URL 또는 로컬 경로
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)

    category_list = [c.strip() for c in categories.split(",") if c.strip()]

    _run(
        target=target,
        model=model,
        subpath=subpath,
        category_list=category_list,
        output_dir=output_dir,
        dry_run=dry_run,
        quiet=quiet,
    )


def _run(
    *,
    target: str,
    model: str,
    subpath: str | None,
    category_list: list[str],
    output_dir: str | None,
    dry_run: bool,
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
        click.echo(f"\n예상 비용: ~${cost:.2f} ({model})")
        click.echo(f"카테고리: {', '.join(category_list)}")

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
