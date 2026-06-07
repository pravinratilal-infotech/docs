"""Import PDFs from Google Drive into PdfDing and queue Docling + enrichment."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from django.core.files import File
from pdf.drive.google_drive_connector import DriveConnectionError, DriveFileInfo, PDF_MIME
from pdf.models.collection_models import Collection
from pdf.models.pdf_models import Pdf
from pdf.services import drive_services
from pdf.services.pdf_services import PdfProcessingServices, create_name_from_file
from users.models import Profile

logger = logging.getLogger(__name__)

GDRIVE_SOURCE = "gdrive"


def _import_collection(profile: Profile) -> Collection:
    """Collection to store imported PDFs (handles 'all' collection view)."""
    if profile.current_collection_id == "all":
        workspace = profile.current_workspace
        default = workspace.collections.filter(name__iexact="default").first()
        return default or workspace.collections.first()
    return profile.current_collection


@dataclass
class DriveImportResult:
    status: str
    pdf: Pdf | None
    message: str


@dataclass
class DriveBulkImportResult:
    imported: int
    skipped: int
    failed: int
    messages: list[str]
    last_pdf: Pdf | None


def annotate_imported_pdfs(nodes, imported_map: dict[str, str]) -> None:
    """Mark tree nodes that already exist as imported PdfDing PDFs."""
    for node in nodes:
        if not node.is_folder:
            node.imported_pdf_id = imported_map.get(node.id)
        if node.children:
            annotate_imported_pdfs(node.children, imported_map)


def get_imported_gdrive_map(workspace) -> dict[str, str]:
    """Map GDrive file IDs to PdfDing PDF UUIDs for a workspace."""
    return {
        pdf.external_id: str(pdf.id)
        for pdf in Pdf.objects.filter(
            collection__workspace=workspace,
            external_source=GDRIVE_SOURCE,
        ).exclude(external_id="")
    }


def find_existing_gdrive_pdf(workspace, file_id: str) -> Pdf | None:
    return Pdf.objects.filter(
        collection__workspace=workspace,
        external_source=GDRIVE_SOURCE,
        external_id=file_id,
    ).first()


def _is_up_to_date(existing: Pdf, info: DriveFileInfo) -> bool:
    if not existing.external_modified_at or not info.modified_at:
        return True
    return existing.external_modified_at >= info.modified_at


def _save_external_metadata(pdf: Pdf, info: DriveFileInfo) -> None:
    pdf.external_source = GDRIVE_SOURCE
    pdf.external_id = info.id
    pdf.external_modified_at = info.modified_at
    pdf.external_url = info.web_view_link or ""
    pdf.save(update_fields=[
        "external_source",
        "external_id",
        "external_modified_at",
        "external_url",
    ])


def import_gdrive_file(
    profile: Profile,
    file_id: str,
    *,
    folder_path: str = "",
    force: bool = False,
) -> DriveImportResult:
    """
    Download a GDrive PDF, save as PdfDing PDF, and auto-queue Docling.

    Skips if the file was already imported and Drive has not changed.
    """
    workspace = profile.current_workspace
    collection = _import_collection(profile)
    connector = drive_services.get_connector()

    try:
        info = connector.get_file(file_id)
    except DriveConnectionError as exc:
        return DriveImportResult("failed", None, str(exc))

    if info.mime_type != PDF_MIME:
        return DriveImportResult(
            "failed",
            None,
            f'"{info.name}" is not a PDF and cannot be imported.',
        )

    existing = find_existing_gdrive_pdf(workspace, file_id)
    if existing and not force:
        if _is_up_to_date(existing, info):
            return DriveImportResult(
                "skipped",
                existing,
                f'"{existing.name}" is already imported and up to date.',
            )
        force = True

    if existing and force:
        existing.delete()

    try:
        data, info = connector.download_file(file_id)
    except DriveConnectionError as exc:
        return DriveImportResult("failed", None, str(exc))

    pdf_file = File(BytesIO(data), name=info.name)
    name = create_name_from_file(pdf_file)

    pdf = PdfProcessingServices.create_pdf(
        name=name,
        collection=collection,
        pdf_file=pdf_file,
        file_directory=folder_path,
    )
    _save_external_metadata(pdf, info)

    logger.info(
        "Imported GDrive file %s as PDF %s (%s)",
        file_id,
        pdf.id,
        pdf.name,
    )
    return DriveImportResult(
        "imported",
        pdf,
        f'Imported "{pdf.name}" from Google Drive. Docling processing has been queued.',
    )


def import_gdrive_folder(
    profile: Profile,
    folder_id: str,
    *,
    force: bool = False,
) -> DriveBulkImportResult:
    """Import all PDFs in a GDrive folder (recursive)."""
    connector = drive_services.get_connector()

    try:
        pdfs = connector.list_pdfs_in_folder(folder_id)
    except DriveConnectionError as exc:
        return DriveBulkImportResult(0, 0, 1, [str(exc)], None)

    if not pdfs:
        return DriveBulkImportResult(
            0,
            0,
            0,
            ["No PDF files found in this folder."],
            None,
        )

    imported = 0
    skipped = 0
    failed = 0
    messages: list[str] = []
    last_pdf: Pdf | None = None

    for info in pdfs:
        result = import_gdrive_file(profile, info.id, force=force)
        if result.status == "imported":
            imported += 1
            last_pdf = result.pdf
        elif result.status == "skipped":
            skipped += 1
        else:
            failed += 1
            messages.append(result.message)

    return DriveBulkImportResult(imported, skipped, failed, messages, last_pdf)
