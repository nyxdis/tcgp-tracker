"""German set and card names from the flibustier dataset (sets.json and
cards.de.json), for the sync_flibustier command.

German names are added to data/set_translations.csv and
data/card_translations.csv when this project has none yet. Existing German
names are never modified; where they disagree with flibustier they are listed
for review instead (KNOWN_*_TRANSLATION_OVERRIDES records verified
differences). flibustier writes "Glurak ex" and "Mega Glurak X ex" where this
project uses the official "Glurak-ex" and "Mega-Glurak X-ex", so its names
are converted before being compared or added. flibustier has no German pack
names, so data/pack_translations.csv must still be filled in by hand.
"""

from apps.tracker.card_name_rules import AFFIX_RULES, derive_translation
from apps.tracker.flibustier import (
    DATA_DIR,
    SKIPPED_RARITY_CODES,
    append_csv,
    is_promo,
    normalise_apostrophe,
    read_csv_as_dict,
)

# Verified German names that differ from flibustier's, keyed by English name.
# Each entry records the flibustier value it was checked against: if
# flibustier's value changes, the name is reported again.
KNOWN_SET_TRANSLATION_OVERRIDES = {
    "Dual Fusion": {
        "flib_german": "Doppelte Fusion",
        "reason": 'the official German name is "Duale Fusion"',
    },
    "Special Pack: First Partners": {
        "flib_german": "Erste Partner",
        "reason": '"Erste Partner" is the pack; the set is "Spezialpack: Erste Partner"',
    },
}
KNOWN_CARD_TRANSLATION_OVERRIDES: dict[str, dict] = {}

SET_TRANSLATION_FIELDS = ["english_name", "german_name"]
CARD_TRANSLATION_FIELDS = ["card_english_name", "card_german_name"]


def sync_german_names(command, all_sets, flib_card_names, set_names, card_names):
    """Add German set and card names this project has none for yet, and
    report the ones that disagree with flibustier.

    *flib_card_names* is the result of flib_german_card_names(); *set_names*
    and *card_names* are the English names in this project's data. Output
    goes to the management *command*'s stdout.
    """
    out, style = command.stdout, command.style
    out.write("\nChecking German names…")
    existing_sets = {
        english: row["german_name"].strip()
        for english, row in read_csv_as_dict(
            DATA_DIR / "set_translations.csv", ("english_name",)
        ).items()
    }
    existing_cards = {
        english.strip(): row["card_german_name"].strip()
        for english, row in read_csv_as_dict(
            DATA_DIR / "card_translations.csv", ("card_english_name",)
        ).items()
    }

    new_set_rows, set_mismatches = collect_set_translations(
        all_sets, set_names, existing_sets
    )
    new_card_rows, card_mismatches, conflicts = collect_card_translations(
        card_names, flib_card_names, existing_cards
    )
    append_csv(DATA_DIR / "set_translations.csv", SET_TRANSLATION_FIELDS, new_set_rows)
    append_csv(
        DATA_DIR / "card_translations.csv", CARD_TRANSLATION_FIELDS, new_card_rows
    )

    if new_set_rows or new_card_rows:
        out.write(
            style.SUCCESS(
                f"Added {len(new_set_rows)} German set name(s) and "
                f"{len(new_card_rows)} German card name(s) from flibustier:"
            )
        )
        for row in new_set_rows:
            out.write(f"  set {row['english_name']}: {row['german_name']}")
        for row in new_card_rows:
            out.write(f"  card {row['card_english_name']}: {row['card_german_name']}")

    mismatches, kept = drop_known_overrides(set_mismatches + card_mismatches)
    for m, reason in kept:
        out.write(f"  known difference kept: {m['kind']} {m['english']} ({reason})")
    if mismatches:
        out.write(
            style.WARNING(
                f"\n{len(mismatches)} German name(s) disagree with "
                "flibustier. Not auto-fixed, please check the official name "
                "and either correct data/*_translations.csv or record it in "
                "KNOWN_*_TRANSLATION_OVERRIDES:"
            )
        )
        for m in mismatches:
            out.write(
                f"  {m['kind']} {m['english']}: local={m['local']} "
                f"flibustier={m['flib_german']}"
            )
    for c in conflicts:
        out.write(
            style.WARNING(
                f"  flibustier has several German names for card "
                f"{c['english']} ({', '.join(c['flib_german'])}), not added"
            )
        )

    untranslated = _untranslated_names(
        set_names,
        card_names,
        existing_sets | {r["english_name"]: r["german_name"] for r in new_set_rows},
        existing_cards
        | {r["card_english_name"]: r["card_german_name"] for r in new_card_rows},
    )
    if untranslated:
        out.write(
            style.WARNING(
                f"\n{len(untranslated)} name(s) have no German name yet and "
                "flibustier has none either; add them by hand to "
                "data/set_translations.csv / data/card_translations.csv:"
            )
        )
        for name in untranslated:
            out.write(f"  {name}")


def _untranslated_names(set_names, card_names, set_lookup, card_lookup) -> list:
    """Local set and card names that still have no German name."""
    return [
        f"set {name}" for name in sorted(set(set_names)) if name not in set_lookup
    ] + [
        f"card {name}"
        for name in sorted(set(card_names))
        if derive_translation(name, card_lookup) is None
    ]


def drop_known_overrides(mismatches: list) -> tuple[list, list]:
    """Split off mismatches listed in KNOWN_*_TRANSLATION_OVERRIDES.

    Returns the remaining mismatches and (mismatch, reason) for each known one.
    """
    known_by_kind = {
        "set": KNOWN_SET_TRANSLATION_OVERRIDES,
        "card": KNOWN_CARD_TRANSLATION_OVERRIDES,
    }
    remaining, kept = [], []
    for m in mismatches:
        known = known_by_kind[m["kind"]].get(m["english"])
        if known is not None and known["flib_german"] == m["flib_german"]:
            kept.append((m, known["reason"]))
        else:
            remaining.append(m)
    return remaining, kept


def to_local_german_style(english: str, german: str) -> str:
    """Convert flibustier's "Glurak ex" / "Mega Glurak X ex" spelling to the
    official "Glurak-ex" / "Mega-Glurak X-ex" this project uses (see
    card_name_rules.AFFIX_RULES)."""
    if english.endswith(" ex") and german.endswith(" ex"):
        german = german[: -len(" ex")] + "-ex"
    if english.startswith("Mega ") and german.startswith("Mega "):
        german = "Mega-" + german[len("Mega ") :]
    return german


def _has_affix(name: str) -> bool:
    """True if *name* is a variant that derive_translation() builds from a
    base name ("X ex", "Mega X", "Alolan X", ...)."""
    return any(
        name.endswith(affix) if kind == "suffix" else name.startswith(affix)
        for kind, affix, _ in AFFIX_RULES
    )


def flib_german_card_names(cards: list[dict], cards_de: list[dict]) -> dict:
    """Map each English card name to the set of German names flibustier
    gives its prints, in this project's spelling."""
    german_by_print = {(c["set"], c["number"]): c["name"] for c in cards_de}
    result: dict[str, set[str]] = {}
    for c in cards:
        if is_promo(c["set"]) or c["rarity"] in SKIPPED_RARITY_CODES:
            continue
        german = german_by_print.get((c["set"], c["number"]))
        if not german:
            continue
        english = normalise_apostrophe(c["name"])
        result.setdefault(english, set()).add(
            to_local_german_style(english, normalise_apostrophe(german))
        )
    return result


def collect_set_translations(
    all_sets: list[dict], set_names, existing: dict
) -> tuple[list, list]:
    """German names for local sets that have none yet, and those that
    disagree with flibustier."""
    wanted = set(set_names)
    new_rows, mismatches = [], []
    for s in all_sets:
        english = normalise_apostrophe(s["name"]["en"])
        german = s["name"].get("de")
        if is_promo(s["code"]) or english not in wanted or not german:
            continue
        german = normalise_apostrophe(german)
        local = existing.get(english)
        if local is None:
            new_rows.append({"english_name": english, "german_name": german})
        elif local != german:
            mismatches.append(
                {
                    "kind": "set",
                    "english": english,
                    "local": local,
                    "flib_german": german,
                }
            )
    return new_rows, mismatches


def collect_card_translations(
    card_names, flib_names: dict, existing: dict
) -> tuple[list, list, list]:
    """German names for local card names that have none yet (not even a
    derived one), names that disagree with flibustier, and names flibustier
    itself is inconsistent about.

    Base names are handled before their variants, so adding e.g. "Hutsassa"
    lets "Amoonguss ex" be derived instead of getting a row of its own.
    """
    lookup = dict(existing)
    new_rows, mismatches, conflicts = [], [], []
    for english in sorted(set(card_names), key=lambda n: (_has_affix(n), n)):
        candidates = flib_names.get(english)
        if not candidates:
            continue
        if len(candidates) > 1:
            conflicts.append({"english": english, "flib_german": sorted(candidates)})
            continue
        (german,) = candidates
        local = derive_translation(english, lookup)
        if local is None:
            lookup[english] = german
            new_rows.append({"card_english_name": english, "card_german_name": german})
        elif local != german:
            mismatches.append(
                {
                    "kind": "card",
                    "english": english,
                    "local": local,
                    "flib_german": german,
                }
            )
    return new_rows, mismatches, conflicts
