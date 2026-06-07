"""Aggregate Docling + enrichment jobs for the PdfDing processing jobs view."""

import logging
from dataclasses import dataclass

from pdf.models.pdf_models import Pdf
from pdf.services import docling_services, enrichment_services
from users.models import Profile

logger = logging.getLogger(__name__)

ACTIVE_DOCLING = {"pending", "processing"}
ACTIVE_ENRICHMENT = {"pending", "processing"}


@dataclass
class ProcessingJobRow:
    job_id: str
    pdf_id: str | None
    pdf_name: str
    filename: str
    docling_status: str
    docling_progress: int
    docling_error: str | None
    enrichment_status: str | None
    enrichment_error: str | None
    enriched_title: str | None
    created_at: str
    completed_at: str | None


def get_workspace_processing_jobs(profile: Profile, limit: int = 100) -> tuple[list[ProcessingJobRow], bool, str | None]:
    """
    Return processing job rows for PDFs in the user's current workspace.

    Returns (rows, has_active_jobs, error_message).
    """
    pdf_ids = {str(pdf_id) for pdf_id in profile.current_pdfs.values_list("id", flat=True)}
    if not pdf_ids:
        return [], False, None

    jobs_data = docling_services.list_jobs(source="pdfding", limit=limit)
    if jobs_data is None:
        return [], False, "Could not reach Docling API."

    enrichments_data = enrichment_services.list_enrichments(source="pdfding", limit=limit)
    if enrichments_data is None:
        enrichments_data = {"enrichments": [], "total": 0}

    enrichment_by_job = {
        str(item["job_id"]): item for item in enrichments_data.get("enrichments", [])
    }

    workspace_jobs = [
        job for job in jobs_data.get("jobs", [])
        if job.get("source_id") in pdf_ids
    ]

    workspace_pdfs = {
        str(pdf.id): pdf
        for pdf in Pdf.objects.filter(id__in=pdf_ids).only(
            "id", "name", "creation_date"
        )
    }
    job_source_ids = {job.get("source_id") for job in workspace_jobs if job.get("source_id")}

    rows: list[ProcessingJobRow] = []
    has_active = False

    for job in workspace_jobs:
        job_id = job["id"]
        docling_status = job.get("status", "unknown")
        enrichment = enrichment_by_job.get(job_id)
        enrichment_status = enrichment.get("status") if enrichment else None

        if docling_status in ACTIVE_DOCLING or enrichment_status in ACTIVE_ENRICHMENT:
            has_active = True

        pdf_id = job.get("source_id")
        pdf = workspace_pdfs.get(pdf_id) if pdf_id else None
        rows.append(
            ProcessingJobRow(
                job_id=job_id,
                pdf_id=pdf_id,
                pdf_name=pdf.name if pdf else "Unknown PDF",
                filename=job.get("filename", "—"),
                docling_status=docling_status,
                docling_progress=job.get("progress") or 0,
                docling_error=job.get("error_message"),
                enrichment_status=enrichment_status,
                enrichment_error=enrichment.get("error_message") if enrichment else None,
                enriched_title=enrichment.get("enriched_title") if enrichment else None,
                created_at=job.get("created_at", ""),
                completed_at=job.get("completed_at"),
            )
        )

    for pdf_id, pdf in workspace_pdfs.items():
        if pdf_id in job_source_ids:
            continue
        rows.append(
            ProcessingJobRow(
                job_id="",
                pdf_id=pdf_id,
                pdf_name=pdf.name,
                filename="—",
                docling_status="not_started",
                docling_progress=0,
                docling_error=None,
                enrichment_status=None,
                enrichment_error=None,
                enriched_title=None,
                created_at=pdf.creation_date.isoformat() if pdf.creation_date else "",
                completed_at=None,
            )
        )

    rows.sort(key=lambda row: row.created_at or "", reverse=True)

    return rows, has_active, None
