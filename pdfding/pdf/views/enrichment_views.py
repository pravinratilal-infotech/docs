"""Views for AI enrichment — status display and applying suggested tags."""

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from pdf.services import docling_services, enrichment_services
from pdf.services.tag_services import TagServices
from pdf.views.pdf_views import PdfMixin


class EnrichmentStatus(PdfMixin, View):
    """HTMX partial — show AI enrichment status for a PDF."""

    def get(self, request: HttpRequest, identifier: str):
        if not request.htmx:
            return redirect("pdf_details", identifier=identifier)

        pdf = self.get_object(request, identifier)
        docling_job = docling_services.get_latest_job_for_pdf(str(pdf.id))
        enrichment = None

        if docling_job and docling_job.get("status") == "completed":
            enrichment = enrichment_services.get_enrichment_for_pdf(str(pdf.id))

        return render(
            request,
            "partials/enrichment_status.html",
            {
                "pdf": pdf,
                "docling_job": docling_job,
                "enrichment": enrichment,
            },
        )


class EnqueueEnrichment(PdfMixin, View):
    """Manually trigger AI enrichment for a PDF with a completed Docling job."""

    def post(self, request: HttpRequest, identifier: str):
        pdf = self.get_object(request, identifier)
        docling_job = docling_services.get_latest_job_for_pdf(str(pdf.id))

        if not docling_job or docling_job.get("status") != "completed":
            messages.error(
                request,
                f'"{pdf.name}" must be processed by Docling before AI tagging.',
            )
        else:
            force = request.POST.get("force") == "true"
            result = enrichment_services.enqueue_enrichment(docling_job["id"], force=force)
            if result:
                messages.success(
                    request,
                    f'AI tagging started for "{pdf.name}".',
                )
            else:
                messages.error(
                    request,
                    "Could not start AI tagging. Enrichment service may be unavailable.",
                )

        if request.htmx:
            return HttpResponseClientRedirect(f"/details/{identifier}")
        return redirect("pdf_details", identifier=identifier)


class ApplyEnrichmentTags(PdfMixin, View):
    """Apply AI-suggested tags to the PDF (merges with existing tags)."""

    def post(self, request: HttpRequest, identifier: str):
        pdf = self.get_object(request, identifier)
        enrichment = enrichment_services.get_enrichment_for_pdf(str(pdf.id))

        if not enrichment or enrichment.get("status") != "completed":
            messages.error(request, "No completed AI enrichment available to apply.")
        else:
            suggested = enrichment.get("enriched_tags") or []
            if not suggested:
                messages.warning(request, "AI enrichment did not suggest any tags.")
            else:
                existing = list(pdf.tags.values_list("name", flat=True))
                merged = list(dict.fromkeys(existing + suggested))
                tags = TagServices.process_tag_names(
                    merged, pdf.collection.workspace
                )
                pdf.tags.set(tags)
                messages.success(
                    request,
                    f"Applied {len(suggested)} suggested tag(s) to \"{pdf.name}\".",
                )

        if request.htmx:
            return HttpResponseClientRedirect(f"/details/{identifier}")
        return redirect("pdf_details", identifier=identifier)
