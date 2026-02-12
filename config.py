"""
Configuration management for CiteBridge.
Handles loading/saving settings and credentials.
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path.home() / ".citebridge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DB_FILE = CONFIG_DIR / "sync_state.db"


@dataclass
class ZoteroConfig:
    api_key: str = ""
    library_id: str = ""
    library_type: str = "user"  # "user" or "group"
    local_storage_path: str = ""  # Path to Zotero/storage/ directory


@dataclass
class NotebookLMConfig:
    storage_path: str = ""  # Path to notebooklm storage_state.json
    authenticated: bool = False


@dataclass
class SyncConfig:
    enabled_collections: List[str] = field(default_factory=list)
    auto_sync_interval_minutes: int = 0  # 0 = disabled
    sync_notes_back: bool = True  # Reverse sync NLM notes → Zotero
    max_file_size_mb: int = 200  # Skip files larger than this


@dataclass
class AppConfig:
    zotero: ZoteroConfig = field(default_factory=ZoteroConfig)
    notebooklm: NotebookLMConfig = field(default_factory=NotebookLMConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    def save(self):
        """Save config to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
        logger.info(f"Config saved to {CONFIG_FILE}")

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from disk, or return defaults."""
        if not CONFIG_FILE.exists():
            logger.info("No config file found, using defaults")
            return cls()
        try:
            with open(CONFIG_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
            config = cls(
                zotero=ZoteroConfig(**data.get("zotero", {})),
                notebooklm=NotebookLMConfig(**data.get("notebooklm", {})),
                sync=SyncConfig(**data.get("sync", {})),
            )
            logger.info(f"Config loaded from {CONFIG_FILE}")
            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return cls()

    def is_zotero_configured(self) -> bool:
        return bool(self.zotero.api_key and self.zotero.library_id)

    def is_notebooklm_configured(self) -> bool:
        """Check if NotebookLM auth tokens exist on disk."""
        from notebooklm.auth import get_storage_path
        storage = Path(self.notebooklm.storage_path) if self.notebooklm.storage_path else get_storage_path()
        return storage.exists()
