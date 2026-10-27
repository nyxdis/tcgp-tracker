# pylint: disable=redefined-outer-name
# Test functions take the fixture as a same-named parameter; that's the
# standard pytest pattern, not an actual shadowing bug.
from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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
from apps.tracker.models.imports import DataImport


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


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A minimal data/ directory with one generation, set and card."""
    files = {
        "rarities.csv": "name,display_name,order\ncommon,C,1\n",
        "generations.csv": "name,display_name,description\nG1,Generation 1,\n",
        "pack_types.csv": (
            "generation,pack_type,display_name,slot_count,"
            "occurrence_probability,description\n"
        ),
        "rarity_probabilities.csv": (
            "generation,pack_type,rarity,is_foil,probability_slot1,"
            "probability_slot2,probability_slot3,probability_slot4,"
            "probability_slot5,probability_slot6\n"
        ),
        "sets.csv": "number,name,release_date,generation\nA1,Genetic Apex,2024-10-30,G1\n",
        "cards.csv": "set_number,number,card,pack,rarity,is_foil\nA1,001,Bulbasaur,,common,0\n",
        "set_translations.csv": "english_name,german_name\n",
        "pack_translations.csv": "set_english_name,pack_english_name,pack_german_name\n",
        "card_translations.csv": "card_english_name,card_german_name\n",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        "apps.tracker.management.commands.import_data.DATA_DIR", f"{tmp_path}/"
    )
    return tmp_path


@pytest.mark.django_db
def test_full_import_records_fingerprint(data_dir):
    call_command("import_data", stdout=StringIO())

    assert Card.objects.filter(set__number="A1", number="001").exists()
    assert DataImport.objects.count() == 1


@pytest.mark.django_db
def test_if_changed_skips_unchanged_data(data_dir):
    call_command("import_data", stdout=StringIO())
    Card.objects.all().delete()

    out = StringIO()
    call_command("import_data", "--if-changed", stdout=out)

    assert "unchanged" in out.getvalue()
    assert not Card.objects.exists()
    assert DataImport.objects.count() == 1


@pytest.mark.django_db
def test_if_changed_imports_changed_data(data_dir):
    call_command("import_data", stdout=StringIO())
    with open(data_dir / "cards.csv", "a", encoding="utf-8") as f:
        f.write("A1,002,Ivysaur,,common,0\n")

    call_command("import_data", "--if-changed", stdout=StringIO())

    assert Card.objects.filter(set__number="A1", number="002").exists()
    assert DataImport.objects.count() == 2


@pytest.mark.django_db
def test_if_changed_imports_when_nothing_was_imported_yet(data_dir):
    call_command("import_data", "--if-changed", stdout=StringIO())

    assert Card.objects.exists()
    assert DataImport.objects.count() == 1


@pytest.mark.django_db
def test_partial_import_records_no_fingerprint(data_dir):
    call_command("import_data", "--rarities", str(data_dir / "rarities.csv"))

    assert not DataImport.objects.exists()


def test_if_changed_rejects_file_options(data_dir):
    with pytest.raises(CommandError):
        call_command(
            "import_data", "--if-changed", "--sets", str(data_dir / "sets.csv")
        )
