"""The shipped rarity tables in data/ must be valid probability distributions."""

from pathlib import Path

import pytest
from django.core.management import call_command

from apps.tracker.management.commands.import_data import Command

DATA = Path(__file__).resolve().parents[3] / "data"


@pytest.mark.django_db
def test_shipped_rarity_probabilities_sum_to_one_per_slot():
    cmd = Command()
    cmd.import_rarities(str(DATA / "rarities.csv"))
    cmd.import_generations(str(DATA / "generations.csv"))
    cmd.import_pack_types(str(DATA / "pack_types.csv"))
    cmd.import_rarity_probabilities(str(DATA / "rarity_probabilities.csv"))

    call_command("validate_probabilities", "--fail-fast")  # raises SystemExit on error
