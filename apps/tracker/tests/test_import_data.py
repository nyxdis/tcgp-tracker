from datetime import date

import pytest

from apps.tracker.management.commands.import_data import Command
from apps.tracker.models.cards import Card, CardNameTranslation, PokemonSet, Rarity


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
