# pylint: disable=protected-access
"""Tests for the flibustier sync's foil handling (no network access)."""

from io import StringIO

from apps.tracker.management.commands import sync_flibustier
from apps.tracker.management.commands.sync_flibustier import (
    Command,
    _collect_card_translations,
    _collect_set_translations,
    _flib_german_card_names,
    _is_foil_print,
    _pool_key,
    _to_local_german_style,
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


def test_known_overrides_are_dropped_only_for_the_recorded_flibustier_value(
    monkeypatch,
):
    # The A4b differences these entries described have since been fixed
    # upstream; they're kept here as example data.
    monkeypatch.setattr(
        sync_flibustier,
        "KNOWN_PACK_TYPE_OVERRIDES",
        {
            ("G3", "god"): {
                "flib_occurrence": 0.0005,
                "flib_slot_count": 5,
                "reason": "the in-game A4b god pack has 4 cards",
            }
        },
    )
    monkeypatch.setattr(
        sync_flibustier,
        "KNOWN_RARITY_PROBABILITY_OVERRIDES",
        {
            ("G3", "normal", "rare", "1"): {
                "flib_slots": (0.0, 0.0, 0.203295, 0.0, 0.0, 0.0),
                "reason": "in-game A4b slot 3 is 0.359% per foil ♢♢♢ card",
            }
        },
    )
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


def _flib_card(set_code, number, name, rarity="C"):
    return {"set": set_code, "number": number, "name": name, "rarity": rarity}


def test_collect_cards_skips_anomaly_and_warns_about_unknown_rarities():
    cmd = Command(stdout=StringIO())
    cards = [
        {**_flib_card("SP1", 1, "Bulbasaur", "AR"), "image": "x_00_y.webp"},
        {**_flib_card("SP1", -1, "Mew", "AN"), "image": "x_00_y.webp"},
        {**_flib_card("SP1", 2, "Ivysaur", "ZZ"), "image": "x_00_y.webp"},
    ]

    new_cards, mismatches = cmd._collect_cards(cards, {}, {"SP1": {"generation": "G4"}})

    assert [c["card"] for c in new_cards] == ["Bulbasaur"]
    assert not mismatches
    output = cmd.stdout.getvalue()
    assert "unknown rarity code 'ZZ'" in output and "SP1 #2 Ivysaur" in output
    assert "Mew" not in output


def test_to_local_german_style_converts_ex_and_mega_spelling():
    assert _to_local_german_style("Charizard ex", "Glurak ex") == "Glurak-ex"
    assert (
        _to_local_german_style("Mega Charizard X ex", "Mega Glurak X ex")
        == "Mega-Glurak X-ex"
    )
    # Only converted when the English name has the affix too.
    assert _to_local_german_style("Exeggcute", "Owei") == "Owei"


def test_flib_german_card_names_skips_promos_and_anomalies():
    cards = [
        _flib_card("A1", 4, "Charizard ex", "RR"),
        _flib_card("PROMO-A", 1, "Potion"),
        _flib_card("SP1", -1, "Mew", "AN"),
    ]
    cards_de = [
        _flib_card("A1", 4, "Glurak ex", "RR"),
        _flib_card("PROMO-A", 1, "Trank"),
        _flib_card("SP1", -1, "Mew", "AN"),
    ]

    assert _flib_german_card_names(cards, cards_de) == {"Charizard ex": {"Glurak-ex"}}


def test_collect_card_translations_adds_base_names_before_variants():
    flib = {
        "Amoonguss": {"Hutsassa"},
        "Amoonguss ex": {"Hutsassa-ex"},
        "Mega Mewtwo X ex": {"Mega-Mewtu X-ex"},
        "Haunter": {"Alpollo"},
        "Pikachu": {"Pikachu", "Pikachuu"},
    }
    existing = {"Haunter": "Apollo"}
    names = ["Amoonguss ex", "Amoonguss", "Mega Mewtwo X ex", "Haunter", "Pikachu"]

    new_rows, mismatches, conflicts = _collect_card_translations(names, flib, existing)

    # "Amoonguss ex" is derived from the new base row, so it gets none itself.
    assert new_rows == [
        {"card_english_name": "Amoonguss", "card_german_name": "Hutsassa"},
        {
            "card_english_name": "Mega Mewtwo X ex",
            "card_german_name": "Mega-Mewtu X-ex",
        },
    ]
    assert mismatches == [
        {
            "kind": "card",
            "english": "Haunter",
            "local": "Apollo",
            "flib_german": "Alpollo",
        }
    ]
    assert conflicts == [{"english": "Pikachu", "flib_german": ["Pikachu", "Pikachuu"]}]


def test_collect_set_translations_only_for_local_sets():
    all_sets = [
        {"code": "C1", "name": {"en": "Dual Fusion", "de": "Doppelte Fusion"}},
        {"code": "A1", "name": {"en": "Genetic Apex", "de": "Unschlagbare Gene"}},
        {"code": "B1", "name": {"en": "Mega Rising", "de": "Mega-Aufstieg"}},
        {"code": "Z9", "name": {"en": "Not Synced", "de": "Nicht synchronisiert"}},
        {"code": "PROMO-A", "name": {"en": "Promo-A", "de": "Promo-A"}},
    ]
    existing = {"Dual Fusion": "Duale Fusion", "Genetic Apex": "Unschlagbare Gene"}

    new_rows, mismatches = _collect_set_translations(
        all_sets, ["Dual Fusion", "Genetic Apex", "Mega Rising", "Promo-A"], existing
    )

    assert new_rows == [{"english_name": "Mega Rising", "german_name": "Mega-Aufstieg"}]
    assert mismatches == [
        {
            "kind": "set",
            "english": "Dual Fusion",
            "local": "Duale Fusion",
            "flib_german": "Doppelte Fusion",
        }
    ]


def test_known_translation_overrides_are_dropped_only_for_the_recorded_value():
    cmd = Command(stdout=StringIO())
    known = {
        "kind": "set",
        "english": "Dual Fusion",
        "local": "Duale Fusion",
        "flib_german": "Doppelte Fusion",
    }
    changed = {**known, "flib_german": "Duale Fusion II"}

    assert cmd._drop_known_translation_overrides([known, changed]) == [changed]
    assert "known difference kept: set Dual Fusion" in cmd.stdout.getvalue()
