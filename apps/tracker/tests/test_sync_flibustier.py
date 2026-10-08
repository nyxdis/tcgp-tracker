"""Tests for the flibustier sync's foil handling (no network access)."""

from io import StringIO

from apps.tracker.management.commands.sync_flibustier import (
    Command,
    _is_foil_print,
    _pool_key,
)


def _card(rarity, variant):
    return {"rarity": rarity, "image": f"cPK_10_000010_{variant}_FUSHIGIDANE_C.webp"}


def test_is_foil_print_only_for_deluxe_base_rarity_variants():
    assert _is_foil_print(_card("C", "01"), "G3")
    assert not _is_foil_print(_card("C", "00"), "G3")
    # Alternate-art variants in regular sets are not foil prints.
    assert not _is_foil_print(_card("C", "01"), "G1")
    # Star rarities have no parallel-foil prints.
    assert not _is_foil_print(_card("AR", "01"), "G3")


def test_pool_key_maps_foil_codes_to_base_rarity():
    assert _pool_key("RF") == ("rare", True)
    assert _pool_key("R") == ("rare", False)
    assert _pool_key("SAR") == ("special_art", False)


def test_slot_mismatches_split_foil_and_sum_shared_rows():
    cmd = Command(stdout=StringIO())
    pack_data = {
        "slots": {
            "1": {"C": 100.0},
            "2": {"R": 60.0, "RF": 10.0, "SR": 20.0, "SAR": 10.0},
        }
    }
    local = {
        ("G3", "normal", "common", "0"): _row(1),
        ("G3", "normal", "rare", "0"): _row(0, 0.6),
        ("G3", "normal", "rare", "1"): _row(0, 0.1),
        # SR + SAR both map to special_art and must be compared summed.
        ("G3", "normal", "special_art", "0"): _row(0, 0.3),
    }

    assert not cmd._collect_slot_mismatches("G3", "normal", [("A4b", pack_data)], local)

    local[("G3", "normal", "rare", "1")] = _row(0, 0.2)
    mismatches = cmd._collect_slot_mismatches(
        "G3", "normal", [("A4b", pack_data)], local
    )
    assert [(m["rarity"], m["is_foil"]) for m in mismatches] == [("rare", True)]


def _row(*slots):
    slots = list(slots) + [0] * (6 - len(slots))
    return {f"probability_slot{i}": str(v) for i, v in enumerate(slots, start=1)}


def _prob_mismatch(key, flib_slots):
    generation, pack_type, rarity, is_foil = key
    return {
        "key": key,
        "generation": generation,
        "pack_type": pack_type,
        "rarity": rarity,
        "is_foil": is_foil == "1",
        "flib_slots": list(flib_slots),
    }


def test_known_overrides_are_dropped_only_for_the_recorded_flibustier_value():
    cmd = Command(stdout=StringIO())
    key = ("G3", "normal", "rare", "1")
    known = _prob_mismatch(key, (0, 0, 0.203295, 0, 0, 0))
    changed = _prob_mismatch(key, (0, 0, 0.1, 0, 0, 0))
    other = _prob_mismatch(("G1", "normal", "rare", "0"), (0, 0, 0.203295, 0, 0, 0))
    god = {
        "key": ("G3", "god"),
        "generation": "G3",
        "pack_type": "god",
        "flib_occurrence": 0.0005,
        "flib_slot_count": 5,
    }

    pack_types, probs = cmd._drop_known_overrides([god], [known, changed, other])

    assert not pack_types
    assert probs == [changed, other]
    assert "known difference kept: G3/normal/rare (foil)" in cmd.stdout.getvalue()
