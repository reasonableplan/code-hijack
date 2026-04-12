"""Claude Code skill entry point for /code-hijack command.

This module defines the skill that runs inside a Claude Code session.
The analysis uses the current session's Claude instance (no API cost).

Usage in Claude Code:
  /code-hijack https://github.com/fastapi/fastapi
  /code-hijack /path/to/local/project
"""

# NOTE: This file serves as documentation and the skill prompt template.
# The actual skill execution happens through Claude Code's skill system,
# which reads the SKILL.md file and executes the analysis using the
# session's built-in Claude instance.
#
# The core/ modules (fetcher, preprocessor, analyzer, generator) contain
# all shared logic. In skill mode, the LLM calls are replaced by
# Claude Code's own analysis capabilities.

SKILL_PROMPT = """\
You are running the code-hijack skill. Analyze the target codebase and extract \
coding style rules that an AI agent can follow.

## Steps

1. **Fetch**: Read the project files and build a structure map
2. **Preprocess**: Identify key files by role (entry point, model, API, test, etc.)
3. **Analyze**: For each category (architecture, coding_style, api_design), deeply \
analyze the code and extract rules with:
   - ✅/❌ example code from the actual project
   - Reference files to read before writing similar code
   - MUST/SHOULD priority
   - Checklist items for self-verification
4. **Generate**: Create output files in docs/hijacked/

Show results for each category and ask for feedback before moving to the next.
"""
