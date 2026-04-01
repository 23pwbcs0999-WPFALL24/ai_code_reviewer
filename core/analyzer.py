"""
core/analyzer.py
─────────────────
Top-level analysis orchestrator.

This is the single entry point the UI calls.
It coordinates the entire pipeline:
  1. Static analysis (always runs)
  2. AI review      (runs if API key is configured)
  3. Merges results into a ReviewResult with computed stats
"""

from __future__ import annotations

from models.schemas import Language, ReviewResult
from core.static_analysis import run_static_analysis
from core.ai_review.reviewer import run_ai_review
from utils.code_utils import count_lines


def analyze_code(
    code: str,
    filename: str = "untitled.py",
    language: str = "Python",
) -> ReviewResult:
    """
    Run the full analysis pipeline on the provided source code.

    Args:
        code:     Source code as a string
        filename: Original filename (used in the report)
        language: Programming language name

    Returns:
        A fully populated ReviewResult object
    """
    # ── 1. Static analysis ────────────────────────────────────────────────────
    static_result = run_static_analysis(code, language)

    # ── 2. AI review ──────────────────────────────────────────────────────────
    # Pass static issues to the AI so it can build on them
    ai_result = run_ai_review(
        code=code,
        language=language,
        static_issues=static_result.issues,
    )

    # ── 3. Combine results ────────────────────────────────────────────────────
    # Map language string to our enum (default to Python if unknown)
    try:
        lang_enum = Language(language)
    except ValueError:
        lang_enum = Language.PYTHON

    result = ReviewResult(
        filename=filename,
        language=lang_enum,
        original_code=code,
        line_count=count_lines(code),
        static=static_result,
        ai=ai_result,
    )

    # Compute aggregate stats (issue counts, final score, etc.)
    result.compute_stats()

    return result
