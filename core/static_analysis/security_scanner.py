"""
core/static_analysis/security_scanner.py
─────────────────────────────────────────
Runs bandit — a security linter for Python — and converts its output
into our Issue schema.

Bandit checks for things like:
  - Hardcoded passwords / secret keys
  - Use of dangerous functions (exec, eval, pickle)
  - SQL injection risks
  - Insecure use of cryptography
  - Shell injection via subprocess
  - Insecure random number generation
"""

import json
import os
import subprocess
import tempfile
from typing import List, Tuple

from models.schemas import Issue, IssueCategory, Severity


# Bandit severity levels → our Severity enum
BANDIT_SEVERITY_MAP = {
    "HIGH":   Severity.CRITICAL,
    "MEDIUM": Severity.HIGH,
    "LOW":    Severity.MEDIUM,
}

# Bandit confidence levels — we only report HIGH and MEDIUM confidence findings
# to reduce false positives
MIN_CONFIDENCE = {"HIGH", "MEDIUM"}


def run_bandit(code: str) -> Tuple[List[Issue], str]:
    """
    Run bandit on the code string.

    Returns:
        (list_of_issues, raw_json_output_as_string)
    """
    path = _write_temp_file(code)
    issues: List[Issue] = []
    raw_output = ""

    try:
        result = subprocess.run(
            [
                "python", "-m", "bandit",
                "-f", "json",         # Machine-readable JSON output
                "-ll",                # Only LOW severity and above (report everything)
                "--quiet",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw_output = result.stdout

        if raw_output.strip():
            issues = _parse_bandit_json(raw_output, code)

    except subprocess.TimeoutExpired:
        raw_output = json.dumps({"error": "bandit timed out after 30 seconds"})
    except FileNotFoundError:
        raw_output = json.dumps({"error": "bandit is not installed. Run: pip install bandit"})
    except Exception as exc:
        raw_output = json.dumps({"error": str(exc)})
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    return issues, raw_output


def _write_temp_file(code: str) -> str:
    """Write code to a temp .py file."""
    fd, path = tempfile.mkstemp(suffix=".py", prefix="acr_bandit_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    return path


def _parse_bandit_json(json_str: str, code: str) -> List[Issue]:
    """Parse bandit JSON report into Issue objects."""
    issues: List[Issue] = []

    try:
        report = json.loads(json_str)
    except json.JSONDecodeError:
        return issues

    results = report.get("results", [])

    for finding in results:
        confidence = finding.get("issue_confidence", "LOW").upper()
        if confidence not in MIN_CONFIDENCE:
            continue   # Skip LOW confidence to reduce noise

        sev_str  = finding.get("issue_severity", "LOW").upper()
        severity = BANDIT_SEVERITY_MAP.get(sev_str, Severity.MEDIUM)

        lineno   = finding.get("line_number")
        test_id  = finding.get("test_id", "")        # e.g. B101
        test_name = finding.get("test_name", "")     # e.g. assert_used
        message  = finding.get("issue_text", "")

        from utils.code_utils import get_line
        snippet = get_line(code, lineno) if lineno else None

        issues.append(Issue(
            category=IssueCategory.SECURITY,
            severity=severity,
            line=lineno,
            column=None,
            rule_id=f"bandit:{test_id}",
            title=f"[{test_id}] {_format_test_name(test_name)}",
            description=_make_friendly_bandit(test_id, test_name, message),
            suggestion=_bandit_suggestion(test_id),
            code_snippet=snippet.strip() if snippet and snippet.strip() else None,
        ))

    return issues


def _format_test_name(name: str) -> str:
    """Turn bandit's snake_case test name into a readable title."""
    return name.replace("_", " ").title()


def _make_friendly_bandit(test_id: str, test_name: str, raw_message: str) -> str:
    """
    Map bandit finding IDs to plain-English security explanations
    that are easy for students to understand.
    """
    descriptions = {
        "B101": (
            "You are using `assert` to check conditions in production code. "
            "Assert statements are removed when Python runs in optimised mode (`-O`), "
            "so security or validation checks written with `assert` may silently stop working."
        ),
        "B102": (
            "`exec()` runs a string as Python code. If that string comes from user input, "
            "an attacker could run any code they like on your system. This is very dangerous."
        ),
        "B103": (
            "Setting file permissions to something overly permissive (like 0o777) "
            "lets any user on the system read, write, or execute the file."
        ),
        "B104": (
            "Binding to 0.0.0.0 exposes the service on all network interfaces, "
            "including public ones. This may expose your service to the internet unintentionally."
        ),
        "B105": "A hardcoded password was found in the code. Never store passwords in source files.",
        "B106": "A hardcoded password was used as a function argument. Use environment variables instead.",
        "B107": "A hardcoded password was used as a default argument. This is a security risk.",
        "B108": (
            "A predictable or insecure temporary file location was used. "
            "Use `tempfile.mkstemp()` instead."
        ),
        "B110": (
            "`try/except/pass` swallows errors silently. "
            "This can hide bugs and security issues."
        ),
        "B112": (
            "`try/except/continue` inside a loop silently ignores errors "
            "and may skip important processing."
        ),
        "B201": (
            "Flask is running in debug mode. In debug mode, the Werkzeug debugger "
            "gives attackers an interactive Python console on your server. "
            "NEVER run with `debug=True` in production."
        ),
        "B301": (
            "`pickle` can execute arbitrary code when deserialising untrusted data. "
            "If the data comes from a user or network, this is a critical vulnerability."
        ),
        "B302": "Using `marshal` to deserialise data is insecure — similar risk to pickle.",
        "B303": "MD5 and SHA1 are cryptographically broken. Use SHA-256 or better.",
        "B304": "DES and RC2 are weak encryption algorithms. Use AES instead.",
        "B305": "CFB and ECB cipher modes are insecure. Use GCM or CBC with proper padding.",
        "B306": "`mktemp()` has a race condition vulnerability. Use `mkstemp()` instead.",
        "B307": (
            "`eval()` executes a string as Python code. If the input comes from a user, "
            "this is a code-injection vulnerability."
        ),
        "B311": (
            "`random` is not suitable for security-sensitive uses like tokens or passwords. "
            "Use `secrets` module instead."
        ),
        "B312": "Telnet sends data unencrypted. Use SSH instead.",
        "B313": "XML parsers can be vulnerable to billion-laughs and XXE attacks with untrusted input.",
        "B320": "Using `lxml` without disabling external entity resolution is insecure.",
        "B324": "MD5 and SHA1 are weak hash algorithms. Use SHA-256 or better for security.",
        "B501": "TLS certificate verification is disabled. Man-in-the-middle attacks become possible.",
        "B502": "The `ssl_version` parameter uses an old, insecure protocol.",
        "B503": "Weak cipher suites are being used. Specify strong ciphers explicitly.",
        "B504": "SSL/TLS context is missing hostname checking.",
        "B505": "A weak RSA or DSA key size (less than 2048 bits) was found.",
        "B506": "YAML's `load()` is unsafe with untrusted input. Use `safe_load()` instead.",
        "B601": "Shell commands built from user input enable shell-injection attacks.",
        "B602": "`subprocess` with `shell=True` is dangerous if any input comes from outside the program.",
        "B603": "`subprocess` without `shell=True` is safer, but still validate all inputs.",
        "B604": "Function calls with shell=True are potentially dangerous.",
        "B605": "Starting a shell process is risky — validate all inputs carefully.",
        "B606": "Starting a process without a shell is safer, but still validate all inputs.",
        "B607": "Starting a process with a partial path is risky — use absolute paths.",
        "B608": "Possible SQL injection: string formatting is used to build a SQL query.",
        "B609": "Wildcard injection: passing a wildcard to a shell command can be exploited.",
        "B610": "Django's `extra()` with user input may enable SQL injection.",
        "B611": "Django's `RawSQL()` with user input may enable SQL injection.",
        "B701": "Jinja2 autoescape is not set. This can lead to cross-site scripting (XSS).",
        "B702": "Mako templates have no autoescape — XSS risk with user-controlled data.",
    }

    return descriptions.get(test_id, f"Security issue detected: {raw_message}")


def _bandit_suggestion(test_id: str) -> str:
    """Return a concise fix suggestion for common bandit findings."""
    suggestions = {
        "B101": "Use proper `if` conditions with `raise` instead of `assert` for validation.",
        "B102": "Never call `exec()` on untrusted strings. Redesign the logic to avoid it.",
        "B105": "Move the password to an environment variable: `os.environ['MY_PASSWORD']`.",
        "B106": "Remove the hardcoded password and read it from `os.environ` or a config file.",
        "B107": "Remove the hardcoded default password. Require the caller to supply it.",
        "B201": "Remove `debug=True` before deploying. Set it via an environment variable only.",
        "B301": "Use JSON or a safer serialisation format instead of pickle for untrusted data.",
        "B303": "Replace `hashlib.md5()` / `hashlib.sha1()` with `hashlib.sha256()`.",
        "B307": "Avoid `eval()`. Parse data properly (e.g. `json.loads()` for JSON, `ast.literal_eval()` for Python literals).",
        "B311": "Use `secrets.token_hex()` or `secrets.token_urlsafe()` for secure random values.",
        "B501": "Remove `verify=False` and ensure the server has a valid TLS certificate.",
        "B506": "Replace `yaml.load(data)` with `yaml.safe_load(data)`.",
        "B602": "Remove `shell=True` and pass the command as a list: `subprocess.run(['ls', '-la'])`.",
        "B608": "Use parameterised queries or an ORM instead of string formatting for SQL.",
        "B701": "Enable Jinja2 autoescape: `Environment(autoescape=True)`.",
    }
    return suggestions.get(test_id, "Review the bandit documentation for this rule and apply the recommended fix.")
