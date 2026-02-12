#!/bin/bash
# ============================================
# CiteBridge — Quick Setup Script
# ============================================
# This script sets up everything you need to run CiteBridge.
# Usage:  chmod +x setup.sh && ./setup.sh
# ============================================

set -e

echo ""
echo "========================================"
echo "  CiteBridge Setup"
echo "  Zotero <-> NotebookLM Sync"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    echo "Install it from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "✅ Found $PYTHON_VERSION"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv .venv

# Activate
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi
echo "✅ Virtual environment created and activated"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"

# NotebookLM login
echo ""
echo "========================================"
echo "  Step 1: NotebookLM Authentication"
echo "========================================"
echo ""
echo "This will open a browser window for Google sign-in."
echo "After signing in, return to this terminal."
echo ""
read -p "Press Enter to start NotebookLM login..."
notebooklm login

echo ""
echo "✅ NotebookLM authentication complete!"

# Zotero setup
echo ""
echo "========================================"
echo "  Step 2: Zotero API Key"
echo "========================================"
echo ""
echo "You need a Zotero API key. Get one at:"
echo "  https://www.zotero.org/settings/keys"
echo ""
echo "1. Click 'Create new private key'"
echo "2. Name it 'CiteBridge'"
echo "3. Check 'Allow library access' (read + write)"
echo "4. Save the key"
echo ""
echo "Your Library ID is the number shown on that same page."
echo ""

# Done!
echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "To start CiteBridge:"
echo ""
echo "  1. Activate the environment:"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "     .venv\\Scripts\\activate"
else
    echo "     source .venv/bin/activate"
fi
echo ""
echo "  2. Run the app:"
echo "     streamlit run app.py"
echo ""
echo "  3. Enter your Zotero API key and Library ID in the sidebar"
echo "  4. Select collections and click SYNC NOW!"
echo ""
