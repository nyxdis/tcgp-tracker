# pylint: disable=redefined-outer-name
# Test functions take the fixture as a same-named parameter; that's the
# standard pytest pattern, not an actual shadowing bug.
import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.tracker.models.cards import Card, PokemonSet, Rarity
from apps.tracker.models.users import UserCard


@pytest.fixture
def user(client):
    user = get_user_model().objects.create_user(username="collector", password="pass")
    client.force_login(user)
    return user


@pytest.fixture
def sets():
    today = timezone.localdate()
    return {
        number: PokemonSet.objects.create(
            number=number,
            name=number,
            release_date=today - datetime.timedelta(days=age),
        )
        for number, age in (("A1", 300), ("A2a", 200), ("B1", 100), ("B2b", 10))
    }


@pytest.mark.parametrize(
    "number, series", [("A1", "A"), ("A2a", "A"), ("B4b", "B"), ("C1", "C")]
)
def test_series_is_number_prefix(number, series):
    assert PokemonSet(number=number).series == series


@pytest.mark.django_db
def test_home_defaults_to_newest_series(client, user, sets):
    response = client.get(reverse("home"))

    assert response.context["selected_series"] == "B"
    assert response.context["series_options"] == ["B", "A"]
    assert [e["set"].number for e in response.context["sets"]] == ["B2b", "B1"]


@pytest.mark.django_db
def test_home_default_ignores_unreleased_series(client, user, sets):
    PokemonSet.objects.create(
        number="C1",
        name="C1",
        release_date=timezone.localdate() + datetime.timedelta(days=7),
    )

    response = client.get(reverse("home"))

    assert response.context["series_options"] == ["C", "B", "A"]
    assert response.context["selected_series"] == "B"


@pytest.mark.django_db
def test_home_filters_by_series(client, user, sets):
    response = client.get(reverse("home"), {"series": "A"})

    assert [e["set"].number for e in response.context["sets"]] == ["A2a", "A1"]


@pytest.mark.django_db
def test_home_all_shows_every_set(client, user, sets):
    response = client.get(reverse("home"), {"series": "all"})

    assert len(response.context["sets"]) == 4


@pytest.mark.django_db
def test_home_unknown_series_falls_back_to_default(client, user, sets):
    response = client.get(reverse("home"), {"series": "Z"})

    assert response.context["selected_series"] == "B"


@pytest.mark.django_db
def test_home_overall_progress_follows_series(client, user, sets):
    rarity = Rarity.objects.create(
        name="one_diamond", display_name="One Diamond", order=1
    )
    a_card = Card.objects.create(set=sets["A1"], number=1, name="a", rarity=rarity)
    Card.objects.create(set=sets["A1"], number=2, name="a2", rarity=rarity)
    Card.objects.create(set=sets["B1"], number=1, name="b", rarity=rarity)
    UserCard.objects.create(user=user, card=a_card)

    series_a = client.get(reverse("home"), {"series": "A"}).context
    series_b = client.get(reverse("home"), {"series": "B"}).context
    every = client.get(reverse("home"), {"series": "all"}).context

    assert (series_a["total_collected"], series_a["total_cards"]) == (1, 2)
    assert (series_b["total_collected"], series_b["total_cards"]) == (0, 1)
    assert (every["total_collected"], every["total_cards"]) == (1, 3)


@pytest.mark.django_db
def test_home_collect_redirect_keeps_series_and_query(client, user, sets):
    rarity = Rarity.objects.create(
        name="one_diamond", display_name="One Diamond", order=1
    )
    card = Card.objects.create(set=sets["A1"], number=1, name="a", rarity=rarity)

    response = client.post(
        reverse("home"),
        {"card_id": card.id, "action": "collect", "series": "A", "q": "a b"},
    )

    assert response.status_code == 302
    assert response.url == f"{reverse('home')}?series=A&q=a+b"
