"""Processing jobs overview — Docling + enrichment status for workspace PDFs."""

from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.views import View

from pdf.services.processing_jobs_services import get_workspace_processing_jobs


class ProcessingJobsOverview(View):
    """List all Docling and enrichment jobs for the current workspace."""

    def get(self, request: HttpRequest):
        rows, has_active, error = get_workspace_processing_jobs(request.user.profile)
        return render(
            request,
            "processing_jobs.html",
            {
                "rows": rows,
                "has_active": has_active,
                "error": error,
                "page": "processing_jobs",
            },
        )


class ProcessingJobsTable(View):
    """HTMX partial — refreshable jobs table."""

    def get(self, request: HttpRequest):
        if not request.htmx:
            return redirect("processing_jobs")

        rows, has_active, error = get_workspace_processing_jobs(request.user.profile)
        return render(
            request,
            "partials/processing_jobs_table.html",
            {
                "rows": rows,
                "has_active": has_active,
                "error": error,
            },
        )
