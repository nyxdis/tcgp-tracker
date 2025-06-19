"""App configuration for tracker app."""

from django.apps import AppConfig


class TrackerConfig(AppConfig):
    """App config for tracker app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tracker"

    def ready(self):
        from apps.tracker import signals
