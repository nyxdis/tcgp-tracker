import ipaddress
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
]


# Add Docker network ranges
def is_docker_ip(ip):
    """Check if IP is from Docker networks"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        # Docker default bridge network
        if (
            ipaddress.ip_address("172.17.0.1")
            <= ip_obj
            <= ipaddress.ip_address("172.17.255.254")
        ):
            return True
        # Docker overlay networks (10.0.x.x)
        if (
            ipaddress.ip_address("10.0.0.1")
            <= ip_obj
            <= ipaddress.ip_address("10.0.255.254")
        ):
            return True
        # Docker user-defined networks (172.x.x.x)
        if (
            ipaddress.ip_address("172.16.0.1")
            <= ip_obj
            <= ipaddress.ip_address("172.31.255.254")
        ):
            return True
        return False
    except ValueError:
        return False


# Custom allowed hosts check that includes Docker IPs
class DockerAwareAllowedHosts:
    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts

    def __contains__(self, host):
        # Remove port if present
        host_ip = host.split(":")[0]

        # Check static allowed hosts first
        if host in self.allowed_hosts or host_ip in self.allowed_hosts:
            return True

        # Check if it's a Docker internal IP
        return is_docker_ip(host_ip)


ALLOWED_HOSTS = DockerAwareAllowedHosts(ALLOWED_HOSTS)

# Environment variable override for flexibility
if "DJANGO_ALLOWED_HOSTS" in os.environ:
    base_hosts = ["tcgp.freyd.is", "tcgp.ngls.eu", "beeblebrox"]
    base_hosts.extend(os.environ["DJANGO_ALLOWED_HOSTS"].split(","))
    ALLOWED_HOSTS = DockerAwareAllowedHosts(base_hosts)

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
