from __future__ import annotations

MVP_CATEGORIES: list[str] = ["architecture", "coding_style", "api_design"]

ALL_CATEGORIES: list[str] = [
    "architecture",
    "coding_style",
    "api_design",
    "testing",
    "dependencies",
    "security",
    "performance",
    "devops",
    "state_management",
    "data_model",
]

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
    "testing": (
        "Analyze testing strategy: test framework choice, directory layout, naming conventions, "
        "fixture and mock patterns, coverage targets, what gets unit-tested vs integration-tested, "
        "how edge cases and error paths are covered. Extract rules that make tests trustworthy."
    ),
    "dependencies": (
        "Analyze dependency management: library selection rationale (why this lib over "
        "alternatives), version pinning strategy, lockfile discipline, import organization "
        "within files, how transitive dependencies are handled. Extract rules for adding "
        "or upgrading packages."
    ),
    "security": (
        "Analyze security practices: authentication and authorization patterns, "
        "secret and credential management (env vars, vaults), input validation and "
        "sanitization, injection prevention (SQL, command, XSS), rate limiting, "
        "and how sensitive data is handled and logged."
    ),
    "performance": (
        "Analyze performance patterns: caching strategies (in-memory, Redis, HTTP), "
        "async/concurrent execution patterns, database query optimization "
        "(N+1 prevention, index usage), memory management, expensive operation "
        "avoidance, and profiling/monitoring hooks."
    ),
    "devops": (
        "Analyze DevOps conventions: CI/CD pipeline structure (steps, jobs, triggers), "
        "Docker image design (base images, layer caching, multi-stage), environment "
        "variable management across environments, deployment strategies "
        "(blue-green, rolling), and infrastructure-as-code patterns."
    ),
    "state_management": (
        "Analyze state management patterns: how global, server, and local state are "
        "separated, data flow direction (unidirectional, bidirectional), mutation rules "
        "(immutable vs mutable), caching of remote data, optimistic updates, "
        "and how state resets or invalidates."
    ),
    "data_model": (
        "Analyze data model design: table/entity naming, relationship patterns "
        "(1:N, N:M, self-referential), soft-delete vs hard-delete decisions, "
        "audit fields (created_at, updated_at), ORM usage conventions, "
        "migration naming and reversibility, and index strategy."
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
            f"Unknown category: {category!r}. Must be one of {ALL_CATEGORIES}."
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
