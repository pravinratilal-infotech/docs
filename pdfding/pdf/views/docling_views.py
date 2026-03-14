"""Views for Docling integration — trigger processing and check status."""

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from pdf.services import docling_services
from pdf.views.pdf_views import PdfMixin


# Docling API dashboard URL — used for redirecting users to the results page.
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
            job_id = result["job_id"]
            target_url = f"{DOCLING_DASHBOARD_URL}/jobs/{job_id}"

            # Use HTMX-aware redirect if this is an HTMX request
            if request.htmx:
                return HttpResponseClientRedirect(target_url)
            return redirect(target_url)
        else:
            messages.error(
                request,
                f'Could not start processing for "{pdf.name}". '
                "Docling API may be unavailable.",
            )
            if request.htmx:
                return HttpResponseClientRedirect(
                    f"/details/{identifier}"
                )
            return redirect("pdf_details", identifier=identifier)


class BulkProcessWithDocling(View):
    """Trigger Docling processing for all PDFs in the current workspace."""

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
                f"View progress on the Docling dashboard.",
            )
            target_url = f"{DOCLING_DASHBOARD_URL}/"
            if request.htmx:
                return HttpResponseClientRedirect(target_url)
            return redirect(target_url)
        else:
            messages.error(
                request,
                "Could not submit PDFs for processing. "
                "Docling API may be unavailable.",
            )
            if request.htmx:
                return HttpResponseClientRedirect("/")
            return redirect("pdf_overview")


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
            {"pdf": pdf, "docling_job": status_info},
        )


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
