"""
core/report/generator.py
─────────────────────────
Generates a downloadable HTML report from a ReviewResult.

Why HTML instead of PDF?
  - No heavy dependencies (no WeasyPrint, wkhtmltopdf, etc.)
  - Looks great in any browser
  - Users can print to PDF using Ctrl+P
  - Easily styled with inline CSS — no external files needed
  - Works offline
"""

from __future__ import annotations
import html as html_lib
from datetime import datetime
from typing import Optional

from models.schemas import ReviewResult, Severity, IssueCategory


# ─── Severity colours ─────────────────────────────────────────────────────────
SEVERITY_COLORS = {
    Severity.CRITICAL: ("#dc2626", "#fee2e2", "🔴"),  # red
    Severity.HIGH:     ("#ea580c", "#ffedd5", "🟠"),  # orange
    Severity.MEDIUM:   ("#ca8a04", "#fef9c3", "🟡"),  # yellow
    Severity.LOW:      ("#2563eb", "#dbeafe", "🔵"),  # blue
    Severity.INFO:     ("#6b7280", "#f3f4f6", "⚪"),  # grey
}

# Category labels
CATEGORY_LABELS = {
    IssueCategory.SYNTAX:   "Syntax",
    IssueCategory.SECURITY: "Security",
    IssueCategory.LINT:     "Lint",
    IssueCategory.STYLE:    "Style",
    IssueCategory.AI:       "AI Review",
}


def generate_html_report(result: ReviewResult) -> str:
    """
    Generate a self-contained HTML report string from a ReviewResult.
    The returned string can be written to a .html file or served directly.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    score_color = _score_color(result.final_score)
    all_issues  = result.all_issues

    # ── Build issue rows ──────────────────────────────────────────────────────
    issue_rows_html = ""
    if all_issues:
        for i, issue in enumerate(all_issues, 1):
            color, bg, emoji = SEVERITY_COLORS.get(
                issue.severity, ("#6b7280", "#f3f4f6", "⚪")
            )
            cat_label = CATEGORY_LABELS.get(issue.category, issue.category.value)
            line_ref  = f"Line {issue.line}" if issue.line else "—"
            snippet_html = ""
            if issue.code_snippet:
                escaped = html_lib.escape(issue.code_snippet)
                snippet_html = f'<pre class="snippet">{escaped}</pre>'

            suggestion_html = ""
            if issue.suggestion:
                suggestion_html = (
                    f'<p class="suggestion">💡 <strong>Fix:</strong> '
                    f'{html_lib.escape(issue.suggestion)}</p>'
                )

            issue_rows_html += f"""
            <div class="issue-card" style="border-left: 4px solid {color}; background: {bg};">
              <div class="issue-header">
                <span class="issue-num">#{i}</span>
                <span class="badge" style="background:{color}; color:white;">{emoji} {issue.severity.value.upper()}</span>
                <span class="badge-cat">{cat_label}</span>
                <span class="issue-loc">{line_ref}</span>
              </div>
              <h4 class="issue-title">{html_lib.escape(issue.title)}</h4>
              <p class="issue-desc">{html_lib.escape(issue.description)}</p>
              {snippet_html}
              {suggestion_html}
            </div>
            """
    else:
        issue_rows_html = '<p class="no-issues">🎉 No issues found!</p>'

    # ── Recommendations ───────────────────────────────────────────────────────
    recs_html = ""
    if result.ai.recommendations:
        items = "".join(
            f"<li>{html_lib.escape(r)}</li>"
            for r in result.ai.recommendations
        )
        recs_html = f"<ul class='rec-list'>{items}</ul>"
    else:
        recs_html = "<p>Run with an AI API key enabled for personalised recommendations.</p>"

    # ── Improved code ─────────────────────────────────────────────────────────
    improved_code_html = ""
    if result.ai.improved_code:
        escaped_code = html_lib.escape(result.ai.improved_code)
        improved_code_html = f"""
        <section>
          <h2>✅ Improved Code</h2>
          <pre class="code-block">{escaped_code}</pre>
        </section>
        """
    else:
        improved_code_html = """
        <section>
          <h2>✅ Improved Code</h2>
          <p>Enable AI review (add an API key) to generate improved code automatically.</p>
        </section>
        """

    # ── Original code ─────────────────────────────────────────────────────────
    escaped_original = html_lib.escape(result.original_code[:5000])
    if len(result.original_code) > 5000:
        escaped_original += "\n\n# ... [truncated in report] ..."

    # ── AI summary ────────────────────────────────────────────────────────────
    ai_summary_html = ""
    if result.ai.summary:
        ai_summary_html = f'<p class="ai-summary">{html_lib.escape(result.ai.summary)}</p>'

    # ── Mode badge ────────────────────────────────────────────────────────────
    if result.ai.ai_available:
        mode_badge = '<span class="mode-badge ai">🤖 AI + Static Analysis</span>'
    else:
        mode_badge = '<span class="mode-badge static">🔍 Static Analysis Only</span>'

    # ─────────────────────────────────────────────────────────────────────────
    # Assemble the full HTML document
    # ─────────────────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Review Report — {html_lib.escape(result.filename)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: #f8fafc; color: #1e293b; line-height: 1.6;
      padding: 0 16px;
    }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 32px 0; }}

    /* Header */
    .report-header {{
      background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
      color: white; border-radius: 16px; padding: 32px;
      margin-bottom: 32px;
    }}
    .report-header h1 {{ font-size: 1.8rem; margin-bottom: 8px; }}
    .report-meta {{ font-size: 0.9rem; opacity: 0.8; margin-top: 8px; }}

    /* Score card */
    .score-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .score-card {{
      background: white; border-radius: 12px; padding: 20px;
      text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .score-big {{ font-size: 3rem; font-weight: 800; color: {score_color}; }}
    .score-label {{ font-size: 0.85rem; color: #64748b; margin-top: 4px; }}
    .count-big {{ font-size: 2rem; font-weight: 700; }}

    /* Section */
    section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    h2 {{ font-size: 1.2rem; font-weight: 700; margin-bottom: 16px; color: #1e293b; }}
    h4 {{ font-size: 1rem; font-weight: 600; margin-bottom: 4px; }}

    /* Issue cards */
    .issue-card {{ border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
    .issue-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
    .issue-num {{ font-size: 0.8rem; color: #94a3b8; }}
    .badge {{ padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }}
    .badge-cat {{ padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; background: #e2e8f0; color: #475569; }}
    .issue-loc {{ font-size: 0.8rem; color: #64748b; margin-left: auto; }}
    .issue-title {{ color: #1e293b; margin-bottom: 6px; }}
    .issue-desc {{ font-size: 0.9rem; color: #475569; margin-bottom: 8px; }}
    .suggestion {{ font-size: 0.88rem; color: #15803d; background: #f0fdf4; padding: 8px 12px; border-radius: 6px; margin-top: 8px; }}
    .snippet {{ font-size: 0.82rem; background: #1e293b; color: #e2e8f0; padding: 8px 12px; border-radius: 6px; overflow-x: auto; margin: 8px 0; font-family: 'Consolas', 'Courier New', monospace; }}
    .no-issues {{ color: #16a34a; font-weight: 600; font-size: 1.1rem; }}

    /* Code block */
    .code-block {{
      background: #0f172a; color: #e2e8f0; padding: 20px; border-radius: 10px;
      overflow-x: auto; font-family: 'Consolas', 'Courier New', monospace;
      font-size: 0.84rem; line-height: 1.7; white-space: pre;
    }}

    /* Recommendations */
    .rec-list {{ padding-left: 20px; }}
    .rec-list li {{ margin-bottom: 8px; color: #334155; }}

    /* Badges */
    .mode-badge {{ padding: 4px 14px; border-radius: 99px; font-size: 0.82rem; font-weight: 600; }}
    .mode-badge.ai {{ background: #ede9fe; color: #6d28d9; }}
    .mode-badge.static {{ background: #e0f2fe; color: #0369a1; }}
    .ai-summary {{ color: #334155; background: #f1f5f9; padding: 12px 16px; border-radius: 8px; border-left: 4px solid #6366f1; }}

    /* Severity summary */
    .sev-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
    .sev-pill {{ padding: 4px 14px; border-radius: 99px; font-size: 0.82rem; font-weight: 600; }}

    /* Footer */
    .report-footer {{ text-align: center; padding: 24px; color: #94a3b8; font-size: 0.85rem; }}

    @media print {{
      body {{ background: white; }}
      section {{ box-shadow: none; border: 1px solid #e2e8f0; }}
    }}
  </style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="report-header">
    <h1>📋 Code Review Report</h1>
    <div class="report-meta">
      <strong>File:</strong> {html_lib.escape(result.filename)} &nbsp;|&nbsp;
      <strong>Language:</strong> {result.language.value} &nbsp;|&nbsp;
      <strong>Lines:</strong> {result.line_count} &nbsp;|&nbsp;
      <strong>Generated:</strong> {now}
    </div>
    <div style="margin-top: 12px;">{mode_badge}</div>
  </div>

  <!-- Score cards -->
  <div class="score-grid">
    <div class="score-card">
      <div class="score-big">{result.final_score}</div>
      <div class="score-label">Quality Score / 100<br><strong>{result.score_label}</strong></div>
    </div>
    <div class="score-card">
      <div class="count-big" style="color:#dc2626">{result.critical_count + result.high_count}</div>
      <div class="score-label">Critical &amp; High Issues</div>
    </div>
    <div class="score-card">
      <div class="count-big" style="color:#ca8a04">{result.medium_count}</div>
      <div class="score-label">Medium Issues</div>
    </div>
    <div class="score-card">
      <div class="count-big" style="color:#2563eb">{result.low_count + result.info_count}</div>
      <div class="score-label">Low &amp; Info Issues</div>
    </div>
  </div>

  <!-- Summary -->
  <section>
    <h2>📝 Summary</h2>
    {ai_summary_html if ai_summary_html else '<p>Add an AI API key to get a detailed summary.</p>'}
    <div class="sev-row" style="margin-top: 16px;">
      <span class="sev-pill" style="background:#fee2e2;color:#dc2626">🔴 Critical: {result.critical_count}</span>
      <span class="sev-pill" style="background:#ffedd5;color:#ea580c">🟠 High: {result.high_count}</span>
      <span class="sev-pill" style="background:#fef9c3;color:#ca8a04">🟡 Medium: {result.medium_count}</span>
      <span class="sev-pill" style="background:#dbeafe;color:#2563eb">🔵 Low: {result.low_count}</span>
      <span class="sev-pill" style="background:#f3f4f6;color:#6b7280">⚪ Info: {result.info_count}</span>
    </div>
  </section>

  <!-- Issues -->
  <section>
    <h2>🐛 Issues Found ({result.total_issues})</h2>
    {issue_rows_html}
  </section>

  <!-- Improved Code -->
  {improved_code_html}

  <!-- Recommendations -->
  <section>
    <h2>💡 Recommendations</h2>
    {recs_html}
  </section>

  <!-- Original Code -->
  <section>
    <h2>📄 Original Code</h2>
    <pre class="code-block">{escaped_original}</pre>
  </section>

  <div class="report-footer">
    Generated by <strong>AI Code Reviewer</strong> v1.0 &nbsp;|&nbsp;
    Print this page (Ctrl+P) to save as PDF
  </div>

</div>
</body>
</html>"""


def _score_color(score: int) -> str:
    """Return a CSS colour string for the score number."""
    if score >= 80: return "#16a34a"    # green
    if score >= 60: return "#ca8a04"    # yellow
    if score >= 40: return "#ea580c"    # orange
    return "#dc2626"                    # red
