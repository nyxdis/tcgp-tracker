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
)
from apps.tracker.models.users import UserCard
from apps.tracker.utils import prob_at_least_one_new_card


@pytest.mark.django_db
def test_no_new_cards_returns_zero_probability():
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="pass")

    generation = Generation.objects.create(name="G1", display_name="Generation 1")
    pack_type = PackType.objects.create(
        generation=generation,
        name="normal",
        display_name="Normal",
        slot_count=5,
        occurrence_probability=1.0,
    )
    pset = PokemonSet.objects.create(
        number="001", name="Base Set", release_date=date(2024, 1, 1)
    )

    # Rarities
    rarity_names = ["Common", "Uncommon", "Rare", "Ultra Rare"]
    rarities = []
    for i, rname in enumerate(rarity_names):
        r = Rarity.objects.create(name=rname, display_name=f"R{i}", order=i)
        RarityProbability.objects.create(
            rarity=r,
            generation=generation,
            pack_type=pack_type,
            probability_slot1=0.25,
            probability_slot2=0.25,
            probability_slot3=0.25,
            probability_slot4=0.25,
            probability_slot5=0.25,
        )
        rarities.append(r)

    # Pack
    pack = Pack.objects.create(set=pset, name="Starter Pack", rarity_version=generation)

    # Eine Karte pro Rarity (alle werden dem User gegeben)
    for rarity in rarities:
        card = Card.objects.create(
            set=pset,
            number=f"C{rarity.order}",
            name=f"{rarity.name} Card",
            rarity=rarity,
        )
        card.packs.add(pack)
        UserCard.objects.create(user=user, card=card, quantity=1)

    # Testfunktion aufrufen
    prob = prob_at_least_one_new_card(pack, user)

    # Erwartung: 0.0 % Chance auf eine neue Karte
    assert prob == 0.0
