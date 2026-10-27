# pylint: disable=redefined-outer-name
# Test functions take the fixture as a same-named parameter; that's the
# standard pytest pattern, not an actual shadowing bug.
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.tracker.management.commands.import_data import data_fingerprint
from apps.tracker.models.imports import DataImport


@pytest.fixture
def import_data_url():
    return reverse("admin:tracker_pokemonset_import_data")


@pytest.mark.django_db
def test_import_data_view_requires_login(client, import_data_url):
    response = client.get(import_data_url)
    assert response.status_code == 302
    assert reverse("admin:login") in response.url


@pytest.mark.django_db
def test_import_data_view_forbidden_for_non_superuser_staff(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_user(
        username="staffuser", password="pass", is_staff=True
    )
    client.force_login(user)

    response = client.get(import_data_url)

    assert response.status_code == 403


@pytest.mark.django_db
def test_import_data_view_get_renders_confirmation(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)

    response = client.get(import_data_url)

    assert response.status_code == 200
    assert b"Import if changed" in response.content
    assert b"Force full re-import" in response.content
    assert b"has never been imported" in response.content


@pytest.mark.django_db
def test_import_data_view_post_starts_command_in_background(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)

    with patch("subprocess.Popen") as mock_popen:
        response = client.post(import_data_url, {"mode": "if_changed"}, follow=True)

    mock_popen.assert_called_once()
    assert mock_popen.call_args.args[0][1:] == [
        "manage.py",
        "import_data",
        "--if-changed",
    ]
    assert mock_popen.call_args.kwargs["start_new_session"] is True
    assert response.redirect_chain == [
        (reverse("admin:tracker_pokemonset_changelist"), 302)
    ]
    assert b"Import started in the background" in response.content


@pytest.mark.django_db
def test_import_data_view_post_force_runs_full_import(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)

    with patch("subprocess.Popen") as mock_popen:
        client.post(import_data_url, {"mode": "force"})

    assert mock_popen.call_args.args[0][1:] == ["manage.py", "import_data"]


@pytest.mark.django_db
def test_import_data_view_get_reports_unchanged_data(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)
    DataImport.objects.create(fingerprint=data_fingerprint())

    response = client.get(import_data_url)

    assert b"is unchanged since the last import" in response.content


@pytest.mark.django_db
def test_import_data_view_get_reports_changed_data(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)
    DataImport.objects.create(fingerprint="0" * 64)

    response = client.get(import_data_url)

    assert b"has changed since the last import" in response.content


@pytest.mark.django_db
def test_import_data_view_post_reports_start_failure(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)

    with patch("subprocess.Popen", side_effect=OSError("no such file")):
        response = client.post(import_data_url, follow=True)

    assert b"Could not start the import: no such file" in response.content
