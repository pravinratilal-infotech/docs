"""Service layer for the enrichment API (AI tagging / metadata)."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ENRICHMENT_URL = getattr(settings, "ENRICHMENT_URL", "http://enrichment:8002")
ENRICHMENT_ENABLED = getattr(settings, "ENRICHMENT_ENABLED", True)


def get_enrichment_for_pdf(pdf_id: str) -> dict | None:
    """Fetch the latest enrichment record for a PdfDing PDF."""
    if not ENRICHMENT_ENABLED:
        return None

    try:
        resp = requests.get(
            f"{ENRICHMENT_URL}/api/v1/enrichments/lookup",
            params={"source": "pdfding", "source_id": pdf_id},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        logger.warning(
            "Enrichment API returned %d for PDF %s", resp.status_code, pdf_id
        )
        return None
    except requests.ConnectionError:
        logger.error("Cannot connect to enrichment service at %s", ENRICHMENT_URL)
        return None
    except Exception as exc:
        logger.error("Error fetching enrichment for PDF %s: %s", pdf_id, exc)
        return None


def enqueue_enrichment(job_id: str, force: bool = False) -> dict | None:
    """Enqueue AI enrichment for a completed Docling job."""
    if not ENRICHMENT_ENABLED:
        return None

    try:
        resp = requests.post(
            f"{ENRICHMENT_URL}/api/v1/jobs/{job_id}/enrich",
            params={"pipeline": "tag_creator", "force": str(force).lower()},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error(
            "Enrichment enqueue returned %d: %s", resp.status_code, resp.text[:200]
        )
        return None
    except Exception as exc:
        logger.error("Error enqueueing enrichment for job %s: %s", job_id, exc)
        return None


def list_enrichments(
    source: str = "pdfding",
    limit: int = 100,
    status: str | None = None,
) -> dict | None:
    """List enrichment records with optional filters."""
    if not ENRICHMENT_ENABLED:
        return {"enrichments": [], "total": 0}

    try:
        params: dict = {"source": source, "limit": limit}
        if status:
            params["status"] = status
        resp = requests.get(
            f"{ENRICHMENT_URL}/api/v1/enrichments",
            params=params,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Enrichment list returned %d", resp.status_code)
        return None
    except Exception as exc:
        logger.error("Error listing enrichments: %s", exc)
        return None
