"""Management command to fill the image bucket with card thumbnails, set
logos and pack art from flibustier's repos: thumbnails and logos from
pokemon-tcg-exchange (public/images/), pack art from
pokemon-tcg-pocket-database (dist/images/packs/).

Only objects missing from the bucket are downloaded and uploaded, so the
command is cheap to re-run after sync_flibustier/import_data add a new set.
Cards and sets are taken from the database, not data/*.csv, so the bucket
matches what the site actually shows.

Not every set has a logo in every language (newer sets are English-only);
missing localized logos are skipped and the image proxy serves the English
one instead.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.tracker import images
from apps.tracker.models.cards import Card, Pack, PokemonSet

SOURCE_URL = (
    "https://raw.githubusercontent.com/flibustier/"
    "pokemon-tcg-exchange/main/public/images"
)
PACK_SOURCE_URL = (
    "https://raw.githubusercontent.com/flibustier/"
    "pokemon-tcg-pocket-database/main/dist/images/packs"
)

# Local pack names whose art flibustier files under a different name.
PACK_SOURCE_NAMES = {
    "Altaria": "Mega Altaria",
    "Blaziken": "Mega Blaziken",
    "Deluxepack": "Deluxe",
    "Extradimensional Crisis": "Extradimensional",
    "Gyarados": "Mega Gyarados",
    "Paldean Wonders": "Paldean",
    "Shining Revelry": "Shining",
    "Suicune": "Secluded",
}

WORKERS = 8


def _thumbnail_url(set_number, card_number):
    return f"{SOURCE_URL}/thumbnails/{set_number}/{int(card_number)}.webp"


def _logo_url(set_number, language):
    locale = images.LOGO_LOCALES[language]
    return f"{SOURCE_URL}/sets/LOGO_expansion_{set_number}_{locale}.webp"


def _pack_url(pack_name):
    name = PACK_SOURCE_NAMES.get(pack_name, pack_name)
    return f"{PACK_SOURCE_URL}/{quote(name)}.webp"


class Command(BaseCommand):
    help = "Upload missing card thumbnails and set logos to the image bucket"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "TCGPTracker-scraper/1.0 (educational data sync)"}
        )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sets",
            nargs="+",
            metavar="SET",
            help="Only sync these set numbers (default: all sets)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-upload images that are already in the bucket",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be uploaded",
        )

    def handle(self, *args, **options):
        if not settings.IMAGES_ENABLED:
            raise CommandError("S3_ENDPOINT is not set; images are disabled.")
        client = images.get_client()
        self._ensure_bucket(client, options["dry_run"])

        wanted = self._wanted_keys(options["sets"])
        existing = set() if options["force"] else self._existing_keys(client)
        missing = sorted(k for k in wanted if k not in existing)
        self.stdout.write(
            f"{len(wanted)} images wanted, {len(wanted) - len(missing)} already "
            f"in bucket {settings.S3_BUCKET}, {len(missing)} to upload."
        )
        if options["dry_run"] or not missing:
            return

        uploaded, not_found, failed = 0, [], []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {
                pool.submit(self._copy, client, k, wanted[k]): k for k in missing
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    found = future.result()
                except (requests.RequestException, ClientError) as exc:
                    failed.append(key)
                    self.stderr.write(f"Failed {key}: {exc}")
                    continue
                if found:
                    uploaded += 1
                else:
                    not_found.append(key)

        self.stdout.write(self.style.SUCCESS(f"Uploaded {uploaded} images."))
        # Missing localized logos are expected (the proxy falls back to
        # English); anything else missing upstream is worth a look.
        expected = [k for k in not_found if images.fallback_logo_key(k)]
        unexpected = sorted(set(not_found) - set(expected))
        if expected:
            self.stdout.write(
                f"{len(expected)} localized logos not available upstream "
                "(English is used instead)."
            )
        for key in unexpected:
            self.stdout.write(self.style.WARNING(f"Not available upstream: {key}"))
        if failed:
            raise CommandError(f"{len(failed)} images failed; re-run to retry.")

    def _ensure_bucket(self, client, dry_run):
        try:
            client.head_bucket(Bucket=settings.S3_BUCKET)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
                raise
            if dry_run:
                self.stdout.write(f"Would create bucket {settings.S3_BUCKET}.")
                return
            client.create_bucket(Bucket=settings.S3_BUCKET)
            self.stdout.write(f"Created bucket {settings.S3_BUCKET}.")

    @staticmethod
    def _wanted_keys(set_numbers):
        """Bucket keys the site can show, mapped to their upstream URLs."""
        sets = PokemonSet.objects.all()
        cards = Card.objects.select_related("set")
        packs = Pack.objects.select_related("set")
        if set_numbers:
            sets = sets.filter(number__in=set_numbers)
            cards = cards.filter(set__number__in=set_numbers)
            packs = packs.filter(set__number__in=set_numbers)
        wanted = {
            images.logo_key(s.number, language): _logo_url(s.number, language)
            for s in sets
            for language in images.LOGO_LOCALES
        }
        wanted.update(
            (
                images.thumbnail_key(c.set.number, c.number),
                _thumbnail_url(c.set.number, c.number),
            )
            for c in cards
        )
        wanted.update(
            (images.pack_key(p.set.number, p.name), _pack_url(p.name)) for p in packs
        )
        return wanted

    @staticmethod
    def _existing_keys(client):
        keys = set()
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.S3_BUCKET):
            keys.update(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def _copy(self, client, key, url):
        """Download one image and upload it; False if it doesn't exist upstream."""
        response = self._session.get(url, timeout=30)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=response.content,
            ContentType=images.CONTENT_TYPE,
        )
        return True
