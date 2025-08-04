"""
URL patterns for profiles app
"""

from django.urls import path
from . import views

urlpatterns = [
    path(
        "auth/verify/<uuid:token>/", views.verify_magic_link, name="verify_magic_link"
    ),
]
