# ZoteroLM — Bidirectional Zotero ↔ NotebookLM Sync App

## Full Architecture & Implementation Plan

**Author:** Rob Voss / Voss AI Consulting
**Date:** February 11, 2026
**Version:** 1.0 — Personal Use → Productizable

---

## 1. The Problem

Researchers and consultants who use both Zotero (reference management) and Google NotebookLM (AI-powered research) face a painful manual workflow:

- Downloading PDFs one-by-one from Zotero and re-uploading them to NotebookLM
- Manually creating NotebookLM notebooks to mirror Zotero collections
- No way to get NotebookLM's AI-generated notes back into Zotero
- Constant drift between the two tools as new sources are added

**ZoteroLM** solves this with one-button bidirectional sync.

---

## 2. What the App Does (User Experience)

### First-Time Setup (5 minutes)
1. User opens ZoteroLM desktop app
2. Clicks "Connect Zotero" → enters API key (copied from zotero.org/settings/keys)
3. Clicks "Connect Google" → OAuth flow authenticates both Google Drive and NotebookLM
4. Selects which Zotero collections to sync (checkboxes)
5. Done. Setup is saved permanently.

### Daily Use (One Button)
1. User clicks **"Sync Now"**
2. App shows progress:
   - ✅ Reading Zotero collections...
   - ✅ Found 3 new PDFs in "AI Ethics" collection
   - ✅ Uploading to Google Drive...
   - ✅ Creating NotebookLM notebook "AI Ethics"...
   - ✅ Adding 3 sources to notebook...
   - ✅ Pulling NotebookLM notes back to Zotero...
   - ✅ Sync complete!
3. User's NotebookLM now mirrors their Zotero collections
4. Any AI notes from NotebookLM are saved as Zotero notes

### Optional: Auto-Sync
- Toggle "Auto-sync every X hours" for hands-free operation
- File watcher detects new Zotero additions and triggers sync

---

## 3. Technical Architecture

```
┌──────────────────────────────────────────────────┐
│              ZoteroLM Desktop App                 │
│         (Python + PyQt6 or Electron)              │
├──────────────────────────────────────────────────┤
│                                                    │
│  ┌─────────────────────────────────────────────┐  │
│  │              UI Layer (Dashboard)            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │  │
│  │  │Collection│ │  Sync    │ │  Settings   │  │  │
│  │  │ Browser  │ │  Button  │ │  Panel      │  │  │
│  │  └──────────┘ └──────────┘ └─────────────┘  │  │
│  └─────────────────────────────────────────────┘  │
│                                                    │
│  ┌─────────────────────────────────────────────┐  │
│  │              Sync Engine                     │  │
│  │                                               │  │
│  │  ┌─────────────┐       ┌──────────────────┐  │  │
│  │  │   Zotero    │       │   NotebookLM     │  │  │
│  │  │   Adapter   │◄─────►│   Adapter        │  │  │
│  │  │  (pyzotero) │       │ (notebooklm-py)  │  │  │
│  │  └──────┬──────┘       └────────┬─────────┘  │  │
│  │         │                       │             │  │
│  │  ┌──────▼──────┐       ┌────────▼─────────┐  │  │
│  │  │  Zotero     │       │   Google Drive   │  │  │
│  │  │  File       │──────►│   Adapter        │  │  │
│  │  │  Reader     │       │  (official API)  │  │  │
│  │  └─────────────┘       └──────────────────┘  │  │
│  │                                               │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │       Sync State Manager (SQLite)       │  │  │
│  │  │  - tracks what's synced                 │  │  │
│  │  │  - detects changes                      │  │  │
│  │  │  - prevents duplicates                  │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────┘  │
│                                                    │
│  ┌─────────────────────────────────────────────┐  │
│  │         Auth & Config Manager                │  │
│  │  - Zotero API key                            │  │
│  │  - Google OAuth tokens                       │  │
│  │  - NotebookLM session                        │  │
│  │  - Sync preferences                          │  │
│  └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 4. The Hybrid API Strategy

### Official (Stable) Pathways
| Component | API | Stability |
|-----------|-----|-----------|
| Read Zotero collections & items | Zotero Web API v3 + pyzotero | ⭐⭐⭐⭐⭐ Very stable |
| Write notes back to Zotero | Zotero Web API v3 (write) | ⭐⭐⭐⭐⭐ Very stable |
| Upload PDFs to Google Drive | Google Drive API v3 | ⭐⭐⭐⭐⭐ Very stable |
| Read Zotero locally (fast) | Zotero Local API (localhost:23119) | ⭐⭐⭐⭐ Stable |

### Unofficial (Needed for Gaps)
| Component | API | Stability | Fallback |
|-----------|-----|-----------|----------|
| Create NotebookLM notebooks | notebooklm-py | ⭐⭐⭐ Moderate | Manual creation + Drive sources |
| Add sources to notebooks | notebooklm-py | ⭐⭐⭐ Moderate | Drive folder auto-import |
| Extract NotebookLM notes | notebooklm-py | ⭐⭐⭐ Moderate | Manual export |

### Fallback Strategy
If `notebooklm-py` breaks (Google changes internal APIs):
1. App detects the failure automatically
2. Falls back to **Google Drive as intermediary**: uploads PDFs to a Drive folder structure that mirrors Zotero collections
3. User manually adds Drive folders as NotebookLM sources (one-time per notebook)
4. App notifies user: "Direct NotebookLM sync unavailable — PDFs are in your Drive, ready to add manually"

This means the app is **always useful** even if the unofficial API breaks.

---

## 5. Detailed Sync Flows

### Flow A: Zotero → NotebookLM (Primary Direction)

```
Step 1: READ ZOTERO
  ├── Connect to Zotero Local API (localhost:23119)
  ├── Fallback: Zotero Web API v3 with API key
  ├── Enumerate selected collections
  ├── For each collection:
  │   ├── Get all items (papers, books, etc.)
  │   ├── Get attachment metadata (PDF paths)
  │   └── Get item metadata (title, authors, year, DOI)
  └── Compare against sync state DB → identify NEW/CHANGED items

Step 2: UPLOAD TO GOOGLE DRIVE (Official Pathway)
  ├── Create Drive folder: "ZoteroLM/{Collection Name}/"
  ├── Upload new PDFs to corresponding folders
  ├── Track Drive file IDs in sync state DB
  └── Skip already-synced files (hash comparison)

Step 3: CREATE/UPDATE NOTEBOOKLM NOTEBOOKS (Hybrid)
  ├── For each collection with new items:
  │   ├── Find or create NotebookLM notebook (name = collection name)
  │   ├── Add Drive files as sources (via notebooklm-py)
  │   └── Record notebook ID in sync state DB
  └── If notebooklm-py fails → notify user, Drive files are ready

Step 4: UPDATE SYNC STATE
  ├── Record all synced items with timestamps
  ├── Store file hashes for change detection
  └── Log sync results
```

### Flow B: NotebookLM → Zotero (Reverse Direction)

```
Step 1: READ NOTEBOOKLM NOTEBOOKS
  ├── Connect via notebooklm-py
  ├── For each synced notebook:
  │   ├── Get notebook notes/summaries
  │   ├── Get any generated content (audio summaries, etc.)
  │   └── Compare against sync state DB → identify NEW notes
  └── If notebooklm-py fails → skip with notification

Step 2: WRITE TO ZOTERO
  ├── For each new NotebookLM note:
  │   ├── Find corresponding Zotero item (by title/DOI match)
  │   ├── Create Zotero note attached to that item
  │   │   ├── Title: "NotebookLM Summary — {date}"
  │   │   ├── Content: the AI-generated note/summary
  │   │   └── Tag: "notebooklm-sync"
  │   └── If no matching item → create standalone note in collection
  └── Update sync state DB

Step 3: OPTIONAL — SAVE GENERATED CONTENT
  ├── Audio overviews → save as Zotero attachments
  ├── Generated study guides → save as Zotero notes
  └── Mind maps / infographics → save as Zotero attachments
```

---

## 6. Data Model (SQLite Sync State)

```sql
-- Track synced collections
CREATE TABLE collections (
    id INTEGER PRIMARY KEY,
    zotero_collection_key TEXT UNIQUE,
    zotero_collection_name TEXT,
    notebooklm_notebook_id TEXT,
    drive_folder_id TEXT,
    last_synced TIMESTAMP,
    sync_enabled BOOLEAN DEFAULT 1
);

-- Track synced items
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    zotero_item_key TEXT UNIQUE,
    collection_id INTEGER REFERENCES collections(id),
    title TEXT,
    doi TEXT,
    file_hash TEXT,
    drive_file_id TEXT,
    notebooklm_source_id TEXT,
    last_synced TIMESTAMP,
    sync_direction TEXT  -- 'zotero_to_nlm', 'nlm_to_zotero', 'both'
);

-- Track NotebookLM notes pulled back
CREATE TABLE nlm_notes (
    id INTEGER PRIMARY KEY,
    notebooklm_notebook_id TEXT,
    note_content TEXT,
    zotero_note_key TEXT,
    created_at TIMESTAMP,
    synced_to_zotero BOOLEAN DEFAULT 0
);

-- Sync log for debugging
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    status TEXT,  -- 'success', 'error', 'skipped'
    details TEXT
);
```

---

## 7. Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Language** | Python 3.11+ | Best library ecosystem for both APIs |
| **GUI** | PyQt6 | Native desktop look, cross-platform, packageable |
| **Zotero API** | pyzotero | Official Python wrapper, well-maintained |
| **NotebookLM** | notebooklm-py | Only programmatic access available |
| **Google Drive** | google-api-python-client | Official Google SDK |
| **Auth** | google-auth-oauthlib | Standard OAuth flow |
| **Database** | SQLite3 (built-in) | Zero config, portable, lightweight |
| **Packaging** | PyInstaller or Briefcase | One-click .app/.exe — no Python needed |
| **Scheduler** | APScheduler | Auto-sync timer |
| **Logging** | Python logging | Debug + sync history |

### Key Dependencies
```
pyzotero>=1.8.0
notebooklm-py>=0.1.0
google-api-python-client>=2.0
google-auth-oauthlib>=1.0
PyQt6>=6.5
apscheduler>=3.10
```

---

## 8. Project Structure

```
zoterolm/
├── main.py                    # Entry point
├── requirements.txt
├── setup.py                   # For packaging
│
├── ui/                        # GUI layer
│   ├── main_window.py         # Main app window
│   ├── collection_browser.py  # Zotero collection tree view
│   ├── sync_dashboard.py      # Sync status & progress
│   ├── settings_dialog.py     # Auth & preferences
│   └── resources/             # Icons, styles
│
├── adapters/                  # API adapters (plugin architecture)
│   ├── base_adapter.py        # Abstract base class
│   ├── zotero_adapter.py      # Zotero read/write
│   ├── notebooklm_adapter.py  # NotebookLM operations
│   └── drive_adapter.py       # Google Drive operations
│
├── engine/                    # Core sync logic
│   ├── sync_engine.py         # Orchestrates sync flows
│   ├── state_manager.py       # SQLite sync state
│   ├── conflict_resolver.py   # Handle sync conflicts
│   └── scheduler.py           # Auto-sync timer
│
├── auth/                      # Authentication
│   ├── zotero_auth.py         # API key management
│   ├── google_auth.py         # OAuth flow
│   └── credentials_store.py   # Secure credential storage
│
├── models/                    # Data models
│   ├── collection.py
│   ├── item.py
│   └── sync_record.py
│
├── utils/                     # Helpers
│   ├── file_utils.py          # PDF handling, hashing
│   ├── logger.py              # Logging setup
│   └── notifications.py       # System notifications
│
└── tests/                     # Test suite
    ├── test_zotero_adapter.py
    ├── test_sync_engine.py
    └── test_state_manager.py
```

---

## 9. Implementation Phases

### Phase 1: Core Sync (Zotero → Drive → NotebookLM) — Week 1-2
**Goal:** Get PDFs from Zotero into NotebookLM with one click

- [ ] Set up project scaffolding
- [ ] Implement Zotero adapter (read collections, items, PDFs)
- [ ] Implement Google Drive adapter (create folders, upload PDFs)
- [ ] Implement NotebookLM adapter (create notebooks, add sources)
- [ ] Build sync engine (orchestrate the flow)
- [ ] Build SQLite state manager
- [ ] Create minimal CLI for testing
- **Deliverable:** Working command-line sync tool

### Phase 2: Desktop GUI — Week 3
**Goal:** Wrap in a clean, one-button desktop interface

- [ ] Build PyQt6 main window
- [ ] Collection browser with checkboxes
- [ ] Sync button with progress bar
- [ ] Settings dialog for auth
- [ ] System tray icon for background running
- **Deliverable:** Functional desktop app

### Phase 3: Reverse Sync (NotebookLM → Zotero) — Week 4
**Goal:** Pull AI-generated notes back into Zotero

- [ ] Read NotebookLM notes/summaries
- [ ] Match notes to Zotero items
- [ ] Create Zotero notes via Web API
- [ ] Handle edge cases (unmatched items, duplicates)
- **Deliverable:** Full bidirectional sync

### Phase 4: Polish & Auto-Sync — Week 5
**Goal:** Production-ready for personal use

- [ ] Auto-sync scheduler (APScheduler)
- [ ] File change detection (watchdog)
- [ ] Error handling & retry logic
- [ ] Sync history/log viewer
- [ ] Package as standalone app (PyInstaller)
- **Deliverable:** Packaged .app / .exe

### Phase 5: Productization Prep — Week 6+ (Optional)
**Goal:** Prepare for sale through Voss AI Consulting

- [ ] User onboarding wizard
- [ ] License key system
- [ ] Auto-update mechanism
- [ ] Landing page + documentation
- [ ] Stripe integration for payments
- [ ] Customer support email setup
- **Deliverable:** Sellable product

---

## 10. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| notebooklm-py breaks (Google API changes) | Medium | High | Google Drive fallback always works; user can add Drive folders to NotebookLM manually |
| Google blocks unofficial API access | Low-Medium | High | Drive intermediary approach is 100% official |
| Zotero API rate limits | Low | Medium | Local API has no limits; batch operations; caching |
| Large libraries overwhelm sync | Medium | Medium | Incremental sync (only changes); configurable collection selection |
| PDF size limits on NotebookLM | Low | Low | Warn user; skip oversized files with notification |
| Auth token expiry | Medium | Low | Auto-refresh tokens; graceful re-auth prompt |

---

## 11. Monetization Strategy (Voss AI Consulting)

### Pricing Model
- **Free tier:** Sync up to 1 collection, 25 items (lead generation)
- **Personal ($9/month or $79/year):** Unlimited collections, auto-sync, reverse sync
- **Team ($29/month):** Shared libraries, multiple Zotero accounts, priority support

### Target Market
1. **Academic researchers** — manage literature reviews across tools
2. **Graduate students** — dissertation research organization
3. **Consulting firms** — knowledge management for client projects
4. **Legal professionals** — case research and AI analysis
5. **Medical researchers** — literature review automation

### Revenue Projections (Conservative)
- Month 1-3: Beta testing, 50 free users → feedback
- Month 4-6: Launch paid tiers, target 100 paying users
- Month 6-12: 500 paying users @ $9/mo avg = **$4,500/month**
- Year 2: 2,000 users @ $12/mo avg = **$24,000/month**

### Marketing Channels
- Zotero forums and community
- Academic Twitter/X and Bluesky
- YouTube tutorial (demo video)
- r/Zotero, r/NotebookLM subreddits
- Voss AI Consulting blog + newsletter
- Conference presentations (academic tech conferences)

### ROI Analysis
- **Development time:** ~120 hours (6 weeks part-time)
- **Your hourly consulting rate:** Likely $150-250/hr
- **Opportunity cost:** ~$18,000-$30,000
- **Break-even:** At $4,500/month recurring, break-even in 4-7 months
- **After break-even:** Pure recurring revenue with minimal maintenance
- **Strategic value:** Positions Voss AI Consulting as a builder, not just an advisor

---

## 12. Competitive Landscape

| Tool | What It Does | Limitation |
|------|-------------|------------|
| zotero-notebooklm-connector (GitHub) | Chrome extension, one-way Zotero→NLM | Manual, no reverse sync, no auto-sync |
| Zotero Better BibTeX | Export citations | No NotebookLM integration |
| Zotero Google Drive sync | Sync Zotero storage to Drive | No NotebookLM awareness |
| **ZoteroLM (this app)** | **Full bidirectional, automated, one-button** | **First of its kind** |

---

## 13. Technical Decision: Why Not a Chrome Extension?

The existing `zotero-notebooklm-connector` is a Chrome extension. Here's why a desktop app is better:

1. **Background sync** — Chrome extensions can't run when browser is closed
2. **File system access** — Direct access to Zotero's PDF storage (no re-downloading)
3. **Scheduling** — Auto-sync every N hours without browser open
4. **Database** — SQLite for tracking sync state across sessions
5. **Packaging** — Distribute as standalone .app/.exe, no extension install
6. **API flexibility** — Can use both local and web Zotero APIs
7. **Productization** — Easier to license, update, and support

---

## 14. Quick-Start: What to Build First

If you want to validate the concept in a single afternoon:

```bash
# 1. Install dependencies
pip install pyzotero notebooklm-py google-api-python-client

# 2. Run the proof-of-concept script (we'll build this)
python zoterolm_poc.py --collection "AI Ethics" --sync
```

This proof-of-concept would:
1. Read one Zotero collection
2. Upload its PDFs to a Google Drive folder
3. Create a NotebookLM notebook with those files as sources
4. Print a success message

**Total code: ~200 lines of Python.** If this works, the full app is just UI and polish on top.

---

## 15. Next Steps

1. **Validate the POC** — Build the 200-line proof-of-concept script
2. **Test with your real Zotero library** — Confirm API access and PDF handling
3. **Decide on GUI framework** — PyQt6 (native) vs. Electron (web-based)
4. **Build Phase 1** — Core sync engine
5. **Iterate** — Add features based on your actual usage patterns

---

*Plan created by Voss AI Consulting — February 2026*
