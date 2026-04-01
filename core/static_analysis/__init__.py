"""
core/static_analysis/__init__.py
──────────────────────────────────
Orchestrates the full local static analysis pipeline:
  1. Syntax check (py_compile / ast)
  2. Security scan (bandit)
  3. Linting (pylint)
  4. Style check (flake8)

Returns a StaticAnalysisResult with all issues merged.
"""

from models.schemas import StaticAnalysisResult, Issue, IssueCategory, Severity
from core.static_analysis.syntax_checker import check_syntax
from core.static_analysis.linter import run_pylint, run_flake8
from core.static_analysis.security_scanner import run_bandit
from utils.code_utils import severity_sort_key


def run_static_analysis(code: str, language: str = "Python") -> StaticAnalysisResult:
    """
    Run all static analysis tools on the given code.

    The pipeline:
      1. If syntax is broken, skip the other tools (they may crash anyway).
      2. Run security scanner first -- security issues are highest priority.
      3. Run pylint for logic and best-practice issues.
      4. Run flake8 for style issues.
      5. Merge all issues, sort by severity, and return.

    Args:
        code:     Source code string
        language: Programming language name (currently only "Python" supported)

    Returns:
        StaticAnalysisResult with all issues and raw tool outputs
    """
    result = StaticAnalysisResult()

    # Step 1: Syntax check
    syntax_ok, syntax_error, syntax_line = check_syntax(code)
    result.syntax_ok = syntax_ok

    if not syntax_ok:
        result.syntax_error_msg = syntax_error
        result.issues.append(Issue(
            category=IssueCategory.SYNTAX,
            severity=Severity.CRITICAL,
            line=syntax_line,
            title="Syntax Error -- Code Cannot Run",
            description=syntax_error or "The code has a syntax error.",
            suggestion=(
                "Fix the syntax error first. "
                "Check for missing colons, unmatched brackets, "
                "or incorrect indentation."
            ),
        ))
        return result

    # Step 2: Security scan
    bandit_issues, raw_bandit = run_bandit(code)
    result.raw_bandit = raw_bandit
    result.issues.extend(bandit_issues)

    # Step 3: Pylint (logic + best practices)
    pylint_issues, raw_pylint = run_pylint(code)
    result.raw_pylint = raw_pylint
    result.issues.extend(pylint_issues)

    # Step 4: Flake8 (style)
    flake8_issues, raw_flake8 = run_flake8(code)
    result.raw_flake8 = raw_flake8
    result.issues.extend(flake8_issues)

    # Step 5: Deduplicate and sort
    result.issues = _deduplicate(result.issues)
    result.issues.sort(key=severity_sort_key)

    return result


def _deduplicate(issues):
    """Remove duplicate issues on the same line with the same rule."""
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.line, issue.rule_id or issue.title[:40])
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique
