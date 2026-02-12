"""
Utility functions for CiteBridge.
"""

import hashlib
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file for change detection."""
    sha = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception as e:
        logger.error(f"Failed to hash file {filepath}: {e}")
        return ""


def file_size_mb(filepath: str) -> float:
    """Get file size in megabytes."""
    try:
        return Path(filepath).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def setup_logging(level: int = logging.INFO):
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_zotero_storage_path() -> str:
    """
    Try to auto-detect the Zotero storage directory.
    Returns empty string if not found.
    """
    candidates = []

    if sys.platform == "darwin":
        candidates = [
            Path.home() / "Zotero" / "storage",
            Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles",
        ]
    elif sys.platform == "win32":
        candidates = [
            Path.home() / "Zotero" / "storage",
            Path(r"C:\Users") / Path.home().name / "Zotero" / "storage",
        ]
    else:  # Linux
        candidates = [
            Path.home() / "Zotero" / "storage",
            Path.home() / ".zotero" / "zotero" / "storage",
            Path.home() / "snap" / "zotero-snap" / "common" / "Zotero" / "storage",
        ]

    for path in candidates:
        if path.exists():
            logger.info(f"Auto-detected Zotero storage: {path}")
            return str(path)

    return ""


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, "_")
    return name.strip()
