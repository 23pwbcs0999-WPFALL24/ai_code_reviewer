@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM AI Code Reviewer — Windows Setup Script
REM Run this once to set up the project on your HP ZBook (Windows 11)
REM ─────────────────────────────────────────────────────────────────────────────

echo.
echo ============================================================
echo   AI Code Reviewer — Setup Script
echo ============================================================
echo.

REM Check Python is installed
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
IF ERRORLEVEL 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/4] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt
IF ERRORLEVEL 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [4/4] Setting up .env file...
IF NOT EXIST .env (
    copy .env.example .env
    echo.
    echo  *** .env file created from template ***
    echo  Open .env in Notepad and add your API key.
    echo  (The app works without one, in static-only mode.)
    echo.
) ELSE (
    echo  .env already exists — skipping.
)

echo.
echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo To run the app:
echo   1. venv\Scripts\activate
echo   2. streamlit run app.py
echo.
echo The app will open at: http://localhost:8501
echo.
pause
