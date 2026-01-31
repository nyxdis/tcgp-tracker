import os

import dj_database_url

from .base import *

DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]

# Base allowed hosts
ALLOWED_HOSTS = [
    "tcgp.freyd.is",
    "tcgp.ngls.eu",
    "beeblebrox",
    # Docker overlay networks (10.0.1.x range)
    *[f"10.0.1.{i}" for i in range(1, 255)],
    # Docker bridge networks (172.17.0.x range)
    *[f"172.17.0.{i}" for i in range(1, 255)],
    # Docker user-defined networks (172.20.0.x range)
    *[f"172.20.0.{i}" for i in range(1, 255)],
    # Additional common Docker ranges
    *[f"172.18.0.{i}" for i in range(1, 255)],
    *[f"172.19.0.{i}" for i in range(1, 255)],
]

# Environment variable override for flexibility
if "DJANGO_ALLOWED_HOSTS" in os.environ:
    ALLOWED_HOSTS.extend(os.environ["DJANGO_ALLOWED_HOSTS"].split(","))

CSRF_TRUSTED_ORIGINS = ["https://tcgp.freyd.is"]
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

DATABASES = {"default": dj_database_url.config(default=os.environ["DATABASE_URL"])}

# WhiteNoise
MIDDLEWARE = [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE,
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

PWA_APP_DEBUG_MODE = False

# Override logging for production - only INFO and above
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "tracker": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "tracker.utils": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
