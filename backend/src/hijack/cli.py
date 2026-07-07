from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import click

from hijack import __version__
from hijack.core.analyzer import run_full_analysis
from hijack.core.apply import apply_session_to_target, render_applied_md
from hijack.core.fetcher import fetch_source
from hijack.core.generator import write_output
from hijack.core.harness_export import export_session
from hijack.core.measure import (
    calc_session_metrics,
    diff_sessions,
    format_measurement_summary,
    write_measurement,
)
from hijack.core.models import SessionResult
from hijack.core.prompts import MVP_CATEGORIES
from hijack.core.session import SessionDiff
from hijack.core.target_stack import TargetStack, normalize_pkg_name
from hijack.errors import LLM_001, OUTPUT_001, LLMError, OutputError
from hijack.llm.base import DEFAULT_MODEL, BaseLLM

# claude-sonnet-5 sticker pricing: $3/MTok input, $15/MTok output.
_COST_PER_INPUT_TOKEN = 3e-6
_COST_PER_OUTPUT_TOKEN = 15e-6
_AVG_TOKENS_PER_FILE = 600
_TOKENS_PER_ANALYSIS_CALL = 4000


def _estimate_cost(file_count: int, category_count: int) -> float:
    input_tokens = file_count * _AVG_TOKENS_PER_FILE + category_count * _TOKENS_PER_ANALYSIS_CALL
    output_tokens = category_count * 2000
    return input_tokens * _COST_PER_INPUT_TOKEN + output_tokens * _COST_PER_OUTPUT_TOKEN


def _load_session_json(path_str: str) -> SessionResult:
    """session.json 또는 세션 디렉토리에서 SessionResult를 로드한다."""
    p = Path(path_str)
    if p.is_dir():
        candidate = p / "session.json"
        if not candidate.exists():
            raise click.BadParameter(f"session.json not found in {p.as_posix()!r}")
        p = candidate
    if not p.exists():
        raise click.BadParameter(f"File not found: {p.as_posix()!r}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Failed to parse session.json ({p.as_posix()!r}): {e.msg}") from e
    try:
        return SessionResult.from_json(data)
    except (KeyError, TypeError) as e:
        raise click.BadParameter(f"session.json schema error ({p.as_posix()!r}): {e}") from e


def _completed_categories(session: SessionResult) -> list[str]:
    """성공적으로 완료된 카테고리 목록을 반환한다."""
    return [cat.category for cat in session.categories if cat.error is None]


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="code-hijack")
def cli() -> None:
    """Analyze a senior codebase with an LLM and extract AI-agent coding rules."""


@cli.command("analyze")
@click.argument("target")
@click.option("--model", "-m", default=DEFAULT_MODEL, show_default=True, help="LLM model ID")
@click.option("--path", "-p", "subpath", default=None, help="Monorepo subdirectory")
@click.option(
    "--categories",
    default=",".join(MVP_CATEGORIES),
    show_default=True,
    help="Categories to analyze (comma-separated)",
)
@click.option("--output", "-o", "output_dir", default=None, help="Output directory")
@click.option("--resume", default=None, metavar="SESSION_JSON",
              help="Previous session.json (skips completed categories)")
@click.option("--dry-run", is_flag=True, help="Print the estimated cost only, no LLM calls")
@click.option("--critic/--no-critic", default=True,
              help="Re-evaluate duplicates/MUST inflation with the critic layer "
                   "(default on, +1 LLM call)")
@click.option("--refresh-prs", is_flag=True,
              help="Clear the PR cache and re-fetch (Phase A1)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress messages")
def analyze(
    target: str,
    model: str,
    subpath: str | None,
    categories: str,
    output_dir: str | None,
    resume: str | None,
    dry_run: bool,
    critic: bool,
    refresh_prs: bool,
    verbose: bool,
    quiet: bool,
) -> None:
    """Analyze the TARGET repo and generate rule documents.

    TARGET: GitHub URL or local path
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
            click.echo(f"[resume] skipping: {', '.join(skipped)}")
        if not category_list:
            click.echo("[resume] all categories already completed.")
            return

    _run(
        target=target,
        model=model,
        subpath=subpath,
        category_list=category_list,
        output_dir=output_dir,
        dry_run=dry_run,
        critic=critic,
        refresh_prs=refresh_prs,
        quiet=quiet,
    )


@cli.command("diff")
@click.argument("session1")
@click.argument("session2")
@click.option("--output", "-o", default=None, metavar="FILE",
              help="Write the diff to a file (default: stdout)")
def diff_cmd(session1: str, session2: str, output: str | None) -> None:
    """Compare rule changes between two sessions.

    SESSION1: older session (session.json or session directory)
    SESSION2: newer session (session.json or session directory)
    """
    old = _load_session_json(session1)
    new = _load_session_json(session2)
    diff = SessionDiff.compare(old, new)
    md = diff.to_markdown()

    if output:
        Path(output).write_text(md, encoding="utf-8")
        click.echo(f"diff written: {output}")
    else:
        click.echo(md)


@cli.command("measure")
@click.argument("session1")
@click.argument("session2", required=False, default=None)
def measure_cmd(session1: str, session2: str | None) -> None:
    """Compute session metrics, or compare two sessions.

    SESSION1: session.json or session directory (single measurement, or comparison base)
    SESSION2: (optional) session.json or session directory — compared against SESSION1
    """
    s1 = _load_session_json(session1)
    m1 = calc_session_metrics(s1)

    p1 = Path(session1)
    session_dir1 = p1 if p1.is_dir() else p1.parent
    write_measurement(m1, session_dir1)

    if session2 is None:
        click.echo(format_measurement_summary(m1))
    else:
        s2 = _load_session_json(session2)
        m2 = calc_session_metrics(s2)
        delta = diff_sessions(m1, m2)
        click.echo(f"session_id_before : {delta['session_id_before']}")
        click.echo(f"session_id_after  : {delta['session_id_after']}")
        click.echo(f"cited_ratio_delta : {delta['cited_ratio_delta']:+.4f}")
        click.echo(f"must_ratio_delta  : {delta['must_ratio_delta']:+.4f}")
        click.echo("tier_distribution_delta:")
        for tier, count in delta["tier_distribution_delta"].items():
            click.echo(f"  {tier}: {count:+d}")
        click.echo("intent_kind_distribution_delta:")
        for kind, count in delta["intent_kind_distribution_delta"].items():
            click.echo(f"  {kind}: {count:+d}")
        click.echo(f"satd_citation_ratio_delta: {delta['satd_citation_ratio_delta']:+.4f}")


@cli.command("harness-export")
@click.argument("session")
@click.option("--output", "-o", "output_dir", required=True,
              metavar="DIR",
              help="HarnessAI docs directory (output root for conventions.md / guidelines/)")
def harness_export_cmd(session: str, output_dir: str) -> None:
    """Convert a code-hijack session into HarnessAI conventions/guidelines format.

    SESSION: session.json or session directory (raw analysis output)

    Only cross_project rules are auto-applied. framework_internal is excluded;
    domain_specific goes to shared-lessons-candidates.md for review.
    """
    session_result = _load_session_json(session)
    output_path = Path(output_dir)
    summary = export_session(session_result, output_path)

    click.echo(f"\n[harness-export] done → {summary.output_dir.as_posix()}")
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
        f"framework_internal: {summary.framework_internal_count} (excluded), "
        f"domain_specific: {summary.domain_specific_count} (lesson candidates)"
    )
    click.echo(f"  anti-patterns: {summary.anti_pattern_count}")
    click.echo("")
    click.echo(
        "Next step: review the output files, then copy them into your "
        "HarnessAI project's docs/."
    )


@cli.command("apply")
@click.argument("session")
@click.argument("target_repo", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", default=None, metavar="FILE",
              help="Output path (default: <target_repo>/CLAUDE.md)")
@click.option("--strict", is_flag=True,
              help="Exclude reference_only rules from the output")
@click.option(
    "--stack",
    default=None,
    metavar="PKGS",
    help="Override target stack detection. Comma-separated package names "
         "(e.g., 'fastapi,pydantic,sqlalchemy'). Skips pyproject.toml/package.json "
         "parsing entirely.",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress messages")
def apply_cmd(
    session: str,
    target_repo: str,
    output: str | None,
    strict: bool,
    stack: str | None,
    quiet: bool,
) -> None:
    """Adapt a senior session's rules to the target repo stack and generate CLAUDE.md.

    SESSION: session.json or session directory from a previous `analyze` run.
    TARGET_REPO: local project path to apply the rules to.
    """
    session_result = _load_session_json(session)
    target_path = Path(target_repo)
    out_path = Path(output) if output else target_path / "CLAUDE.md"

    # Build override TargetStack when --stack is provided
    override_stack: TargetStack | None = None
    if stack is not None:
        raw_pkgs = [p.strip() for p in stack.split(",") if p.strip()]
        normalized = frozenset(normalize_pkg_name(p) for p in raw_pkgs if normalize_pkg_name(p))
        override_stack = TargetStack(
            repo_root=target_path,
            python_deps=normalized,
            js_deps=frozenset(),
            detected_files=["<--stack override>"],
        )

    if out_path.exists() and not quiet:
        prompt = f"\nOverwrite existing file ({out_path.as_posix()})?"
        if not click.confirm(prompt, default=True):
            click.echo("Cancelled.")
            return

    result = apply_session_to_target(
        session_result, target_path, strict=strict, target_stack=override_stack
    )

    # Warn when stack detection found nothing and user did not override via --stack
    if stack is None and result.target_stack.is_empty and not quiet:
        click.echo(
            "[apply] Warning: no dependencies detected in target_repo "
            "(no pyproject.toml or package.json). All framework_internal rules will "
            'fall to "For Reference" section. '
            "Use --stack <pkg1,pkg2,...> to override.",
            err=True,
        )
    md = render_applied_md(result, source_target=session_result.target)
    out_path.write_text(md, encoding="utf-8")

    if not quiet:
        by_v = result.by_verdict
        as_is = by_v.get("as_is", [])
        universal = [a for a in as_is if (a.rule.scope or "cross_project") == "cross_project"]
        stack_specific = [a for a in as_is if (a.rule.scope or "cross_project") != "cross_project"]
        adapted = by_v.get("adapted", [])
        domain = by_v.get("domain_adapt", [])
        reference = by_v.get("reference_only", [])

        stack = result.target_stack
        stack_pkgs = ", ".join(sorted(stack.all_deps)) if stack.all_deps else "none"

        adapted_note = ""
        if adapted:
            senior_pkgs = sorted({p for a in adapted for p in a.matched_packages})
            target_pkgs = sorted(stack.all_deps)
            if senior_pkgs and target_pkgs:
                adapted_note = (
                    f"senior used {', '.join(senior_pkgs)}; "
                    f"you use {', '.join(target_pkgs)} — translation noted"
                )
            else:
                adapted_note = "translation noted"

        click.echo(
            f"\n[apply] Applied {result.total_input_rules} rules to {target_repo}:"
        )
        click.echo(f"  - {len(universal)} universal (apply directly)")
        click.echo(
            f"  - {len(stack_specific)} stack-specific"
            f" (your project uses {stack_pkgs})"
        )
        if adapted_note:
            click.echo(f"  - {len(adapted)} adapted ({adapted_note})")
        else:
            click.echo(f"  - {len(adapted)} adapted")
        click.echo(f"  - {len(domain)} domain (review literal values)")
        click.echo(f"  - {len(reference)} reference-only (incompatible)")
        click.echo(f"Output: {out_path.as_posix()}")


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
    refresh_prs: bool = False,
    quiet: bool,
) -> None:
    if not quiet:
        click.echo(f"\n{'━' * 50}")
        click.echo(f" code-hijack  →  {target}")
        click.echo(f"{'━' * 50}\n")

    if not quiet:
        click.echo("[1/4] Collecting files...")
    files, repo_root = fetch_source(target, subpath=subpath)
    if not quiet:
        click.echo(f"  → {len(files)} files collected")

    cost = _estimate_cost(len(files), len(category_list))
    if not quiet:
        click.echo("\n[2/4] Cost estimate")
        click.echo(f"  → Estimated cost: ~${cost:.2f} ({model})")
        click.echo(f"  → Categories: {', '.join(category_list)}")

    if dry_run:
        click.echo("\n[dry-run] Exiting without LLM calls.")
        return

    if not quiet:
        confirmed = click.confirm("\nStart the analysis?", default=True)
        if not confirmed:
            click.echo("Cancelled.")
            return

    base = Path(output_dir) if output_dir else repo_root / "docs" / "hijacked"
    llm: BaseLLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError(LLM_001, "ANTHROPIC_API_KEY is not set.")
    # lazy import: measure/diff 등 API 불필요 커맨드가 anthropic 없이 돌도록
    from hijack.llm.api import ClaudeAPIClient

    llm = ClaudeAPIClient(api_key=api_key)

    if not quiet:
        click.echo("\n[3/4] Running LLM analysis...")

    result = asyncio.run(
        run_full_analysis(
            files,
            repo_root,
            categories=category_list,
            llm=llm,
            model=model,
            target=target,
            critic=critic,
            refresh_prs=refresh_prs,
        )
    )

    integrated = base / "integrated"
    if integrated.exists() and not quiet:
        prompt = f"\nOverwrite existing integrated files ({integrated.as_posix()})?"
        if not click.confirm(prompt, default=True):
            raise OutputError(OUTPUT_001, f"Overwrite declined: {integrated.as_posix()}")
    write_output(result, base)

    if not quiet:
        click.echo("\n[4/4] Done!")
        click.echo(f"\nSession files: {(base / result.session_id).as_posix()}")
        click.echo(f"Integrated files: {(base / 'integrated').as_posix()}")
        failed = [c.category for c in result.categories if c.error]
        if failed:
            click.echo(f"\n⚠️  Failed categories: {', '.join(failed)}", err=True)
