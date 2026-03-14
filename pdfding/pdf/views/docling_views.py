"""Views for Docling integration — trigger processing, check status, view results."""

import markdown as md_lib
import nh3
from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from pdf.models.pdf_models import MarkdownHelper
from pdf.services import docling_services
from pdf.views.pdf_views import PdfMixin


# Docling API dashboard URL — used for linking users to the results page.
# In production, this is the Caddy-proxied URL for the docling-api dashboard.
DOCLING_DASHBOARD_URL = getattr(
    settings, "DOCLING_DASHBOARD_URL", "/docling"
)


class ProcessWithDocling(PdfMixin, View):
    """Trigger Docling processing for a single PDF."""

    def post(self, request: HttpRequest, identifier: str):
        pdf = self.get_object(request, identifier)

        result = docling_services.submit_pdf_for_processing(pdf)

        if result and result.get("job_id"):
            messages.success(
                request,
                f'Processing started for "{pdf.name}". '
                "You can continue using the app — processing runs in the background.",
            )
        else:
            messages.error(
                request,
                f'Could not start processing for "{pdf.name}". '
                "Docling API may be unavailable.",
            )

        # Always redirect back to the details page.
        # The HTMX status div will poll and show progress.
        if request.htmx:
            return HttpResponseClientRedirect(f"/details/{identifier}")
        return redirect("pdf_details", identifier=identifier)


class BulkProcessWithDocling(View):
    """Trigger Docling processing for multiple PDFs in the current workspace."""

    def post(self, request: HttpRequest):
        profile = request.user.profile
        pdfs = profile.current_pdfs.filter(archived=False)

        if not pdfs.exists():
            messages.warning(request, "No PDFs to process.")
            if request.htmx:
                return HttpResponseClientRedirect("/")
            return redirect("pdf_overview")

        results = docling_services.submit_bulk_pdfs_for_processing(pdfs)

        if results:
            messages.success(
                request,
                f"Submitted {len(results)} PDF(s) for Docling processing. "
                f"They will be processed one by one in the background.",
            )
        else:
            messages.error(
                request,
                "Could not submit PDFs for processing. "
                "Docling API may be unavailable.",
            )

        if request.htmx:
            return HttpResponseClientRedirect("/")
        return redirect("pdf_overview")


class DoclingResult(PdfMixin, View):
    """Display the Docling-processed output for a PDF."""

    def get(self, request: HttpRequest, identifier: str):
        pdf = self.get_object(request, identifier)
        job_info = _get_latest_job_for_pdf(str(pdf.id))

        result_data = None
        result_html = None

        if job_info and job_info.get("status") == "completed":
            result_data = docling_services.get_job_result(job_info["id"])
            if result_data and result_data.get("markdown"):
                result_html = _render_markdown(result_data["markdown"])

        return render(
            request,
            "docling_result.html",
            {
                "pdf": pdf,
                "docling_job": job_info,
                "result_data": result_data,
                "result_html": result_html,
                "DOCLING_DASHBOARD_URL": DOCLING_DASHBOARD_URL,
            },
        )


class DoclingStatus(PdfMixin, View):
    """HTMX partial — show Docling processing status for a PDF."""

    def get(self, request: HttpRequest, identifier: str):
        """Returns an HTMX fragment with the Docling job status."""
        if not request.htmx:
            return redirect("pdf_details", identifier=identifier)

        pdf = self.get_object(request, identifier)
        status_info = _get_latest_job_for_pdf(str(pdf.id))

        return render(
            request,
            "partials/docling_status.html",
            {
                "pdf": pdf,
                "docling_job": status_info,
                "DOCLING_DASHBOARD_URL": DOCLING_DASHBOARD_URL,
            },
        )


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_latest_job_for_pdf(pdf_id: str) -> dict | None:
    """Query the Docling API for the latest job associated with a PDF."""
    import requests as req
    from pdf.services.docling_services import DOCLING_API_URL

    try:
        resp = req.get(
            f"{DOCLING_API_URL}/api/v1/jobs",
            params={"source": "pdfding", "source_id": pdf_id, "limit": 1},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            if jobs:
                return jobs[0]
        return None
    except Exception:
        return None


def _render_markdown(markdown_text: str) -> str:
    """Convert Docling markdown to sanitised HTML for display."""
    raw_html = md_lib.markdown(
        markdown_text,
        extensions=["fenced_code", "nl2br", "tables", "toc"],
    )
    cleaned = nh3.clean(
        raw_html,
        attributes=_get_docling_allowed_attributes(),
        tags=_get_docling_allowed_tags(),
    )
    return mark_safe(cleaned)  # nosec — sanitised by nh3


def _get_docling_allowed_tags() -> set[str]:
    """Extended tag set for Docling output (includes tables and images)."""
    base = MarkdownHelper.get_allowed_markdown_tags()
    base.update({
        "table", "thead", "tbody", "tr", "th", "td",
        "img", "figure", "figcaption",
    })
    return base


def _get_docling_allowed_attributes() -> dict[str, set[str]]:
    """Extended attribute set for Docling output."""
    base = MarkdownHelper.get_allowed_markdown_attributes()
    base["img"] = {"src", "alt", "title", "width", "height"}
    base["td"] = {"colspan", "rowspan", "align"}
    base["th"] = {"colspan", "rowspan", "align"}
    base["table"] = {"class"}
    return base
