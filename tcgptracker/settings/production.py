import os

import dj_database_url

from .base import *

DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]
ALLOWED_HOSTS = [
    "tcgp.freyd.is",
    "tcgp.ngls.eu",
    "beeblebrox",
    # Docker Swarm overlay network IPs
    "10.0.1.1",
    "10.0.1.2",
    "10.0.1.3",
    "10.0.1.4",
    "10.0.1.5",
    "10.0.1.6",
    "10.0.1.7",
    "10.0.1.8",
    "10.0.1.9",
    "10.0.1.10",
    "10.0.1.11",
    "10.0.1.12",
    "10.0.1.13",
    "10.0.1.14",
    "10.0.1.15",
    "10.0.1.16",
    "10.0.1.17",
    "10.0.1.18",
    "10.0.1.19",
    "10.0.1.20",
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
