# ZoteroLM

**One-button bidirectional sync between Zotero and Google NotebookLM.**

ZoteroLM reads your Zotero collections, uploads PDFs directly to NotebookLM as organized notebooks, and pulls AI-generated notes back into Zotero — all with a single click.

Built by [Voss AI Consulting](https://www.vossaiconsulting.com)

---

## What It Does

- **Zotero → NotebookLM:** Automatically creates a NotebookLM notebook for each Zotero collection and uploads all PDFs as sources
- **NotebookLM → Zotero (Sources):** Import raw sources from any NotebookLM notebook into Zotero as proper library items — with original URLs, correct item types, and full extracted text
- **NotebookLM → Zotero (Notes):** Pulls AI-generated notes back into Zotero as attached notes
- **Smart sync:** Tracks what's already been synced — only uploads new or changed items
- **One-button:** Select your collections or notebooks, click Sync or Import, done

---

## Quick Start (15 minutes)

### Prerequisites

- **Python 3.9+** — [Download here](https://www.python.org/downloads/)
- **Zotero** desktop app installed with some collections
- **A Google account** with access to [NotebookLM](https://notebooklm.google.com)

### Step 1: Download & Install

```bash
# Unzip the project (or clone from repo)
cd zoterolm

# Mac/Linux:
chmod +x setup.sh
./setup.sh

# Windows:
# Double-click setup.bat
```

**Or manual setup:**

```bash
cd zoterolm
python3 -m venv .venv
source .venv/bin/activate     # Mac/Linux
# .venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### Step 2: Authenticate NotebookLM

```bash
# Make sure you're in the virtual environment first
source .venv/bin/activate     # Mac/Linux

# Run the login command — this opens a browser
notebooklm login
```

This opens Google sign-in in your browser. After authenticating, return to the terminal. Your auth tokens are saved locally at `~/.notebooklm/`.

### Step 3: Get Your Zotero API Key

1. Go to [zotero.org/settings/keys](https://www.zotero.org/settings/keys)
2. Click **"Create new private key"**
3. Name it **"ZoteroLM"**
4. Under "Personal Library," check:
   - ✅ Allow library access
   - ✅ Allow write access
5. Click **Save Key**
6. **Copy the key** (you'll paste it into the app)
7. **Note your Library ID** — it's the number shown at the top of the keys page (labeled "Your userID for use in API calls is XXXXXXX")

### Step 4: Launch the App

```bash
streamlit run app.py
```

This opens the ZoteroLM dashboard in your browser (usually at `http://localhost:8501`).

### Step 5: Configure & Sync

1. In the **sidebar**, expand "Zotero Connection"
2. Paste your **API Key** and **Library ID**
3. Click **"Save & Test Zotero"** — you should see a green checkmark
4. Expand "NotebookLM Connection" and click **"Verify NotebookLM Connection"**
5. On the main page, **check the collections** you want to sync
6. Click the big **🔄 SYNC NOW** button
7. Watch the progress as your PDFs are uploaded to NotebookLM!

---

## How It Works

```
Zotero Collection          Google NotebookLM
┌─────────────────┐        ┌──────────────────┐
│  AI Ethics      │───────►│  AI Ethics       │
│  ├── paper1.pdf │  sync  │  ├── paper1 (src) │
│  ├── paper2.pdf │───────►│  ├── paper2 (src) │
│  └── paper3.pdf │        │  ├── paper3 (src) │
│                 │◄───────│  └── AI Notes     │
└─────────────────┘ notes  └──────────────────┘
```

**Forward sync (Zotero → NotebookLM):**
1. Reads your Zotero collections via the Zotero API
2. Downloads PDFs (from local storage or via API)
3. Creates a matching NotebookLM notebook for each collection
4. Uploads PDFs directly as sources

**Reverse sync (NotebookLM → Zotero):**
1. Reads notes from each synced NotebookLM notebook
2. Matches notes to Zotero items by title
3. Creates Zotero notes tagged with `notebooklm-sync`

**State tracking:**
- Uses a local SQLite database (`~/.zoterolm/sync_state.db`)
- Tracks what's been synced with file hashes
- Only syncs new or changed items

---

## Project Structure

```
zoterolm/
├── app.py                  # Streamlit GUI (run this!)
├── requirements.txt        # Python dependencies
├── setup.sh / setup.bat    # One-line setup scripts
├── README.md               # This file
└── zoterolm/               # Core library
    ├── config.py            # Configuration management
    ├── zotero_client.py     # Zotero API wrapper
    ├── notebooklm_client.py # NotebookLM API wrapper
    ├── sync_engine.py       # Sync orchestration
    ├── state_db.py          # SQLite state tracking
    └── utils.py             # Helpers
```

---

## Troubleshooting

### "NotebookLM connection failed"
- Run `notebooklm login` again in your terminal
- Make sure you completed the Google sign-in in the browser
- Check that `~/.notebooklm/storage_state.json` exists

### "Zotero connection failed"
- Verify your API key at [zotero.org/settings/keys](https://www.zotero.org/settings/keys)
- Make sure the key has library access enabled
- Double-check your Library ID (it's a number, not your username)

### "No PDFs found for items"
- Some items may not have PDF attachments in Zotero
- If you set a local storage path, make sure it points to `Zotero/storage/`
- The app will fall back to downloading PDFs via the Zotero API

### Sync seems slow
- NotebookLM needs time to process each PDF after upload
- Large PDFs (50MB+) take longer
- The app waits for each source to be ready before moving on

### NotebookLM API errors
- The NotebookLM integration uses an unofficial library that may occasionally break
- If this happens, your Zotero data is never affected
- Try updating: `pip install --upgrade notebooklm-py`

---

## Configuration

All settings are saved in `~/.zoterolm/config.yaml`. You can edit this file directly or use the sidebar in the app.

```yaml
zotero:
  api_key: "your-key-here"
  library_id: "12345678"
  library_type: "user"
  local_storage_path: "/Users/you/Zotero/storage"
notebooklm:
  storage_path: ""  # blank = default location
  authenticated: true
sync:
  enabled_collections:
    - "ABCD1234"
    - "EFGH5678"
  sync_notes_back: true
  max_file_size_mb: 200
```

---

## Important Notes

- **NotebookLM API:** This app uses an unofficial library (`notebooklm-py`) that relies on undocumented Google APIs. It works well but may break if Google changes their internal APIs. If that happens, update the library and try again.
- **Your data is safe:** The app only reads from Zotero (except when writing notes back). It never deletes or modifies your existing Zotero items.
- **Auth tokens stay local:** All credentials are stored on your machine only (`~/.zoterolm/` and `~/.notebooklm/`).

---

## Author

**Rob Voss, Ph.D.** — [Voss AI Consulting](https://www.vossaiconsulting.com)

Voss AI Consulting helps businesses, educational institutions, and financial firms understand and leverage AI to save time, protect client data, and increase profitability.

- Website: [www.vossaiconsulting.com](https://www.vossaiconsulting.com)
- Personal: [www.robvoss.com](https://www.robvoss.com)

For custom AI integrations, consulting, or enterprise licensing, contact Rob at [www.vossaiconsulting.com](https://www.vossaiconsulting.com).

---

## License

MIT License

Copyright (c) 2026 Rob Voss / Voss AI Consulting (www.vossaiconsulting.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Built with [pyzotero](https://github.com/urschrei/pyzotero) and [notebooklm-py](https://github.com/teng-lin/notebooklm-py).
