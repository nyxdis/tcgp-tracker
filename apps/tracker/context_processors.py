"""Context processors for tracker app."""

import os


def git_hash(request):
    git_hash_value = os.environ.get("GIT_HASH", "unknown")
    return {"git_hash": git_hash_value}
