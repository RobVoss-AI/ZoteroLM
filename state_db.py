"""
SQLite-based sync state manager.
Tracks what has been synced between Zotero and NotebookLM
to avoid duplicates and detect changes.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncedCollection:
    id: int
    zotero_key: str
    zotero_name: str
    nlm_notebook_id: str
    last_synced: str


@dataclass
class SyncedItem:
    id: int
    zotero_key: str
    collection_zotero_key: str
    title: str
    file_hash: str
    nlm_source_id: str
    last_synced: str


@dataclass
class SyncLogEntry:
    timestamp: str
    action: str
    status: str
    details: str


class SyncStateDB:
    """Manages sync state in a local SQLite database."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            from config import DB_FILE
            db_path = str(DB_FILE)

        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS synced_collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zotero_key TEXT UNIQUE NOT NULL,
                    zotero_name TEXT NOT NULL,
                    nlm_notebook_id TEXT,
                    last_synced TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS synced_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zotero_key TEXT NOT NULL,
                    collection_zotero_key TEXT NOT NULL,
                    title TEXT,
                    file_hash TEXT,
                    nlm_source_id TEXT,
                    last_synced TIMESTAMP,
                    UNIQUE(zotero_key, collection_zotero_key)
                );

                CREATE TABLE IF NOT EXISTS nlm_notes_synced (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nlm_notebook_id TEXT NOT NULL,
                    nlm_note_id TEXT NOT NULL,
                    zotero_item_key TEXT,
                    zotero_note_key TEXT,
                    synced_at TIMESTAMP,
                    UNIQUE(nlm_note_id)
                );

                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT
                );
            """)
        logger.info(f"Sync state DB initialized at {self.db_path}")

    # ── Collection tracking ──

    def upsert_collection(self, zotero_key: str, zotero_name: str,
                          nlm_notebook_id: str = ""):
        """Insert or update a synced collection."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO synced_collections (zotero_key, zotero_name, nlm_notebook_id, last_synced)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(zotero_key) DO UPDATE SET
                    zotero_name = excluded.zotero_name,
                    nlm_notebook_id = COALESCE(NULLIF(excluded.nlm_notebook_id, ''), nlm_notebook_id),
                    last_synced = excluded.last_synced
            """, (zotero_key, zotero_name, nlm_notebook_id, now))

    def get_collection(self, zotero_key: str) -> Optional[SyncedCollection]:
        """Get a synced collection by Zotero key."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, zotero_key, zotero_name, nlm_notebook_id, last_synced "
                "FROM synced_collections WHERE zotero_key = ?",
                (zotero_key,)
            ).fetchone()
            if row:
                return SyncedCollection(*row)
        return None

    def get_notebook_id_for_collection(self, zotero_key: str) -> Optional[str]:
        """Get the NotebookLM notebook ID for a Zotero collection."""
        coll = self.get_collection(zotero_key)
        return coll.nlm_notebook_id if coll else None

    # ── Item tracking ──

    def is_item_synced(self, zotero_key: str, collection_key: str,
                       file_hash: str = "") -> bool:
        """Check if an item has already been synced (and hasn't changed)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT file_hash FROM synced_items "
                "WHERE zotero_key = ? AND collection_zotero_key = ?",
                (zotero_key, collection_key)
            ).fetchone()
            if row is None:
                return False
            # If we have a hash, check if the file changed
            if file_hash and row[0] and row[0] != file_hash:
                return False
            return True

    def upsert_item(self, zotero_key: str, collection_key: str,
                    title: str, file_hash: str = "",
                    nlm_source_id: str = ""):
        """Insert or update a synced item."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO synced_items
                    (zotero_key, collection_zotero_key, title, file_hash, nlm_source_id, last_synced)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(zotero_key, collection_zotero_key) DO UPDATE SET
                    title = excluded.title,
                    file_hash = COALESCE(NULLIF(excluded.file_hash, ''), file_hash),
                    nlm_source_id = COALESCE(NULLIF(excluded.nlm_source_id, ''), nlm_source_id),
                    last_synced = excluded.last_synced
            """, (zotero_key, collection_key, title, file_hash, nlm_source_id, now))

    def get_synced_items_for_collection(self, collection_key: str) -> List[SyncedItem]:
        """Get all synced items for a collection."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, zotero_key, collection_zotero_key, title, "
                "file_hash, nlm_source_id, last_synced "
                "FROM synced_items WHERE collection_zotero_key = ?",
                (collection_key,)
            ).fetchall()
            return [SyncedItem(*r) for r in rows]

    # ── NLM note tracking (reverse sync) ──

    def is_nlm_note_synced(self, nlm_note_id: str) -> bool:
        """Check if a NotebookLM note has been synced to Zotero."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM nlm_notes_synced WHERE nlm_note_id = ?",
                (nlm_note_id,)
            ).fetchone()
            return row is not None

    def record_nlm_note_sync(self, nlm_notebook_id: str, nlm_note_id: str,
                              zotero_item_key: str = "",
                              zotero_note_key: str = ""):
        """Record that a NotebookLM note has been synced to Zotero."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO nlm_notes_synced
                    (nlm_notebook_id, nlm_note_id, zotero_item_key, zotero_note_key, synced_at)
                VALUES (?, ?, ?, ?, ?)
            """, (nlm_notebook_id, nlm_note_id, zotero_item_key, zotero_note_key, now))

    # ── Sync log ──

    def log(self, action: str, status: str, details: str = ""):
        """Add an entry to the sync log."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sync_log (action, status, details) VALUES (?, ?, ?)",
                (action, status, details)
            )

    def get_recent_logs(self, limit: int = 50) -> List[SyncLogEntry]:
        """Get recent sync log entries."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT timestamp, action, status, details "
                "FROM sync_log ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [SyncLogEntry(*r) for r in rows]

    def get_sync_stats(self) -> Dict[str, Any]:
        """Get summary statistics about sync state."""
        with sqlite3.connect(self.db_path) as conn:
            collections = conn.execute(
                "SELECT COUNT(*) FROM synced_collections"
            ).fetchone()[0]
            items = conn.execute(
                "SELECT COUNT(*) FROM synced_items"
            ).fetchone()[0]
            notes = conn.execute(
                "SELECT COUNT(*) FROM nlm_notes_synced"
            ).fetchone()[0]
            last_sync = conn.execute(
                "SELECT MAX(last_synced) FROM synced_items"
            ).fetchone()[0]

        return {
            "collections_synced": collections,
            "items_synced": items,
            "notes_synced_back": notes,
            "last_sync": last_sync or "Never",
        }
