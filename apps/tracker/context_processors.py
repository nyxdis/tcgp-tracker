"""Context processors for tracker app."""

import os

from django.conf import settings


def git_hash(request):
    git_hash_value = os.environ.get("GIT_HASH", "unknown")
    return {"git_hash": git_hash_value}


def oidc_enabled(request):
    return {"oidc_enabled": settings.OIDC_ENABLED}
