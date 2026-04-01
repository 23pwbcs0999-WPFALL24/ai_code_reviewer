@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM AI Code Reviewer — Quick Launch Script (Windows)
REM Double-click this file to start the app after setup.bat has been run.
REM ─────────────────────────────────────────────────────────────────────────────

echo Starting AI Code Reviewer...
call venv\Scripts\activate.bat
streamlit run app.py
pause
