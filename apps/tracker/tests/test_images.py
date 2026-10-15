# pylint: disable=redefined-outer-name
"""Tests for card thumbnails and set logos (bucket keys, proxy, sync command)."""

import datetime
import threading
from io import BytesIO, StringIO

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from apps.tracker import images
from apps.tracker.management.commands import sync_card_images
from apps.tracker.models.cards import Card, Generation, Pack, PokemonSet, Rarity

BUCKET = "test-images"


@pytest.fixture
def images_enabled(settings):
    settings.S3_ENDPOINT = "http://minio:9000"
    settings.S3_BUCKET = BUCKET
    settings.IMAGES_ENABLED = True


@pytest.fixture
def s3(monkeypatch, images_enabled):
    client = boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        region_name="eu-central-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    monkeypatch.setattr(images, "get_client", lambda: client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def card(db):
    pokemon_set = PokemonSet.objects.create(
        number="A1a", name="Mythical Island", release_date=datetime.date(2024, 12, 17)
    )
    rarity = Rarity.objects.create(name="common", display_name="C", order=1)
    return Card.objects.create(set=pokemon_set, number="007", name="Mew", rarity=rarity)


@pytest.fixture
def pack(card):
    generation = Generation.objects.create(name="G1", display_name="Gen 1")
    return Pack.objects.create(
        set=card.set, name="Shining Revelry", rarity_version=generation
    )


def test_keys_mirror_flibustier_layout():
    assert images.thumbnail_key("A1a", "007") == "thumbnails/A1a/7.webp"
    assert images.logo_key("B4b", "de") == "logos/B4b/de.webp"
    assert images.pack_key("A4", "Ho-Oh") == "packs/A4/ho-oh.webp"
    assert (
        images.pack_key("B4b", "Deluxe Pack Mega") == "packs/B4b/deluxe-pack-mega.webp"
    )


@pytest.mark.parametrize(
    "key, fallback",
    [
        ("logos/B4b/de.webp", "logos/B4b/en.webp"),
        ("logos/B4b/en.webp", None),
        ("thumbnails/B4b/1.webp", None),
    ],
)
def test_fallback_logo_key(key, fallback):
    assert images.fallback_logo_key(key) == fallback


@pytest.mark.parametrize(
    "key",
    [
        "thumbnails/PROMO-A/12.webp",
        "logos/A1a/de.webp",
        "packs/B4b/deluxe-pack-mega.webp",
    ],
)
def test_key_re_accepts_image_keys(key):
    assert images.KEY_RE.match(key)


@pytest.mark.parametrize(
    "key",
    [
        "thumbnails/A1/../secret.webp",
        "thumbnails/A1/1.png",
        "logos/A1/de_DE.webp",
        "other/A1/1.webp",
        "packs/A1/Shining Revelry.webp",
    ],
)
def test_key_re_rejects_other_objects(key):
    assert not images.KEY_RE.match(key)


def test_urls_are_none_when_images_disabled(settings, card):
    settings.IMAGES_ENABLED = False
    assert card.thumbnail_url is None
    assert card.set.logo_url is None


def test_urls_point_at_proxy(images_enabled, pack):
    card = Card.objects.get()
    assert card.thumbnail_url == "/images/thumbnails/A1a/7.webp"
    assert pack.image_url == "/images/packs/A1a/shining-revelry.webp"
    with translation.override("de"):
        assert card.set.logo_url == "/images/logos/A1a/de.webp"
    with translation.override("fr"):
        assert card.set.logo_url == "/images/logos/A1a/en.webp"


def _body(data):
    return {
        "Body": StreamingBody(BytesIO(data), len(data)),
        "ContentLength": len(data),
        "ETag": '"abc"',
    }


def test_proxy_streams_image(client, s3):
    s3.add_response(
        "get_object",
        _body(b"webp-bytes"),
        {"Bucket": BUCKET, "Key": "thumbnails/A1/1.webp"},
    )

    response = client.get(reverse("image", args=["thumbnails/A1/1.webp"]))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"webp-bytes"
    assert response["Content-Type"] == "image/webp"
    assert response["ETag"] == '"abc"'
    assert "max-age" in response["Cache-Control"]


def test_proxy_falls_back_to_english_logo(client, s3):
    s3.add_client_error("get_object", "NoSuchKey", http_status_code=404)
    s3.add_response(
        "get_object", _body(b"en-logo"), {"Bucket": BUCKET, "Key": "logos/B4/en.webp"}
    )

    response = client.get(reverse("image", args=["logos/B4/de.webp"]))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"en-logo"


def test_proxy_404s_for_missing_thumbnail(client, s3):
    s3.add_client_error("get_object", "NoSuchKey", http_status_code=404)

    response = client.get(reverse("image", args=["thumbnails/A1/999.webp"]))

    assert response.status_code == 404


def test_proxy_passes_through_not_modified(client, s3):
    s3.add_client_error("get_object", "304", http_status_code=304)

    response = client.get(
        reverse("image", args=["thumbnails/A1/1.webp"]), HTTP_IF_NONE_MATCH='"abc"'
    )

    assert response.status_code == 304
    assert response["ETag"] == '"abc"'


def test_proxy_502s_on_bucket_error(client, s3):
    s3.add_client_error("get_object", "AccessDenied", http_status_code=403)

    response = client.get(reverse("image", args=["thumbnails/A1/1.webp"]))

    assert response.status_code == 502


def test_proxy_rejects_unexpected_keys(client, s3):
    response = client.get("/images/backups/db.sql")

    assert response.status_code == 404


def test_proxy_404s_when_images_disabled(client, settings):
    settings.IMAGES_ENABLED = False

    response = client.get(reverse("image", args=["thumbnails/A1/1.webp"]))

    assert response.status_code == 404


class FakeS3:
    """Just enough of an S3 client for the sync command (thread-safe)."""

    def __init__(self, keys=(), bucket_exists=True):
        self.objects = {key: b"" for key in keys}
        self.bucket_exists = bucket_exists
        self._lock = threading.Lock()

    def head_bucket(self, Bucket):  # pylint: disable=invalid-name,unused-argument
        if not self.bucket_exists:
            raise images_client_error("404")

    def create_bucket(self, Bucket):  # pylint: disable=invalid-name,unused-argument
        self.bucket_exists = True

    def get_paginator(self, _name):
        objects = self.objects

        class Paginator:  # pylint: disable=too-few-public-methods
            def paginate(self, Bucket):  # pylint: disable=invalid-name,unused-argument
                return [{"Contents": [{"Key": key} for key in objects]}]

        return Paginator()

    def put_object(
        self, Bucket, Key, Body, ContentType
    ):  # pylint: disable=invalid-name,unused-argument
        with self._lock:
            self.objects[Key] = Body


def images_client_error(code):
    # pylint: disable=import-outside-toplevel
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code}}, "HeadBucket")


class FakeResponse:  # pylint: disable=too-few-public-methods
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        assert self.status_code == 200


@pytest.fixture
def upstream(monkeypatch):
    """Serve every flibustier URL except German logos, recording requests."""
    requested = []

    def fake_get(_session, url, timeout):  # pylint: disable=unused-argument
        requested.append(url)
        if url.endswith("_de_DE.webp"):
            return FakeResponse(404)
        return FakeResponse(200, url.encode())

    monkeypatch.setattr("requests.Session.get", fake_get)
    return requested


def _run_sync(fake, monkeypatch, *args):
    monkeypatch.setattr(images, "get_client", lambda: fake)
    out = StringIO()
    call_command("sync_card_images", *args, stdout=out)
    return out.getvalue()


def test_sync_uploads_only_missing_images(monkeypatch, images_enabled, pack, upstream):
    fake = FakeS3(keys=["thumbnails/A1a/7.webp"], bucket_exists=False)

    output = _run_sync(fake, monkeypatch)

    assert fake.bucket_exists
    assert set(fake.objects) == {
        "thumbnails/A1a/7.webp",
        "logos/A1a/en.webp",
        "packs/A1a/shining-revelry.webp",
    }
    assert fake.objects["logos/A1a/en.webp"] == (
        f"{sync_card_images.SOURCE_URL}/sets/LOGO_expansion_A1a_en_US.webp".encode()
    )
    # Pack art comes from the database repo, under flibustier's own name.
    assert fake.objects["packs/A1a/shining-revelry.webp"] == (
        f"{sync_card_images.PACK_SOURCE_URL}/Shining.webp".encode()
    )
    # The thumbnail already in the bucket isn't downloaded again.
    assert not any("thumbnails" in url for url in upstream)
    assert "Uploaded 2 images." in output
    assert "1 localized logos not available upstream" in output


def test_sync_dry_run_uploads_nothing(monkeypatch, images_enabled, card, upstream):
    fake = FakeS3()

    output = _run_sync(fake, monkeypatch, "--dry-run")

    assert not fake.objects
    assert not upstream
    assert "3 to upload" in output


# pylint: disable=protected-access
def test_sync_source_urls():
    assert sync_card_images._thumbnail_url("A1a", "007") == (
        f"{sync_card_images.SOURCE_URL}/thumbnails/A1a/7.webp"
    )
    assert sync_card_images._pack_url("Deluxe Pack Mega") == (
        f"{sync_card_images.PACK_SOURCE_URL}/Deluxe%20Pack%20Mega.webp"
    )
    assert sync_card_images._pack_url("Altaria") == (
        f"{sync_card_images.PACK_SOURCE_URL}/Mega%20Altaria.webp"
    )
