"""
Views for profiles app
"""

from django.shortcuts import redirect
from django.http import HttpResponse
from django.conf import settings
from .services import EmailService


def verify_magic_link(request, token):
    """Verify magic link and redirect to frontend with token for verification"""
    # Instead of verifying here, redirect to frontend with the token
    # so the frontend can use GraphQL to verify and handle the result
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    return redirect(f"{frontend_url}/auth/verify/{token}")
