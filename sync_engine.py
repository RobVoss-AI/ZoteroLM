"""
Core sync engine — orchestrates bidirectional sync between Zotero and NotebookLM.
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field

from zotero_client import ZoteroClient, ZoteroCollection, ZoteroItem
from notebooklm_client import NotebookLMClient, NLMNotebook, NLMSourceFull
from state_db import SyncStateDB
from utils import file_hash, file_size_mb
from config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a single sync operation."""
    success: bool
    message: str
    items_synced: int = 0
    items_skipped: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class FullSyncResult:
    """Result of a full bidirectional sync."""
    collections_processed: int = 0
    items_uploaded: int = 0
    items_skipped: int = 0
    notes_synced_back: int = 0
    errors: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Collections processed: {self.collections_processed}",
            f"Items uploaded to NotebookLM: {self.items_uploaded}",
            f"Items skipped (already synced): {self.items_skipped}",
            f"Notes synced back to Zotero: {self.notes_synced_back}",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
        return "\n".join(lines)


class SyncEngine:
    """
    Orchestrates the sync between Zotero and NotebookLM.

    Usage:
        engine = SyncEngine(config)
        result = engine.sync_all(collection_keys=["ABC123", "DEF456"])
    """

    def __init__(self, config: AppConfig,
                 progress_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            config: Application configuration
            progress_callback: Optional function called with status messages
        """
        self.config = config
        self._progress = progress_callback or (lambda msg: None)

        # Initialize clients
        self.zotero = ZoteroClient(
            library_id=config.zotero.library_id,
            api_key=config.zotero.api_key,
            library_type=config.zotero.library_type,
            local_storage_path=config.zotero.local_storage_path,
        )
        self.nlm = NotebookLMClient(
            storage_path=config.notebooklm.storage_path or None,
        )
        self.db = SyncStateDB()

    def _emit(self, msg: str):
        """Emit a progress message."""
        logger.info(msg)
        self._progress(msg)

    def sync_all(self, collection_keys: Optional[List[str]] = None) -> FullSyncResult:
        """
        Run a full bidirectional sync.

        Args:
            collection_keys: Specific Zotero collection keys to sync.
                             If None, syncs all enabled collections from config.
        """
        result = FullSyncResult()

        keys = collection_keys or self.config.sync.enabled_collections
        if not keys:
            result.errors.append("No collections selected for sync")
            return result

        # Get collection details from Zotero
        self._emit("Reading Zotero collections...")
        all_collections = self.zotero.get_collections()
        coll_map = {c.key: c for c in all_collections}

        for key in keys:
            coll = coll_map.get(key)
            if not coll:
                result.errors.append(f"Collection {key} not found in Zotero")
                result.log.append(f"⚠️ Collection {key} not found")
                continue

            self._emit(f"Syncing collection: {coll.name}...")

            # Forward sync: Zotero → NotebookLM
            fwd_result = self._sync_collection_forward(coll)
            result.collections_processed += 1
            result.items_uploaded += fwd_result.items_synced
            result.items_skipped += fwd_result.items_skipped
            result.errors.extend(fwd_result.errors)
            result.log.append(
                f"✅ {coll.name}: {fwd_result.items_synced} uploaded, "
                f"{fwd_result.items_skipped} skipped"
            )

            # Reverse sync: NotebookLM → Zotero (if enabled)
            if self.config.sync.sync_notes_back:
                rev_result = self._sync_collection_reverse(coll)
                result.notes_synced_back += rev_result.items_synced
                result.errors.extend(rev_result.errors)
                if rev_result.items_synced > 0:
                    result.log.append(
                        f"🔄 {coll.name}: {rev_result.items_synced} notes synced back"
                    )

        self.db.log("full_sync", "success" if result.success else "partial",
                    result.summary())
        self._emit("Sync complete!")
        return result

    def _sync_collection_forward(self, collection: ZoteroCollection) -> SyncResult:
        """
        Sync a single collection: Zotero → NotebookLM.

        1. Get/create NotebookLM notebook
        2. Get items with PDFs from Zotero
        3. Upload new PDFs to NotebookLM
        """
        result = SyncResult(success=True, message="")
        errors = []

        try:
            # Step 1: Find or create the NotebookLM notebook
            self._emit(f"  Finding/creating notebook: {collection.name}...")
            notebook = self.nlm.find_or_create_notebook(collection.name)
            self.db.upsert_collection(
                collection.key, collection.name, notebook.id
            )

            # Step 2: Get existing sources in the notebook (to avoid duplicates)
            existing_sources = self.nlm.list_sources(notebook.id)
            existing_titles = {s.title.lower().strip() for s in existing_sources}

            # Step 3: Get items from Zotero
            self._emit(f"  Reading items from {collection.name}...")
            items = self.zotero.get_collection_items(collection.key)

            if not items:
                result.message = f"No items in {collection.name}"
                return result

            # Step 4: Process each item
            download_dir = tempfile.mkdtemp(prefix="citebridge_")

            for item in items:
                try:
                    # Check if already synced
                    if self.db.is_item_synced(item.key, collection.key):
                        result.items_skipped += 1
                        continue

                    # Check if title already exists in notebook
                    if item.title.lower().strip() in existing_titles:
                        self._emit(f"  ⏭️ Already in notebook: {item.title}")
                        self.db.upsert_item(item.key, collection.key, item.title)
                        result.items_skipped += 1
                        continue

                    # Get the PDF
                    pdf_path = self.zotero.get_item_pdf(item.key, download_dir)
                    if not pdf_path:
                        self._emit(f"  ⚠️ No PDF for: {item.title}")
                        # Still record as synced (it's a non-PDF item)
                        self.db.upsert_item(item.key, collection.key, item.title)
                        result.items_skipped += 1
                        continue

                    # Check file size
                    size = file_size_mb(pdf_path)
                    if size > self.config.sync.max_file_size_mb:
                        self._emit(
                            f"  ⚠️ Skipping {item.title} ({size:.1f}MB > "
                            f"{self.config.sync.max_file_size_mb}MB limit)"
                        )
                        result.items_skipped += 1
                        continue

                    # Upload to NotebookLM
                    self._emit(f"  📄 Uploading: {item.title}...")
                    source = self.nlm.add_pdf_source(
                        notebook.id, pdf_path, wait=True
                    )

                    # Record in state DB
                    fhash = file_hash(pdf_path)
                    self.db.upsert_item(
                        item.key, collection.key, item.title,
                        file_hash=fhash, nlm_source_id=source.id,
                    )
                    result.items_synced += 1
                    self._emit(f"  ✅ Uploaded: {item.title}")

                except Exception as e:
                    error_msg = f"Error syncing {item.title}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    self._emit(f"  ❌ {error_msg}")

        except Exception as e:
            error_msg = f"Error syncing collection {collection.name}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            result.success = False

        result.errors = errors
        result.message = (
            f"{collection.name}: {result.items_synced} uploaded, "
            f"{result.items_skipped} skipped"
        )
        return result

    def _sync_collection_reverse(self, collection: ZoteroCollection) -> SyncResult:
        """
        Reverse sync: NotebookLM → Zotero.

        Pulls notes from NotebookLM notebooks and creates
        corresponding notes in Zotero.
        """
        result = SyncResult(success=True, message="")
        errors = []

        try:
            # Get the notebook ID for this collection
            notebook_id = self.db.get_notebook_id_for_collection(collection.key)
            if not notebook_id:
                return result  # No notebook mapped yet

            # Get notes from NotebookLM
            self._emit(f"  Reading NotebookLM notes for {collection.name}...")
            nlm_notes = self.nlm.list_notes(notebook_id)

            if not nlm_notes:
                return result

            # Get Zotero items for matching
            zotero_items = self.zotero.get_collection_items(collection.key)
            # Build a simple lookup by title
            item_by_title = {}
            for item in zotero_items:
                item_by_title[item.title.lower().strip()] = item

            for note in nlm_notes:
                try:
                    # Skip if already synced
                    if self.db.is_nlm_note_synced(note.id):
                        continue

                    # Try to find a matching Zotero item
                    # (simple title matching — could be improved)
                    matched_item = None
                    note_title_lower = note.title.lower().strip()
                    for title, item in item_by_title.items():
                        if title in note_title_lower or note_title_lower in title:
                            matched_item = item
                            break

                    if matched_item:
                        # Create note attached to the matched item
                        zotero_note_key = self.zotero.create_note(
                            matched_item.key,
                            title=f"NotebookLM: {note.title}",
                            content=note.content,
                            tags=["notebooklm-sync", "ai-generated"],
                        )
                        self.db.record_nlm_note_sync(
                            notebook_id, note.id,
                            zotero_item_key=matched_item.key,
                            zotero_note_key=zotero_note_key or "",
                        )
                        result.items_synced += 1
                        self._emit(
                            f"  🔄 Note synced to Zotero: {note.title} "
                            f"→ {matched_item.title}"
                        )
                    else:
                        # Record as synced even without match to avoid retry
                        self.db.record_nlm_note_sync(notebook_id, note.id)
                        self._emit(
                            f"  ⏭️ No Zotero match for note: {note.title}"
                        )

                except Exception as e:
                    error_msg = f"Error syncing note {note.title}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

        except Exception as e:
            error_msg = f"Error in reverse sync for {collection.name}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        result.errors = errors
        return result

    # ══════════════════════════════════════════════════════
    #  SOURCE IMPORT: NotebookLM → Zotero
    #  Pulls the raw source collection into Zotero as items
    # ══════════════════════════════════════════════════════

    def import_notebook_sources(self, notebook_id: str,
                                 notebook_title: str = "",
                                 collection_name: Optional[str] = None,
                                 include_fulltext: bool = True
                                 ) -> SyncResult:
        """
        Import all sources from a NotebookLM notebook into Zotero.

        Creates a Zotero collection matching the notebook name,
        then creates a Zotero library item for each source with:
        - Proper item type (webpage, article, video, etc.)
        - Original URL (when available)
        - Full extracted text as an attached note

        Args:
            notebook_id: NotebookLM notebook ID
            notebook_title: Display name (for the Zotero collection)
            collection_name: Override name for the Zotero collection
            include_fulltext: Whether to fetch and attach full text (slower but more valuable)

        Returns:
            SyncResult with counts of imported items
        """
        result = SyncResult(success=True, message="")
        errors = []
        coll_name = collection_name or notebook_title or "NotebookLM Import"

        try:
            # Step 1: Create or find the Zotero collection
            self._emit(f"📁 Creating Zotero collection: {coll_name}...")
            zotero_coll_key = self.zotero.find_or_create_collection(
                f"NLM: {coll_name}"
            )
            if not zotero_coll_key:
                result.errors.append(f"Failed to create collection '{coll_name}'")
                result.success = False
                return result

            # Step 2: Get sources (with or without fulltext)
            if include_fulltext:
                self._emit(f"📖 Reading sources with full text from {coll_name}...")
                sources = self.nlm.get_all_sources_with_content(notebook_id)
            else:
                self._emit(f"📋 Reading source list from {coll_name}...")
                raw_sources = self.nlm.list_sources(notebook_id)
                sources = [
                    NLMSourceFull(
                        id=s.id, title=s.title,
                        source_type=s.source_type, url=s.url,
                    )
                    for s in raw_sources
                ]

            if not sources:
                result.message = f"No sources found in notebook {coll_name}"
                self._emit(f"  ℹ️ {result.message}")
                return result

            self._emit(f"  Found {len(sources)} sources to import")

            # Step 3: Import each source as a Zotero item
            for src in sources:
                try:
                    # Check if already imported (by title match in collection)
                    existing_items = self.zotero.get_collection_items(zotero_coll_key)
                    already_exists = any(
                        item.title.lower().strip() == src.title.lower().strip()
                        for item in existing_items
                    )
                    if already_exists:
                        self._emit(f"  ⏭️ Already in Zotero: {src.title}")
                        result.items_skipped += 1
                        continue

                    # Create the Zotero item
                    self._emit(f"  📥 Importing: {src.title} [{src.source_type}]")
                    item_key = self.zotero.import_source_as_item(
                        source_type=src.source_type,
                        title=src.title,
                        url=src.url,
                        fulltext=src.content,
                        collection_key=zotero_coll_key,
                        tags=["notebooklm-import", f"nlm:{coll_name}"],
                    )

                    if item_key:
                        result.items_synced += 1
                        self._emit(f"  ✅ Imported: {src.title}")

                        # Record in state DB
                        self.db.upsert_item(
                            zotero_key=item_key,
                            collection_key=zotero_coll_key,
                            title=src.title,
                            nlm_source_id=src.id,
                        )
                    else:
                        errors.append(f"Failed to import: {src.title}")
                        self._emit(f"  ❌ Failed to import: {src.title}")

                except Exception as e:
                    error_msg = f"Error importing {src.title}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    self._emit(f"  ❌ {error_msg}")

            # Record the collection mapping
            self.db.upsert_collection(
                zotero_coll_key, coll_name, notebook_id
            )

        except Exception as e:
            error_msg = f"Error importing notebook {coll_name}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            result.success = False

        result.errors = errors
        result.message = (
            f"Imported {result.items_synced} sources, "
            f"skipped {result.items_skipped}"
        )

        self.db.log(
            "import_sources",
            "success" if result.success else "error",
            result.message,
        )
        return result

    def import_all_notebooks(self, notebook_ids: List[str],
                              include_fulltext: bool = True
                              ) -> FullSyncResult:
        """
        Import sources from multiple NotebookLM notebooks into Zotero.
        Each notebook becomes a Zotero collection.
        """
        result = FullSyncResult()

        # Get notebook details
        all_notebooks = self.nlm.list_notebooks()
        nb_map = {nb.id: nb for nb in all_notebooks}

        for nb_id in notebook_ids:
            nb = nb_map.get(nb_id)
            title = nb.title if nb else nb_id

            self._emit(f"📓 Importing notebook: {title}...")
            import_result = self.import_notebook_sources(
                nb_id, title,
                include_fulltext=include_fulltext,
            )

            result.collections_processed += 1
            result.items_uploaded += import_result.items_synced
            result.items_skipped += import_result.items_skipped
            result.errors.extend(import_result.errors)
            result.log.append(
                f"{'✅' if import_result.success else '❌'} {title}: "
                f"{import_result.message}"
            )

        self._emit("Import complete!")
        return result

    # ══════════════════════════════════════════════════════

    def test_connections(self) -> Dict[str, bool]:
        """Test connections to both services."""
        results = {}

        self._emit("Testing Zotero connection...")
        results["zotero"] = self.zotero.test_connection()
        self._emit(
            "  ✅ Zotero connected" if results["zotero"]
            else "  ❌ Zotero connection failed"
        )

        self._emit("Testing NotebookLM connection...")
        results["notebooklm"] = self.nlm.test_connection()
        self._emit(
            "  ✅ NotebookLM connected" if results["notebooklm"]
            else "  ❌ NotebookLM connection failed"
        )

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get sync statistics."""
        return self.db.get_sync_stats()
