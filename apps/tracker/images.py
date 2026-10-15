"""Card thumbnails, set logos and pack art stored in an S3-compatible bucket
(MinIO).

Bucket layout:
    thumbnails/<set number>/<card number without leading zeros>.webp
    logos/<set number>/<language code>.webp
    packs/<set number>/<slugified pack name>.webp

The sync_card_images command populates the bucket from flibustier's
pokemon-tcg-exchange (thumbnails, logos) and pokemon-tcg-pocket-database
(pack art) repos.
"""

import functools
import re

import boto3
from botocore.config import Config
from django.conf import settings
from django.utils.text import slugify

# Site languages (settings.LANGUAGES) mapped to flibustier's logo locales.
LOGO_LOCALES = {"en": "en_US", "de": "de_DE"}
DEFAULT_LOGO_LANGUAGE = "en"

# Anything the /images/ proxy is willing to serve. Restricting the key shape
# keeps the proxy from being usable to read arbitrary objects in the bucket.
KEY_RE = re.compile(
    r"^(thumbnails/[A-Za-z0-9-]+/\d+"
    r"|logos/[A-Za-z0-9-]+/[a-z]{2}"
    r"|packs/[A-Za-z0-9-]+/[a-z0-9-]+)\.webp$"
)
_LOGO_KEY_RE = re.compile(r"^logos/(?P<set>[A-Za-z0-9-]+)/[a-z]{2}\.webp$")

CONTENT_TYPE = "image/webp"


def thumbnail_key(set_number, card_number):
    """Bucket key for a card's thumbnail ("001" is stored as "1.webp")."""
    return f"thumbnails/{set_number}/{int(card_number)}.webp"


def logo_key(set_number, language_code):
    """Bucket key for a set's logo in the given site language."""
    return f"logos/{set_number}/{language_code}.webp"


def pack_key(set_number, pack_name):
    """Bucket key for a pack's art ("Ho-Oh" is stored as "ho-oh.webp")."""
    return f"packs/{set_number}/{slugify(pack_name)}.webp"


def fallback_logo_key(key):
    """The default-language logo key to try when a localized logo is missing,
    or None if the key isn't a non-default-language logo."""
    match = _LOGO_KEY_RE.match(key)
    if not match:
        return None
    fallback = logo_key(match["set"], DEFAULT_LOGO_LANGUAGE)
    return fallback if fallback != key else None


@functools.cache
def get_client():
    """Shared boto3 S3 client for the configured bucket (thread-safe)."""
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        # MinIO is addressed as http://minio:9000/<bucket>, not via
        # bucket subdomains.
        config=Config(s3={"addressing_style": "path"}),
    )
