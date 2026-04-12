"""Tests for analyzer module — parsing LLM output."""

from hijack.core.analyzer import _parse_rules_from_markdown, _parse_checklist, _parse_design_intent


SAMPLE_LLM_OUTPUT = """\
## Architecture Analysis

### Design Intent
This project uses a layered architecture with clear separation of concerns.

### Rules
1. **[MUST] All routes must be in the routes/ directory**
   - 📁 Reference: routes/users.py
   - ✅ Good:
     ```python
     router = APIRouter(prefix="/users")
     ```
   - ❌ Bad:
     ```python
     @app.get("/users")
     ```
   - Reason: Keeps routing logic separate from business logic

2. **[SHOULD] Use dependency injection for database sessions**
   - 📁 Reference: deps.py
   - ✅ Good:
     ```python
     async def get_db() -> AsyncGenerator:
         async with async_session() as session:
             yield session
     ```
   - ❌ Bad:
     ```python
     db = SessionLocal()
     ```
   - Reason: Ensures proper session lifecycle management

### Checklist
- [ ] Routes are in routes/ directory
- [ ] Dependencies use Depends()
- [ ] No direct DB session creation in route handlers
"""


def test_parse_rules():
    rules = _parse_rules_from_markdown(SAMPLE_LLM_OUTPUT)
    assert len(rules) == 2

    assert rules[0].priority == "MUST"
    assert "routes/ directory" in rules[0].rule
    assert rules[0].ref_files == ["routes/users.py"]
    assert "APIRouter" in rules[0].good_example
    assert "@app.get" in rules[0].bad_example
    assert "separate" in rules[0].reason.lower()

    assert rules[1].priority == "SHOULD"
    assert "dependency injection" in rules[1].rule.lower()


def test_parse_checklist():
    items = _parse_checklist(SAMPLE_LLM_OUTPUT)
    assert len(items) == 3
    assert "routes/ directory" in items[0]
    assert "Depends()" in items[1]


def test_parse_design_intent():
    intent = _parse_design_intent(SAMPLE_LLM_OUTPUT)
    assert "layered architecture" in intent.lower()


def test_parse_empty_input():
    rules = _parse_rules_from_markdown("")
    assert rules == []
    items = _parse_checklist("")
    assert items == []
    intent = _parse_design_intent("")
    assert intent == ""
