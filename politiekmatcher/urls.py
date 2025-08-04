"""
PolitiekMatcher URL Configuration

This module defines the URL routing for the PolitiekMatcher project.
"""

from django.contrib import admin
from django.urls import path, include
from strawberry.django.views import GraphQLView
from apps.api.schema import schema
from apps.content.views import serve_pdf

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql/", GraphQLView.as_view(schema=schema), name="graphql"),
    path("pdf/<str:filename>", serve_pdf, name="serve_pdf"),
    path("", include("apps.profiles.urls")),
]
