"""
models/schemas.py
─────────────────
Pydantic v2 data models that flow through the entire system.
These act as the "contract" between modules — if data shape changes,
you update it here and the type checker catches mismatches everywhere.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── Enumerations ─────────────────────────────────────────────────────────────

class Severity(str, Enum):
    """How serious is the issue? Used for colour-coding in the UI."""
    CRITICAL = "critical"    # Security vulnerability, crash-causing bug
    HIGH     = "high"        # Likely to cause wrong results / data loss
    MEDIUM   = "medium"      # Bad practice, performance problem
    LOW      = "low"         # Style issue, minor readability problem
    INFO     = "info"        # Suggestion / informational note


class IssueCategory(str, Enum):
    """Which type of checker found this issue?"""
    SYNTAX   = "syntax"      # Broken Python syntax
    SECURITY = "security"    # Bandit finding
    LINT     = "lint"        # Pylint / Flake8
    STYLE    = "style"       # PEP 8 / code style
    AI       = "ai"          # LLM-identified issue


class Language(str, Enum):
    """Supported programming languages."""
    PYTHON = "Python"
    # Future: JAVASCRIPT = "JavaScript"


# ─── Issue ────────────────────────────────────────────────────────────────────

class Issue(BaseModel):
    """
    A single problem found in the code.
    This is the core data unit of the review system.
    """
    category:    IssueCategory          = Field(description="Which tool found this")
    severity:    Severity               = Field(description="How serious is it")
    line:        Optional[int]          = Field(None, description="Line number (1-indexed)")
    column:      Optional[int]          = Field(None, description="Column number")
    rule_id:     Optional[str]          = Field(None, description="Tool rule code, e.g. E501, B101")
    title:       str                    = Field(description="Short one-line title")
    description: str                    = Field(description="Plain-English explanation")
    suggestion:  Optional[str]          = Field(None, description="How to fix it")
    code_snippet: Optional[str]         = Field(None, description="The offending code line(s)")


# ─── Static Analysis Result ───────────────────────────────────────────────────

class StaticAnalysisResult(BaseModel):
    """Output of the local static analysis pipeline."""
    issues:          List[Issue]  = Field(default_factory=list)
    raw_pylint:      str          = Field("", description="Raw pylint output text")
    raw_flake8:      str          = Field("", description="Raw flake8 output text")
    raw_bandit:      str          = Field("", description="Raw bandit output text")
    syntax_ok:       bool         = Field(True, description="Did the file parse without error?")
    syntax_error_msg: Optional[str] = Field(None)


# ─── AI Review Result ─────────────────────────────────────────────────────────

class AIReviewResult(BaseModel):
    """Output of the LLM-based deep review."""
    summary:          str         = Field("", description="2-3 sentence overview")
    issues:           List[Issue] = Field(default_factory=list, description="AI-found issues")
    improved_code:    str         = Field("", description="Full rewritten/improved code")
    recommendations:  List[str]   = Field(default_factory=list, description="Bullet-point tips")
    score:            int         = Field(0, ge=0, le=100, description="Quality score 0-100")
    ai_available:     bool        = Field(False, description="Was an LLM actually used?")
    error_message:    Optional[str] = Field(None, description="Set if AI call failed")


# ─── Combined Final Result ────────────────────────────────────────────────────

class ReviewResult(BaseModel):
    """
    The complete review output combining static analysis + AI review.
    This is what the UI renders and the report generator consumes.
    """
    # Input metadata
    filename:       str               = Field("untitled.py")
    language:       Language          = Field(Language.PYTHON)
    original_code:  str               = Field("")
    line_count:     int               = Field(0)

    # Sub-results
    static:         StaticAnalysisResult
    ai:             AIReviewResult

    # Merged summary stats (computed after combining both)
    total_issues:   int               = Field(0)
    critical_count: int               = Field(0)
    high_count:     int               = Field(0)
    medium_count:   int               = Field(0)
    low_count:      int               = Field(0)
    info_count:     int               = Field(0)
    final_score:    int               = Field(0, ge=0, le=100)

    def compute_stats(self) -> None:
        """
        Populate count fields from the combined issue list.
        Call this after both static and AI results are attached.
        """
        all_issues = self.static.issues + self.ai.issues
        self.total_issues   = len(all_issues)
        self.critical_count = sum(1 for i in all_issues if i.severity == Severity.CRITICAL)
        self.high_count     = sum(1 for i in all_issues if i.severity == Severity.HIGH)
        self.medium_count   = sum(1 for i in all_issues if i.severity == Severity.MEDIUM)
        self.low_count      = sum(1 for i in all_issues if i.severity == Severity.LOW)
        self.info_count     = sum(1 for i in all_issues if i.severity == Severity.INFO)

        # Perfect score when no issues are present across static + AI results.
        if self.total_issues == 0:
            self.final_score = 100
            return

        # Use AI score if available, otherwise compute from static issues
        if self.ai.ai_available and self.ai.score > 0:
            self.final_score = self.ai.score
        else:
            self.final_score = self._compute_static_score()

    def _compute_static_score(self) -> int:
        """
        Heuristic score based on static analysis alone.
        Starts at 100 and deducts points per issue severity.
        """
        deductions = (
            self.critical_count * 25 +
            self.high_count     * 15 +
            self.medium_count   *  8 +
            self.low_count      *  3 +
            self.info_count     *  1
        )
        return max(0, 100 - deductions)

    @property
    def all_issues(self) -> List[Issue]:
        """Convenience accessor for the full merged issue list."""
        return self.static.issues + self.ai.issues

    @property
    def score_label(self) -> str:
        """Human-friendly label for the final score."""
        s = self.final_score
        if s >= 90: return "Excellent"
        if s >= 75: return "Good"
        if s >= 60: return "Fair"
        if s >= 40: return "Needs Work"
        return "Poor"
