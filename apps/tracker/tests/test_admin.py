# pylint: disable=redefined-outer-name
# Test functions take the fixture as a same-named parameter; that's the
# standard pytest pattern, not an actual shadowing bug.
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


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
    assert b"Run Import" in response.content


@pytest.mark.django_db
def test_import_data_view_post_runs_command(client, import_data_url):
    User = get_user_model()
    user = User.objects.create_superuser(username="admin", password="pass")
    client.force_login(user)

    with patch("django.core.management.call_command") as mock_call_command:

        def fake_call_command(*args, **kwargs):
            kwargs["stdout"].write("Created Set: Genetic Apex\n")
            kwargs["stdout"].write("Updated Card: Bulbasaur\n")
            kwargs["stderr"].write("Skipping card X: Set not found\n")

        mock_call_command.side_effect = fake_call_command

        response = client.post(import_data_url, follow=True)

    mock_call_command.assert_called_once()
    assert mock_call_command.call_args.args[0] == "import_data"
    assert response.redirect_chain == [
        (reverse("admin:tracker_pokemonset_changelist"), 302)
    ]
    assert b"1 created, 1 updated" in response.content
    assert b"1 row(s) skipped" in response.content
