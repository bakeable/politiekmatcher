"""
Views for serving content files.
"""

import os
from django.http import HttpResponse, Http404, FileResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from pathlib import Path


@require_GET
@csrf_exempt
def serve_pdf(request, filename):
    """
    Serve PDF files from the scraped_content directory.

    Args:
        request: HTTP request object
        filename: Name of the PDF file to serve

    Returns:
        FileResponse with the PDF file or Http404 if not found
    """
    # Construct the file path
    scraped_content_dir = Path(settings.BASE_DIR) / "scraped_content"
    file_path = scraped_content_dir / filename

    # Security check: ensure the file is within the scraped_content directory
    try:
        file_path = file_path.resolve()
        scraped_content_dir = scraped_content_dir.resolve()
        if not str(file_path).startswith(str(scraped_content_dir)):
            raise Http404("File not found")
    except (OSError, ValueError):
        raise Http404("File not found")

    # Check if file exists
    if not file_path.exists() or not file_path.is_file():
        raise Http404("File not found")

    # Check if it's a PDF file
    if not filename.lower().endswith(".pdf"):
        raise Http404("File not found")

    # Serve the file
    try:
        response = FileResponse(
            open(file_path, "rb"),
            content_type="application/pdf",
            as_attachment=False,  # Display in browser, not download
        )

        # Add filename for better browser handling
        response["Content-Disposition"] = f'inline; filename="{filename}"'

        return response

    except IOError:
        raise Http404("File not found")
