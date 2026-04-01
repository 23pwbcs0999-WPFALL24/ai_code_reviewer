"""
utils/code_utils.py
───────────────────
Small helper functions used across the codebase for working with
source code strings.
"""

from __future__ import annotations
import re
from typing import List, Optional, Tuple


def get_line(code: str, line_number: int) -> str:
    """
    Return the source line at the given 1-indexed line number.
    Returns empty string if the line number is out of range.
    """
    lines = code.splitlines()
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1]
    return ""


def get_context_snippet(
    code: str,
    line_number: int,
    context: int = 2,
) -> str:
    """
    Return a few lines around `line_number` for display in the report.

    Args:
        code:        Full source code string
        line_number: The problematic line (1-indexed)
        context:     How many lines to show above and below

    Returns:
        A formatted multi-line string with line numbers prefixed.
    """
    lines = code.splitlines()
    total = len(lines)
    start = max(0, line_number - 1 - context)
    end   = min(total, line_number - 1 + context + 1)

    snippet_lines: List[str] = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        marker = ">>>" if i == line_number else "   "
        snippet_lines.append(f"{marker} {i:4d} | {line}")

    return "\n".join(snippet_lines)


def truncate_code(code: str, max_lines: int = 200) -> Tuple[str, bool]:
    """
    Truncate code to `max_lines` lines for sending to the LLM API
    (keeps token usage low).

    Returns:
        (truncated_code, was_truncated)
    """
    lines = code.splitlines()
    if len(lines) <= max_lines:
        return code, False

    half = max_lines // 2
    head = lines[:half]
    tail = lines[-half:]
    separator = [
        "",
        f"# ... [{len(lines) - max_lines} lines omitted to save tokens] ...",
        "",
    ]
    return "\n".join(head + separator + tail), True


def extract_code_blocks(text: str) -> List[str]:
    """
    Pull out fenced code blocks from a markdown string.
    Used to extract improved code from the LLM response.

    Example:
        ```python
        def foo(): pass
        ```
        → ["def foo(): pass"]
    """
    pattern = r"```(?:python|py|)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [m.strip() for m in matches if m.strip()]


def clean_llm_code_response(text: str) -> str:
    """
    Extract improved code from the LLM response.
    Falls back to the raw text if no code block is found.
    """
    blocks = extract_code_blocks(text)
    if blocks:
        # Return the largest code block (most likely the full improved file)
        return max(blocks, key=len)
    return text.strip()


def severity_sort_key(issue) -> int:
    """
    Sort key so that critical issues appear first.
    Works with Issue objects from models/schemas.py.
    """
    from models.schemas import Severity
    order = {
        Severity.CRITICAL: 0,
        Severity.HIGH:     1,
        Severity.MEDIUM:   2,
        Severity.LOW:      3,
        Severity.INFO:     4,
    }
    return order.get(issue.severity, 99)


def score_to_grade(score: int) -> str:
    """Map a 0-100 score to a letter grade."""
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def count_lines(code: str) -> int:
    """Count non-empty lines in the code string."""
    return len(code.rstrip("\n").splitlines())
