"""
core/static_analysis/linter.py
────────────────────────────────
Runs pylint and flake8 on the code by writing it to a temporary file,
invoking the tools as subprocesses, and parsing their output into our
Issue schema.

Design choice — subprocess vs. API:
  pylint and flake8 both have Python APIs, but the subprocess approach
  is more robust (no version conflicts, cleaner output parsing).
"""

import os
import re
import subprocess
import tempfile
from typing import List

from models.schemas import Issue, IssueCategory, Severity


# ─── Severity mapping ─────────────────────────────────────────────────────────

# pylint message categories: C=convention, R=refactor, W=warning, E=error, F=fatal
PYLINT_SEVERITY_MAP = {
    "F": Severity.CRITICAL,
    "E": Severity.HIGH,
    "W": Severity.MEDIUM,
    "R": Severity.LOW,
    "C": Severity.LOW,
}

# flake8 rule prefixes → severity
FLAKE8_SEVERITY_MAP = {
    "E9":  Severity.HIGH,    # Runtime errors (syntax-related)
    "F8":  Severity.HIGH,    # pyflakes: undefined names, unused imports
    "F4":  Severity.MEDIUM,  # pyflakes: import issues
    "W6":  Severity.MEDIUM,  # deprecated features
    "E5":  Severity.MEDIUM,  # line too long, etc.
    "E1":  Severity.LOW,     # indentation
    "E2":  Severity.LOW,     # whitespace
    "E3":  Severity.LOW,     # blank lines
    "E4":  Severity.LOW,     # imports
    "E7":  Severity.LOW,     # statement
    "W":   Severity.LOW,     # general warnings
}


def _write_temp_file(code: str) -> str:
    """Write code to a temp .py file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".py", prefix="acr_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    return path


# ─── Pylint ───────────────────────────────────────────────────────────────────

def run_pylint(code: str) -> tuple[List[Issue], str]:
    """
    Run pylint on the code.

    Returns:
        (list_of_issues, raw_output_text)
    """
    path = _write_temp_file(code)
    issues: List[Issue] = []
    raw_output = ""

    try:
        result = subprocess.run(
            [
                "python", "-m", "pylint",
                "--output-format=text",
                "--score=no",
                "--disable=C0114,C0115,C0116",   # Skip missing-docstring for brevity
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw_output = result.stdout + result.stderr
        issues = _parse_pylint_output(raw_output, code)
    except subprocess.TimeoutExpired:
        raw_output = "pylint timed out after 30 seconds."
    except FileNotFoundError:
        raw_output = "pylint is not installed. Run: pip install pylint"
    except Exception as exc:
        raw_output = f"pylint error: {exc}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    return issues, raw_output


def _parse_pylint_output(output: str, code: str) -> List[Issue]:
    """
    Parse pylint text output into Issue objects.

    Pylint line format:
        filename.py:10:4: W0611: Unused import os (unused-import)
    """
    issues: List[Issue] = []
    # Pattern: path:line:col: TYPE_CODE: message (rule-name)
    pattern = re.compile(
        r":(\d+):(\d+):\s+([FEWRC]\d+):\s+(.+?)\s+\((.+?)\)"
    )

    for line in output.splitlines():
        m = pattern.search(line)
        if not m:
            continue

        lineno     = int(m.group(1))
        col        = int(m.group(2))
        rule_code  = m.group(3)          # e.g. W0611
        message    = m.group(4).strip()
        rule_name  = m.group(5).strip()  # e.g. unused-import

        category_char = rule_code[0].upper()
        severity = PYLINT_SEVERITY_MAP.get(category_char, Severity.LOW)

        from utils.code_utils import get_line
        snippet = get_line(code, lineno)

        issues.append(Issue(
            category=IssueCategory.LINT,
            severity=severity,
            line=lineno,
            column=col if col > 0 else None,
            rule_id=f"pylint:{rule_code}",
            title=f"[{rule_code}] {rule_name.replace('-', ' ').title()}",
            description=_make_friendly_pylint(message, rule_name),
            suggestion=_pylint_suggestion(rule_name),
            code_snippet=snippet.strip() if snippet.strip() else None,
        ))

    return issues


def _make_friendly_pylint(message: str, rule_name: str) -> str:
    """
    Convert pylint's terse message to a beginner-friendly description.
    """
    friendly = {
        "unused-import":          "You imported something but never used it. This clutters the code.",
        "undefined-variable":     "You used a variable that was never assigned a value. Python will crash here.",
        "redefined-outer-name":   "A variable inside a function has the same name as one outside — this can cause confusion.",
        "unused-variable":        "You created a variable but never used it. Consider removing it.",
        "missing-function-docstring": "The function has no docstring. A short description helps others understand what it does.",
        "invalid-name":           "The variable or function name does not follow Python naming conventions.",
        "too-many-arguments":     "This function takes too many parameters. Consider splitting it up or using a class.",
        "too-many-branches":      "This function has too many if/elif branches. It may be hard to read and test.",
        "line-too-long":          "This line is too long. PEP 8 recommends keeping lines under 79 characters.",
        "broad-except":           "Catching a generic Exception hides real errors. Catch specific exception types instead.",
        "bare-except":            "A bare `except:` catches everything including KeyboardInterrupt. Always specify an exception type.",
        "global-statement":       "Using `global` variables is generally bad practice. Prefer passing values as function arguments.",
        "no-else-return":         "No need for `else` after a `return` statement.",
        "simplifiable-if-statement": "This if statement can be written more simply.",
    }
    return friendly.get(rule_name, message)


def _pylint_suggestion(rule_name: str) -> str:
    """Return a short fix suggestion for common pylint rules."""
    suggestions = {
        "unused-import":     "Remove the import, or use it somewhere in your code.",
        "undefined-variable":"Check that the variable is assigned before use, and is in the correct scope.",
        "unused-variable":   "Delete the variable, or use `_` as its name to signal it is intentionally unused.",
        "broad-except":      "Replace `except Exception` with a specific type like `except ValueError`.",
        "bare-except":       "Replace `except:` with `except Exception as e:` at minimum.",
        "global-statement":  "Pass the value as a function argument or use a class attribute instead of `global`.",
        "line-too-long":     "Break the line using parentheses or a backslash, or extract part of it into a variable.",
        "too-many-arguments":"Group related parameters into a dataclass or pass a configuration dictionary.",
    }
    return suggestions.get(rule_name, "Follow pylint's suggestion above.")


# ─── Flake8 ───────────────────────────────────────────────────────────────────

def run_flake8(code: str) -> tuple[List[Issue], str]:
    """
    Run flake8 on the code.

    Returns:
        (list_of_issues, raw_output_text)
    """
    path = _write_temp_file(code)
    issues: List[Issue] = []
    raw_output = ""

    try:
        result = subprocess.run(
            [
                "python", "-m", "flake8",
                "--max-line-length=120",   # Slightly relaxed to reduce noise
                "--format=default",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw_output = result.stdout + result.stderr
        issues = _parse_flake8_output(raw_output, code)
    except subprocess.TimeoutExpired:
        raw_output = "flake8 timed out after 30 seconds."
    except FileNotFoundError:
        raw_output = "flake8 is not installed. Run: pip install flake8"
    except Exception as exc:
        raw_output = f"flake8 error: {exc}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    return issues, raw_output


def _parse_flake8_output(output: str, code: str) -> List[Issue]:
    """
    Parse flake8 output into Issue objects.

    Flake8 line format:
        filename.py:10:5: E302 expected 2 blank lines, found 1
    """
    issues: List[Issue] = []
    # Pattern: path:line:col: CODE message
    pattern = re.compile(r":(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)")

    seen_rules: set = set()    # Deduplicate identical rule+line combinations

    for line in output.splitlines():
        m = pattern.search(line)
        if not m:
            continue

        lineno   = int(m.group(1))
        col      = int(m.group(2))
        code_id  = m.group(3)     # e.g. E302
        message  = m.group(4).strip()

        key = (lineno, code_id)
        if key in seen_rules:
            continue
        seen_rules.add(key)

        severity = _flake8_severity(code_id)

        from utils.code_utils import get_line
        snippet = get_line(code, lineno)

        issues.append(Issue(
            category=IssueCategory.STYLE,
            severity=severity,
            line=lineno,
            column=col if col > 0 else None,
            rule_id=f"flake8:{code_id}",
            title=f"[{code_id}] {message}",
            description=_make_friendly_flake8(code_id, message),
            suggestion=_flake8_suggestion(code_id),
            code_snippet=snippet.strip() if snippet.strip() else None,
        ))

    return issues


def _flake8_severity(code_id: str) -> Severity:
    """Map a flake8 code like E302 to a Severity level."""
    for prefix, sev in FLAKE8_SEVERITY_MAP.items():
        if code_id.startswith(prefix):
            return sev
    return Severity.INFO


def _make_friendly_flake8(code_id: str, message: str) -> str:
    friendly = {
        "E101": "Mixed tabs and spaces. Use spaces only (PEP 8).",
        "E111": "Indentation is not a multiple of four spaces.",
        "E225": "Missing whitespace around operator. Add spaces around `=`, `+`, etc.",
        "E231": "Missing whitespace after `,`, `;`, or `:`.",
        "E302": "Expected two blank lines before a function or class definition.",
        "E303": "Too many blank lines in a row.",
        "E401": "Multiple imports on one line. Put each import on its own line.",
        "E501": "Line is too long. Keep lines under 120 characters.",
        "F401": "An import is unused — it was imported but never referenced.",
        "F811": "A name was redefined without being used first.",
        "F821": "An undefined name was used — the variable or function does not exist yet.",
        "W291": "Trailing whitespace at the end of a line.",
        "W293": "Whitespace on a blank line — remove the spaces.",
        "W391": "Blank line at the end of the file.",
        "W503": "Line break before a binary operator (style preference).",
    }
    return friendly.get(code_id, f"flake8 says: {message}")


def _flake8_suggestion(code_id: str) -> str:
    suggestions = {
        "E302": "Add two blank lines before this function or class definition.",
        "E303": "Remove the extra blank lines.",
        "E401": "Put each import on a separate line: `import os` then `import sys`.",
        "E501": "Break this line into multiple shorter lines using parentheses.",
        "F401": "Remove the unused import, or use it somewhere.",
        "F821": "Define or import the name before using it.",
        "W291": "Delete the trailing spaces at the end of this line.",
        "W391": "Delete the trailing blank lines at the end of the file.",
    }
    return suggestions.get(code_id, "Fix the style issue noted above.")
