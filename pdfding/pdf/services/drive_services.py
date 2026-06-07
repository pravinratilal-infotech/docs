"""Google Drive helpers for listing shared folder hierarchies."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from pdf.drive.google_drive_connector import (
    DriveConnectionError,
    DriveTreeNode,
    GoogleDriveConnector,
    count_tree_items,
)


def get_key_file() -> Path:
    key_file = Path(getattr(settings, "GOOGLE_DRIVE_KEY_FILE", "") or "")
    if not key_file.is_file():
        raise DriveConnectionError(f"Service account key not found: {key_file}")
    return key_file


def get_optional_folder_id() -> str | None:
    folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "") or ""
    return folder_id or None


def get_connector() -> GoogleDriveConnector:
    return GoogleDriveConnector(get_key_file())


def list_shared_tree() -> tuple[list[DriveTreeNode], int, int]:
    """
    Return the shared Drive hierarchy and item counts.

    Discovers all folders shared with the service account unless
    GOOGLE_DRIVE_FOLDER_ID is set (optional scope to one subtree).
    """
    connector = get_connector()
    tree = connector.list_shared_hierarchy(root_folder_id=get_optional_folder_id())
    folder_count, file_count = count_tree_items(tree)
    return tree, folder_count, file_count
