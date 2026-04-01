"""
core/static_analysis/syntax_checker.py
───────────────────────────────────────
Uses Python's built-in `py_compile` module to check whether the code
can be parsed at all.  This runs before pylint/flake8 because those
tools crash or give unhelpful output on code with syntax errors.

Why py_compile?
  - Zero external dependencies
  - Gives the exact line number and error message from the Python parser
  - Very fast (milliseconds)
"""

import ast
import textwrap
from typing import Optional, Tuple


def check_syntax(code: str) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Parse the code string as Python source.

    Returns:
        (ok, error_message, error_line)

        ok           – True if the code has no syntax errors
        error_message – Human-readable error text (None if ok)
        error_line    – Line number where the error occurred (None if ok)

    Example:
        ok, msg, line = check_syntax("def foo(:\n    pass")
        # ok=False, msg="invalid syntax ...", line=1
    """
    try:
        ast.parse(code)
        return True, None, None
    except SyntaxError as exc:
        # Build a friendly, beginner-readable message
        msg = _format_syntax_error(exc)
        return False, msg, exc.lineno
    except Exception as exc:
        # Catch-all for unexpected parser errors
        return False, f"Unexpected parse error: {exc}", None


def _format_syntax_error(exc: SyntaxError) -> str:
    """
    Turn a SyntaxError into a plain-English explanation
    that a beginner can understand.
    """
    raw_msg = str(exc.msg) if exc.msg else "Syntax error"

    # Map common cryptic messages to friendly equivalents
    friendly_map = {
        "invalid syntax":               "The code has a syntax error — Python cannot understand this line.",
        "unexpected EOF while parsing":  "The code seems to be incomplete — something is left open (missing closing bracket, quote, or colon).",
        "EOL while scanning string literal": "A string is not closed — you opened a quote but never closed it.",
        "expected an indented block":    "Python expected an indented block here (e.g. the body of an if, def, or for).",
        "unindent does not match":       "The indentation is inconsistent — mixed tabs and spaces, or wrong number of spaces.",
        "cannot assign to":              "You are trying to assign a value to something that is not a variable.",
    }

    for pattern, friendly in friendly_map.items():
        if pattern.lower() in raw_msg.lower():
            friendly_desc = friendly
            break
    else:
        friendly_desc = f"Python parser says: {raw_msg}"

    lines = [friendly_desc]
    if exc.lineno:
        lines.append(f"  • Location: line {exc.lineno}")
    if exc.text and exc.text.strip():
        lines.append(f"  • Code:     {exc.text.strip()}")

    return "\n".join(lines)


def get_ast_summary(code: str) -> dict:
    """
    Parse code into an AST and return a quick structural summary.
    Used by the AI reviewer to give context without sending the full code.

    Returns a dict with counts of top-level constructs.
    """
    summary = {
        "functions": [],
        "classes": [],
        "imports": [],
        "has_main_guard": False,
    }

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return summary   # Can't parse — return empty summary

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and isinstance(node.col_offset, int) and node.col_offset == 0:
            summary["functions"].append(node.name)
        elif isinstance(node, ast.ClassDef) and node.col_offset == 0:
            summary["classes"].append(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    summary["imports"].append(alias.name)
            else:
                summary["imports"].append(node.module or "")

    # Detect `if __name__ == "__main__":` guard
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ):
            summary["has_main_guard"] = True
            break

    # Deduplicate
    summary["imports"] = list(dict.fromkeys(summary["imports"]))
    return summary
