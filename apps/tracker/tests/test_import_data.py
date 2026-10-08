from datetime import date

import pytest

from apps.tracker.management.commands.import_data import Command
from apps.tracker.models.cards import (
    Card,
    CardNameTranslation,
    Generation,
    Pack,
    PokemonSet,
    Rarity,
)


@pytest.mark.django_db
def test_import_card_translations_derives_ex_variant(tmp_path):
    pset = PokemonSet.objects.create(
        number="A1", name="Genetic Apex", release_date=date(2024, 1, 1)
    )
    rarity = Rarity.objects.create(name="rare", display_name="R", order=1)
    base_card = Card.objects.create(set=pset, number="001", name="Absol", rarity=rarity)
    ex_card = Card.objects.create(
        set=pset, number="002", name="Absol ex", rarity=rarity
    )

    csv_path = tmp_path / "card_translations.csv"
    csv_path.write_text(
        "card_english_name,card_german_name\nAbsol,Absol\n", encoding="utf-8"
    )

    Command().import_card_translations(str(csv_path))

    assert (
        CardNameTranslation.objects.get(
            card=base_card, language_code="de"
        ).localized_name
        == "Absol"
    )
    assert (
        CardNameTranslation.objects.get(card=ex_card, language_code="de").localized_name
        == "Absol-ex"
    )


@pytest.mark.django_db
def test_import_cards_uses_set_generation_for_new_and_existing_packs(tmp_path):
    g1 = Generation.objects.create(name="G1", display_name="Generation 1")
    g4 = Generation.objects.create(name="G4", display_name="Generation 4")
    pset = PokemonSet.objects.create(
        number="A1", name="Genetic Apex", release_date=date(2024, 1, 1), generation=g1
    )
    Rarity.objects.create(name="common", display_name="C", order=1)
    # An existing pack that was wrongly assigned the newest generation.
    Pack.objects.create(set=pset, name="Mewtwo", rarity_version=g4)

    csv_path = tmp_path / "cards.csv"
    csv_path.write_text(
        "set_number,number,card,pack,rarity\n"
        "A1,001,Bulbasaur,Mewtwo,common\n"
        "A1,002,Ivysaur,Pikachu|Charizard,common\n",
        encoding="utf-8",
    )

    Command().import_cards(str(csv_path))

    assert set(
        Pack.objects.filter(set=pset).values_list("name", "rarity_version_id")
    ) == {("Mewtwo", "G1"), ("Pikachu", "G1"), ("Charizard", "G1")}
