"""
ui/components.py
─────────────────
Reusable Streamlit UI building blocks.
Each function renders a specific piece of the UI.
Centralising these avoids repeating HTML/Streamlit code across pages.
"""

from __future__ import annotations
import streamlit as st
from models.schemas import ReviewResult, Issue, Severity, IssueCategory
from ui.styles import severity_badge_html, score_circle_html, get_score_color


# ─── Score Section ────────────────────────────────────────────────────────────

def render_score_section(result: ReviewResult) -> None:
    """Display the quality score circle and issue count cards."""
    col_score, col_c, col_h, col_m, col_l = st.columns([2, 1, 1, 1, 1])

    with col_score:
        color = get_score_color(result.final_score)
        st.markdown(
            score_circle_html(result.final_score, result.score_label, color),
            unsafe_allow_html=True,
        )
        if not result.ai.ai_available:
            st.caption("⚠️ Score estimated from static analysis only")

    with col_c:
        st.metric("🔴 Critical", result.critical_count)
    with col_h:
        st.metric("🟠 High",     result.high_count)
    with col_m:
        st.metric("🟡 Medium",   result.medium_count)
    with col_l:
        st.metric("🔵 Low",      result.low_count)


# ─── Summary Banner ───────────────────────────────────────────────────────────

def render_summary_banner(result: ReviewResult) -> None:
    """Display the AI-mode indicator and summary text."""
    if result.ai.ai_available:
        mode_html = (
            '<div class="mode-banner ai">'
            '🤖 <strong>AI + Static Analysis Mode</strong> — '
            'Deep analysis powered by LLM'
            '</div>'
        )
    else:
        mode_html = (
            '<div class="mode-banner static">'
            '🔍 <strong>Static Analysis Only Mode</strong> — '
            'Add an API key in .env for AI-powered insights'
            '</div>'
        )
    st.markdown(mode_html, unsafe_allow_html=True)

    if result.ai.summary:
        st.info(f"**AI Summary:** {result.ai.summary}")

    if result.ai.error_message:
        st.warning(f"⚠️ AI review note: {result.ai.error_message}")


# ─── Issue List ───────────────────────────────────────────────────────────────

def render_issue_list(result: ReviewResult) -> None:
    """Render the full issue list with filters."""
    all_issues = result.all_issues

    if not all_issues:
        st.success("🎉 Great news! No issues were found in your code.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    col_sev, col_cat, col_search = st.columns([2, 2, 3])

    with col_sev:
        sev_options = ["All"] + [s.value.title() for s in Severity]
        sev_filter = st.selectbox("Filter by severity", sev_options, key="sev_filter")

    with col_cat:
        cat_options = ["All"] + [c.value.title() for c in IssueCategory]
        cat_filter = st.selectbox("Filter by category", cat_options, key="cat_filter")

    with col_search:
        search_query = st.text_input("🔍 Search issues", key="issue_search", placeholder="Type to search...")

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = all_issues

    if sev_filter != "All":
        target_sev = sev_filter.lower()
        filtered = [i for i in filtered if i.severity.value == target_sev]

    if cat_filter != "All":
        target_cat = cat_filter.lower()
        filtered = [i for i in filtered if i.category.value == target_cat]

    if search_query:
        q = search_query.lower()
        filtered = [
            i for i in filtered
            if q in i.title.lower() or q in i.description.lower()
        ]

    st.caption(f"Showing {len(filtered)} of {len(all_issues)} issues")

    # ── Render each issue ─────────────────────────────────────────────────────
    for i, issue in enumerate(filtered, 1):
        _render_single_issue(i, issue)


def _render_single_issue(index: int, issue: Issue) -> None:
    """Render one issue card with expand/collapse."""
    sev = issue.severity.value
    emoji_map = {
        "critical": "🔴", "high": "🟠", "medium": "🟡",
        "low": "🔵", "info": "⚪",
    }
    emoji = emoji_map.get(sev, "⚪")

    line_ref = f"line {issue.line}" if issue.line else ""
    cat_label = issue.category.value.upper()

    expander_label = (
        f"{emoji} **[{sev.upper()}]** {issue.title}  "
        f"{'`' + line_ref + '`' if line_ref else ''}"
    )

    with st.expander(expander_label, expanded=(sev in ("critical", "high") and index <= 3)):
        # Category pill
        st.markdown(
            f'<span style="background:#e2e8f0;color:#475569;padding:2px 10px;'
            f'border-radius:999px;font-size:0.8rem;">{cat_label}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**What's wrong:** {issue.description}")

        if issue.code_snippet:
            st.code(issue.code_snippet, language="python")

        if issue.suggestion:
            st.markdown(f"💡 **How to fix it:** {issue.suggestion}")

        if issue.rule_id:
            st.caption(f"Rule: `{issue.rule_id}`")


# ─── Improved Code ────────────────────────────────────────────────────────────

def render_improved_code(result: ReviewResult) -> None:
    """Display the AI-generated improved code."""
    if result.ai.improved_code:
        st.success("✅ Here is your improved code, generated by AI:")
        st.code(result.ai.improved_code, language="python")

        # Copy button workaround (Streamlit doesn't have native copy)
        st.download_button(
            label="⬇️ Download Improved Code",
            data=result.ai.improved_code,
            file_name=f"improved_{result.filename}",
            mime="text/plain",
        )
    else:
        st.info(
            "No improved code available. "
            "Configure an LLM API key in your `.env` file to generate improved code automatically."
        )


# ─── Recommendations ──────────────────────────────────────────────────────────

def render_recommendations(result: ReviewResult) -> None:
    """Display AI recommendations as a numbered list."""
    recs = result.ai.recommendations
    if recs:
        for i, rec in enumerate(recs, 1):
            st.markdown(f"**{i}.** {rec}")
    else:
        st.info(
            "Enable AI review to get personalised recommendations for your code."
        )


# ─── Raw Tool Output ──────────────────────────────────────────────────────────

def render_raw_output(result: ReviewResult) -> None:
    """Show raw output from static analysis tools (for advanced users)."""
    with st.expander("🔧 Raw pylint output", expanded=False):
        st.text(result.static.raw_pylint or "pylint did not run.")

    with st.expander("🔧 Raw flake8 output", expanded=False):
        st.text(result.static.raw_flake8 or "flake8 did not run.")

    with st.expander("🔒 Raw bandit output", expanded=False):
        st.text(result.static.raw_bandit or "bandit did not run.")


# ─── File Info Bar ────────────────────────────────────────────────────────────

def render_file_info(result: ReviewResult) -> None:
    """Show a one-line info bar about the reviewed file."""
    cols = st.columns(4)
    cols[0].metric("📄 File", result.filename)
    cols[1].metric("🔤 Language", result.language.value)
    cols[2].metric("📏 Lines", result.line_count)
    cols[3].metric("🐛 Total Issues", result.total_issues)
