"""
app.py
───────
Main Streamlit application — the entry point for the AI Code Reviewer.

Run with:
    streamlit run app.py

The app has three input methods:
  1. Paste code directly
  2. Upload a single file
  3. Upload a ZIP archive (project folder)

After analysis, results are shown across four tabs:
  Overview | Issues | Improved Code | Report
"""

import sys
import os

# ── Add project root to Python path so imports work ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from config.settings import settings
from core.analyzer import analyze_code
from core.report.generator import generate_html_report
from ui.styles import CUSTOM_CSS
from ui.components import (
    render_score_section,
    render_summary_banner,
    render_issue_list,
    render_improved_code,
    render_recommendations,
    render_raw_output,
    render_file_info,
)
from utils.file_handler import (
    read_uploaded_file,
    read_zip_archive,
    detect_language,
)


# ─── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title=settings.APP_TITLE,
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
def render_sidebar() -> None:
    """Render the configuration sidebar."""
    with st.sidebar:
        st.title("⚙️ Settings")

        # AI status indicator
        if settings.llm_available:
            st.success(
                f"✅ AI Active\n\n"
                f"**Provider:** {settings.LLM_PROVIDER.upper()}\n\n"
                f"**Model:** `{settings.active_model}`"
            )
        else:
            st.warning(
                "⚠️ **AI Review Disabled**\n\n"
                "Static analysis only mode.\n\n"
                "To enable AI review:\n"
                "1. Copy `.env.example` → `.env`\n"
                "2. Add your API key\n"
                "3. Restart the app"
            )

        st.divider()

        # Quick provider setup guide
        with st.expander("📖 How to get a free API key"):
            st.markdown("""
**Groq (Recommended — Free)**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for free
3. Create an API key
4. Add to `.env`: `GROQ_API_KEY=your_key`

**Google Gemini (Free tier)**
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with Google
3. Create API key
4. Add to `.env`: `GEMINI_API_KEY=your_key`
            """)

        st.divider()
        st.caption(f"Version: {settings.APP_VERSION}")
        st.caption("Built for university project demo")


# ─── Input Section ────────────────────────────────────────────────────────────
def render_input_section() -> tuple[str | None, str, str]:
    """
    Render the code input area and return (code, filename, language).
    Returns (None, ..., ...) if no code has been provided yet.
    """
    st.header("📥 Input Your Code")

    # Input method selector
    input_method = st.radio(
        "Choose how to provide your code:",
        ["✏️ Paste Code", "📄 Upload File", "📦 Upload ZIP / Project Folder"],
        horizontal=True,
    )

    code     = None
    filename = "untitled.py"
    language = "Python"

    # ── Method 1: Paste ───────────────────────────────────────────────────────
    if input_method == "✏️ Paste Code":
        if "paste_area" not in st.session_state:
            st.session_state["paste_area"] = ""

        # Update the state before creating the text_area widget for this run.
        if st.button("📋 Load sample buggy code", help="Load an example with intentional bugs"):
            st.session_state["paste_area"] = _sample_buggy_code()

        col_lang, col_fname = st.columns([2, 3])
        with col_lang:
            lang_choice = st.selectbox(
                "Language",
                list(settings.SUPPORTED_LANGUAGES.values()),
                index=0,
            )
            language = lang_choice

        with col_fname:
            filename = st.text_input(
                "File name (for the report)",
                value="my_code.py",
                placeholder="e.g. main.py",
            )

        pasted = st.text_area(
            "Paste your code here:",
            height=300,
            placeholder="# Paste your Python code here...\n\ndef hello():\n    print('Hello, world!')",
            key="paste_area",
        )

        if pasted and pasted.strip():
            code = pasted

    # ── Method 2: Upload file ─────────────────────────────────────────────────
    elif input_method == "📄 Upload File":
        supported_exts = list(settings.SUPPORTED_LANGUAGES.keys())
        uploaded = st.file_uploader(
            f"Upload a source file ({', '.join(supported_exts)})",
            type=[ext.lstrip(".") for ext in supported_exts],
        )

        if uploaded is not None:
            try:
                code, language = read_uploaded_file(uploaded.read(), uploaded.name)
                filename = uploaded.name
                st.success(f"✅ Loaded **{uploaded.name}** ({language}, {len(code.splitlines())} lines)")
            except ValueError as exc:
                st.error(f"❌ {exc}")

    # ── Method 3: Upload ZIP ──────────────────────────────────────────────────
    else:
        uploaded_zip = st.file_uploader(
            "Upload a ZIP file containing your project",
            type=["zip"],
        )

        if uploaded_zip is not None:
            try:
                code, language, included = read_zip_archive(uploaded_zip.read())
                filename = uploaded_zip.name.replace(".zip", "_project.py")
                st.success(
                    f"✅ Loaded **{len(included)} file(s)** from ZIP:\n"
                    + "\n".join(f"  • `{f}`" for f in included[:10])
                    + ("\n  • ... and more" if len(included) > 10 else "")
                )
            except ValueError as exc:
                st.error(f"❌ {exc}")

    return code, filename, language


# ─── Results Section ──────────────────────────────────────────────────────────
def render_results(result) -> None:
    """Render the full results view after analysis completes."""
    st.divider()
    st.header("📊 Review Results")

    # File info bar
    render_file_info(result)

    # Score and summary
    st.subheader("🏆 Quality Score")
    render_score_section(result)
    render_summary_banner(result)

    # Syntax error — show prominently before the tabs
    if not result.static.syntax_ok:
        st.error(
            "⛔ **Syntax Error Detected** — your code cannot run until this is fixed!\n\n"
            + (result.static.syntax_error_msg or "")
        )

    # Results tabs
    tab_issues, tab_improved, tab_recs, tab_report, tab_raw = st.tabs([
        f"🐛 Issues ({result.total_issues})",
        "✅ Improved Code",
        "💡 Recommendations",
        "📋 Download Report",
        "🔧 Raw Tool Output",
    ])

    with tab_issues:
        render_issue_list(result)

    with tab_improved:
        render_improved_code(result)

    with tab_recs:
        render_recommendations(result)

    with tab_report:
        _render_report_tab(result)

    with tab_raw:
        render_raw_output(result)


def _render_report_tab(result) -> None:
    """Render the report download tab."""
    st.subheader("📋 Downloadable HTML Report")
    st.markdown(
        "Download a complete, well-formatted report you can open in any browser. "
        "Use **Ctrl+P** in the browser to save it as PDF."
    )

    # Generate HTML report
    html_report = generate_html_report(result)

    st.download_button(
        label="⬇️ Download HTML Report",
        data=html_report,
        file_name=f"review_{result.filename.replace('.py', '')}.html",
        mime="text/html",
        use_container_width=True,
    )

    # Preview
    with st.expander("👁️ Preview report in browser"):
        st.components.v1.html(html_report, height=600, scrolling=True)


# ─── Sample Code ──────────────────────────────────────────────────────────────
def _sample_buggy_code() -> str:
    """Return sample Python code with intentional bugs for demonstration."""
    return '''import os
import sys
import hashlib
import pickle
import random

# Bad practice: hardcoded password
PASSWORD = "admin123"
SECRET_KEY = "mysecretkey_do_not_share"

def calculate_average(numbers):
    # Bug: no check for empty list -> ZeroDivisionError
    total = 0
    for n in numbers:
        total = total + n
    return total / len(numbers)

def get_user_data(user_id):
    # Security: SQL injection risk (string formatting)
    query = "SELECT * FROM users WHERE id = %s" % user_id
    return query

def hash_password(password):
    # Security: MD5 is cryptographically broken
    return hashlib.md5(password.encode()).hexdigest()

def load_user_session(session_file):
    # Security: pickle deserialisation is dangerous
    with open(session_file, "rb") as f:
        return pickle.load(f)

def generate_token():
    # Security: random is not cryptographically secure
    return random.randint(100000, 999999)

class UserManager:
    def __init__(self):
        self.users = {}

    def add_user(self,username,password,email):   # style: no spaces
        # Bug: no input validation
        self.users[username] = {"password": hash_password(password), "email": email}

    def delete_user(self, username):
        # Bug: no check if user exists -> KeyError
        del self.users[username]

    def authenticate(self, username, password):
        # Bug: returns None instead of False when user not found
        if username in self.users:
            stored = self.users[username]["password"]
            if stored == hash_password(password):
                return True

# Unused import and unused variable
unused_variable = 42

def process_data(data):
    result = []
    for item in data:
        try:
            result.append(int(item))
        except:  # Bad: bare except
            pass  # Bad: silently swallows errors
    return result

if __name__ == "__main__":
    nums = [1, 2, 3, 4, 5]
    avg = calculate_average(nums)
    print(f"Average: {avg}")

    empty_avg = calculate_average([])   # This will crash!
    print(f"Empty average: {empty_avg}")
'''


# ─── Main App ─────────────────────────────────────────────────────────────────
def main() -> None:
    """Main application entry point."""
    # Sidebar
    render_sidebar()

    # App title
    st.title(f"🔍 {settings.APP_TITLE}")
    st.markdown(
        "**Paste your code, upload a file, or upload a ZIP project folder** "
        "to get an instant review — bugs, security issues, style problems, "
        "and an AI-powered explanation with improved code."
    )

    st.divider()

    # ── Input ─────────────────────────────────────────────────────────────────
    code, filename, language = render_input_section()

    # ── Analyse button ────────────────────────────────────────────────────────
    st.divider()

    if code:
        col_btn, col_info = st.columns([2, 5])
        with col_btn:
            run_review = st.button(
                "🚀 Run Code Review",
                type="primary",
                use_container_width=True,
            )
        with col_info:
            line_count = len(code.splitlines())
            st.markdown(
                f"Ready to review **{line_count} lines** of **{language}** code "
                f"from `{filename}`"
            )
    else:
        st.info(
            "👆 Paste some code or upload a file above, "
            "then click **Run Code Review** to start."
        )
        run_review = False

    # ── Run analysis ──────────────────────────────────────────────────────────
    if code and run_review:
        with st.spinner("🔍 Running static analysis (pylint, flake8, bandit)..."):
            # We do this in two stages so the user sees progress
            from core.static_analysis import run_static_analysis
            static_result = run_static_analysis(code, language)

        if settings.llm_available:
            with st.spinner(
                f"🤖 Running AI review with {settings.LLM_PROVIDER.upper()} "
                f"({settings.active_model})..."
            ):
                from core.ai_review.reviewer import run_ai_review
                ai_result = run_ai_review(code, language, static_result.issues)
        else:
            from core.ai_review.reviewer import _static_only_fallback
            ai_result = _static_only_fallback(static_result.issues)

        # Build full result
        from models.schemas import ReviewResult, Language as Lang
        try:
            lang_enum = Lang(language)
        except ValueError:
            lang_enum = Lang.PYTHON

        from utils.code_utils import count_lines as _count
        result = ReviewResult(
            filename=filename,
            language=lang_enum,
            original_code=code,
            line_count=_count(code),
            static=static_result,
            ai=ai_result,
        )
        result.compute_stats()

        # Cache result in session state so it persists on reruns
        st.session_state["last_result"] = result

    # ── Show results (from session state, persists after reruns) ──────────────
    if "last_result" in st.session_state:
        render_results(st.session_state["last_result"])


if __name__ == "__main__":
    main()
