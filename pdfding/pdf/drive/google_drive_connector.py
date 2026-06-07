"""Thin Google Drive API v3 wrapper (service account)."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests
from django.utils.dateparse import parse_datetime
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

_DRIVE_FILE_FIELDS = (
    "id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink, iconLink"
)

PDF_MIME = "application/pdf"
FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


@dataclass(frozen=True)
class DriveFileInfo:
    id: str
    name: str
    mime_type: str
    size: int | None
    modified_at: datetime | None
    web_view_link: str | None
    thumbnail_link: str | None = None


@dataclass
class DriveTreeNode:
    id: str
    name: str
    mime_type: str
    is_folder: bool
    size: int | None = None
    modified_at: datetime | None = None
    web_view_link: str | None = None
    thumbnail_link: str | None = None
    imported_pdf_id: str | None = None
    docling_status: str | None = None
    enrichment_status: str | None = None
    children: list[DriveTreeNode] = field(default_factory=list)


class GoogleDriveConnector:
    def __init__(self, key_file: Path):
        creds = service_account.Credentials.from_service_account_file(str(key_file), scopes=SCOPES)
        self.service_account_email = creds.service_account_email
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def get_folder(self, folder_id: str) -> dict:
        return (
            self._service.files()
            .get(
                fileId=folder_id,
                fields="id, name, mimeType, driveId",
                supportsAllDrives=True,
            )
            .execute()
        )

    def get_file(self, file_id: str) -> DriveFileInfo:
        item = (
            self._service.files()
            .get(
                fileId=file_id,
                fields=_DRIVE_FILE_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )
        return self._to_drive_file_info(item)

    def fetch_thumbnail(self, file_id: str) -> tuple[bytes, str] | None:
        """Download thumbnail bytes using service account credentials."""
        item = (
            self._service.files()
            .get(
                fileId=file_id,
                fields="thumbnailLink, iconLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        url = item.get("thumbnailLink") or item.get("iconLink")
        if not url:
            return None

        creds = self._service._http.credentials
        if not creds.valid:
            creds.refresh(GoogleAuthRequest())

        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            content_type = resp.headers.get("Content-Type", "image/png")
            return resp.content, content_type
        except requests.RequestException as exc:
            logger.debug("Drive thumbnail fetch failed for %s: %s", file_id, exc)
            return None

    def download_file(self, file_id: str) -> tuple[bytes, DriveFileInfo]:
        """Download a Drive file. Only PDFs are supported for import."""
        info = self.get_file(file_id)
        if info.mime_type != PDF_MIME:
            raise DriveConnectionError(
                f'"{info.name}" is not a PDF (type: {info.mime_type}).'
            )

        request = self._service.files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        return buffer.getvalue(), info

    def list_pdfs_in_folder(self, folder_id: str) -> list[DriveFileInfo]:
        """Recursively list all PDF files under a folder."""
        pdfs: list[DriveFileInfo] = []
        for entry in self.list_folder(folder_id):
            if entry.mime_type == FOLDER_MIME:
                pdfs.extend(self.list_pdfs_in_folder(entry.id))
            elif entry.mime_type == PDF_MIME:
                pdfs.append(entry)
        return pdfs

    def list_folder(self, folder_id: str, *, pdf_only: bool = False) -> list[DriveFileInfo]:
        query_parts = [f"'{folder_id}' in parents", "trashed = false"]
        if pdf_only:
            query_parts.append(f"mimeType = '{PDF_MIME}'")

        return self._list_files(" and ".join(query_parts))

    def list_shared_hierarchy(self, *, root_folder_id: str | None = None) -> list[DriveTreeNode]:
        """
        Build a folder/file tree from everything shared with the service account.

        When root_folder_id is set, only that folder subtree is returned (optional scope).
        Otherwise discovers shared-with-me items and shared-drive roots automatically.
        """
        if root_folder_id:
            folder_meta = verify_folder(self, root_folder_id)
            return [self._build_subtree(root_folder_id, folder_meta.get("name", ""), set())]

        forest: list[DriveTreeNode] = []
        seen_roots: set[str] = set()

        for root in self._collect_shared_roots():
            if root.id in seen_roots:
                continue
            seen_roots.add(root.id)

            if root.mime_type == FOLDER_MIME:
                forest.append(self._build_subtree(root.id, root.name, set()))
            else:
                forest.append(
                    DriveTreeNode(
                        id=root.id,
                        name=root.name,
                        mime_type=root.mime_type,
                        is_folder=False,
                        size=root.size,
                        modified_at=root.modified_at,
                        web_view_link=root.web_view_link,
                        thumbnail_link=root.thumbnail_link,
                    )
                )

        forest.sort(key=lambda node: (not node.is_folder, node.name.lower()))
        return forest

    def _collect_shared_roots(self) -> list[DriveFileInfo]:
        """Top-level folders/files shared with the service account."""
        roots = self._list_files("sharedWithMe = true and trashed = false")
        roots_by_id = {item.id: item for item in roots}

        for drive in self._list_shared_drives():
            drive_id = drive["id"]
            if drive_id not in roots_by_id:
                roots_by_id[drive_id] = DriveFileInfo(
                    id=drive_id,
                    name=drive.get("name", "Shared drive"),
                    mime_type=FOLDER_MIME,
                    size=None,
                    modified_at=None,
                    web_view_link=None,
                )

        return list(roots_by_id.values())

    def _list_shared_drives(self) -> list[dict]:
        drives: list[dict] = []
        page_token = None

        while True:
            response = (
                self._service.drives()
                .list(pageSize=100, pageToken=page_token)
                .execute()
            )
            drives.extend(response.get("drives", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return drives

    def _list_files(self, query: str) -> list[DriveFileInfo]:
        files: list[DriveFileInfo] = []
        page_token = None

        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    fields=f"nextPageToken, files({_DRIVE_FILE_FIELDS})",
                    pageSize=100,
                    pageToken=page_token,
                    orderBy="folder,name",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files", []):
                files.append(self._to_drive_file_info(item))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files

    def _build_subtree(self, folder_id: str, name: str, visited: set[str]) -> DriveTreeNode:
        if folder_id in visited:
            return DriveTreeNode(
                id=folder_id,
                name=name,
                mime_type=FOLDER_MIME,
                is_folder=True,
            )

        visited = visited | {folder_id}
        children: list[DriveTreeNode] = []

        for entry in self.list_folder(folder_id):
            if entry.mime_type == FOLDER_MIME:
                children.append(self._build_subtree(entry.id, entry.name, visited))
            else:
                children.append(
                    DriveTreeNode(
                        id=entry.id,
                        name=entry.name,
                        mime_type=entry.mime_type,
                        is_folder=False,
                        size=entry.size,
                        modified_at=entry.modified_at,
                        web_view_link=entry.web_view_link,
                        thumbnail_link=entry.thumbnail_link,
                    )
                )

        children.sort(key=lambda node: (not node.is_folder, node.name.lower()))
        return DriveTreeNode(
            id=folder_id,
            name=name,
            mime_type=FOLDER_MIME,
            is_folder=True,
            children=children,
        )

    @staticmethod
    def _to_drive_file_info(item: dict) -> DriveFileInfo:
        modified_raw = item.get("modifiedTime")
        modified_at = parse_datetime(modified_raw.replace("Z", "+00:00")) if modified_raw else None
        size_raw = item.get("size")
        return DriveFileInfo(
            id=item["id"],
            name=item.get("name", ""),
            mime_type=item.get("mimeType", ""),
            size=int(size_raw) if size_raw else None,
            modified_at=modified_at,
            web_view_link=item.get("webViewLink"),
            thumbnail_link=item.get("thumbnailLink"),
        )


class DriveConnectionError(Exception):
    """Raised when Drive is misconfigured or unreachable."""


def folder_not_found_message(service_account_email: str) -> str:
    return (
        f"Folder not found or not shared with {service_account_email}. "
        "Share the folder in Google Drive with that email as Editor."
    )


def verify_folder(connector: GoogleDriveConnector, folder_id: str) -> dict:
    try:
        return connector.get_folder(folder_id)
    except HttpError as exc:
        if exc.resp.status == 404:
            raise DriveConnectionError(folder_not_found_message(connector.service_account_email)) from exc
        raise DriveConnectionError(str(exc)) from exc


def count_tree_items(nodes: list[DriveTreeNode]) -> tuple[int, int]:
    """Return (folder_count, file_count) for a forest of tree nodes."""
    folders = 0
    files = 0
    for node in nodes:
        if node.is_folder:
            folders += 1
            child_folders, child_files = count_tree_items(node.children)
            folders += child_folders
            files += child_files
        else:
            files += 1
    return folders, files
