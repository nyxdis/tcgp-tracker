from .base import *

DEBUG = True
SECRET_KEY = "insecure-dev-key"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.dev.sqlite3",
    }
}
