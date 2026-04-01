"""
ui/styles.py
─────────────
Custom CSS injected into the Streamlit app.
Streamlit supports limited CSS customisation via st.markdown with unsafe_allow_html.
"""

CUSTOM_CSS = """
<style>
/* ── Global ─────────────────────────────────────────────────────────────────── */
.block-container { padding-top: 2rem; }

/* ── Score circle ───────────────────────────────────────────────────────────── */
.score-circle {
    width: 120px; height: 120px;
    border-radius: 50%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    margin: 0 auto 8px;
    font-weight: 800;
    box-shadow: 0 4px 15px rgba(0,0,0,0.15);
}
.score-number { font-size: 2.4rem; line-height: 1; }
.score-label  { font-size: 0.75rem; opacity: 0.9; }

/* ── Issue cards ────────────────────────────────────────────────────────────── */
.issue-card {
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 5px solid;
}
.issue-card.critical { border-color: #dc2626; background: #fef2f2; }
.issue-card.high     { border-color: #ea580c; background: #fff7ed; }
.issue-card.medium   { border-color: #ca8a04; background: #fefce8; }
.issue-card.low      { border-color: #2563eb; background: #eff6ff; }
.issue-card.info     { border-color: #6b7280; background: #f9fafb; }

/* ── Severity badges ────────────────────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 2px 10px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.badge-critical { background: #dc2626; color: white; }
.badge-high     { background: #ea580c; color: white; }
.badge-medium   { background: #ca8a04; color: white; }
.badge-low      { background: #2563eb; color: white; }
.badge-info     { background: #6b7280; color: white; }

/* ── Stat cards ─────────────────────────────────────────────────────────────── */
.stat-card {
    background: white;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.stat-number { font-size: 2rem; font-weight: 800; }
.stat-label  { font-size: 0.8rem; color: #64748b; margin-top: 2px; }

/* ── Mode banner ────────────────────────────────────────────────────────────── */
.mode-banner {
    padding: 10px 18px; border-radius: 8px;
    font-size: 0.9rem; font-weight: 600;
    margin-bottom: 16px;
}
.mode-banner.ai     { background: #ede9fe; color: #6d28d9; border-left: 4px solid #7c3aed; }
.mode-banner.static { background: #e0f2fe; color: #0369a1; border-left: 4px solid #0284c7; }

/* ── Syntax error box ───────────────────────────────────────────────────────── */
.syntax-error-box {
    background: #fef2f2; border: 2px solid #fca5a5;
    border-radius: 10px; padding: 16px;
    color: #991b1b;
}

/* ── Code snippet in issue card ─────────────────────────────────────────────── */
.code-snippet {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 0.82rem;
    background: #1e293b; color: #e2e8f0;
    padding: 8px 12px; border-radius: 6px;
    overflow-x: auto; white-space: pre;
    margin-top: 6px;
}
</style>
"""


def severity_badge_html(severity: str) -> str:
    """Return a coloured HTML badge for a severity string."""
    emoji_map = {
        "critical": "🔴",
        "high":     "🟠",
        "medium":   "🟡",
        "low":      "🔵",
        "info":     "⚪",
    }
    emoji = emoji_map.get(severity.lower(), "⚪")
    return (
        f'<span class="badge badge-{severity.lower()}">'
        f'{emoji} {severity.upper()}'
        f'</span>'
    )


def score_circle_html(score: int, label: str, color: str) -> str:
    """Return the HTML for the circular score display."""
    return f"""
    <div class="score-circle" style="background: {color}; color: white;">
        <span class="score-number">{score}</span>
        <span class="score-label">{label}</span>
    </div>
    """


def get_score_color(score: int) -> str:
    """Return a background colour for the given score."""
    if score >= 80: return "#16a34a"
    if score >= 60: return "#ca8a04"
    if score >= 40: return "#ea580c"
    return "#dc2626"
