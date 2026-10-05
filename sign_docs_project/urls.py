from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from . import views as pwa_views

urlpatterns = [
    # PWA endpoints (served from the root so the service worker gets full scope)
    path("manifest.webmanifest", pwa_views.manifest_view, name="manifest"),
    path("service-worker.js", pwa_views.service_worker_view, name="service_worker"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("documents.urls")),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
