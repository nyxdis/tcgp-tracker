"""Health check view for load balancer probes."""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for load balancers."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        return JsonResponse({"status": "healthy", "database": "connected"})
    except Exception:  # pylint: disable=broad-except
        return JsonResponse(
            {"status": "unhealthy", "database": "disconnected"}, status=503
        )
