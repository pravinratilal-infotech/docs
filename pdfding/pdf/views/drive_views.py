"""Google Drive views — browse shared files and import PDFs."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect, render
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from pdf.drive.google_drive_connector import DriveConnectionError
from pdf.services import drive_import_services, drive_services


class DriveOverview(View):
    """List folders and files shared with the service account."""

    def get(self, request: HttpRequest):
        tree = []
        folder_count = 0
        file_count = 0
        scoped_folder_id = drive_services.get_optional_folder_id()
        error = None
        imported_pdfs: dict[str, str] = {}

        root_folders: list = []
        root_pdfs: list = []

        try:
            tree, folder_count, file_count = drive_services.list_shared_tree()
            imported_pdfs = drive_import_services.get_imported_gdrive_map(
                request.user.profile.current_workspace
            )
            workspace = request.user.profile.current_workspace
            drive_import_services.annotate_imported_pdfs(tree, imported_pdfs)
            drive_import_services.annotate_processing_status(tree)
            drive_import_services.attach_imported_pdf_objects(tree, workspace)
            root_folders, root_pdfs = drive_import_services.split_tree_roots(tree)
        except DriveConnectionError as exc:
            error = str(exc)
            messages.error(request, error)

        return render(
            request,
            "drive_overview.html",
            {
                "tree": tree,
                "root_folders": root_folders,
                "root_pdfs": root_pdfs,
                "folder_count": folder_count,
                "file_count": file_count,
                "scoped_folder_id": scoped_folder_id,
                "imported_pdfs": imported_pdfs,
                "error": error,
                "layout": request.user.profile.layout,
                "page": "gdrive_overview",
            },
        )


class ServeDriveThumbnail(View):
    """Proxy Google Drive thumbnails using the service account."""

    def get(self, request: HttpRequest, file_id: str):
        try:
            result = drive_services.fetch_thumbnail(file_id)
        except DriveConnectionError:
            return HttpResponseNotFound()
        if not result:
            return HttpResponseNotFound()
        data, content_type = result
        response = HttpResponse(data, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response


class ImportDriveFile(View):
    """Import a single PDF from Google Drive."""

    def post(self, request: HttpRequest, file_id: str):
        folder_path = request.POST.get("folder_path", "").strip()
        force = request.POST.get("force") == "true"

        result = drive_import_services.import_gdrive_file(
            request.user.profile,
            file_id,
            folder_path=folder_path,
            force=force,
        )

        if result.status == "imported":
            messages.success(request, result.message)
            if request.htmx and result.pdf:
                return HttpResponseClientRedirect(f"/details/{result.pdf.id}")
            return redirect("pdf_details", identifier=result.pdf.id)

        if result.status == "skipped":
            messages.info(request, result.message)
            if request.htmx and result.pdf:
                return HttpResponseClientRedirect(f"/details/{result.pdf.id}")
            if result.pdf:
                return redirect("pdf_details", identifier=result.pdf.id)

        messages.error(request, result.message)
        if request.htmx:
            return HttpResponseClientRedirect("/gdrive/")
        return redirect("gdrive_overview")


class ImportDriveFolder(View):
    """Import all PDFs in a Google Drive folder."""

    def post(self, request: HttpRequest, folder_id: str):
        force = request.POST.get("force") == "true"
        result = drive_import_services.import_gdrive_folder(
            request.user.profile,
            folder_id,
            force=force,
        )

        if result.imported:
            messages.success(
                request,
                f"Imported {result.imported} PDF(s) from Google Drive. "
                "Docling processing has been queued for each.",
            )
        if result.skipped:
            messages.info(
                request,
                f"Skipped {result.skipped} file(s) already imported and up to date.",
            )
        for msg in result.messages[:5]:
            messages.warning(request, msg)
        if len(result.messages) > 5:
            messages.warning(
                request,
                f"…and {len(result.messages) - 5} more error(s).",
            )
        if not result.imported and not result.skipped and not result.messages:
            messages.warning(request, "No PDFs were imported.")

        if request.htmx:
            if result.imported == 1 and result.last_pdf:
                return HttpResponseClientRedirect(f"/details/{result.last_pdf.id}")
            return HttpResponseClientRedirect("/gdrive/")
        return redirect("gdrive_overview")
