# pylint: disable=redefined-outer-name
# Test functions take fixtures as same-named parameters (standard pytest pattern).
"""Tests for reprints sharing their original's collection entry."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.tracker import collection
from apps.tracker.models.cards import (
    Card,
    Generation,
    Pack,
    PackType,
    PokemonSet,
    Rarity,
    RarityProbability,
)
from apps.tracker.models.users import UserCard
from apps.tracker.utils import prob_at_least_one_new_card


@pytest.fixture
def user(db, client):
    user = get_user_model().objects.create_user(username="collector", password="x")
    client.force_login(user)
    return user


@pytest.fixture
def generation(db):
    return Generation.objects.create(name="G5", display_name="Generation 5")


@pytest.fixture
def common(db):
    return Rarity.objects.create(name="common", display_name="C", order=1)


@pytest.fixture
def cards(generation, common):
    """B1 #001 Bulbasaur, reprinted as B4b #001, plus B4b's own #002."""
    b1 = PokemonSet.objects.create(
        number="B1", name="Mega Rising", release_date=date(2026, 1, 1)
    )
    b4b = PokemonSet.objects.create(
        number="B4b", name="Deluxe Pack: Mega", release_date=date(2026, 9, 30)
    )
    original = Card.objects.create(
        set=b1, number="001", name="Bulbasaur", rarity=common
    )
    reprint = Card.objects.create(
        set=b4b, number="001", name="Bulbasaur", rarity=common, reprint_of=original
    )
    new_card = Card.objects.create(set=b4b, number="002", name="Ivysaur", rarity=common)
    pack = Pack.objects.create(
        set=b4b, name="Deluxe Pack Mega", rarity_version=generation
    )
    reprint.packs.add(pack)
    new_card.packs.add(pack)
    return {"original": original, "reprint": reprint, "new": new_card, "pack": pack}


def test_owning_the_original_owns_the_reprint(user, cards):
    UserCard.objects.create(user=user, card=cards["original"], quantity=2)

    assert collection.owned_card_ids(user) == {
        cards["original"].id,
        cards["reprint"].id,
    }
    quantities = collection.owned_quantities(user, list(Card.objects.all()))
    assert quantities == {
        cards["original"].id: 2,
        cards["reprint"].id: 2,
        cards["new"].id: 0,
    }


def test_collecting_a_reprint_stores_it_on_the_original(user, cards):
    collection.collect(user, cards["reprint"])

    assert list(UserCard.objects.values_list("card_id", flat=True)) == [
        cards["original"].id
    ]

    collection.uncollect(user, cards["reprint"].id)

    assert not UserCard.objects.exists()


def test_merge_moves_reprint_entries_and_keeps_the_higher_quantity(user, cards):
    other = get_user_model().objects.create_user(username="other", password="x")
    # user has both prints recorded; other only the reprint.
    UserCard.objects.create(user=user, card=cards["original"], quantity=1)
    UserCard.objects.create(user=user, card=cards["reprint"], quantity=3)
    UserCard.objects.create(user=other, card=cards["reprint"], quantity=2)

    assert collection.merge_reprint_entries() == 2

    assert set(
        UserCard.objects.values_list("user__username", "card_id", "quantity")
    ) == {
        ("collector", cards["original"].id, 3),
        ("other", cards["original"].id, 2),
    }


def test_new_card_odds_treat_a_reprint_of_an_owned_card_as_owned(
    user, generation, common, cards
):
    normal = PackType.objects.create(
        generation=generation,
        name="normal",
        display_name="Normal",
        slot_count=1,
        occurrence_probability=1.0,
    )
    RarityProbability.objects.create(
        rarity=common, generation=generation, pack_type=normal, probability_slot1=1.0
    )

    assert prob_at_least_one_new_card(cards["pack"], user) == 1.0

    # Owning the B1 original makes the B4b reprint not new: only Ivysaur is.
    UserCard.objects.create(user=user, card=cards["original"])
    assert prob_at_least_one_new_card(cards["pack"], user) == 0.5


def test_set_detail_collects_a_reprint_on_its_original(client, user, cards):
    response = client.post(
        reverse("set_detail", args=["B4b"]),
        {"card_id": cards["reprint"].id, "action": "collect"},
    )
    assert response.status_code == 302
    assert list(UserCard.objects.values_list("card_id", flat=True)) == [
        cards["original"].id
    ]

    for set_number in ("B1", "B4b"):
        response = client.get(reverse("set_detail", args=[set_number]))
        shown = {c.number: c.collected_quantity for c in response.context["cards"]}
        assert shown["001"] == 1


def test_home_and_pack_list_count_reprints_of_owned_cards(client, user, cards):
    UserCard.objects.create(user=user, card=cards["original"])

    home = client.get(reverse("home"), {"series": "B"})
    progress = {e["set"].number: e["collected"] for e in home.context["sets"]}
    assert progress == {"B1": 1, "B4b": 1}

    packs = client.get(reverse("pack_list"))
    entries = [
        entry for _set, group in packs.context["grouped_packs"] for entry in group
    ]
    assert [(e["owned"], e["total"]) for e in entries] == [(1, 2)]


def test_public_profile_counts_reprints_of_owned_cards(client, user, cards):
    UserCard.objects.create(user=user, card=cards["original"])

    response = client.get(reverse("public_profile", args=[user.username]))

    assert response.context["total_collected"] == 2
