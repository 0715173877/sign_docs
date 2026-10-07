from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

from . import views as pwa_views

urlpatterns = [
    # PWA endpoints (served from the root so the service worker gets full scope)
    path("manifest.webmanifest", pwa_views.manifest_view, name="manifest"),
    path("service-worker.js", pwa_views.service_worker_view, name="service_worker"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("documents.urls")),
]

# Serve static files in development (WhiteNoise handles them in production)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Always serve user-uploaded media (documents, page previews, signatures, stamps).
# WhiteNoise only handles STATIC files, so without this the /media/ URLs would
# 404 whenever DEBUG=False (e.g. the production .env). For high-traffic
# deployments this should be offloaded to the front-end web server (nginx).
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
