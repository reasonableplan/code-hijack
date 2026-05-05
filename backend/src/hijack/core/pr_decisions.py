"""pr_decisions — Phase A1: senior judgment signals from a repo's PR history.

Surfaces what senior maintainers *discussed and decided* in code review —
distinct from G1 (style), G2 (statistics), and B (test defenses). The output
catalog gives AI agents context like "this team rejects X for Y reason" or
"scaling concerns dominate review feedback here."

Four signals:
  1. Vocabulary clusters  — theme aggregation from review comments by keyword
  2. Notable PRs          — most-discussed merged PRs (proxy for "iterated on")
  3. Rejected PRs         — closed-without-merge catalog ("we decided NOT to")
  4. Recurring labels     — top-N labels across all scanned PRs (project taxonomy)

Pure mechanical: gh CLI + regex + counting. No LLM calls anywhere.

## Auth + network

Primary: gh CLI via subprocess.run(["gh", ...]).
Fallback: raw GitHub API calls via urllib.request + GH_TOKEN env var.
If neither works, extract_pr_decisions returns None (caller treats as "skipped").

## Source target parsing

Phase A1 only runs when the session target is a GitHub URL OR a local path
whose `git remote get-url origin` resolves to a GitHub URL. Otherwise returns
None silently — no error.

## Cache layout

    <cache_dir>/<owner>__<repo>/
      index.json          {"last_updated": ISO8601, "pr_numbers": [123, ...]}
      pr_<number>.json    raw gh JSON per PR (metadata + comments)

v1 cache strategy: conservative. If the <owner>__<repo> subdirectory is
non-empty, use the existing cache as-is (no incremental update). Pass
refresh=True to blow away and re-fetch. Document any staleness in the module
docstring (not in the output).

## Two-tier fetch strategy

Tier 1 (bulk): Fetch PR metadata for merged + closed (rejected) sets.
  - merged: gh pr list --state merged --limit N
  - closed: gh pr list --state closed --limit N, filter mergedAt is None → rejected

Tier 2 (comment detail): Sort merged PRs by diff size (additions+deletions)
within [_NOTABLE_MIN_DIFF, _NOTABLE_MAX_DIFF]. Take top 50 candidates. For each,
fetch: gh pr view <n> --json comments,reviews. Keep PRs with
len(comments)+len(reviews) >= _NOTABLE_MIN_COMMENTS. Sort by total comment
count desc, cap at _NOTABLE_TOP_N.

Rejected PRs skip comment fetching (saves network). Use bulk metadata only.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — tunables
# ---------------------------------------------------------------------------

_MAX_PRS_TO_SCAN = 500        # most-recent merged + rejected, combined
_NOTABLE_TOP_N = 30
_REJECTED_TOP_N = 30
_LABELS_TOP_N = 20
_VOCAB_MIN_COUNT = 3          # vocabulary clusters with fewer hits are dropped
_NOTABLE_MIN_COMMENTS = 3     # PRs with fewer review comments are not "discussed"
_NOTABLE_MIN_DIFF = 50        # additions+deletions floor (skip trivial)
_NOTABLE_MAX_DIFF = 5000      # ceiling (skip auto-generated / massive renames)

_NOTABLE_CANDIDATES_POOL = 50  # how many diff-filtered PRs get comment fetches

# Bot label patterns — these are auto-applied and carry no human taxonomy signal
_BOT_LABEL_RE = re.compile(r"^(bot:|auto:)", re.IGNORECASE)

# GitHub URL patterns for parsing
_GH_HTTPS_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\.\s]+?)(?:\.git)?/?$"
)
_GH_SSH_RE = re.compile(
    r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/\.\s]+?)(?:\.git)?$"
)

# Anonymization: strip @username mentions
_AT_MENTION_RE = re.compile(r"@[A-Za-z0-9_-]+")

# ---------------------------------------------------------------------------
# Vocabulary themes
# ---------------------------------------------------------------------------

_VOCAB_THEMES: dict[str, tuple[str, ...]] = {
    "scaling/performance": (
        "won't scale", "wont scale", "doesn't scale", "scaling", "performance",
        "O(n", "slow", "expensive", "memory", "throughput", "latency",
    ),
    "backwards_compat": (
        "backwards compat", "backward compat", "breaking change", "BC break",
        "breaks downstream", "deprecate", "deprecation", "migration",
    ),
    "concurrency": (
        "race condition", "thread safety", "thread-safe", "concurrent",
        "deadlock", "atomic", "lock contention",
    ),
    "security": (
        "security", "vulnerability", "CVE", "auth", "sanitize",
        "escape", "injection", "XSS", "CSRF",
    ),
    "api_design": (
        "API design", "public API", "interface contract", "public surface",
        "ergonomic", "footgun",
    ),
    "maintenance/complexity": (
        "tech debt", "technical debt", "maintain", "complexity",
        "simpler", "over-engineer", "YAGNI",
    ),
    "testing": (
        "test coverage", "edge case", "regression test", "flaky",
    ),
    "documentation": (
        "docstring", "documentation", "doc string", "README", "needs docs",
    ),
}

# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VocabularyCluster:
    """Theme aggregation from review comments."""

    theme: str                          # key from _VOCAB_THEMES
    count: int                          # total keyword-match count across all text
    matched_keywords: list[str]         # distinct keywords that matched
    examples: list[tuple[str, str]]     # up to 5 (keyword, anonymized_excerpt) pairs

    def to_json(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "count": self.count,
            "matched_keywords": self.matched_keywords,
            "examples": [{"keyword": k, "excerpt": e} for k, e in self.examples],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> VocabularyCluster:
        return cls(
            theme=data["theme"],
            count=data["count"],
            matched_keywords=data.get("matched_keywords", []),
            examples=[
                (ex["keyword"], ex["excerpt"])
                for ex in data.get("examples", [])
            ],
        )


@dataclass
class NotablePR:
    """A merged PR that generated significant discussion (iterated on)."""

    number: int
    title: str
    body_excerpt: str        # first 300 chars, sanitized whitespace
    labels: list[str]
    comment_count: int       # len(comments) + len(reviews)
    diff_size: int           # additions + deletions
    url: str

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "body_excerpt": self.body_excerpt,
            "labels": self.labels,
            "comment_count": self.comment_count,
            "diff_size": self.diff_size,
            "url": self.url,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> NotablePR:
        return cls(
            number=data["number"],
            title=data["title"],
            body_excerpt=data.get("body_excerpt", ""),
            labels=data.get("labels", []),
            comment_count=data.get("comment_count", 0),
            diff_size=data.get("diff_size", 0),
            url=data.get("url", ""),
        )


@dataclass
class RejectedPR:
    """A PR closed without merge — explicit 'we decided NOT to' signal."""

    number: int
    title: str
    body_excerpt: str        # first 200 chars
    labels: list[str]
    url: str
    closed_at: str           # ISO8601 from gh

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "body_excerpt": self.body_excerpt,
            "labels": self.labels,
            "url": self.url,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RejectedPR:
        return cls(
            number=data["number"],
            title=data["title"],
            body_excerpt=data.get("body_excerpt", ""),
            labels=data.get("labels", []),
            url=data.get("url", ""),
            closed_at=data.get("closed_at", ""),
        )


@dataclass
class LabelCount:
    """Aggregated label frequency across all scanned PRs."""

    label: str
    count: int

    def to_json(self) -> dict[str, Any]:
        return {"label": self.label, "count": self.count}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LabelCount:
        return cls(label=data["label"], count=data["count"])


@dataclass
class PRDecisions:
    """Aggregated PR-history signals extracted from a GitHub repo.

    Tell pytest this is a data class, not a test class. Without this, pytest
    tries to collect it (sees the `PR` prefix doesn't match but `Decisions`
    does nothing — still safest to include __test__ = False).
    """

    __test__ = False  # data class, not pytest collectable

    repo_slug: str                          # "owner/repo"
    total_prs_scanned: int
    vocabulary_clusters: list[VocabularyCluster]
    notable_prs: list[NotablePR]
    rejected_prs: list[RejectedPR]
    label_counts: list[LabelCount]

    def to_json(self) -> dict[str, Any]:
        return {
            "repo_slug": self.repo_slug,
            "total_prs_scanned": self.total_prs_scanned,
            "vocabulary_clusters": [c.to_json() for c in self.vocabulary_clusters],
            "notable_prs": [p.to_json() for p in self.notable_prs],
            "rejected_prs": [p.to_json() for p in self.rejected_prs],
            "label_counts": [lc.to_json() for lc in self.label_counts],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PRDecisions:
        return cls(
            repo_slug=data.get("repo_slug", ""),
            total_prs_scanned=data.get("total_prs_scanned", 0),
            vocabulary_clusters=[
                VocabularyCluster.from_json(c)
                for c in data.get("vocabulary_clusters", [])
            ],
            notable_prs=[
                NotablePR.from_json(p) for p in data.get("notable_prs", [])
            ],
            rejected_prs=[
                RejectedPR.from_json(p) for p in data.get("rejected_prs", [])
            ],
            label_counts=[
                LabelCount.from_json(lc) for lc in data.get("label_counts", [])
            ],
        )

    @property
    def has_signal(self) -> bool:
        return bool(
            self.vocabulary_clusters or self.notable_prs
            or self.rejected_prs or self.label_counts
        )


# ---------------------------------------------------------------------------
# GitHub target parsing
# ---------------------------------------------------------------------------

def _parse_github_target(
    target: str,
    repo_root: Path | None,
) -> tuple[str, str] | None:
    """Return (owner, repo) if target resolves to a GitHub URL, else None.

    Accepts:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
      - Local path where git remote get-url origin returns one of the above
    """
    # Direct URL match
    for pattern in (_GH_HTTPS_RE, _GH_SSH_RE):
        m = pattern.match(target.strip())
        if m:
            return m.group("owner"), m.group("repo")

    # Local path — try git remote
    search_root: Path | None = None
    if repo_root is not None and repo_root.exists():
        search_root = repo_root
    else:
        p = Path(target)
        if p.exists() and p.is_dir():
            search_root = p

    if search_root is not None:
        # Only consult git when search_root is itself a git repo (has its own
        # .git). Without this guard, git walks up the directory tree and any
        # subdirectory inside another repo (test fixtures, vendored sources,
        # nested workspaces) would inherit the parent's origin — silently
        # mining the wrong project's PRs and creating side-effect cache dirs.
        if not (search_root / ".git").exists():
            return None
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=str(search_root), timeout=10,
            )
            if result.returncode == 0:
                remote_url = result.stdout.strip()
                return _parse_github_target(remote_url, None)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return None


# ---------------------------------------------------------------------------
# gh CLI / GitHub API runner
# ---------------------------------------------------------------------------

def _default_gh_runner(args: list[str]) -> str:
    """Run gh CLI; return stdout. Raise RuntimeError on non-zero exit."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise RuntimeError("gh CLI not found") from None
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"gh CLI timed out: {args[:3]}") from e

    if result.returncode != 0:
        raise RuntimeError(
            f"gh CLI failed (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )
    return result.stdout


def _make_api_runner(token: str) -> Callable[[list[str]], str]:
    """Build a gh-runner that falls back to raw GitHub REST API calls.

    Only handles the two gh subcommand shapes used in this module:
      ["pr", "list", "--repo", "<o/r>", "--state", "<state>", "--limit", N, "--json", fields]
      ["pr", "view", "<n>", "--repo", "<o/r>", "--json", fields]

    More complex gh commands are not translatable and will raise RuntimeError.
    """
    def _run(args: list[str]) -> str:
        # Parse enough structure to build a REST URL
        if len(args) >= 2 and args[0] == "pr" and args[1] == "list":
            # Extract --repo, --state, --limit from args
            repo = _flag_value(args, "--repo")
            state = _flag_value(args, "--state") or "open"
            limit = _flag_value(args, "--limit") or "30"
            if repo is None:
                raise RuntimeError(f"Cannot translate gh args (no --repo): {args}")
            # Map gh state to GitHub REST state
            gh_state = "closed" if state in ("closed", "merged") else "open"
            url = (
                f"https://api.github.com/repos/{repo}/pulls"
                f"?state={gh_state}&per_page={limit}&sort=updated&direction=desc"
            )
            data = _api_get(url, token)
            # gh pr list --json returns a list; REST already returns a list
            return json.dumps(data)

        if len(args) >= 3 and args[0] == "pr" and args[1] == "view":
            pr_num = args[2]
            repo = _flag_value(args, "--repo")
            if repo is None:
                raise RuntimeError(f"Cannot translate gh args (no --repo): {args}")
            # Fetch PR + comments
            pr_data = _api_get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}", token
            )
            comments_data = _api_get(
                f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments?per_page=100",
                token,
            )
            reviews_data = _api_get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews?per_page=100",
                token,
            )
            # Shape to match gh pr view --json comments,reviews output
            result = {
                "comments": [{"body": c.get("body", "")} for c in comments_data],
                "reviews": [{"body": r.get("body", "")} for r in reviews_data],
            }
            # Merge in pr_data fields
            result.update({k: pr_data.get(k) for k in
                           ("title", "body", "number", "additions", "deletions",
                            "labels", "html_url", "merged_at", "closed_at")
                           if k in pr_data})
            return json.dumps(result)

        raise RuntimeError(f"Cannot translate gh args to REST API: {args}")

    return _run


def _flag_value(args: list[str], flag: str) -> str | None:
    """Return the value immediately after `flag` in args list."""
    try:
        idx = args.index(flag)
        return args[idx + 1] if idx + 1 < len(args) else None
    except ValueError:
        return None


def _api_get(url: str, token: str) -> Any:
    """Make a GitHub REST API GET request and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API error {e.code}: {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GitHub API network error: {e.reason}") from e


def _resolve_runner(
    gh_runner: Callable[[list[str]], str] | None,
) -> Callable[[list[str]], str] | None:
    """Return a runner to use, or None if no auth is available."""
    if gh_runner is not None:
        return gh_runner

    # Try gh CLI — probe with gh auth status
    try:
        result = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return _default_gh_runner
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Try GH_TOKEN fallback
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return _make_api_runner(token)

    return None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_dir_for(cache_dir: Path, owner: str, repo: str) -> Path:
    return cache_dir / f"{owner}__{repo}"


def _read_index(repo_cache: Path) -> dict[str, Any]:
    idx_path = repo_cache / "index.json"
    if idx_path.exists():
        try:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_index(repo_cache: Path, pr_numbers: list[int]) -> None:
    idx = {
        "last_updated": datetime.now(UTC).isoformat(),
        "pr_numbers": pr_numbers,
    }
    (repo_cache / "index.json").write_text(
        json.dumps(idx, indent=2), encoding="utf-8"
    )


def _read_cached_pr(repo_cache: Path, number: int) -> dict[str, Any] | None:
    path = repo_cache / f"pr_{number}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_cached_pr(repo_cache: Path, number: int, data: dict[str, Any]) -> None:
    (repo_cache / f"pr_{number}.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _sanitize_body(text: str | None, max_chars: int) -> str:
    """Collapse whitespace and truncate body text."""
    if not text:
        return ""
    # Collapse whitespace sequences (newlines, tabs, multi-spaces)
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:max_chars]


def _anonymize(text: str) -> str:
    """Replace @username mentions with @<contributor>."""
    return _AT_MENTION_RE.sub("@<contributor>", text)


def _excerpt(text: str, keyword: str, max_chars: int = 100) -> str:
    """Find keyword in text and return a short surrounding excerpt.

    Finds the first occurrence (case-insensitive), takes max_chars characters
    centered around the match, and truncates at word boundaries.
    """
    lo = text.lower()
    kw_lo = keyword.lower()
    idx = lo.find(kw_lo)
    if idx == -1:
        return text[:max_chars]

    # Window around the match
    start = max(0, idx - 40)
    end = min(len(text), start + max_chars)
    chunk = text[start:end]

    # Trim to word boundaries
    if start > 0 and not text[start - 1].isspace():
        sp = chunk.find(" ")
        chunk = chunk[sp + 1:] if sp != -1 else chunk
    if end < len(text) and not text[end].isspace():
        sp = chunk.rfind(" ")
        chunk = chunk[:sp] if sp != -1 else chunk

    return chunk.strip()


def _extract_labels(pr_data: dict[str, Any]) -> list[str]:
    """Extract label name strings from a PR JSON blob (handles both gh and REST shapes)."""
    raw = pr_data.get("labels") or []
    result = []
    for item in raw:
        name = (
            (item.get("name") or item.get("label") or "") if isinstance(item, dict) else str(item)
        )
        if name:
            result.append(name)
    return result


def _pr_url(pr_data: dict[str, Any]) -> str:
    return pr_data.get("url") or pr_data.get("html_url") or ""


def _pr_additions(pr_data: dict[str, Any]) -> int:
    return int(pr_data.get("additions") or 0)


def _pr_deletions(pr_data: dict[str, Any]) -> int:
    return int(pr_data.get("deletions") or 0)


# ---------------------------------------------------------------------------
# Bulk fetch helpers
# ---------------------------------------------------------------------------

def _fetch_pr_list(
    runner: Callable[[list[str]], str],
    owner: str,
    repo: str,
    state: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch list of PRs from gh CLI and return parsed JSON list."""
    raw = runner([
        "pr", "list",
        "--repo", f"{owner}/{repo}",
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,body,labels,additions,deletions,url,closedAt,mergedAt",
    ])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("gh pr list returned non-JSON for %s/%s (%s)", owner, repo, state)
        return []
    if not isinstance(data, list):
        return []
    return data


def _fetch_pr_detail(
    runner: Callable[[list[str]], str],
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    """Fetch comments + reviews for a single PR."""
    raw = runner([
        "pr", "view", str(number),
        "--repo", f"{owner}/{repo}",
        "--json", "comments,reviews",
    ])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Signal processors
# ---------------------------------------------------------------------------

def _build_notable_prs(
    merged_prs: list[dict[str, Any]],
    repo_cache: Path,
    runner: Callable[[list[str]], str],
    owner: str,
    repo: str,
) -> list[NotablePR]:
    """Filter merged PRs to notable ones; fetch comment details for candidates."""
    # Tier 1: filter by diff size
    candidates = [
        pr for pr in merged_prs
        if _NOTABLE_MIN_DIFF
        <= (_pr_additions(pr) + _pr_deletions(pr))
        <= _NOTABLE_MAX_DIFF
    ]
    # Sort by diff size desc, take top pool
    candidates.sort(key=lambda p: _pr_additions(p) + _pr_deletions(p), reverse=True)
    candidates = candidates[:_NOTABLE_CANDIDATES_POOL]

    notable: list[NotablePR] = []
    for pr_data in candidates:
        number = int(pr_data["number"])
        cached = _read_cached_pr(repo_cache, number)

        if cached and ("comments" in cached or "reviews" in cached):
            detail = cached
        else:
            # Fetch comment detail
            try:
                detail = _fetch_pr_detail(runner, owner, repo, number)
            except RuntimeError as e:
                logger.warning("Failed to fetch PR #%d detail: %s", number, e)
                detail = {}
            # Merge into existing cached data
            merged_data = {**pr_data, **detail}
            _write_cached_pr(repo_cache, number, merged_data)
            detail = merged_data

        comments = detail.get("comments") or []
        reviews = detail.get("reviews") or []
        comment_count = len(comments) + len(reviews)

        if comment_count < _NOTABLE_MIN_COMMENTS:
            continue

        diff_size = _pr_additions(pr_data) + _pr_deletions(pr_data)
        notable.append(NotablePR(
            number=number,
            title=pr_data.get("title") or "",
            body_excerpt=_sanitize_body(pr_data.get("body"), 300),
            labels=_extract_labels(pr_data),
            comment_count=comment_count,
            diff_size=diff_size,
            url=_pr_url(pr_data),
        ))

    # Sort by comment_count desc, then number desc (recency tiebreak)
    notable.sort(key=lambda p: (-p.comment_count, -p.number))
    return notable[:_NOTABLE_TOP_N]


def _build_rejected_prs(closed_prs: list[dict[str, Any]]) -> list[RejectedPR]:
    """Filter closed PRs to only those that were NOT merged (true rejections)."""
    rejected = []
    for pr_data in closed_prs:
        merged_at = pr_data.get("mergedAt")
        if merged_at:
            # This PR was merged then closed — not a rejection
            continue
        rejected.append(RejectedPR(
            number=int(pr_data["number"]),
            title=pr_data.get("title") or "",
            body_excerpt=_sanitize_body(pr_data.get("body"), 200),
            labels=_extract_labels(pr_data),
            url=_pr_url(pr_data),
            closed_at=pr_data.get("closedAt") or "",
        ))
    # Sort by closed_at desc
    rejected.sort(key=lambda p: p.closed_at, reverse=True)
    return rejected[:_REJECTED_TOP_N]


def _build_label_counts(
    merged_prs: list[dict[str, Any]],
    rejected_prs_raw: list[dict[str, Any]],
) -> list[LabelCount]:
    """Aggregate labels across all PRs; skip bot labels; sort by count desc then label asc."""
    counts: dict[str, int] = {}
    for pr_data in (*merged_prs, *rejected_prs_raw):
        for label in _extract_labels(pr_data):
            if _BOT_LABEL_RE.match(label):
                continue
            counts[label] = counts.get(label, 0) + 1
    result = [LabelCount(label=k, count=v) for k, v in counts.items()]
    result.sort(key=lambda lc: (-lc.count, lc.label))
    return result[:_LABELS_TOP_N]


def _build_vocabulary_clusters(
    notable_prs: list[NotablePR],
    all_pr_data: dict[int, dict[str, Any]],
) -> list[VocabularyCluster]:
    """Match _VOCAB_THEMES keywords against notable PR bodies and review comments."""
    # Collect text corpus: body + comments + reviews of notable PRs
    corpus_texts: list[str] = []
    for pr in notable_prs:
        number = pr.number
        pr_data = all_pr_data.get(number, {})
        body = pr_data.get("body") or ""
        corpus_texts.append(body)
        for comment in (pr_data.get("comments") or []):
            if isinstance(comment, dict):
                corpus_texts.append(comment.get("body") or "")
            elif isinstance(comment, str):
                corpus_texts.append(comment)
        for review in (pr_data.get("reviews") or []):
            if isinstance(review, dict):
                corpus_texts.append(review.get("body") or "")
            elif isinstance(review, str):
                corpus_texts.append(review)

    clusters: list[VocabularyCluster] = []
    for theme, keywords in _VOCAB_THEMES.items():
        count = 0
        matched_kws: list[str] = []
        examples: list[tuple[str, str]] = []

        for keyword in keywords:
            kw_lo = keyword.lower()
            for text in corpus_texts:
                if not text:
                    continue
                lo = text.lower()
                occurrences = lo.count(kw_lo)
                if occurrences > 0:
                    count += occurrences
                    if keyword not in matched_kws:
                        matched_kws.append(keyword)
                    if len(examples) < 5:
                        raw_excerpt = _excerpt(text, keyword)
                        anonymized = _anonymize(raw_excerpt)
                        examples.append((keyword, anonymized))

        if count < _VOCAB_MIN_COUNT:
            continue

        clusters.append(VocabularyCluster(
            theme=theme,
            count=count,
            matched_keywords=matched_kws,
            examples=examples,
        ))

    clusters.sort(key=lambda c: (-c.count, c.theme))
    return clusters


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract_pr_decisions(
    target: str,
    repo_root: Path | None,
    cache_dir: Path,
    *,
    refresh: bool = False,
    gh_runner: Callable[[list[str]], str] | None = None,
) -> PRDecisions | None:
    """Extract PR-history signals for the given target.

    Returns:
      None — target doesn't resolve to GitHub, or no auth available, or network
             failure. Caller treats this as "Phase A1 skipped."
      PRDecisions(has_signal=False) — fetch succeeded but nothing passed
             thresholds (rare). Caller may surface as "ran, nothing to show."

    Parameters:
      target     — GitHub URL or local path
      repo_root  — local repo root for git-remote resolution (may be None)
      cache_dir  — where to write per-PR JSON cache files
      refresh    — when True, blow away existing cache for this repo first
      gh_runner  — injectable for testing; defaults to _default_gh_runner (real gh CLI)
    """
    parsed = _parse_github_target(target, repo_root)
    if parsed is None:
        logger.debug("pr_decisions: target %r is not a GitHub URL — skipping", target)
        return None

    owner, repo = parsed
    repo_slug = f"{owner}/{repo}"

    runner = _resolve_runner(gh_runner)
    if runner is None:
        logger.warning(
            "pr_decisions: no gh CLI and no GH_TOKEN — cannot fetch PRs for %s", repo_slug
        )
        return None

    # Cache setup
    repo_cache = _cache_dir_for(cache_dir, owner, repo)
    if refresh and repo_cache.exists():
        import shutil
        shutil.rmtree(repo_cache)
    repo_cache.mkdir(parents=True, exist_ok=True)

    existing_index = _read_index(repo_cache)

    # v1: if cache has been populated before (non-empty pr_numbers), reuse as-is.
    if existing_index.get("pr_numbers") and not refresh:
        return _build_from_cache(repo_cache, repo_slug, existing_index)

    # Fetch fresh data
    half = _MAX_PRS_TO_SCAN // 2
    try:
        merged_raw = _fetch_pr_list(runner, owner, repo, "merged", half)
        closed_raw = _fetch_pr_list(runner, owner, repo, "closed", half)
    except RuntimeError as e:
        logger.warning("pr_decisions: fetch failed for %s: %s", repo_slug, e)
        return None

    # Write bulk data to cache
    all_numbers: list[int] = []
    for pr_data in (*merged_raw, *closed_raw):
        n = int(pr_data.get("number", 0))
        if n:
            all_numbers.append(n)
            existing = _read_cached_pr(repo_cache, n) or {}
            merged_data = {**existing, **pr_data}
            _write_cached_pr(repo_cache, n, merged_data)

    _write_index(repo_cache, sorted(set(all_numbers), reverse=True))

    # Build signals
    rejected_prs = _build_rejected_prs(closed_raw)
    label_counts = _build_label_counts(merged_raw, closed_raw)

    # For notable PRs we need comment details — _build_notable_prs handles fetching
    notable_prs = _build_notable_prs(merged_raw, repo_cache, runner, owner, repo)

    # Re-read all cached PR data for vocabulary clustering (now includes comments)
    all_pr_data: dict[int, dict[str, Any]] = {}
    for n in all_numbers:
        data = _read_cached_pr(repo_cache, n)
        if data:
            all_pr_data[n] = data

    vocab_clusters = _build_vocabulary_clusters(notable_prs, all_pr_data)

    total_scanned = len(set(all_numbers))

    return PRDecisions(
        repo_slug=repo_slug,
        total_prs_scanned=total_scanned,
        vocabulary_clusters=vocab_clusters,
        notable_prs=notable_prs,
        rejected_prs=rejected_prs,
        label_counts=label_counts,
    )


def _build_from_cache(
    repo_cache: Path,
    repo_slug: str,
    index: dict[str, Any],
) -> PRDecisions:
    """Reconstruct PRDecisions entirely from the cache directory."""
    pr_numbers: list[int] = index.get("pr_numbers", [])
    all_pr_data: dict[int, dict[str, Any]] = {}
    merged_raw: list[dict[str, Any]] = []
    closed_raw: list[dict[str, Any]] = []

    for n in pr_numbers:
        data = _read_cached_pr(repo_cache, n)
        if data is None:
            continue
        all_pr_data[n] = data
        merged_at = data.get("mergedAt")
        closed_at = data.get("closedAt")
        if merged_at:
            merged_raw.append(data)
        elif closed_at:
            closed_raw.append(data)

    rejected_prs = _build_rejected_prs(closed_raw)
    label_counts = _build_label_counts(merged_raw, closed_raw)

    # Build notable from cached merged data (no comment fetch — use cached detail)
    notable: list[NotablePR] = []
    diff_filtered = [
        pr for pr in merged_raw
        if _NOTABLE_MIN_DIFF
        <= (_pr_additions(pr) + _pr_deletions(pr))
        <= _NOTABLE_MAX_DIFF
    ]
    diff_filtered.sort(key=lambda p: _pr_additions(p) + _pr_deletions(p), reverse=True)
    for pr_data in diff_filtered[:_NOTABLE_CANDIDATES_POOL]:
        number = int(pr_data["number"])
        detail = all_pr_data.get(number, {})
        comments = detail.get("comments") or []
        reviews = detail.get("reviews") or []
        comment_count = len(comments) + len(reviews)
        if comment_count < _NOTABLE_MIN_COMMENTS:
            continue
        notable.append(NotablePR(
            number=number,
            title=pr_data.get("title") or "",
            body_excerpt=_sanitize_body(pr_data.get("body"), 300),
            labels=_extract_labels(pr_data),
            comment_count=comment_count,
            diff_size=_pr_additions(pr_data) + _pr_deletions(pr_data),
            url=_pr_url(pr_data),
        ))
    notable.sort(key=lambda p: (-p.comment_count, -p.number))
    notable = notable[:_NOTABLE_TOP_N]

    vocab_clusters = _build_vocabulary_clusters(notable, all_pr_data)

    return PRDecisions(
        repo_slug=repo_slug,
        total_prs_scanned=len(pr_numbers),
        vocabulary_clusters=vocab_clusters,
        notable_prs=notable,
        rejected_prs=rejected_prs,
        label_counts=label_counts,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_pr_decisions_md(decisions: PRDecisions, *, source_target: str) -> str:
    """Render PRDecisions as Markdown.

    Returns '' when has_signal is False — caller skips writing the file.
    """
    if not decisions.has_signal:
        return ""

    lines: list[str] = [
        "# PR Decisions — what the senior team considered and rejected",
        "",
        f"> Mined from {decisions.total_prs_scanned} PRs of {decisions.repo_slug}:"
        " review feedback, notable",
        f"> iterations, rejected proposals, and recurring labels from {source_target}.",
        "> These show what the maintainers chose to discuss and what they explicitly",
        "> chose to NOT do.",
        "",
    ]

    # --- Vocabulary clusters ---
    if decisions.vocabulary_clusters:
        lines += ["## Concerns raised in review (vocabulary clusters)", ""]
        for cluster in decisions.vocabulary_clusters:
            kw_list = ", ".join(f"`{k}`" for k in cluster.matched_keywords[:5])
            lines.append(f"- **{cluster.theme}** ({cluster.count} mentions)")
            lines.append(f"  - matched: {kw_list}")
            if cluster.examples:
                lines.append("  - examples:")
                for keyword, excerpt in cluster.examples:
                    lines.append(f'    - "{excerpt}..." (matched: {keyword})')
        lines.append("")

    # --- Notable PRs ---
    if decisions.notable_prs:
        lines += ["## Most-discussed merged PRs (got iterated on)", ""]
        for pr in decisions.notable_prs:
            diff_str = f"+{pr.diff_size}" if pr.diff_size else "unknown diff"
            lines.append(
                f"- [#{pr.number}]({pr.url}) **{pr.title}**"
                f" ({pr.comment_count} comments, {diff_str} lines)"
            )
            if pr.body_excerpt:
                lines.append(f"  > {pr.body_excerpt}")
            if pr.labels:
                label_str = ", ".join(f"`{lbl}`" for lbl in pr.labels)
                lines.append(f"  Labels: {label_str}")
        lines.append("")

    # --- Rejected PRs ---
    if decisions.rejected_prs:
        lines += [
            '## Rejected (closed without merge) — explicit "we decided NOT to" decisions',
            "",
        ]
        for pr in decisions.rejected_prs:
            closed = pr.closed_at[:10] if pr.closed_at else "unknown"
            lines.append(
                f"- [#{pr.number}]({pr.url}) **{pr.title}** (closed {closed})"
            )
            if pr.body_excerpt:
                lines.append(f"  > {pr.body_excerpt}")
            if pr.labels:
                label_str = ", ".join(f"`{lbl}`" for lbl in pr.labels)
                lines.append(f"  Labels: {label_str}")
        lines.append("")

    # --- Label counts ---
    if decisions.label_counts:
        lines += ["## Recurring labels (project taxonomy)", ""]
        label_parts = [
            f"`{lc.label}` ({lc.count})" for lc in decisions.label_counts
        ]
        lines.append("- " + ", ".join(label_parts))
        lines.append("")

    return "\n".join(lines)
