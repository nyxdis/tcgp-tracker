"""Proxy for card thumbnails and set logos stored in the private image bucket."""

import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseNotModified,
)
from django.views.decorators.http import require_safe

from apps.tracker import images

logger = logging.getLogger(__name__)

# The images are static game assets; the key only changes if the art does.
CACHE_CONTROL = "public, max-age=2592000"  # 30 days


def _get_object(key, if_none_match):
    params = {"Bucket": settings.S3_BUCKET, "Key": key}
    if if_none_match:
        params["IfNoneMatch"] = if_none_match
    return images.get_client().get_object(**params)


def _error_code(exc):
    return exc.response.get("Error", {}).get("Code")


@require_safe
def image_proxy(request, key):
    """Stream an image from the bucket, falling back to the English logo when
    a set has no logo in the requested language."""
    if not settings.IMAGES_ENABLED or not images.KEY_RE.match(key):
        raise Http404
    if_none_match = request.headers.get("If-None-Match")
    candidates = [key, images.fallback_logo_key(key)]
    for candidate in filter(None, candidates):
        try:
            obj = _get_object(candidate, if_none_match)
        except ClientError as exc:
            code = _error_code(exc)
            if code == "304":
                response = HttpResponseNotModified()
                response["ETag"] = if_none_match
                response["Cache-Control"] = CACHE_CONTROL
                return response
            if code in ("NoSuchKey", "404"):
                continue
            logger.warning("Image bucket error for %s: %s", candidate, exc)
            return HttpResponse(status=502)
        except BotoCoreError as exc:
            logger.warning("Image bucket unreachable for %s: %s", candidate, exc)
            return HttpResponse(status=502)
        response = FileResponse(obj["Body"], content_type=images.CONTENT_TYPE)
        response["Content-Length"] = obj["ContentLength"]
        response["ETag"] = obj["ETag"]
        response["Cache-Control"] = CACHE_CONTROL
        return response
    raise Http404
