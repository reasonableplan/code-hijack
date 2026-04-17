from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomllib  # type: ignore[no-redef]

from hijack.errors import FETCH_001, INPUT_001, INPUT_002, FetchError, InputError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".coverage",
})

_SUPPORTED_SUFFIXES = frozenset({".py", ".ts", ".tsx"})

_MAX_LINES = 2000


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SourceFile:
    path: Path      # 레포 루트 기준 상대 경로 (Path 객체)
    content: str    # 파일 전체 내용 (2000줄 초과 시 부분 추출)
    layer: str      # "frontend"|"backend"|"db"|"devops"|"shared"
    role: str       # "entry_point"|"model"|"api"|"test"|"config"|"service"|"other"


# ---------------------------------------------------------------------------
# Layer detection
# ---------------------------------------------------------------------------

def detect_layer(
    file_path: Path,
    repo_root: Path,
    package_json_deps: set[str],
    pyproject_deps: set[str],
) -> str:
    """결정론적 규칙으로 레이어를 반환한다."""
    rel = file_path.relative_to(repo_root)
    rel_posix = rel.as_posix()
    suffix = file_path.suffix.lower()
    name = file_path.name

    # 1. .tsx / .jsx → frontend
    if suffix in {".tsx", ".jsx"}:
        return "frontend"

    # 2. rel 경로에 프론트엔드 디렉토리 포함 → frontend
    _frontend_dirs = {"frontend/", "client/", "web/", "app/", "ui/", "components/"}
    if any(d in rel_posix for d in _frontend_dirs):
        return "frontend"

    # 3. package_json_deps에 프론트엔드 프레임워크 AND suffix .ts → frontend
    _fe_frameworks = {"react", "vue", "svelte", "next", "nuxt"}
    if _fe_frameworks & package_json_deps and suffix == ".ts":
        return "frontend"

    # 4. .sql / .prisma → db
    if suffix in {".sql", ".prisma"}:
        return "db"

    # 5. rel에 DB 관련 디렉토리 AND suffix .py/.ts → db
    _db_dirs = {"migrations/", "schemas/", "prisma/", "models/"}
    if any(d in rel_posix for d in _db_dirs) and suffix in {".py", ".ts"}:
        return "db"

    # 6. Dockerfile 또는 devops 디렉토리 → devops
    if name == "Dockerfile" or any(d in rel_posix for d in {".github/", "k8s/", "terraform/"}):
        return "devops"

    # 7. .py AND (backend 디렉토리 OR pyproject_deps에 backend 프레임워크) → backend
    _backend_dirs = {"backend/", "server/", "api/", "routes/"}
    _backend_frameworks = {"fastapi", "django", "flask"}
    if suffix == ".py" and (
        any(d in rel_posix for d in _backend_dirs)
        or bool(_backend_frameworks & pyproject_deps)
    ):
        return "backend"

    # 8. 나머지 → shared
    return "shared"


# ---------------------------------------------------------------------------
# File content reader
# ---------------------------------------------------------------------------

def _read_file_content(path: Path) -> str:
    """2000줄 이하이면 전체, 초과이면 핵심 부분만 추출한다."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    lines = text.splitlines(keepends=True)
    if len(lines) <= _MAX_LINES:
        return text

    # 핵심 부분 추출: import 문, 클래스/함수 시그니처, 데코레이터, docstring 첫 줄
    _sig_pattern = re.compile(
        r"^(?:"
        r"(?:from|import)\s"               # import 문
        r"|(?:class|def|async\s+def)\s"    # 클래스/함수 선언
        r"|@\w"                            # 데코레이터
        r'|"""'                            # docstring 시작
        r"|'''"
        r")"
    )

    extracted: list[str] = []
    in_docstring = False
    docstring_char: str | None = None

    for line in lines:
        stripped = line.rstrip("\n")

        if in_docstring:
            # docstring 첫 줄 이후는 종료 여부만 체크
            if docstring_char and docstring_char in stripped:
                in_docstring = False
            continue

        if _sig_pattern.match(stripped):
            extracted.append(line)
            # docstring 시작 감지
            if stripped.lstrip().startswith('"""') or stripped.lstrip().startswith("'''"):
                docstring_char = '"""' if '"""' in stripped else "'''"
                # 같은 줄에서 바로 닫히지 않으면 멀티라인
                remaining = stripped.lstrip()[3:]
                if docstring_char not in remaining:
                    in_docstring = True

    header = f"# [TRUNCATED: {len(lines)} lines → key signatures only]\n"
    return header + "".join(extracted)


# ---------------------------------------------------------------------------
# Dependency readers
# ---------------------------------------------------------------------------

def _read_package_json_deps(repo_root: Path) -> set[str]:
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return set()
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    deps: set[str] = set()
    deps.update(data.get("dependencies", {}).keys())
    deps.update(data.get("devDependencies", {}).keys())
    return deps


def _read_pyproject_deps(repo_root: Path) -> set[str]:
    pyproj = repo_root / "pyproject.toml"
    if not pyproj.exists():
        return set()
    try:
        data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()
    raw: list[str] = data.get("project", {}).get("dependencies", [])
    deps: set[str] = set()
    for dep in raw:
        # "fastapi>=0.100" → "fastapi"
        name = re.split(r"[><=!\[;@ ]", dep)[0].lower().strip()
        if name:
            deps.add(name)
    return deps


# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------

def _detect_role(rel: Path) -> str:
    rel_posix = rel.as_posix().lower()
    name = rel.name.lower()

    if "test" in rel_posix or "spec" in rel_posix:
        return "test"
    if name in {"main.py", "app.py", "index.ts", "server.ts", "__main__.py"}:
        return "entry_point"
    if "model" in rel_posix or "schema" in rel_posix or "types" in rel_posix:
        return "model"
    if any(k in rel_posix for k in ("route", "api", "controller", "endpoint")):
        return "api"
    if "service" in rel_posix or "lib" in rel_posix or "util" in rel_posix:
        return "service"
    return "other"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_source(
    target: str,
    *,
    subpath: str | None = None,
) -> tuple[list[SourceFile], Path]:
    """(files, repo_root) 반환."""

    # 1. 소스 위치 결정
    local_path = Path(target)
    if local_path.exists():
        repo_root = local_path / subpath if subpath else local_path
    elif target.startswith(("http://", "https://")) or "github.com" in target:
        tmpdir = tempfile.mkdtemp()
        result = subprocess.run(
            ["git", "clone", "--depth=1", target, tmpdir],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise FetchError(FETCH_001, f"git clone 실패: {result.stderr.strip()}")
        repo_root = Path(tmpdir) / subpath if subpath else Path(tmpdir)
    else:
        raise InputError(INPUT_001, f"유효하지 않은 경로 또는 URL: {target!r}")

    # 2. 파일 재귀 수집 (_SKIP_DIRS 제외, _SUPPORTED_SUFFIXES만)
    collected: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        # 조상 디렉토리 중 _SKIP_DIRS에 포함된 것이 있으면 제외
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in _SUPPORTED_SUFFIXES:
            collected.append(p)

    # 3. 지원 파일 0개이면 InputError
    if not collected:
        msg = f"지원 파일(.py/.ts/.tsx) 없음: {repo_root.as_posix()!r}"
        raise InputError(INPUT_002, msg)

    # 4. 의존성 추출
    package_json_deps = _read_package_json_deps(repo_root)
    pyproject_deps = _read_pyproject_deps(repo_root)

    # 5. SourceFile 목록 생성
    files: list[SourceFile] = []
    for abs_path in collected:
        rel = abs_path.relative_to(repo_root)
        content = _read_file_content(abs_path)
        layer = detect_layer(abs_path, repo_root, package_json_deps, pyproject_deps)
        role = _detect_role(rel)
        files.append(SourceFile(path=rel, content=content, layer=layer, role=role))

    return files, repo_root
