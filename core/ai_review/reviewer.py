"""
core/ai_review/reviewer.py
───────────────────────────
High-level AI review orchestrator.

Flow:
  1. Check if LLM is available (API key configured).
  2. Build a prompt that includes static analysis findings.
  3. Call the LLM API.
  4. Parse the JSON response into an AIReviewResult.
  5. If anything fails, return a graceful fallback result.
"""

from __future__ import annotations
import ast
import json
import re
from typing import Optional

from config.settings import settings
from models.schemas import AIReviewResult, Issue, IssueCategory, Severity
from core.ai_review.llm_client import get_llm_client, LLMError
from core.ai_review.prompts import SYSTEM_PROMPT, build_review_prompt
from utils.code_utils import truncate_code, clean_llm_code_response


# Maximum lines of code to send to the LLM
# (keeps API costs and latency low on large files)
LLM_MAX_LINES = 300


def run_ai_review(
    code: str,
    language: str,
    static_issues: list,
) -> AIReviewResult:
    """
    Run the LLM-based code review.

    Args:
        code:          Source code to review
        language:      Programming language name (e.g. "Python")
        static_issues: Issues already found by static analysis

    Returns:
        AIReviewResult — populated if LLM succeeded, minimal if not.
    """
    # ── Check if LLM is available ─────────────────────────────────────────────
    client = get_llm_client()

    if client is None:
        return _static_only_fallback(static_issues)

    # ── Truncate code if it's very long ───────────────────────────────────────
    code_for_llm, was_truncated = truncate_code(code, max_lines=LLM_MAX_LINES)

    # ── Build prompt ──────────────────────────────────────────────────────────
    user_prompt = build_review_prompt(
        code=code_for_llm,
        language=language,
        static_issues=static_issues,
        use_mini=False,
    )

    # ── Call LLM ──────────────────────────────────────────────────────────────
    try:
        raw_response = client.complete(
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.15,   # Low temperature for consistent, accurate reviews
            max_tokens=4096,
        )
    except LLMError as exc:
        return AIReviewResult(
            ai_available=False,
            error_message=f"AI review failed: {exc}",
        )
    except Exception as exc:
        return AIReviewResult(
            ai_available=False,
            error_message=f"Unexpected error during AI review: {exc}",
        )

    # ── Parse response ────────────────────────────────────────────────────────
    try:
        result = _parse_llm_response(raw_response)
        result.ai_available = True

        # If code was truncated, note that in the improved_code
        if was_truncated and result.improved_code:
            result.improved_code = (
                f"# Note: The original code was truncated for the AI review.\n"
                f"# The improved code below covers the portion that was reviewed.\n\n"
                + result.improved_code
            )

        return result

    except Exception as exc:
        return AIReviewResult(
            ai_available=False,
            error_message=(
                f"Could not parse the AI response: {exc}. "
                "Raw response logged for debugging."
            ),
        )


# ─── Response Parser ──────────────────────────────────────────────────────────

def _parse_llm_response(raw: str) -> AIReviewResult:
    """
    Parse the LLM's JSON response into an AIReviewResult.
    Handles common formatting issues (LLMs sometimes add markdown fences).
    """
    # Strip markdown code fences if present
    cleaned = _extract_json_from_response(raw)
    data = _load_ai_json(cleaned, raw)

    # Parse classic issues (backward-compatible)
    issues: list[Issue] = []
    for item in data.get("issues", []):
        sev_str = str(item.get("severity", "medium")).lower()
        severity = _parse_severity(sev_str)

        line_val = item.get("line")
        line = int(line_val) if line_val and str(line_val).isdigit() else None

        issues.append(Issue(
            category=IssueCategory.AI,
            severity=severity,
            line=line,
            title=str(item.get("title", "Issue found by AI"))[:120],
            description=str(item.get("description", "")),
            suggestion=str(item.get("suggestion", "")) or None,
        ))

    # Parse static-issue classification review.
    # We project these into regular Issue cards so UI can render them directly.
    for item in data.get("static_issue_review", []):
        status = str(item.get("status", "partially_correct")).strip().lower()
        status_map = {
            "correct_issue": "Correct Issue",
            "false_positive": "False Positive",
            "partially_correct": "Partially Correct",
            "uncertain": "Uncertain",
        }
        label = status_map.get(status, "Partially Correct")

        title_text = str(item.get("title", "Static finding review")).strip()
        # Guardrail: models sometimes echo the prompt helper text as a fake issue.
        if title_text.lower() in {
            "no issues found by static analysis tools",
            "no issues found",
            "static analysis found no issues",
        }:
            continue

        sev_str = str(item.get("severity", "info")).lower()
        severity = _parse_severity(sev_str)
        if status == "false_positive":
            severity = Severity.INFO
        if status == "uncertain" and severity in {Severity.CRITICAL, Severity.HIGH}:
            severity = Severity.MEDIUM

        line_val = item.get("line")
        line = int(line_val) if line_val and str(line_val).isdigit() else None

        issues.append(Issue(
            category=IssueCategory.AI,
            severity=severity,
            line=line,
            title=f"[{label}] {title_text[:95]}",
            description=str(item.get("reason", "Classification generated by AI reviewer.")).strip(),
            suggestion=str(item.get("fix", "")).strip() or None,
        ))

    # Parse missed issues (new field).
    for item in data.get("missed_issues", []):
        sev_str = str(item.get("severity", "medium")).lower()
        severity = _parse_severity(sev_str)

        line_val = item.get("line")
        line = int(line_val) if line_val and str(line_val).isdigit() else None

        issues.append(Issue(
            category=IssueCategory.AI,
            severity=severity,
            line=line,
            title=f"[Missed by Static] {str(item.get('title', 'Missed issue'))[:95]}",
            description=str(item.get("description", "")).strip(),
            suggestion=str(item.get("suggestion", "")).strip() or None,
        ))

    # Deduplicate repeated findings across sections.
    deduped: list[Issue] = []
    seen: set[tuple[str, int | None, str]] = set()
    for issue in issues:
        key = (
            issue.title.strip().lower(),
            issue.line,
            issue.description.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    issues = deduped

    # Parse score
    score_raw = data.get("score", 50)
    try:
        score = max(0, min(100, int(score_raw)))
    except (TypeError, ValueError):
        score = 50

    # Parse recommendations
    recs = data.get("recommendations", [])
    recommendations = [str(r) for r in recs if r]

    # Extract improved code (may be in the JSON or as a code block)
    improved_code = str(data.get("improved_code", "")).strip()
    if isinstance(data.get("improved_code"), list):
        improved_code = "\n".join(str(x) for x in data.get("improved_code", []))

    return AIReviewResult(
        summary=str(data.get("summary", "")).strip(),
        issues=issues,
        improved_code=improved_code,
        recommendations=recommendations,
        score=score,
        ai_available=True,
    )


def _extract_json_from_response(text: str) -> str:
    """
    Extract a clean JSON string from the LLM response.
    LLMs sometimes wrap JSON in markdown fences or add commentary.
    """
    # Remove ```json ... ``` fences
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    match = re.search(fence_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try to find the outermost { ... } block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    # Fall back to the raw text
    return text.strip()


def _load_ai_json(cleaned: str, raw: str) -> dict:
    """
    Parse model output with resilient fallbacks for near-JSON responses.
    """
    candidates = [cleaned]

    # Common repairs for LLM output: trailing commas and smart quotes.
    repaired = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    candidates.append(repaired)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # Python-literal style fallback when model returns single quotes.
    try:
        literal = re.sub(r"\btrue\b", "True", repaired, flags=re.IGNORECASE)
        literal = re.sub(r"\bfalse\b", "False", literal, flags=re.IGNORECASE)
        literal = re.sub(r"\bnull\b", "None", literal, flags=re.IGNORECASE)
        parsed = ast.literal_eval(literal)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Last resort: recover key fields heuristically so the app still returns value.
    return _heuristic_parse_ai_payload(raw)


def _heuristic_parse_ai_payload(raw: str) -> dict:
    """
    Recover partial data when model output is not valid JSON.
    """
    summary = ""
    score = 50
    recommendations: list[str] = []
    issues = []
    improved_code = ""

    summary_match = re.search(
        r'"summary"\s*:\s*"([\s\S]*?)"\s*(?:,\s*"score"|,\s*"issues"|,\s*"improved_code"|,\s*"recommendations"|})',
        raw,
    )
    if summary_match:
        summary = summary_match.group(1).strip()

    score_match = re.search(r'"score"\s*:\s*(\d{1,3})', raw)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except Exception:
            score = 50

    # Try to parse issues array if the segment is valid enough.
    issues_match = re.search(r'"issues"\s*:\s*(\[[\s\S]*?\])\s*,\s*"improved_code"', raw)
    if issues_match:
        issues_raw = re.sub(r",\s*([}\]])", r"\1", issues_match.group(1))
        try:
            parsed_issues = json.loads(issues_raw)
            if isinstance(parsed_issues, list):
                issues = parsed_issues
        except Exception:
            pass

    recs_match = re.search(r'"recommendations"\s*:\s*\[([\s\S]*?)\]', raw)
    if recs_match:
        recommendations = [m.strip() for m in re.findall(r'"(.*?)"', recs_match.group(1), flags=re.DOTALL) if m.strip()]

    # Prefer code fences for improved code if present.
    code_block = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\n([\s\S]*?)```", raw)
    if code_block:
        improved_code = code_block.group(1).strip()
    else:
        # Fallback to JSON field capture.
        code_match = re.search(r'"improved_code"\s*:\s*"([\s\S]*?)"\s*(?:,\s*"recommendations"|})', raw)
        if code_match:
            improved_code = code_match.group(1).strip().replace("\\n", "\n")

    if not summary:
        summary = "AI response was partially parsed due to invalid JSON formatting."

    return {
        "summary": summary,
        "score": score,
        "issues": issues,
        "improved_code": improved_code,
        "recommendations": recommendations,
    }


def _parse_severity(sev_str: str) -> Severity:
    """Map a severity string to our Severity enum, with a safe default."""
    mapping = {
        "critical": Severity.CRITICAL,
        "high":     Severity.HIGH,
        "medium":   Severity.MEDIUM,
        "low":      Severity.LOW,
        "info":     Severity.INFO,
    }
    return mapping.get(sev_str.lower(), Severity.MEDIUM)


# ─── Fallback Mode ────────────────────────────────────────────────────────────

def _static_only_fallback(static_issues: list) -> AIReviewResult:
    """
    Return an AIReviewResult that makes it clear the LLM was not used,
    but still provides value from the static analysis context.
    """
    n = len(static_issues)
    provider = settings.LLM_PROVIDER

    if n == 0:
        summary = (
            "Static analysis found no issues. "
            "Add an API key to get a deeper AI-powered review."
        )
    else:
        summary = (
            f"Static analysis found {n} issue(s). "
            f"Set up a '{provider}' API key in your .env file "
            "to get AI explanations, improved code, and a quality score."
        )

    return AIReviewResult(
        summary=summary,
        ai_available=False,
        score=0,
        recommendations=[
            f"Add your {provider.upper()}_API_KEY to the .env file to enable AI review.",
            "Groq offers a free API key at https://console.groq.com — it's fast and easy.",
            "Fix the static analysis issues shown in the Issues tab.",
        ],
        error_message=None,
    )
