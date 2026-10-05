"""
PWA (Progressive Web App) views.

These are served from the site root rather than ``/static/`` so that the
service worker controls the whole origin scope and the web app manifest is
reachable at ``/manifest.webmanifest``.

Rendering them through Django templates (instead of plain static files) lets
us use ``{% static %}`` so asset URLs stay correct regardless of the static
storage backend (e.g. hashed filenames from WhiteNoise's
``CompressedManifestStaticFilesStorage``).
"""

from django.http import HttpResponse
from django.template.loader import render_to_string


def manifest_view(request):
    """Serve the web app manifest at the ``/manifest.webmanifest`` root path."""
    content = render_to_string("manifest.webmanifest", request=request)
    response = HttpResponse(content, content_type="application/manifest+json")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def service_worker_view(request):
    """Serve the service worker at ``/service-worker.js`` (full origin scope)."""
    content = render_to_string("service-worker.js", request=request)
    response = HttpResponse(content, content_type="application/javascript")
    # Allow the worker to control the entire origin.
    response["Service-Worker-Allowed"] = "/"
    # The browser must always revalidate the worker script itself.
    response["Cache-Control"] = "no-cache"
    return response
