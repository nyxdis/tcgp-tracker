import dj_database_url
import os

from .base import *

DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]
ALLOWED_HOSTS = ["tcgp.freyd.is", "tcgp.ngls.eu", "beeblebrox"]

CSRF_TRUSTED_ORIGINS = ["https://tcgp.freyd.is"]
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

DATABASES = {
    'default': dj_database_url.config(default=os.environ["DATABASE_URL"])
}

# WhiteNoise
MIDDLEWARE = [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE,
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
