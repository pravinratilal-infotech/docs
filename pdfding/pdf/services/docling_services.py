"""Service layer for communicating with the Docling API service.

Sends PDF files from PdfDing to the docling-api for processing.
The docling-api is reachable within the Docker network.
"""

import logging
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Docling API base URL — internal Docker network
DOCLING_API_URL = getattr(settings, "DOCLING_API_URL", "http://docling-api:8001")


def submit_pdf_for_processing(pdf) -> dict | None:
    """
    Submit a PdfDing PDF to the Docling API for processing.

    Args:
        pdf: A PdfDing Pdf model instance.

    Returns:
        dict with job_id and status, or None if submission failed.
    """
    try:
        file_path = Path(pdf.file.path)
        if not file_path.exists():
            logger.error("PDF file not found: %s", file_path)
            return None

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/pdf")}
            data = {
                "source": "pdfding",
                "source_id": str(pdf.id),
            }

            resp = requests.post(
                f"{DOCLING_API_URL}/api/v1/jobs",
                files=files,
                data=data,
                timeout=30,
            )

        if resp.status_code == 200:
            result = resp.json()
            logger.info(
                "Submitted PDF %s to Docling API — job_id=%s",
                pdf.name,
                result.get("job_id"),
            )
            return result
        else:
            logger.error(
                "Docling API returned %d: %s", resp.status_code, resp.text[:200]
            )
            return None

    except requests.ConnectionError:
        logger.error("Cannot connect to Docling API at %s", DOCLING_API_URL)
        return None
    except Exception as exc:
        logger.error("Error submitting to Docling API: %s", exc)
        return None


def submit_bulk_pdfs_for_processing(pdfs) -> list[dict]:
    """
    Submit multiple PdfDing PDFs to the Docling API for processing.

    Args:
        pdfs: Iterable of PdfDing Pdf model instances.

    Returns:
        List of dicts with job_id and status for each PDF.
    """
    results = []
    for pdf in pdfs:
        result = submit_pdf_for_processing(pdf)
        if result:
            results.append(result)
    return results


def get_job_status(job_id: str) -> dict | None:
    """Get the status of a Docling processing job."""
    try:
        resp = requests.get(
            f"{DOCLING_API_URL}/api/v1/jobs/{job_id}",
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as exc:
        logger.error("Error checking Docling job status: %s", exc)
        return None
