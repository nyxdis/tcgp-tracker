"""Health check view for load balancer probes."""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for load balancers."""
    status = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status["database"] = "connected"
    except Exception:  # pylint: disable=broad-except
        status["database"] = "disconnected"
        healthy = False

    try:
        cache.set("health_check", "ok", timeout=5)
        status["cache"] = (
            "connected" if cache.get("health_check") == "ok" else "disconnected"
        )
        healthy = healthy and status["cache"] == "connected"
    except Exception:  # pylint: disable=broad-except
        status["cache"] = "disconnected"
        healthy = False

    return JsonResponse(
        {"status": "healthy" if healthy else "unhealthy", **status},
        status=200 if healthy else 503,
    )
