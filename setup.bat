@echo off
REM ============================================
REM CiteBridge — Quick Setup Script (Windows)
REM ============================================
REM Usage: Double-click this file, or run: setup.bat
REM ============================================

echo.
echo ========================================
echo   CiteBridge Setup
echo   Zotero ^<-^> NotebookLM Sync
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3 is required but not installed.
    echo Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat
echo Virtual environment created.

echo.
echo Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo Dependencies installed.

echo.
echo ========================================
echo   Step 1: NotebookLM Authentication
echo ========================================
echo.
echo This will open a browser window for Google sign-in.
echo After signing in, return to this terminal.
echo.
pause
notebooklm login

echo.
echo ========================================
echo   Step 2: Zotero API Key
echo ========================================
echo.
echo Get your API key at: https://www.zotero.org/settings/keys
echo 1. Click 'Create new private key'
echo 2. Name it 'CiteBridge'
echo 3. Check 'Allow library access' (read + write)
echo 4. Save the key
echo.

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo To start CiteBridge:
echo   1. .venv\Scripts\activate
echo   2. streamlit run app.py
echo   3. Enter your Zotero credentials in the sidebar
echo   4. Select collections and click SYNC NOW!
echo.
pause
