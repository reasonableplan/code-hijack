"""Tests for preprocessor module."""

from pathlib import Path

from hijack.core.fetcher import SourceFile
from hijack.core.preprocessor import preprocess, build_file_summary_for_llm


def _make_file(path: str, lang: str = "python", content: str = "") -> SourceFile:
    return SourceFile(path=Path(path), content=content or f"# {path}", language=lang)


def test_classify_entry_point():
    files = [
        _make_file("main.py"),
        _make_file("utils/helper.py"),
    ]
    result = preprocess(files, "")
    # main.py should be classified as entry_point (highest priority)
    assert result.classified[0].role == "entry_point"
    assert result.classified[0].file.path == Path("main.py")


def test_classify_model():
    files = [
        _make_file("models/user.py"),
        _make_file("other.py"),
    ]
    result = preprocess(files, "")
    model_file = next(c for c in result.classified if c.role == "model")
    assert model_file.file.path == Path("models/user.py")


def test_classify_api():
    files = [
        _make_file("routes/users.py"),
        _make_file("api/health.py"),
    ]
    result = preprocess(files, "")
    api_files = [c for c in result.classified if c.role == "api"]
    assert len(api_files) == 2


def test_counts():
    files = [
        _make_file("main.py", "python"),
        _make_file("app.ts", "typescript"),
        _make_file("index.tsx", "typescript"),
    ]
    result = preprocess(files, "test structure")
    assert result.total_files == 3
    assert result.python_count == 1
    assert result.typescript_count == 2


def test_build_file_summary():
    files = [
        _make_file("main.py", content="print('hello world')"),
        _make_file("routes/users.py", content="@router.get('/')"),
    ]
    result = preprocess(files, "src/ (2 files)")
    summary = build_file_summary_for_llm(result)
    assert "main.py" in summary
    assert "routes/users.py" in summary
    assert "entry_point" in summary
