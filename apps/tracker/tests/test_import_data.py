from datetime import date

import pytest

from apps.tracker.management.commands.import_data import Command
from apps.tracker.models.cards import (
    Card,
    CardNameTranslation,
    Generation,
    Pack,
    PackType,
    PokemonSet,
    Rarity,
    RarityProbability,
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


@pytest.mark.django_db
def test_import_cards_reads_optional_is_foil_column(tmp_path):
    g3 = Generation.objects.create(name="G3", display_name="Generation 3")
    pset = PokemonSet.objects.create(
        number="A4b",
        name="Deluxe Pack ex",
        release_date=date(2025, 9, 30),
        generation=g3,
    )
    Rarity.objects.create(name="common", display_name="C", order=1)

    with_flag = tmp_path / "cards.csv"
    with_flag.write_text(
        "set_number,number,card,pack,rarity,is_foil\n"
        "A4b,001,Bulbasaur,Deluxepack,common,0\n"
        "A4b,002,Bulbasaur,Deluxepack,common,1\n",
        encoding="utf-8",
    )
    Command().import_cards(str(with_flag))
    assert dict(Card.objects.filter(set=pset).values_list("number", "is_foil")) == {
        "001": False,
        "002": True,
    }

    without_flag = tmp_path / "legacy.csv"
    without_flag.write_text(
        "set_number,number,card,pack,rarity\nA4b,003,Ivysaur,Deluxepack,common\n",
        encoding="utf-8",
    )
    Command().import_cards(str(without_flag))
    assert not Card.objects.get(set=pset, number="003").is_foil


@pytest.mark.django_db
def test_import_rarity_probabilities_keeps_standard_and_foil_rows(tmp_path):
    g3 = Generation.objects.create(name="G3", display_name="Generation 3")
    PackType.objects.create(
        generation=g3,
        name="normal",
        display_name="Deluxe Pack",
        slot_count=4,
        occurrence_probability=0.9995,
    )
    Rarity.objects.create(name="rare", display_name="R", order=3)

    csv_path = tmp_path / "rarity_probabilities.csv"
    header = "generation,pack_type,rarity,is_foil," + ",".join(
        f"probability_slot{i}" for i in range(1, 7)
    )
    csv_path.write_text(
        f"{header}\n"
        "G3,normal,rare,0,0,0,0.3,0,0,0\n"
        "G3,normal,rare,1,0,0,0.1,0,0,0\n",
        encoding="utf-8",
    )
    # Importing twice must replace, not duplicate or merge, each row.
    Command().import_rarity_probabilities(str(csv_path))
    Command().import_rarity_probabilities(str(csv_path))

    assert dict(
        RarityProbability.objects.values_list("is_foil", "probability_slot3")
    ) == {False: 0.3, True: 0.1}
