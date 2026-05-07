from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomllib  # type: ignore[no-redef]

from hijack.core.archaeology import FileHistory
from hijack.errors import FETCH_001, INPUT_001, INPUT_002, FetchError, InputError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".coverage",
})

_SUPPORTED_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".kt", ".java"})

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
    history: FileHistory | None = None  # git archaeology — None when unavailable
    original_chars: int = 0  # truncate 전 원본 파일 문자 수 (0 = fallback to len(content))


# ---------------------------------------------------------------------------
# Layer detection helpers
# ---------------------------------------------------------------------------

_FE_FRAMEWORK_DEPS = frozenset({"react", "vue", "svelte", "next", "nuxt"})


def _has_frontend_context(repo_root: Path, package_json_deps: set[str]) -> bool:
    """레포가 프론트엔드 프로젝트인지 시그널 검사."""
    if _FE_FRAMEWORK_DEPS & package_json_deps:
        return True
    return bool((repo_root / "package.json").exists())


_PY_ORM_DEPS = frozenset({
    "sqlalchemy", "django", "peewee", "tortoise-orm",
    "sqlmodel", "pony", "mongoengine", "alembic",
})
_JS_ORM_DEPS = frozenset({
    "prisma", "typeorm", "sequelize", "mongoose",
    "drizzle-orm", "knex",
})


def _has_android_context(repo_root: Path) -> bool:
    """Android 프로젝트 검출 — `.kt` / `.java` 파일에 Android-aware 레이어 규칙 적용 시그널.

    AndroidManifest.xml 가 한 번이라도 존재하면 Android. multi-module 레포
    (NowInAndroid 식 — `app/`, `core-*/`, `feature-*/` 분할) 도 최소 1개 모듈이
    manifest 를 들고 있으므로 rglob 1회로 충분히 잡힌다.

    KMP/JVM 라이브러리 (안드로이드 무관 Kotlin) 는 manifest 없으므로 False —
    그 경우 .kt 파일은 fallback "shared" 로 떨어진다.
    """
    for _ in repo_root.rglob("AndroidManifest.xml"):
        return True
    return False


def _has_orm_context(
    repo_root: Path,
    pyproject_deps: set[str],
    package_json_deps: set[str],
) -> bool:
    """레포가 ORM/DB 를 쓰는지 시그널 검사."""
    if _PY_ORM_DEPS & pyproject_deps:
        return True
    if _JS_ORM_DEPS & package_json_deps:
        return True
    if (repo_root / "migrations").exists():
        return True
    if (repo_root / "prisma").exists():
        return True
    return bool((repo_root / "alembic").exists())


# ---------------------------------------------------------------------------
# Layer detection
# ---------------------------------------------------------------------------

def detect_layer(
    file_path: Path,
    repo_root: Path,
    package_json_deps: set[str],
    pyproject_deps: set[str],
    *,
    android_context: bool = False,
) -> str:
    """결정론적 규칙으로 레이어를 반환한다.

    `android_context=True` 일 때 .kt/.java 파일에 Android-aware 매핑이 켜진다.
    fetch_source 가 `_has_android_context` 로 한 번 계산해서 모든 detect_layer
    호출에 같은 값을 패스한다 (per-file rglob 회피).
    """
    rel = file_path.relative_to(repo_root)
    rel_posix = rel.as_posix()
    suffix = file_path.suffix.lower()
    name = file_path.name

    # 1. .tsx / .jsx → frontend
    if suffix in {".tsx", ".jsx"}:
        return "frontend"

    # 2. STRONG frontend dirs → frontend (컨텍스트 불문)
    _frontend_strong = {"frontend/", "ui/", "components/"}
    if any(d in rel_posix for d in _frontend_strong):
        return "frontend"

    # 3. WEAK frontend dirs → FE 컨텍스트 있을 때만 frontend
    _frontend_weak = {"client/", "web/", "app/"}
    if any(d in rel_posix for d in _frontend_weak) and _has_frontend_context(
        repo_root, package_json_deps
    ):
        return "frontend"

    # 4. package_json_deps에 프론트엔드 프레임워크 AND suffix .ts → frontend
    if _FE_FRAMEWORK_DEPS & package_json_deps and suffix == ".ts":
        return "frontend"

    # 5. .sql / .prisma → db
    if suffix in {".sql", ".prisma"}:
        return "db"

    # 6. STRONG db dirs → db (컨텍스트 불문)
    _db_strong = {"migrations/", "prisma/"}
    if any(d in rel_posix for d in _db_strong) and suffix in {".py", ".ts"}:
        return "db"

    # 7. WEAK db dirs → ORM 컨텍스트 있을 때만 db
    _db_weak = {"schemas/", "models/"}
    if (
        any(d in rel_posix for d in _db_weak)
        and suffix in {".py", ".ts"}
        and _has_orm_context(repo_root, pyproject_deps, package_json_deps)
    ):
        return "db"

    # 8. Dockerfile 또는 devops 디렉토리 → devops
    if name == "Dockerfile" or any(d in rel_posix for d in {".github/", "k8s/", "terraform/"}):
        return "devops"

    # 9. .py AND backend signal → backend
    #   9a: backend 디렉토리
    #   9b: pyproject 가 fastapi/django/flask 를 dep 로 선언
    #   9c: 첫 경로 세그먼트가 backend 프레임워크 이름 — 프레임워크 자기 소스 레포 대응
    #       (예: fastapi 레포의 `fastapi/applications.py`, django 레포의 `django/core/...`)
    _backend_dirs = {"backend/", "server/", "api/", "routes/"}
    _backend_frameworks = {"fastapi", "django", "flask"}
    first_seg = rel_posix.split("/", 1)[0] if "/" in rel_posix else ""
    if suffix == ".py" and (
        any(d in rel_posix for d in _backend_dirs)
        or bool(_backend_frameworks & pyproject_deps)
        or first_seg in _backend_frameworks
    ):
        return "backend"

    # 10. Android (.kt / .java) — manifest 발견된 레포 한정.
    #     Android 는 client-only 앱이라 web 의 frontend/backend 분리와 다름.
    #     매핑: UI 표면 (Activity/Fragment/Compose Screen) → frontend,
    #           ViewModel/UseCase/Repository/DataSource → backend (logic 분리),
    #           Room (Dao/Database) → db.
    if suffix in {".kt", ".java"} and android_context:
        name_lower = name.lower()
        # 10a. UI 표면 → frontend
        _ui_suffixes = (
            "activity.kt", "activity.java",
            "fragment.kt", "fragment.java",
            "screen.kt", "composable.kt",
        )
        if name_lower.endswith(_ui_suffixes):
            return "frontend"
        if any(d in rel_posix for d in {"/ui/", "/presentation/", "/screens/", "/compose/"}):
            return "frontend"
        # 10b. Room / DB → db
        _db_suffixes = (
            "dao.kt", "dao.java",
            "database.kt", "database.java",
        )
        if name_lower.endswith(_db_suffixes):
            return "db"
        # 10c. ViewModel / Repository / UseCase / DataSource → backend
        _logic_suffixes = (
            "viewmodel.kt", "viewmodel.java",
            "repository.kt", "repository.java",
            "usecase.kt", "interactor.kt",
            "datasource.kt", "datasource.java",
        )
        if name_lower.endswith(_logic_suffixes):
            return "backend"
        if any(d in rel_posix for d in {"/data/", "/domain/", "/repository/", "/network/"}):
            return "backend"

    # 11. 나머지 → shared
    return "shared"


# ---------------------------------------------------------------------------
# File content reader
# ---------------------------------------------------------------------------

def _read_file_content(path: Path) -> tuple[str, int]:
    """2000줄 이하이면 전체, 초과이면 핵심 부분만 추출한다.

    Returns (processed_content, original_char_count). original_char_count 는
    truncate 여부와 상관없이 raw 파일 크기로, 선별 알고리즘이 truncate 후
    크기로 정렬하다 핵심 파일을 후순위로 밀어버리는 것을 방지하는 용.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", 0

    original = len(text)
    lines = text.splitlines(keepends=True)
    if len(lines) <= _MAX_LINES:
        return text, original

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
    return header + "".join(extracted), original


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

    # Android Kotlin/Java patterns — name suffix 매칭이 generic substring 보다
    # 먼저. "viewmodel.kt" 가 "model" substring 에 걸려 model 로 분류되는 회귀 차단
    # (ViewModel 은 service 의도, model 아님). 패턴이 Android-only 가 아니라
    # 일반 Kotlin/MVVM 컨벤션이므로 KMP/JVM 라이브러리에도 동일 적용.
    if name.endswith(("activity.kt", "activity.java",
                      "fragment.kt", "fragment.java")):
        return "entry_point"
    if name in {"mainapplication.kt", "application.kt", "main.kt"}:
        return "entry_point"
    if name.endswith(("composable.kt", "screen.kt")):
        return "api"
    if name.endswith(("viewmodel.kt", "viewmodel.java", "presenter.kt",
                      "repository.kt", "repository.java",
                      "usecase.kt", "interactor.kt",
                      "datasource.kt", "datasource.java")):
        return "service"
    if name.endswith(("entity.kt", "entity.java",
                      "dao.kt", "dao.java",
                      "dto.kt", "dto.java")):
        return "model"

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
# Persistent remote-repo cache
# ---------------------------------------------------------------------------

_CACHE_DIR_ENV = "HIJACK_CACHE_DIR"
_CACHE_DISABLE_ENV = "HIJACK_NO_CACHE"


def _cache_root() -> Path:
    """Persistent repo 캐시 루트. HIJACK_CACHE_DIR 로 override 가능."""
    if override := os.environ.get(_CACHE_DIR_ENV):
        return Path(override)
    return Path.home() / ".cache" / "code-hijack" / "repos"


def _cache_key(url: str) -> str:
    """16-char hex digest. URL trailing slash / case 는 normalize."""
    normalized = url.rstrip("/").lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _cache_enabled() -> bool:
    """HIJACK_NO_CACHE 가 truthy 가 아니면 캐시 사용."""
    return os.environ.get(_CACHE_DISABLE_ENV, "") in ("", "0", "false", "False")


def _git_clone(target: str, dest: str) -> None:
    """git clone with --filter=blob:none, fallback --depth=1.

    파일 위치만 dest 로 다르고 로직은 기존과 동일. 실패 시 FetchError(FETCH_001).
    """
    result = subprocess.run(
        ["git", "clone", "--filter=blob:none", target, dest],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "clone", "--depth=1", target, dest],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise FetchError(FETCH_001, f"git clone 실패: {result.stderr.strip()}")


def _fetch_remote(target: str) -> Path:
    """원격 레포를 clone 해서 repo_root 반환. 캐시 우선.

    캐시 hit: <cache_root>/<key>/.git 존재 시 그대로 재사용.
    캐시 miss: 캐시 dir 에 clone (실패 시 FetchError).
    캐시 비활성화: HIJACK_NO_CACHE=1 → 매번 tempfile.mkdtemp.

    skill 모드처럼 같은 URL 을 다중 process 에서 호출할 때 두 번째 이후
    호출이 git clone 없이 즉시 반환되도록 한다.
    """
    if not _cache_enabled():
        tmpdir = tempfile.mkdtemp()
        _git_clone(target, tmpdir)
        return Path(tmpdir)

    cache_dir = _cache_root() / _cache_key(target)

    # 캐시 hit
    if (cache_dir / ".git").is_dir():
        return cache_dir

    # 부분 clone 실패 잔재 (디렉토리는 있는데 .git 없음) → wipe & retry
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    _git_clone(target, str(cache_dir))
    return cache_dir


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_source(
    target: str,
    *,
    subpath: str | None = None,
    attach_history: bool = True,
    history_depth: int = 3,
) -> tuple[list[SourceFile], Path]:
    """(files, repo_root) 반환.

    attach_history: when True (default), each SourceFile gets `git log --follow`
    history attached. Disabled in `--no-archaeology` mode and in tests that
    don't care about git context.
    """

    # 1. 소스 위치 결정
    local_path = Path(target)
    if local_path.exists():
        repo_root = local_path / subpath if subpath else local_path
    elif target.startswith(("http://", "https://")) or "github.com" in target:
        cloned_root = _fetch_remote(target)
        repo_root = cloned_root / subpath if subpath else cloned_root
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
        msg = f"지원 파일(.py/.ts/.tsx/.kt/.java) 없음: {repo_root.as_posix()!r}"
        raise InputError(INPUT_002, msg)

    # 4. 의존성 추출
    package_json_deps = _read_package_json_deps(repo_root)
    pyproject_deps = _read_pyproject_deps(repo_root)
    android_context = _has_android_context(repo_root)

    # 5. SourceFile 목록 생성
    files: list[SourceFile] = []
    for abs_path in collected:
        rel = abs_path.relative_to(repo_root)
        content, original_chars = _read_file_content(abs_path)
        layer = detect_layer(
            abs_path, repo_root, package_json_deps, pyproject_deps,
            android_context=android_context,
        )
        role = _detect_role(rel)
        files.append(SourceFile(
            path=rel, content=content, layer=layer, role=role,
            original_chars=original_chars,
        ))

    # 6. Attach git history (best-effort; skipped when not in a git repo).
    if attach_history:
        _attach_git_history(files, repo_root, depth=history_depth)

    return files, repo_root


def _attach_git_history(
    files: list[SourceFile],
    repo_root: Path,
    *,
    depth: int,
) -> None:
    """Mutate `files` in place to attach FileHistory. Silent on non-git roots."""
    # Imported locally so the pure `core` modules don't pull in subprocess wrapping
    # at import time (keeps test isolation cheap).
    from hijack.io.git import get_file_archaeology, is_git_repo

    if not is_git_repo(repo_root):
        return

    for f in files:
        f.history = get_file_archaeology(repo_root, repo_root / f.path, depth=depth)
