"""Tracker app data import models."""

from django.db import models


class DataImport(models.Model):
    """Records a completed import of the data/ CSV files.

    The fingerprint is a hash of the imported files, so a startup can tell
    whether the data baked into the image has changed since the last import.
    """

    fingerprint = models.CharField(max_length=64)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "imported_at"
        verbose_name = "Data Import"
        verbose_name_plural = "Data Imports"

    def __str__(self):
        return f"{self.fingerprint[:12]} imported at {self.imported_at:%Y-%m-%d %H:%M}"
