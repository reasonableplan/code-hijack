# ruff: noqa: E501
# 이 파일은 LLM 프롬프트 템플릿이라 긴 문자열 리터럴이 본질적. E501 제외.
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
      "ref_files": ["<file path>:<line_number>", "<file path>:<start>-<end>"],
      "good_example": "<ACTUAL code snippet from the repo, copy-pasted>",
      "bad_example": "<ACTUAL anti-pattern code, NOT a descriptive comment>",
      "reason": "<1-sentence intent gist, ≤150 chars>",
      "layer": "frontend" or "backend" or "db" or "devops" or "shared",
      "evidence": [
        {
          "kind": "commit" or "revert" or "doc",
          "ref": "<short SHA from <history>, or repo-relative path from <repo_context>>",
          "headline": "<verbatim subject or section heading, ≤120 chars>",
          "quote": "<verbatim body excerpt, ≤500 chars>",
          "intent_kind": "rejection" or "constraint" or "incident" or "preference" or null
        }
      ]
    }
  ],
  "anti_patterns": [{"pattern": "", "reason": "", "alternative": ""}],
  "file_type_guides": {"<file_type>": "<guidance>"},
  "checklist": ["<item>"]
}

QUALITY REQUIREMENTS (non-negotiable):

0. OUTPUT LANGUAGE: write every prose field (rule, reason, design_intent,
   anti_patterns, file_type_guides, checklist) in English, regardless of the
   conversation language. Evidence headline/quote and code excerpts stay
   verbatim in their original language.

1. `ref_files`: MUST include line number(s). Format: "path/to/file.py:42" for a single
   line, "path/to/file.py:42-58" for a range. NEVER just the filename.
   If you cite a function/class, point to its definition line (def/class line).

2. `good_example`: MUST be actual code copied from one of the ref_files — verbatim,
   not paraphrased. Keep it short (3-10 lines). If you can't extract a real snippet,
   don't create the rule.

3. `bad_example`: MUST be actual anti-pattern code, not a comment describing what to
   avoid. NEVER write "# don't do this" or "# X is not allowed" — always provide
   the concrete code form the author avoided or that would break the rule.
   GOOD bad_example:  `x = eval(user_input)`
   BAD  bad_example:  `# runs user input through eval`

4. `priority`: MUST only for non-negotiable rules (violation = PR rejection).
   SHOULD for strong preferences. Don't inflate — when uncertain, use SHOULD.
   Calibration target: ~30-40% MUST, ~60-70% SHOULD across all rules.
   If overall MUST ratio exceeds 40%, or any single category exceeds 50%,
   re-evaluate — these thresholds match the lint emitted by `write_output`.

   PRIORITY SELF-CHECK (mandatory before emitting JSON):
   After drafting all rules in this category, count MUST/total. If > 50%,
   pick the rule whose violation is LEAST likely to trigger PR rejection
   (typical candidates: perf optimization that affects only large inputs,
   readability/consistency rule, layering preference where the alternative
   still works) and downgrade it to SHOULD before returning.

   Note: the post-write `evidence.downgrade_speculative_rules` pass only
   demotes rules with NO cited evidence. Cited MUSTs are NEVER auto-
   demoted — over-tagging cited rules as MUST is a writer-side mistake
   that this self-check is your only defence against. Heuristic: a cited
   commit body that says "to avoid O(n²) on large inputs" is a perf
   optimization → SHOULD, not MUST. A cited commit body that says
   "without this, server leaks 500 to client / loads 1GB into memory"
   is a correctness/safety guarantee → MUST.

5. `reason` — 1-SENTENCE INTENT GIST:
   ≤150 chars. The headline of the senior's why. Examples:
     "Minimise async-path runtime regressions (per Revert a1b2c3d)."
     "Reversibility of migrations is required by RDS rollback policy."
   Do NOT put long explanations or multiple citations here — those go in
   `evidence`. If no evidence available, prefix with "[no-evidence]".

   IMPORTANT: `reason` is NOT a paraphrase of `evidence[].quote`. The quote
   carries the senior's verbatim words; `reason` carries the rule's design
   intent in compressed form (or a short quoted phrase + commit ref). Do not
   restate the quote — that is pure redundancy. The reader should be able to
   skim `reason` and read `quote` for full context, not read both saying the
   same thing twice.

6. `evidence` — STRUCTURED CITATIONS (this is the whole point of the tool):
   The senior's actual reasoning lives in commit bodies, ADRs, and reverts.
   Your job is to PRESERVE that reasoning verbatim, not paraphrase it.

   For each rule, fill `evidence` with one or more entries drawn from the
   <history> and <repo_context> blocks in the input:

   - `kind`: "commit" for any commit, "revert" for entries listed under
     `reverts touching this file`, "doc" for README / ARCHITECTURE / ADR /
     CONTRIBUTING citations.
   - `ref`: short SHA (commit/revert) OR repo-relative path (doc).
     Both MUST appear in the input. NEVER invent SHAs or doc paths.
   - `headline`: copy the actual subject (commit) or section heading (doc)
     VERBATIM. ≤120 chars. Single-quote inside the JSON string is fine.
   - `quote`: copy a substantive sentence from the body (commit body / doc
     paragraph) VERBATIM. ≤500 chars. This is what the user will read in the
     output — preserve the senior's voice, not yours.
   - `intent_kind`: classify the WHY. Pick one or null:
       * "rejection" — pattern was tried then rolled back (revert evidence)
       * "constraint" — external requirement (perf SLA, security, compliance,
         tool limitation, spec)
       * "incident" — past failure or post-mortem driving the choice
       * "preference" — internal philosophy / consistency / trade-off
     If you cannot tell from the source, set null. Do NOT guess.

   MATCHING PROCEDURE — for each rule, do this:
   1. List the file paths cited in `ref_files` (drop the `:line` suffix).
   2. Find commits in <history> whose touched files intersect step 1.
   2b. If step 2 yields no file intersect, fall back to SEMANTIC INTENT
       matching: read every commit in <history> (subject + body) and identify
       any whose RECORDED DECISION aligns with this rule's reason — same
       design intent, even if the touched files don't overlap with ref_files.
       Examples of alignment:
         rule: "deprecate implicit shortcuts via warning + explicit alternative"
         commit: "Deprecate `app=...` in favour of explicit `WSGITransport`"
         → aligned (both express the same deprecation discipline).

         rule: "model multi-round-trip auth as generator protocol"
         commit: "Switched Auth to generator-based flow because Digest needs
                  the response of the first request"
         → aligned (commit body states the exact reason the rule encodes).
       Pick at most ONE commit, only when alignment is unambiguous. The
       senior must have written something that you could quote as the WHY of
       this rule. If you would have to paraphrase or stretch, do NOT match —
       leave evidence: [] with [no-evidence] prefix. A false citation is much
       worse than an empty one.

       (A keyword-overlap helper `find_semantic_candidates` exists in
       `core.archaeology` for non-LLM call-sites; for LLM-driven analysis,
       prefer reading the commit bodies and judging intent directly — Jaccard
       is too coarse for principle-level rules in mixed-language codebases.)
   3. Among those, prefer commits whose body uses decision-pattern keywords
      ("instead of", "rather than", "decided to", "reverted because",
      "switched from", "rejected", "abandoned") aligned with the rule's reason.
   4. Pick 1-2 most relevant commits. Map the body's keyword to `intent_kind`:
        - "reverted because" / "rolled back" / "regression"  → "incident"
        - "rejected" / "abandoned" / "switched from"          → "rejection"
        - "instead of" / "rather than" / "decided to" /
          "as opposed to" / "to avoid" / "to prevent"         → "preference"
        - "due to" / "motivated by" / external SLA / spec /
          compliance / tool limit                              → "constraint"
      When multiple keywords match, priority: rejection > incident > preference.
   5. Doc evidence works the same way against <repo_context>: ref = repo-
      relative path, headline = section heading verbatim, quote = paragraph
      verbatim.

   If no evidence is available in the input, set `evidence: []`,
   `confidence: "low"`, and prefix `reason` with "[no-evidence]".

   DO NOT pad evidence with paraphrased filler. Drop a rule entirely rather
   than inventing evidence — extracting the senior's *actual* recorded
   reasoning is the whole point. A false citation is much worse than an
   empty one.

7. `rule` — PRINCIPLE OVER PRESCRIPTION:
   The rule body must describe the underlying DESIGN PRINCIPLE, not prescribe
   a specific internal class/function/sentinel/helper name unique to this repo.
   The rules will be consumed by an agent writing code in OTHER projects where
   that internal symbol does not exist — so a rule that says "use BaseTransport"
   or "use the USE_CLIENT_DEFAULT sentinel" or "call to_bytes from _utils.py"
   transfers to nothing.

   Abstract one level. Describe what design constraint the symbol satisfies.
   Cite the internal symbol in `good_example` (concrete evidence) and `ref_files`
   — keep the rule body principle-level.

   GOOD rule body (transferable):
     "Per-call optional parameters must distinguish 'unset' from 'explicit None'
      via a dedicated sentinel object, so caller-level and client-level defaults
      can fall through cleanly."
   BAD rule body (cargo-cult, codebase-bound):
     "Use the USE_CLIENT_DEFAULT sentinel for unset request-level params."

   GOOD rule body:
     "Multi-round-trip authentication schemes must be modeled as a generator
      protocol yielding Request objects, so the client transport stays decoupled
      from any specific auth algorithm."
   BAD rule body:
     "Authentication must be implemented via the Auth.auth_flow generator method."

   Heuristic: if the rule body contains a specific identifier name you would
   ALSO put in good_example, the body is too prescriptive. Move that identifier
   to good_example and rewrite the rule as a constraint on shape/behavior.

---

FEW-SHOT EXAMPLE #1 — GOOD quality rule (intent_kind=incident):

{
  "rule": "subprocess.run must always be called with the capture_output=True + text=True combination",
  "priority": "MUST",
  "confidence": "high",
  "ref_files": ["src/hijack/core/fetcher.py:229-237"],
  "good_example": "result = subprocess.run(cmd, capture_output=True, text=True)\\nif result.returncode != 0:\\n    raise FetchError(FETCH_001, result.stderr.strip())",
  "bad_example": "subprocess.run([\\"git\\", \\"clone\\", target, tmpdir])",
  "reason": "Surface git stderr on clone failure (per a1b2c3d).",
  "layer": "backend",
  "evidence": [
    {
      "kind": "commit",
      "ref": "a1b2c3d",
      "headline": "fix: surface git stderr on clone failure",
      "quote": "Without capture_output, stderr is lost and FetchError leaks an empty string to the user.",
      "intent_kind": "incident"
    }
  ]
}

FEW-SHOT EXAMPLE #2 — GOOD quality rule (intent_kind=preference, principle-level):

{
  "rule": "Multi-round-trip authentication schemes must be modeled as a generator protocol yielding Request objects, so client transport stays decoupled from any specific auth algorithm.",
  "priority": "MUST",
  "confidence": "high",
  "ref_files": ["src/auth.py:22-110"],
  "good_example": "class Auth:\\n    def auth_flow(self, request):\\n        yield request\\n\\n    def sync_auth_flow(self, request):\\n        flow = self.auth_flow(request)\\n        request = next(flow)\\n        while True:\\n            response = yield request\\n            try:\\n                request = flow.send(response)\\n            except StopIteration:\\n                break",
  "bad_example": "def authenticate(request, response_of_first_attempt=None):\\n    if response_of_first_attempt and response_of_first_attempt.status_code == 401:\\n        ...",
  "reason": "Decouple transport from auth algorithm (per d4e5f6a refactor).",
  "layer": "shared",
  "evidence": [
    {
      "kind": "commit",
      "ref": "d4e5f6a",
      "headline": "Refactor Auth into generator-based flow",
      "quote": "Originally Auth was a Callable[[Request], Request], but Digest needs the response of the first request to compute the second. Switched to generator protocol so multi-round schemes don't require Client-internal hooks.",
      "intent_kind": "preference"
    }
  ]
}

FEW-SHOT EXAMPLE #3 — BAD quality rule (AVOID these mistakes):

{
  "rule": "Write good code",                       // ❌ too abstract
  "priority": "MUST",                              // ❌ MUST on an unjudgeable rule
  "confidence": "high",
  "ref_files": ["src/main.py"],                    // ❌ no line number
  "good_example": "# good example code",           // ❌ a comment, not real code
  "bad_example": "# don't do this",                // ❌ description — pattern matching impossible
  "reason": "Because it matters",                  // ❌ no design intent
  "layer": "shared",
  "evidence": []                                   // ❌ no source — drop the rule entirely
}

Avoid every ❌ in the NEGATIVE EXAMPLE. In particular:
- rule states a concrete behavior (WHAT, with the WHY implied)
- ref_files must use the "path:line" format
- good/bad_example are real code excerpts, not comments
- reason is a 1-sentence intent gist (≤150 chars)
- if evidence is empty, only [no-evidence] rules pass — otherwise drop the rule"""

_LAYER_INSTRUCTION = (
    "LAYER FIELD: Each file in <files> has a header like "
    "`### path/to/file.py [role=core, layer=backend]`. The `layer=` value "
    "is determined by the preprocessor and is AUTHORITATIVE — copy it for "
    "any rule whose ref_files cites that file. Do NOT override based on "
    "filename guessing.\n"
    "When a rule cites files spanning multiple layers, use 'shared'. "
    "Reference values: 'frontend' (UI/React/Vue), 'backend' (server/API/"
    "service), 'db' (database/migration/ORM), 'devops' (CI/Docker/infra), "
    "'shared' (cross-cutting concerns or multi-layer rules)."
)


def build_category_prompt(
    category: str,
    file_summaries: list[str],
    *,
    repo_context: str = "",
) -> str:
    """카테고리 분석 프롬프트를 반환한다.

    file_summaries: 각 파일의 내용 또는 요약 문자열 목록.
    repo_context: pre-rendered <repo_context> block from `core.docs`. Empty
    string means no repo-level docs were collected — the block is omitted
    rather than emitted with a placeholder.
    """
    if category not in _CATEGORY_INSTRUCTIONS:
        raise ValueError(
            f"Unknown category: {category!r}. Must be one of {ALL_CATEGORIES}."
        )

    category_instruction = _CATEGORY_INSTRUCTIONS[category]
    joined = "\n\n".join(file_summaries)

    context_section = f"{repo_context}\n\n" if repo_context else ""

    return (
        f"You are an expert code analyst specializing in {category} analysis.\n\n"
        f"{context_section}"
        f"<files>\n{joined}\n</files>\n\n"
        f"{category_instruction}\n\n"
        f"{_OUTPUT_FORMAT}\n\n"
        f"{_LAYER_INSTRUCTION}"
    )
