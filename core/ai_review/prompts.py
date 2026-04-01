"""
core/ai_review/prompts.py
──────────────────────────
Centralised home for all LLM prompt templates.

Keeping prompts separate from logic makes them easy to iterate on,
translate, or swap without touching any business logic code.
"""

from __future__ import annotations
from string import Template


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert code reviewer and software engineering mentor.
Your job is to help students and developers improve their code.

Rules you MUST follow:
1. Always explain problems in simple, friendly language — imagine you are explaining to a smart high-school student.
2. Never be harsh or discouraging. Focus on what can be improved.
3. Always provide concrete, working code examples for your fixes.
4. Be specific — reference actual line numbers and variable names from the code.
5. Format your entire response as valid JSON (no markdown, no extra text).
6. Be accurate — if you're not sure about something, say so.
7. Distinguish true issues from false positives.
8. Prefer secure and production-safe fixes over quick hacks.
9. Do NOT invent vulnerabilities that are not visible in the code.
10. Only report an issue when the exact risky pattern is present in the given code.
11. If a security claim depends on missing context, classify it as "uncertain".
"""


# ─── Main Review Prompt ───────────────────────────────────────────────────────

REVIEW_PROMPT_TEMPLATE = Template("""
Review the following $language code. 

Static analysis tools have already found these issues:
$static_issues_summary

Your job is to:
1. Classify each static-analysis issue as one of: correct_issue, false_positive, partially_correct, uncertain
2. Explain each issue in simple words (1-2 sentences per issue)
3. Identify real issues MISSED by static tools (logic bugs, security flaws, bad error handling, input validation gaps, algorithm inefficiencies)
4. Write the full IMPROVED version of the code with all problems fixed
5. Give an overall quality score from 0 to 100
6. Give 3-7 practical recommendations
7. Ensure fixes include:
  - Secure authentication patterns
  - Proper exception handling
  - Safe file handling (with open + context manager + validation)
  - No eval/exec for untrusted input
  - Input validation and type checks
  - Performance improvements where possible
  - Python best practices and PEP 8 style
8. For SQL injection classification, use this rule:
  - correct_issue: untrusted input is interpolated/concatenated and query is executed
  - partially_correct: unsafe query string is built but execution context is not shown
  - false_positive: query uses proper parameterized placeholders/bound parameters
  - uncertain: query handling cannot be verified from the provided snippet

Security checks you MUST consider:
  - Hardcoded secrets or API keys
  - Unsafe eval() or exec()
  - Unsafe pickle.loads()/pickle.load() or yaml.load() with unsafe loader
  - SQL query string concatenation/interpolation
  - Path traversal risks in file reads/writes
  - Insecure randomness for security tokens
  - Missing input validation
  - Missing exception handling

Also check for performance issues such as:
  - O(n^2) loops that can be optimized
  - Inefficient list/string concatenation in loops
  - Repeated expensive operations
  - Unnecessary memory allocations

Line-number rule:
  - When possible, return the exact line number.
  - If unsure, return null.

Deduplication rule:
  - Do not repeat the same finding across static_issue_review, missed_issues, and issues.

Reasoning rule:
  - Internally reason through the code step-by-step before finalizing JSON.

CODE TO REVIEW:
```$language_lower
$code
```

Respond with ONLY this JSON structure (no other text):
{
  "summary": "2-3 sentence plain-English summary of the code and its main problems",
  "score": <integer 0-100>,
  "static_issue_review": [
    {
      "status": "correct_issue|false_positive|partially_correct|uncertain",
      "line": <integer or null>,
      "title": "Original issue title",
      "severity": "critical|high|medium|low|info",
      "reason": "Why this classification is correct",
      "fix": "Correct and secure fix"
    }
  ],
  "missed_issues": [
    {
      "severity": "critical|high|medium|low|info",
      "line": <integer or null>,
      "title": "Missed issue title",
      "description": "What was missed and why it matters",
      "suggestion": "Correct and secure fix"
    }
  ],
  "issues": [
    {
      "severity": "<critical|high|medium|low|info>",
      "line": <integer or null>,
      "title": "Short title",
      "description": "Plain English explanation of the problem",
      "suggestion": "How to fix it in one or two sentences",
      "evidence": {
        "function": "Function/class name where issue appears, or null",
        "snippet": "Exact risky code snippet from the provided code"
      }
    }
  ],
  "improved_code": "The complete improved version of the code (JSON-safe string with escaped newlines as \\n and escaped quotes)",
  "recommendations": [
    "Recommendation 1",
    "Recommendation 2",
    "Recommendation 3"
  ]
}

Scoring guide:
  100:   No correctness, security, validation, reliability, or style issues found
  90-99: Near-perfect code, very few minor issues
  75-89:  Good code with minor issues
  60-74:  Acceptable but has multiple issues that need fixing
  40-59:  Has significant problems that affect correctness or security
  0-39:   Serious issues — may not work correctly, has security flaws

Score consistency rules:
  - If issues + missed_issues are both empty, set score to exactly 100.
  - Do not assign 100 when any critical/high issue exists.

Score deductions:
  - Critical issue: -25
  - High issue: -15
  - Medium issue: -8
  - Low issue: -3
""")


# ─── Fallback Prompt (smaller context, for low-token APIs) ───────────────────

MINI_REVIEW_PROMPT_TEMPLATE = Template("""
Review this $language code snippet and respond with ONLY valid JSON:

CODE:
```
$code
```

JSON format:
{
  "summary": "Brief summary",
  "score": <0-100>,
  "static_issue_review": [{"status": "correct_issue|false_positive|partially_correct|uncertain", "line": null, "title": "...", "severity": "high|medium|low|info", "reason": "...", "fix": "..."}],
  "missed_issues": [{"severity": "high|medium|low", "line": null, "title": "...", "description": "...", "suggestion": "..."}],
  "issues": [{"severity": "high|medium|low", "line": null, "title": "...", "description": "...", "suggestion": "...", "evidence": {"function": null, "snippet": "..."}}],
  "improved_code": "improved version here (JSON-safe escaped string)",
  "recommendations": ["tip 1", "tip 2"]
}
""")


# ─── Helper: Format static issues for the prompt ─────────────────────────────

def format_static_issues_for_prompt(issues: list) -> str:
    """
    Convert a list of Issue objects into a compact text block for the prompt.
    This gives the LLM context about what the static tools already found
    so it can focus on issues the static tools missed.
    """
    if not issues:
        return "No issues found by static analysis tools."

    lines = []
    for issue in issues[:20]:   # Cap at 20 to avoid prompt bloat
        severity = getattr(issue.severity, "value", issue.severity)
        line_ref = f"line {issue.line}" if issue.line else "location unknown"
        lines.append(
            f"  - [{str(severity).upper()}] {issue.title} ({line_ref})"
        )

    if len(issues) > 20:
        lines.append(f"  ... and {len(issues) - 20} more issues")

    return "\n".join(lines)


def build_review_prompt(
    code: str,
    language: str,
    static_issues: list,
    use_mini: bool = False,
) -> str:
    """
    Build the final prompt string to send to the LLM.

    Args:
        code:           The source code to review
        language:       Language display name (e.g. "Python")
        static_issues:  Issues already found by static analysis
        use_mini:       If True, use a shorter prompt (for small-context models)
    """
    if use_mini:
        return MINI_REVIEW_PROMPT_TEMPLATE.substitute(
            language=language,
            code=code[:3000],   # Hard limit for mini prompt
        )

    static_summary = format_static_issues_for_prompt(static_issues)

    return REVIEW_PROMPT_TEMPLATE.substitute(
        language=language,
        language_lower=language.lower(),
        code=code,
        static_issues_summary=static_summary,
    )
