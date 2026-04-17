from __future__ import annotations

MVP_CATEGORIES: list[str] = ["architecture", "coding_style", "api_design"]

LAYERS: list[str] = ["frontend", "backend", "db", "devops", "shared"]

_CATEGORY_INSTRUCTIONS: dict[str, str] = {
    "architecture": (
        "Analyze the overall architecture: layer separation, module dependencies, "
        "why this structure was chosen. Focus on: entry points, service/repository layers, "
        "dependency flow, what patterns are enforced (e.g. clean architecture, hexagonal)."
    ),
    "coding_style": (
        "Analyze coding conventions: naming (variables, functions, classes, files), "
        "function length, class structure, import organization, comment patterns, "
        "error handling style. Extract rules that make this codebase consistently readable."
    ),
    "api_design": (
        "Analyze API design patterns: endpoint naming, request/response structure, "
        "error responses, authentication patterns, versioning, HTTP method usage. "
        "If this is a CLI or library (no HTTP), analyze the public interface design instead."
    ),
}

_OUTPUT_FORMAT = """\
Return a JSON object with this exact structure:
{
  "design_intent": "<overall design intent>",
  "rules": [
    {
      "rule": "<specific rule>",
      "priority": "MUST" or "SHOULD",
      "confidence": "high" or "medium" or "low",
      "ref_files": ["<file path>"],
      "good_example": "<code showing correct usage>",
      "bad_example": "<code showing incorrect usage>",
      "reason": "<why this rule>",
      "layer": "frontend" or "backend" or "db" or "devops" or "shared"
    }
  ],
  "anti_patterns": [{"pattern": "", "reason": "", "alternative": ""}],
  "file_type_guides": {"<file_type>": "<guidance>"},
  "checklist": ["<item>"]
}"""

_LAYER_INSTRUCTION = (
    "For each rule, assign a `layer` field: "
    "'frontend' for UI/React/Vue code, "
    "'backend' for server/API/service code, "
    "'db' for database/migration/ORM code, "
    "'devops' for CI/Docker/infra code, "
    "'shared' for cross-cutting concerns."
)


def build_category_prompt(category: str, file_summaries: list[str]) -> str:
    """카테고리 분석 프롬프트를 반환한다.

    file_summaries: 각 파일의 내용 또는 요약 문자열 목록.
    """
    if category not in _CATEGORY_INSTRUCTIONS:
        raise ValueError(
            f"Unknown category: {category!r}. Must be one of {MVP_CATEGORIES}."
        )

    category_instruction = _CATEGORY_INSTRUCTIONS[category]
    joined = "\n\n".join(file_summaries)

    return (
        f"You are an expert code analyst specializing in {category} analysis.\n\n"
        f"<files>\n{joined}\n</files>\n\n"
        f"{category_instruction}\n\n"
        f"{_OUTPUT_FORMAT}\n\n"
        f"{_LAYER_INSTRUCTION}"
    )
