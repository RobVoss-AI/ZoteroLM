"""
Zotero API client — wraps pyzotero for reading collections,
items, and PDFs from a user's Zotero library.
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from pyzotero import zotero

logger = logging.getLogger(__name__)


@dataclass
class ZoteroItem:
    """Represents a single Zotero library item (paper, book, etc.)."""
    key: str
    title: str
    item_type: str
    creators: List[Dict[str, str]] = field(default_factory=list)
    date: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    tags: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    pdf_path: Optional[str] = None  # Local path to PDF if available
    pdf_key: Optional[str] = None   # Zotero key for the PDF attachment


@dataclass
class ZoteroCollection:
    """Represents a Zotero collection (folder)."""
    key: str
    name: str
    parent_key: Optional[str] = None
    num_items: int = 0


class ZoteroClient:
    """High-level client for interacting with a Zotero library."""

    def __init__(self, library_id: str, api_key: str,
                 library_type: str = "user",
                 local_storage_path: str = ""):
        """
        Initialize the Zotero client.

        Args:
            library_id: Your Zotero user ID (find at zotero.org/settings/keys)
            api_key: Your Zotero API key
            library_type: "user" or "group"
            local_storage_path: Optional path to Zotero/storage/ for direct PDF access
        """
        self.library_id = library_id
        self.api_key = api_key
        self.library_type = library_type
        self.local_storage_path = local_storage_path

        self.zot = zotero.Zotero(library_id, library_type, api_key)
        logger.info(f"ZoteroClient initialized for {library_type} library {library_id}")

    def test_connection(self) -> bool:
        """Test if the API connection works."""
        try:
            self.zot.collections(limit=1)
            return True
        except Exception as e:
            logger.error(f"Zotero connection test failed: {e}")
            return False

    def get_collections(self) -> List[ZoteroCollection]:
        """Get all collections in the library."""
        try:
            raw_collections = self.zot.collections()
            collections = []
            for c in raw_collections:
                data = c.get("data", c)
                collections.append(ZoteroCollection(
                    key=data.get("key", ""),
                    name=data.get("name", "Untitled"),
                    parent_key=data.get("parentCollection", None) or None,
                    num_items=data.get("meta", {}).get("numItems", 0)
                        if "meta" in c else 0,
                ))
            logger.info(f"Found {len(collections)} collections")
            return collections
        except Exception as e:
            logger.error(f"Failed to get collections: {e}")
            return []

    def get_collection_items(self, collection_key: str) -> List[ZoteroItem]:
        """
        Get all items in a specific collection.
        Returns only top-level items (not attachments).
        """
        try:
            raw_items = self.zot.collection_items(collection_key)
            items = []
            for item in raw_items:
                data = item.get("data", item)
                # Skip attachments and notes at top level
                if data.get("itemType") in ("attachment", "note"):
                    continue

                z_item = ZoteroItem(
                    key=data.get("key", ""),
                    title=data.get("title", "Untitled"),
                    item_type=data.get("itemType", ""),
                    creators=data.get("creators", []),
                    date=data.get("date", ""),
                    doi=data.get("DOI", ""),
                    url=data.get("url", ""),
                    abstract=data.get("abstractNote", ""),
                    tags=[t.get("tag", "") for t in data.get("tags", [])],
                    collections=data.get("collections", []),
                )
                items.append(z_item)

            logger.info(f"Found {len(items)} items in collection {collection_key}")
            return items
        except Exception as e:
            logger.error(f"Failed to get items for collection {collection_key}: {e}")
            return []

    def get_item_pdf(self, item_key: str, download_dir: Optional[str] = None) -> Optional[str]:
        """
        Get the PDF for a library item.

        First tries local storage (fast), then falls back to API download.
        Returns the local file path to the PDF, or None if no PDF found.
        """
        try:
            # Get children (attachments) of this item
            children = self.zot.children(item_key)

            pdf_attachment = None
            for child in children:
                data = child.get("data", child)
                content_type = data.get("contentType", "")
                if content_type == "application/pdf":
                    pdf_attachment = data
                    break

            if not pdf_attachment:
                logger.debug(f"No PDF attachment found for item {item_key}")
                return None

            attachment_key = pdf_attachment.get("key", "")
            filename = pdf_attachment.get("filename", f"{attachment_key}.pdf")

            # Strategy 1: Try local Zotero storage
            if self.local_storage_path:
                local_pdf = self._find_local_pdf(attachment_key, filename)
                if local_pdf:
                    return local_pdf

            # Strategy 2: Download via API
            return self._download_pdf(attachment_key, filename, download_dir)

        except Exception as e:
            logger.error(f"Failed to get PDF for item {item_key}: {e}")
            return None

    def _find_local_pdf(self, attachment_key: str, filename: str) -> Optional[str]:
        """Look for PDF in Zotero's local storage directory."""
        storage = Path(self.local_storage_path)
        if not storage.exists():
            return None

        # Zotero stores files as: storage/{ATTACHMENT_KEY}/{filename}
        pdf_dir = storage / attachment_key
        if pdf_dir.exists():
            for f in pdf_dir.iterdir():
                if f.suffix.lower() == ".pdf":
                    logger.debug(f"Found local PDF: {f}")
                    return str(f)
        return None

    def _download_pdf(self, attachment_key: str, filename: str,
                      download_dir: Optional[str] = None) -> Optional[str]:
        """Download PDF via Zotero API."""
        try:
            if not download_dir:
                download_dir = tempfile.mkdtemp(prefix="citebridge_")

            dest = Path(download_dir) / filename
            # pyzotero's file() method returns the binary content
            pdf_content = self.zot.file(attachment_key)
            with open(dest, "wb") as f:
                f.write(pdf_content)

            logger.info(f"Downloaded PDF to {dest}")
            return str(dest)
        except Exception as e:
            logger.error(f"Failed to download PDF {attachment_key}: {e}")
            return None

    def get_item_pdfs_for_collection(self, collection_key: str,
                                      download_dir: Optional[str] = None
                                      ) -> List[Dict[str, Any]]:
        """
        Get all items with their PDFs for a given collection.
        Returns list of dicts with item info and pdf_path.
        """
        items = self.get_collection_items(collection_key)
        results = []

        for item in items:
            pdf_path = self.get_item_pdf(item.key, download_dir)
            results.append({
                "item": item,
                "pdf_path": pdf_path,
                "has_pdf": pdf_path is not None,
            })

        with_pdf = sum(1 for r in results if r["has_pdf"])
        logger.info(
            f"Collection {collection_key}: {with_pdf}/{len(results)} items have PDFs"
        )
        return results

    def create_note(self, parent_item_key: str, title: str, content: str,
                    tags: Optional[List[str]] = None) -> Optional[str]:
        """
        Create a note attached to a Zotero item.
        Used for syncing NotebookLM notes back to Zotero.

        Returns the key of the created note, or None on failure.
        """
        try:
            note_template = self.zot.item_template("note")
            note_template["note"] = f"<h2>{title}</h2>\n{content}"
            note_template["tags"] = [{"tag": t} for t in (tags or ["notebooklm-sync"])]

            result = self.zot.create_items([note_template], parentid=parent_item_key)
            if result and "successful" in result:
                created = result["successful"]
                if created:
                    key = list(created.values())[0].get("data", {}).get("key", "")
                    logger.info(f"Created note {key} under item {parent_item_key}")
                    return key
            return None
        except Exception as e:
            logger.error(f"Failed to create note for item {parent_item_key}: {e}")
            return None

    # ── Source Import (NotebookLM → Zotero) ──

    def create_collection(self, name: str,
                          parent_key: Optional[str] = None) -> Optional[str]:
        """
        Create a new Zotero collection.
        Returns the collection key, or None on failure.
        """
        try:
            payload = [{"name": name}]
            if parent_key:
                payload[0]["parentCollection"] = parent_key

            result = self.zot.create_collections(payload)
            if result and "successful" in result:
                created = result["successful"]
                if created:
                    key = list(created.values())[0].get("data", {}).get("key", "")
                    logger.info(f"Created collection '{name}' ({key})")
                    return key
            return None
        except Exception as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            return None

    def find_collection_by_name(self, name: str) -> Optional[str]:
        """Find a collection by name. Returns key or None."""
        collections = self.get_collections()
        for c in collections:
            if c.name == name:
                return c.key
        return None

    def find_or_create_collection(self, name: str) -> Optional[str]:
        """Find existing collection by name, or create a new one."""
        key = self.find_collection_by_name(name)
        if key:
            logger.info(f"Found existing collection: {name}")
            return key
        return self.create_collection(name)

    def import_source_as_item(self, source_type: str, title: str,
                               url: Optional[str] = None,
                               fulltext: str = "",
                               collection_key: Optional[str] = None,
                               tags: Optional[List[str]] = None
                               ) -> Optional[str]:
        """
        Create a Zotero library item from a NotebookLM source.

        Determines the appropriate Zotero item type based on the NLM source type,
        creates the item, attaches the fulltext as a child note, and adds it to
        the specified collection.

        Args:
            source_type: NLM source type (e.g., 'pdf', 'web_page', 'youtube')
            title: Source title
            url: Original URL (if available)
            fulltext: Full extracted text from NotebookLM
            collection_key: Zotero collection to add the item to
            tags: Tags to apply

        Returns:
            The Zotero item key, or None on failure.
        """
        try:
            # Map NLM source types to Zotero item types
            zotero_type = self._nlm_type_to_zotero_type(source_type)
            template = self.zot.item_template(zotero_type)

            # Set common fields
            template["title"] = title
            template["tags"] = [
                {"tag": t} for t in (tags or ["notebooklm-import", "nlm-source"])
            ]
            if collection_key:
                template["collections"] = [collection_key]

            # Set type-specific fields
            if url:
                template["url"] = url

            if zotero_type == "webpage":
                template["websiteTitle"] = "NotebookLM Source"
                if url:
                    template["url"] = url
            elif zotero_type == "videoRecording":
                template["videoRecordingFormat"] = "YouTube"
                if url:
                    template["url"] = url
            elif zotero_type == "document":
                template["publisher"] = "NotebookLM Import"
            elif zotero_type == "journalArticle":
                # For PDFs, try to extract basic metadata from title
                pass

            # Create the item
            result = self.zot.create_items([template])
            if not result or "successful" not in result:
                logger.error(f"Failed to create item for '{title}'")
                return None

            created = result["successful"]
            if not created:
                return None

            item_key = list(created.values())[0].get("data", {}).get("key", "")
            logger.info(f"Created Zotero item: {title} ({item_key}) [{zotero_type}]")

            # Attach the fulltext as a child note (this is the real value)
            if fulltext:
                # Truncate very long content for Zotero note (limit ~1MB)
                max_chars = 500_000
                text = fulltext[:max_chars]
                if len(fulltext) > max_chars:
                    text += f"\n\n[...truncated, {len(fulltext):,} chars total]"

                self.create_note(
                    item_key,
                    title=f"Full Text (from NotebookLM)",
                    content=f"<pre>{self._escape_html(text)}</pre>",
                    tags=["nlm-fulltext"],
                )
                logger.info(f"  Attached fulltext ({len(fulltext):,} chars) to {item_key}")

            return item_key

        except Exception as e:
            logger.error(f"Failed to import source '{title}': {e}")
            return None

    @staticmethod
    def _nlm_type_to_zotero_type(source_type: str) -> str:
        """Map NotebookLM source types to Zotero item types."""
        mapping = {
            "web_page": "webpage",
            "pdf": "journalArticle",
            "youtube": "videoRecording",
            "google_docs": "document",
            "google_slides": "presentation",
            "google_spreadsheet": "document",
            "google_drive_audio": "audioRecording",
            "google_drive_video": "videoRecording",
            "csv": "document",
            "docx": "document",
            "markdown": "document",
            "pasted_text": "document",
            "image": "artwork",
        }
        return mapping.get(source_type, "document")

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters for Zotero note content."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
