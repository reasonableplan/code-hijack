"""Tests for session management."""

from hijack.core.session import create_session_id, _extract_repo_name


def test_extract_github_url():
    assert _extract_repo_name("https://github.com/fastapi/fastapi") == "fastapi"
    assert _extract_repo_name("https://github.com/vercel/next.js.git") == "next.js"
    assert _extract_repo_name("https://github.com/owner/my-repo") == "my-repo"


def test_extract_local_path():
    assert _extract_repo_name("/home/user/my-project") == "my-project"
    assert _extract_repo_name("./src") == "src"


def test_create_session_id():
    sid = create_session_id("https://github.com/fastapi/fastapi")
    assert "fastapi" in sid
    # Should start with date pattern
    assert sid[4] == "-"
    assert sid[7] == "-"
