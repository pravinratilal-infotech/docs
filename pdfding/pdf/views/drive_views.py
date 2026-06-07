"""Google Drive view — lists shared folder hierarchy."""

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render
from django.views import View

from pdf.drive.google_drive_connector import DriveConnectionError
from pdf.services import drive_services


class DriveOverview(View):
    """List folders and files shared with the service account."""

    def get(self, request: HttpRequest):
        tree = []
        folder_count = 0
        file_count = 0
        scoped_folder_id = drive_services.get_optional_folder_id()
        error = None

        try:
            tree, folder_count, file_count = drive_services.list_shared_tree()
        except DriveConnectionError as exc:
            error = str(exc)
            messages.error(request, error)

        return render(
            request,
            "drive_overview.html",
            {
                "tree": tree,
                "folder_count": folder_count,
                "file_count": file_count,
                "scoped_folder_id": scoped_folder_id,
                "error": error,
                "page": "gdrive_overview",
            },
        )
