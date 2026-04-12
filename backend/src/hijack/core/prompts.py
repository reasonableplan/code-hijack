"""Structured prompts for each analysis category."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are code-hijack — a senior code analyst. Your job is to deeply analyze a codebase \
and extract the coding style, architecture decisions, and design philosophy so that an \
AI agent can replicate the exact same style.

You don't just find patterns — you explain WHY the developer made each decision.

Output rules:
- Be specific. Use actual file paths and code from the provided files.
- Every rule must include a ✅ good example and ❌ bad example from the actual codebase.
- Mark each rule as MUST (critical) or SHOULD (recommended).
- Include reference files that an AI agent should read before writing similar code.
- Write in the language of the codebase comments (Korean if comments are Korean, English otherwise).
"""

# Category-specific user prompts
CATEGORY_PROMPTS: dict[str, str] = {
    "architecture": """\
Analyze the **architecture** of this project.

Focus on:
1. Overall structure — how is the codebase organized? What layers exist?
2. Module dependencies — which modules depend on which?
3. Design intent — WHY was it structured this way? What problem does this structure solve?
4. Entry points — how does execution flow start?
5. Separation of concerns — how are responsibilities divided?

For each finding, provide:
- A concrete rule that an AI agent should follow
- The reference file(s) to read
- ✅ How this project does it (with actual code)
- ❌ How NOT to do it
- A checklist item for self-verification

Output format:
```
## Architecture Analysis

### Design Intent
(Explain the overall architecture philosophy)

### Rules
1. **[MUST/SHOULD] Rule description**
   - 📁 Reference: path/to/file.py
   - ✅ Good:
     ```python
     actual code from the project
     ```
   - ❌ Bad:
     ```python
     what NOT to do
     ```
   - Reason: why this matters

### Checklist
- [ ] Check item 1
- [ ] Check item 2
```
""",
    "coding_style": """\
Analyze the **coding style** of this project.

Focus on:
1. Naming conventions — functions, variables, classes, files, directories
2. Code formatting — line length, indentation, blank lines
3. Function/method patterns — size, parameter style, return patterns
4. Class patterns — inheritance, composition, mixins
5. Comment/docstring style — when and how they write comments
6. Import organization — order, grouping, absolute vs relative
7. Error handling patterns — try/except style, custom exceptions
8. Type hints — usage level, style (Optional vs | None, etc.)

For each finding, provide:
- A concrete rule
- The reference file(s)
- ✅ Actual code example from the project
- ❌ What NOT to do
- A checklist item

Output format:
```
## Coding Style Analysis

### Design Intent
(Explain the coding philosophy)

### Rules
1. **[MUST/SHOULD] Rule description**
   - 📁 Reference: path/to/file.py
   - ✅ Good:
     ```
     actual code
     ```
   - ❌ Bad:
     ```
     what NOT to do
     ```
   - Reason: why

### Checklist
- [ ] Check item
```
""",
    "api_design": """\
Analyze the **API design** of this project.

Focus on:
1. Endpoint naming — URL patterns, HTTP methods, versioning
2. Request/Response format — data structure, naming (camelCase vs snake_case)
3. Error handling — error response format, error codes, status codes
4. Authentication/Authorization — how auth is handled in APIs
5. Pagination — pattern used (offset/limit, cursor)
6. Middleware — what middleware exists and why
7. Dependency injection — how dependencies are passed to handlers
8. Validation — input validation approach

For each finding, provide:
- A concrete rule
- The reference file(s)
- ✅ Actual code example
- ❌ What NOT to do
- A checklist item

Output format:
```
## API Design Analysis

### Design Intent
(Explain the API design philosophy)

### Rules
1. **[MUST/SHOULD] Rule description**
   - 📁 Reference: path/to/file.py
   - ✅ Good:
     ```
     actual code
     ```
   - ❌ Bad:
     ```
     what NOT to do
     ```
   - Reason: why

### Checklist
- [ ] Check item
```
""",
}

MVP_CATEGORIES = ["architecture", "coding_style", "api_design"]


def build_analysis_prompt(
    category: str,
    files_content: str,
    structure_map: str,
) -> str:
    """Build the full user prompt for a category analysis."""
    base = CATEGORY_PROMPTS[category]
    return (
        f"{base}\n\n"
        f"---\n\n"
        f"## Project Structure\n```\n{structure_map}\n```\n\n"
        f"## Source Files\n{files_content}"
    )
