# pylint: disable=redefined-outer-name,too-many-arguments,too-many-positional-arguments
# Test functions take fixtures as same-named parameters (standard pytest pattern).
"""Tests for the pull probability calculation."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.tracker.models.cards import (
    Card,
    Generation,
    Pack,
    PackType,
    PokemonSet,
    Rarity,
    RarityProbability,
    god_pack_slot_table,
)
from apps.tracker.models.users import UserCard
from apps.tracker.utils import (
    load_rarity_tables,
    prob_at_least_one_new_card,
    prob_new_card_any_pack_type,
)

ZERO = (0.0,) * 6


def _rarity(name, order):
    return Rarity.objects.get_or_create(
        name=name, defaults={"display_name": str(order), "order": order}
    )[0]


def _table(generation, pack_type, rows):
    """Create RarityProbability rows from ``{rarity: (slot1..slot6)}``.

    A key may also be ``(rarity, is_foil)`` for a parallel-foil row.
    """
    for key, probs in rows.items():
        rarity, is_foil = key if isinstance(key, tuple) else (key, False)
        probs = tuple(probs) + ZERO[len(probs) :]
        RarityProbability.objects.create(
            rarity=rarity,
            is_foil=is_foil,
            generation=generation,
            pack_type=pack_type,
            **{f"probability_slot{i + 1}": p for i, p in enumerate(probs)},
        )


def _cards(pset, pack, rarity, count, prefix, is_foil=False):
    cards = []
    for i in range(count):
        card = Card.objects.create(
            set=pset,
            number=f"{prefix}{i:03}",
            name=f"{prefix}{i}",
            rarity=rarity,
            is_foil=is_foil,
        )
        card.packs.add(pack)
        cards.append(card)
    return cards


def _own(user, cards):
    for card in cards:
        UserCard.objects.create(user=user, card=card, quantity=1)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="tester", password="x")


@pytest.fixture
def generation(db):
    return Generation.objects.create(name="G1", display_name="Generation 1")


@pytest.fixture
def pset(generation):
    return PokemonSet.objects.create(
        number="T1",
        name="Test Set",
        release_date=date(2024, 1, 1),
        generation=generation,
    )


@pytest.fixture
def pack(pset, generation):
    return Pack.objects.create(set=pset, name="Test Pack", rarity_version=generation)


@pytest.fixture
def normal(generation):
    return PackType.objects.create(
        generation=generation,
        name="normal",
        display_name="Normal",
        slot_count=5,
        occurrence_probability=0.9995,
    )


@pytest.fixture
def god(generation):
    return PackType.objects.create(
        generation=generation,
        name="god",
        display_name="God Pack",
        slot_count=5,
        occurrence_probability=0.0005,
    )


def test_all_cards_owned_gives_zero(user, generation, pset, pack, normal):
    rarities = [_rarity(n, i) for i, n in enumerate(["common", "uncommon", "rare"])]
    _table(generation, normal, {r: (1 / 3,) * 5 for r in rarities})
    for r in rarities:
        _own(user, _cards(pset, pack, r, 2, r.name))

    assert prob_at_least_one_new_card(pack, user) == 0.0


def test_nothing_owned_gives_one(user, generation, pset, pack, normal):
    common = _rarity("common", 1)
    _table(generation, normal, {common: (1,) * 5})
    _cards(pset, pack, common, 3, "c")

    assert prob_at_least_one_new_card(pack, user) == 1.0


def test_hand_computed_value(user, generation, pset, pack, normal):
    """Two slots; slot 1 always common (half owned), slot 2 common or rare."""
    common, rare = _rarity("common", 1), _rarity("rare", 3)
    normal.slot_count = 2
    normal.save()
    _table(generation, normal, {common: (1, 0.8), rare: (0, 0.2)})
    commons = _cards(pset, pack, common, 4, "c")
    rares = _cards(pset, pack, rare, 2, "r")
    _own(user, commons[:2])  # 2/4 commons owned
    _own(user, rares)  # 2/2 rares owned

    # slot1: P(no new) = 1 * 0.5 ; slot2: 0.8 * 0.5 + 0.2 * 1 = 0.6
    expected = round(1 - 0.5 * 0.6, 4)
    assert prob_at_least_one_new_card(pack, user) == expected


def test_only_active_slots_are_used(user, generation, pset, pack, normal):
    """A 4-slot pack type must ignore slot 5 even if the table has a value there."""
    common = _rarity("common", 1)
    normal.slot_count = 4
    normal.save()
    _table(generation, normal, {common: (1, 1, 1, 1, 1)})
    commons = _cards(pset, pack, common, 2, "c")
    _own(user, commons[:1])

    assert prob_at_least_one_new_card(pack, user) == round(1 - 0.5**4, 4)


def test_missing_rarity_is_renormalised(user, generation, pset, pack, normal):
    """A rarity in the table with no cards in the pack must not inflate the chance."""
    common, shiny = _rarity("common", 1), _rarity("shiny_rare", 8)
    normal.slot_count = 1
    normal.save()
    _table(generation, normal, {common: (0.9,), shiny: (0.1,)})
    _own(user, _cards(pset, pack, common, 2, "c"))  # no shiny cards exist

    assert prob_at_least_one_new_card(pack, user) == 0.0


def test_slot_with_no_present_rarity_yields_nothing(
    user, generation, pset, pack, normal
):
    common, shiny = _rarity("common", 1), _rarity("shiny_rare", 8)
    normal.slot_count = 2
    normal.save()
    _table(generation, normal, {common: (1, 0), shiny: (0, 1)})
    _own(user, _cards(pset, pack, common, 2, "c"))

    assert prob_at_least_one_new_card(pack, user) == 0.0


def test_result_is_clamped_for_oversubscribed_table(
    user, generation, pset, pack, normal
):
    """Slot sums above 1 (bad data) must not produce a negative probability."""
    common, rare = _rarity("common", 1), _rarity("rare", 3)
    normal.slot_count = 1
    normal.save()
    _table(generation, normal, {common: (0.9,), rare: (0.3,)})
    _own(user, _cards(pset, pack, common, 1, "c"))
    _own(user, _cards(pset, pack, rare, 1, "r"))

    assert prob_at_least_one_new_card(pack, user) == 0.0


def test_god_pack_uses_pack_pool(user, generation, pset, pack, god):
    """God pack draws uniformly from the pack's eligible cards only."""
    other_pack = Pack.objects.create(set=pset, name="Other", rarity_version=generation)
    illu, crown = _rarity("illustration_rare", 5), _rarity("crown_rare", 10)
    common = _rarity("common", 1)
    _cards(pset, pack, common, 5, "c")  # not eligible
    _own(user, _cards(pset, pack, illu, 3, "i"))  # 3/3 owned
    crowns = _cards(pset, pack, crown, 1, "k")  # 0/1 owned
    _cards(pset, other_pack, illu, 10, "o")  # must not influence this pack

    # pool = 4 cards, P(crown) = 1/4 per slot, crown is the only new card
    expected = round(1 - (3 / 4) ** 5, 4)
    assert prob_at_least_one_new_card(pack, user, god) == expected

    _own(user, crowns)
    assert prob_at_least_one_new_card(pack, user, god) == 0.0


def test_god_pack_slot_table_shares_and_padding():
    table = god_pack_slot_table({"a": 3, "b": 1, "c": 0}, slot_count=4)
    assert table == {"a": [0.75] * 4 + [0.0] * 2, "b": [0.25] * 4 + [0.0] * 2}
    assert not god_pack_slot_table({"a": 0}, 5)


def test_weighted_over_pack_types(user, generation, pset, pack, normal, god):
    """Law of total probability across pack types."""
    common, crown = _rarity("common", 1), _rarity("crown_rare", 10)
    normal.slot_count = 1
    normal.save()
    god.slot_count = 1
    god.save()
    _table(generation, normal, {common: (1,)})
    _own(user, _cards(pset, pack, common, 1, "c"))
    _cards(pset, pack, crown, 1, "k")

    # normal pack: only commons, all owned -> 0 ; god pack: crown only -> 1
    assert prob_at_least_one_new_card(pack, user, normal) == 0.0
    assert prob_at_least_one_new_card(pack, user, god) == 1.0
    assert prob_new_card_any_pack_type(pack, user) == round(0.0005 / 1.0, 4)


def test_prefetched_inputs_match_queried(user, generation, pset, pack, normal, god):
    common, rare = _rarity("common", 1), _rarity("rare", 3)
    _table(generation, normal, {common: (1, 1, 1, 0.9, 0.6), rare: (0, 0, 0, 0.1, 0.4)})
    commons = _cards(pset, pack, common, 4, "c")
    _cards(pset, pack, rare, 2, "r")
    _own(user, commons[:3])

    queried = prob_new_card_any_pack_type(pack, user)
    prefetched = prob_new_card_any_pack_type(
        pack,
        user,
        pack_types=[normal, god],
        cards=list(pack.cards.all()),
        owned_card_ids={c.id for c in commons[:3]},
        rarity_tables=load_rarity_tables(generation),
    )
    assert queried == prefetched
    assert 0.0 < queried < 1.0


def test_no_cards_or_no_pack_type(user, generation, pset, pack):
    assert prob_at_least_one_new_card(pack, user) == 0.0
    assert prob_new_card_any_pack_type(pack, user) == 0.0


def test_foil_and_standard_prints_are_separate_pools(
    user, generation, pset, pack, normal
):
    """Deluxe packs draw standard prints in slot 1 and foil prints in slot 2."""
    common = _rarity("common", 1)
    normal.slot_count = 2
    normal.save()
    _table(generation, normal, {common: (1, 0), (common, True): (0, 1)})
    _own(user, _cards(pset, pack, common, 4, "c"))  # all standard owned
    foils = _cards(pset, pack, common, 4, "f", is_foil=True)
    _own(user, foils[:3])  # 3/4 foils owned

    # slot1: standard only, all owned -> 1 ; slot2: foil only -> 3/4
    assert prob_at_least_one_new_card(pack, user) == round(1 - 3 / 4, 4)


def test_load_rarity_tables_keys_by_rarity_and_foil(generation, normal):
    common = _rarity("common", 1)
    _table(generation, normal, {common: (1,), (common, True): (0, 1)})

    table = load_rarity_tables(generation)[normal.id]
    assert table[("common", False)][:2] == [1, 0]
    assert table[("common", True)][:2] == [0, 1]
