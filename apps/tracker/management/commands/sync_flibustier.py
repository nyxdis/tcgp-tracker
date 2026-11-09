"""Management command to sync data/ CSV files from the flibustier
pokemon-tcg-pocket-database JSON dataset (github.com/flibustier/pokemon-tcg-pocket-database).

Fetches sets.json and cards.json and appends any new sets/cards to
data/sets.csv and data/cards.csv. Only rows that do not already exist are
added; existing rows are never modified.

Also fetches pullRates.json and cross-checks it against data/pack_types.csv
and data/rarity_probabilities.csv, which stay generation-scoped: flibustier's
rates are per real set, and a couple of sets (A4/A4a, B2b) have genuine
one-off bonus packs (a guaranteed-rare "baby slot" pack, an ultra-rare
"Themed Rare Pack") that don't fit this project's shared-per-generation
pack_type model. Those are deliberately ignored rather than modeled.

Deluxe sets (DELUXE_GENERATIONS) contain parallel-foil reprints of their
♢/♢♢/♢♢♢ cards. flibustier gives those the same rarity code as the standard
print and only tells them apart by the image's variant index, and uses the
separate pull-rate codes CF/UF/RF for them. Both are mapped to this project's
is_foil flag. A new deluxe set is only recognised as such once its generation
in data/sets.csv has been changed by hand (new sets default to G4).

A reprint with the same artwork is the same card as its original in the game;
the reprint_of column of data/cards.csv records the original ("SET/NUMBER"),
derived from prints sharing an image (see _reprint_links). It is
filled in for new cards and for existing rows that have none yet; existing
values that disagree are reported, not changed.

German set names (sets.json) and card names (cards.de.json) are added to
data/set_translations.csv and data/card_translations.csv when this project
has none yet. Existing German names are never modified; where they disagree
with flibustier they are listed for review instead (KNOWN_*_TRANSLATION_
OVERRIDES records verified differences). flibustier writes "Glurak ex" and
"Mega Glurak X ex" where this project uses the official "Glurak-ex" and
"Mega-Glurak X-ex", so its names are converted before being compared or
added. flibustier has no German pack names, so data/pack_translations.csv
must still be filled in by hand.
"""

import csv
import sys
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from apps.tracker.card_name_rules import AFFIX_RULES, derive_translation

DATA_DIR = Path(__file__).resolve().parents[4] / "data"
BASE_URL = (
    "https://raw.githubusercontent.com/flibustier/"
    "pokemon-tcg-pocket-database/main/dist"
)

# Maps flibustier rarity codes (dist/rarities.json) to this project's
# internal rarity names (data/rarities.csv). SR and SAR are visually distinct
# card treatments that both occupy the "2-star" probability tier, so both
# map to special_art.
RARITY_MAP = {
    "C": "common",
    "U": "uncommon",
    "R": "rare",
    "RR": "double_rare",
    "AR": "illustration_rare",
    "SR": "special_art",
    "SAR": "special_art",
    "IM": "immersive_rare",
    "UR": "crown_rare",
    "S": "shiny_rare",
    "SSR": "double_shiny_rare",
}

# Pull-rate-only codes for the parallel-foil prints of deluxe sets, mapped to
# the base rarity they share with the standard print.
FOIL_RARITY_MAP = {"CF": "common", "UF": "uncommon", "RF": "rare"}

# Rarity codes of cards this project deliberately doesn't track. AN
# ("Anomaly") is only used by the three unnumbered, untradeable RGB Mews in
# the SP1 special pack. Cards with any other unknown code are skipped too,
# but with a warning, so a new rarity is noticed instead of being written to
# data/cards.csv as a raw code that import_data can't resolve.
SKIPPED_RARITY_CODES = ("AN",)

# Generations whose sets have parallel-foil prints of their ♢/♢♢/♢♢♢ cards.
DELUXE_GENERATIONS = ("G3", "G5")
_FOIL_RARITY_CODES = ("C", "U", "R")

# All sets this command can add postdate the introduction of generation G4.
_DEFAULT_GENERATION = "G4"

CARD_FIELDS = [
    "set_number",
    "number",
    "card",
    "pack",
    "rarity",
    "is_foil",
    "reprint_of",
]

PACK_TYPE_FIELDS = [
    "generation",
    "pack_type",
    "display_name",
    "slot_count",
    "occurrence_probability",
    "description",
]
RARITY_PROBABILITY_FIELDS = ["generation", "pack_type", "rarity", "is_foil"] + [
    f"probability_slot{i}" for i in range(1, 7)
]

# Probabilities are compared as fractions; ~0.01 percentage points of drift
# in the source data (rounding noise) is not worth flagging as a mismatch.
_PROB_TOLERANCE = 1e-4

# Known, verified-in-game differences where flibustier is wrong and the local
# data is kept. Each entry records the flibustier value it was checked
# against, so if flibustier changes that value (e.g. fixes it) the row is
# reported again instead of being silently skipped. Entry shapes:
#   KNOWN_PACK_TYPE_OVERRIDES[(generation, pack_type)] =
#       {"flib_occurrence": 0.0005, "flib_slot_count": 5, "reason": "..."}
#   KNOWN_RARITY_PROBABILITY_OVERRIDES[(generation, pack_type, rarity, is_foil)] =
#       {"flib_slots": (0.0, 0.0, 0.2, 0.0, 0.0, 0.0), "reason": "..."}
KNOWN_PACK_TYPE_OVERRIDES: dict[tuple, dict] = {}
KNOWN_RARITY_PROBABILITY_OVERRIDES: dict[tuple, dict] = {}

# Verified German names that differ from flibustier's, keyed by English name,
# in the same shape as the overrides above: if flibustier's value changes,
# the name is reported again.
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


class Command(BaseCommand):
    help = "Sync data/sets.csv and data/cards.csv from the flibustier JSON dataset"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "TCGPTracker-scraper/1.0 (educational data sync)"}
        )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interactive",
            action="store_true",
            help=(
                "Prompt for each rarity mismatch against flibustier and let "
                "you accept or keep the local value, instead of just listing "
                "them."
            ),
        )

    def handle(self, *args, **options):
        existing_sets = _read_csv_as_dict(DATA_DIR / "sets.csv", ("number",))
        existing_cards = _read_csv_as_dict(
            DATA_DIR / "cards.csv", ("set_number", "number")
        )
        existing_pack_types = _read_csv_as_dict(
            DATA_DIR / "pack_types.csv", ("generation", "pack_type")
        )
        existing_rarity_probs = _read_csv_as_dict(
            DATA_DIR / "rarity_probabilities.csv",
            ("generation", "pack_type", "rarity", "is_foil"),
        )

        self.stdout.write("Fetching flibustier dataset…")
        sets_by_series = self._fetch_json("sets.json")
        cards = self._fetch_json("cards.json")
        cards_de = self._fetch_json("cards.de.json")
        pull_rates = self._fetch_json("pullRates.json")
        all_sets = [s for series in sets_by_series.values() for s in series]

        new_sets = self._collect_new_sets(all_sets, existing_sets)
        new_cards, mismatches = self._collect_cards(
            cards, existing_cards, existing_sets
        )
        reprint_links = _reprint_links(cards, all_sets)
        for c in new_cards:
            c["reprint_of"] = reprint_links.get((c["set_number"], c["number"]), "")
        linked, link_conflicts = _fill_reprint_links(existing_cards, reprint_links)

        if not new_sets and not new_cards and not linked:
            self.stdout.write(
                self.style.SUCCESS("All sets are up to date. Nothing to do.")
            )
        else:
            _append_csv(
                DATA_DIR / "sets.csv",
                ["number", "name", "release_date", "generation"],
                new_sets,
            )
            if linked:
                # Existing rows changed, so the whole file is rewritten.
                _write_csv(
                    DATA_DIR / "cards.csv",
                    CARD_FIELDS,
                    list(existing_cards.values()) + new_cards,
                )
            else:
                _append_csv(DATA_DIR / "cards.csv", CARD_FIELDS, new_cards)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Added {len(new_sets)} set(s), {len(new_cards)} card(s)."
                )
            )
            if new_sets:
                self.stdout.write(
                    "New sets need German pack names added by hand to "
                    "data/pack_translations.csv (flibustier has none):"
                )
                for s in new_sets:
                    self.stdout.write(f"  {s['number']} - {s['name']}")
        # The new cards are in cards.csv now; a later rewrite of the file
        # (--interactive) must keep them.
        existing_cards.update({(c["set_number"], c["number"]): c for c in new_cards})
        self._report_reprint_links(linked, link_conflicts)

        if options["interactive"]:
            self._review_mismatches_interactively(mismatches, existing_cards)
        else:
            self._report_mismatches(mismatches)

        self._sync_translations(
            all_sets,
            cards,
            cards_de,
            set_names=[s["name"] for s in existing_sets.values()]
            + [s["name"] for s in new_sets],
            card_names=[c["card"] for c in existing_cards.values()],
        )

        self.stdout.write("\nChecking pull-rate probabilities…")
        pack_type_mismatches, prob_mismatches = self._collect_probability_data(
            pull_rates, existing_sets, existing_pack_types, existing_rarity_probs
        )
        pack_type_mismatches, prob_mismatches = self._drop_known_overrides(
            pack_type_mismatches, prob_mismatches
        )
        if options["interactive"]:
            self._review_probability_mismatches_interactively(
                pack_type_mismatches,
                prob_mismatches,
                existing_pack_types,
                existing_rarity_probs,
            )
        else:
            self._report_probability_mismatches(pack_type_mismatches, prob_mismatches)

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------

    def _collect_new_sets(self, all_sets: list[dict], existing_sets: dict) -> list:
        new_sets = []
        for s in all_sets:
            code = s["code"]
            if _is_promo(code) or code in existing_sets:
                continue
            new_sets.append(
                {
                    "number": code,
                    "name": _normalise_apostrophe(s["name"]["en"]),
                    "release_date": s.get("releaseDate", ""),
                    "generation": _DEFAULT_GENERATION,
                }
            )
        return new_sets

    def _collect_cards(
        self, cards: list[dict], existing_cards: dict, existing_sets: dict
    ) -> tuple[list, list]:
        new_cards = []
        mismatches = []
        unknown_codes = {}
        for c in cards:
            set_code = c["set"]
            if _is_promo(set_code) or c["rarity"] in SKIPPED_RARITY_CODES:
                continue
            if c["rarity"] not in RARITY_MAP:
                unknown_codes.setdefault(c["rarity"], []).append(
                    f"{set_code} #{c['number']} {c['name']}"
                )
                continue
            number = str(c["number"]).zfill(3)
            key = (set_code, number)
            rarity = RARITY_MAP[c["rarity"]]
            generation = existing_sets.get(set_code, {}).get(
                "generation", _DEFAULT_GENERATION
            )
            is_foil = _is_foil_print(c, generation)
            pack = "|".join(
                sorted(_normalise_apostrophe(p) for p in c.get("packs") or [])
            )

            existing = existing_cards.get(key)
            if existing is None:
                new_cards.append(
                    {
                        "set_number": set_code,
                        "number": number,
                        "card": _normalise_apostrophe(c["name"]),
                        "pack": pack,
                        "rarity": rarity,
                        "is_foil": int(is_foil),
                    }
                )
            elif (existing["rarity"], _parse_flag(existing.get("is_foil"))) != (
                rarity,
                is_foil,
            ):
                set_name = existing_sets.get(set_code, {}).get("name", "")
                mismatches.append(
                    {
                        "key": key,
                        "set_code": set_code,
                        "set_name": set_name,
                        "number": number,
                        "name": existing["card"],
                        "local_rarity": existing["rarity"],
                        "local_is_foil": _parse_flag(existing.get("is_foil")),
                        "flib_rarity": rarity,
                        "flib_is_foil": is_foil,
                    }
                )
        for code, skipped in sorted(unknown_codes.items()):
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {len(skipped)} card(s) with unknown rarity code "
                    f"{code!r} (add it to RARITY_MAP or SKIPPED_RARITY_CODES): "
                    f"{', '.join(skipped)}"
                )
            )
        return new_cards, mismatches

    def _report_mismatches(self, mismatches: list) -> None:
        if not mismatches:
            return
        self.stdout.write(
            self.style.WARNING(
                f"\n{len(mismatches)} existing card(s) have a rarity in "
                "data/cards.csv that disagrees with flibustier. Not auto-fixed, "
                "please review and correct by hand (or re-run with "
                "--interactive):"
            )
        )
        for m in mismatches:
            self.stdout.write(
                f"  {m['set_code']} ({m['set_name']}) #{m['number']} {m['name']}: "
                f"local={_rarity_label(m['local_rarity'], m['local_is_foil'])} "
                f"flibustier={_rarity_label(m['flib_rarity'], m['flib_is_foil'])}"
            )

    def _report_reprint_links(self, linked: list, conflicts: list) -> None:
        if linked:
            self.stdout.write(
                f"Linked {len(linked)} existing card(s) as reprints of the "
                "same card (reprint_of):"
            )
            for (set_code, number), original in linked:
                self.stdout.write(f"  {set_code} #{number} -> {original}")
        if conflicts:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(conflicts)} card(s) have a reprint_of in "
                    "data/cards.csv that disagrees with flibustier's images. "
                    "Not auto-fixed, please check:"
                )
            )
            for (set_code, number), local, flib in conflicts:
                self.stdout.write(
                    f"  {set_code} #{number}: local={local or '-'} "
                    f"flibustier={flib or '-'}"
                )

    def _review_mismatches_interactively(
        self, mismatches: list, existing_cards: dict
    ) -> None:
        if not mismatches:
            return
        self.stdout.write(
            self.style.WARNING(
                f"\n{len(mismatches)} rarity mismatch(es) to review. For each, "
                "press (no Enter needed): "
                "[y] use flibustier's rarity  [n] keep local (default)  "
                "[q] stop reviewing"
            )
        )
        fixed = 0
        for i, m in enumerate(mismatches, start=1):
            prompt = (
                f"[{i}/{len(mismatches)}] {m['set_code']} ({m['set_name']}) "
                f"#{m['number']} {m['name']}: "
                f"local={_rarity_label(m['local_rarity'], m['local_is_foil'])} "
                f"flibustier={_rarity_label(m['flib_rarity'], m['flib_is_foil'])} "
                "— fix? [y/N/q] "
            )
            answer = _read_key(prompt)
            if answer == "q":
                self.stdout.write(
                    f"Stopped reviewing ({len(mismatches) - i + 1} left unreviewed)."
                )
                break
            if answer == "y":
                existing_cards[m["key"]]["rarity"] = m["flib_rarity"]
                existing_cards[m["key"]]["is_foil"] = int(m["flib_is_foil"])
                fixed += 1

        if fixed:
            _write_csv(DATA_DIR / "cards.csv", CARD_FIELDS, existing_cards.values())
        self.stdout.write(
            self.style.SUCCESS(f"Fixed {fixed} of {len(mismatches)} mismatch(es).")
        )

    def _collect_probability_data(
        self,
        pull_rates: dict,
        existing_sets: dict,
        existing_pack_types: dict,
        existing_rarity_probs: dict,
    ) -> tuple[list, list]:
        """
        Group flibustier's per-set pull rates by (generation, pack_type),
        verify member sets agree, and diff the result against the current
        pack_types.csv / rarity_probabilities.csv rows.
        """
        groups: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        for set_code, packs in pull_rates.items():
            generation = existing_sets.get(set_code, {}).get("generation")
            if not generation:
                continue
            for pack_name, pack_data in packs.items():
                pack_type = _classify_pull_rate_pack(pack_name, pack_data)
                if pack_type is None:
                    self.stdout.write(
                        f'  ignored non-standard pack "{pack_name}" for set '
                        f"{set_code} (not modeled)"
                    )
                    continue
                groups.setdefault((generation, pack_type), []).append(
                    (set_code, pack_data)
                )

        pack_type_mismatches = []
        prob_mismatches = []
        for (generation, pack_type), entries in sorted(groups.items()):
            rate, rate_ok = _cluster_consensus(
                [e[1]["appearance_rate"] for e in entries],
                lambda a, b: abs(a - b) <= 0.01,
            )
            cards, cards_ok = _cluster_consensus(
                [e[1]["cards"] for e in entries], lambda a, b: a == b
            )
            if not rate_ok or not cards_ok:
                self.stdout.write(
                    self.style.WARNING(
                        f"  conflict: {generation}/{pack_type} sets disagree "
                        "on appearance_rate/cards, skipping: "
                        f"{[(e[0], e[1]['appearance_rate'], e[1]['cards']) for e in entries]}"
                    )
                )
                continue

            pt_key = (generation, pack_type)
            existing_pt = existing_pack_types.get(pt_key)
            occurrence_probability = round(rate / 100, 6)
            if existing_pt is None or (
                abs(
                    float(existing_pt["occurrence_probability"])
                    - occurrence_probability
                )
                > _PROB_TOLERANCE
                or int(existing_pt["slot_count"]) != cards
            ):
                pack_type_mismatches.append(
                    {
                        "key": pt_key,
                        "generation": generation,
                        "pack_type": pack_type,
                        "local_occurrence": (
                            existing_pt["occurrence_probability"]
                            if existing_pt
                            else None
                        ),
                        "flib_occurrence": occurrence_probability,
                        "local_slot_count": (
                            existing_pt["slot_count"] if existing_pt else None
                        ),
                        "flib_slot_count": cards,
                        "is_new": existing_pt is None,
                    }
                )

            if pack_type != "god":
                # God pack rarity odds are calculated dynamically at runtime
                # from each real set's actual card counts (see
                # Generation.calculate_god_pack_probabilities) and are never
                # stored in rarity_probabilities.csv, so there's nothing to
                # compare per rarity here.
                prob_mismatches.extend(
                    self._collect_slot_mismatches(
                        generation, pack_type, entries, existing_rarity_probs
                    )
                )

        return pack_type_mismatches, prob_mismatches

    def _drop_known_overrides(
        self, pack_type_mismatches: list, prob_mismatches: list
    ) -> tuple[list, list]:
        """Remove mismatches listed in the KNOWN_*_OVERRIDES tables, noting each."""

        def is_known_pack_type(m):
            known = KNOWN_PACK_TYPE_OVERRIDES.get(m["key"])
            return (
                known is not None
                and abs(m["flib_occurrence"] - known["flib_occurrence"])
                <= _PROB_TOLERANCE
                and m["flib_slot_count"] == known["flib_slot_count"]
            )

        def is_known_prob(m):
            known = KNOWN_RARITY_PROBABILITY_OVERRIDES.get(m["key"])
            return known is not None and all(
                abs(a - b) <= _PROB_TOLERANCE
                for a, b in zip(m["flib_slots"], known["flib_slots"])
            )

        for m in pack_type_mismatches:
            if is_known_pack_type(m):
                self.stdout.write(
                    f"  known difference kept: {m['generation']}/{m['pack_type']} "
                    f"({KNOWN_PACK_TYPE_OVERRIDES[m['key']]['reason']})"
                )
        for m in prob_mismatches:
            if is_known_prob(m):
                label = _rarity_label(m["rarity"], m["is_foil"])
                self.stdout.write(
                    f"  known difference kept: {m['generation']}/{m['pack_type']}/"
                    f"{label} "
                    f"({KNOWN_RARITY_PROBABILITY_OVERRIDES[m['key']]['reason']})"
                )
        return (
            [m for m in pack_type_mismatches if not is_known_pack_type(m)],
            [m for m in prob_mismatches if not is_known_prob(m)],
        )

    def _collect_slot_mismatches(
        self,
        generation: str,
        pack_type: str,
        entries: list[tuple[str, dict]],
        existing_rarity_probs: dict,
    ) -> list:
        slot_vectors = [_sorted_slots(pack_data) for _set_code, pack_data in entries]
        all_codes = {code for slots in slot_vectors for slot in slots for code in slot}

        unrecognized = sorted(all_codes - RARITY_MAP.keys() - FOIL_RARITY_MAP.keys())
        if unrecognized:
            self.stdout.write(
                self.style.WARNING(
                    f"  skipping {generation}/{pack_type}: uses rarity code(s) "
                    f"{unrecognized} this project has no equivalent for "
                    "(needs manual review, possibly a schema gap)"
                )
            )
            return []

        # Several codes can share one local row (SR and SAR are both
        # special_art), so their slot percentages are summed per pool.
        pool_keys = sorted({_pool_key(code) for code in all_codes})
        mismatches = []
        for rarity, is_foil in pool_keys:
            per_set_values = [
                tuple(
                    sum(
                        pct
                        for code, pct in slot.items()
                        if _pool_key(code) == (rarity, is_foil)
                    )
                    for slot in slots
                )
                for slots in slot_vectors
            ]
            label = f"{generation}/{pack_type}/{_rarity_label(rarity, is_foil)}"
            value, is_majority = _cluster_consensus(
                per_set_values,
                lambda a, b: all(abs(x - y) <= 0.01 for x, y in zip(a, b)),
            )
            if not is_majority:
                self.stdout.write(
                    self.style.WARNING(
                        f"  conflict: {label} sets disagree on slot percentages, "
                        "skipping: "
                        f"{list(zip((s for s, _ in entries), per_set_values))}"
                    )
                )
                continue

            flib_slots = [round(v / 100, 6) for v in value]
            while len(flib_slots) < 6:
                flib_slots.append(0.0)

            rp_key = (generation, pack_type, rarity, str(int(is_foil)))
            existing_rp = existing_rarity_probs.get(rp_key)
            local_slots = (
                [float(existing_rp[f"probability_slot{i}"]) for i in range(1, 7)]
                if existing_rp
                else None
            )
            if local_slots is None or any(
                abs(a - b) > _PROB_TOLERANCE for a, b in zip(local_slots, flib_slots)
            ):
                mismatches.append(
                    {
                        "key": rp_key,
                        "generation": generation,
                        "pack_type": pack_type,
                        "rarity": rarity,
                        "is_foil": is_foil,
                        "local_slots": local_slots,
                        "flib_slots": flib_slots,
                        "is_new": existing_rp is None,
                    }
                )
        return mismatches

    def _report_probability_mismatches(
        self, pack_type_mismatches: list, prob_mismatches: list
    ) -> None:
        if not pack_type_mismatches and not prob_mismatches:
            return
        self.stdout.write(
            self.style.WARNING(
                f"\n{len(pack_type_mismatches)} pack_types.csv row(s) and "
                f"{len(prob_mismatches)} rarity_probabilities.csv row(s) "
                "disagree with flibustier. Not auto-fixed, please review and "
                "correct by hand (or re-run with --interactive):"
            )
        )
        for m in pack_type_mismatches:
            tag = "NEW" if m["is_new"] else "MISMATCH"
            self.stdout.write(
                f"  [{tag}] {m['generation']}/{m['pack_type']}: occurrence "
                f"local={m['local_occurrence']} flib={m['flib_occurrence']}, "
                f"slot_count local={m['local_slot_count']} "
                f"flib={m['flib_slot_count']}"
            )
        for m in prob_mismatches:
            tag = "NEW" if m["is_new"] else "MISMATCH"
            self.stdout.write(
                f"  [{tag}] {m['generation']}/{m['pack_type']}/"
                f"{_rarity_label(m['rarity'], m['is_foil'])}: "
                f"local={m['local_slots']} flib={m['flib_slots']}"
            )

    def _review_probability_mismatches_interactively(
        self,
        pack_type_mismatches: list,
        prob_mismatches: list,
        existing_pack_types: dict,
        existing_rarity_probs: dict,
    ) -> None:
        total = len(pack_type_mismatches) + len(prob_mismatches)
        if not total:
            return
        self.stdout.write(
            self.style.WARNING(
                f"\n{total} pack-type/probability mismatch(es) to review. "
                "For each, press (no Enter needed): "
                "[y] use flibustier's value  [n] keep local (default)  "
                "[q] stop reviewing"
            )
        )

        fixed_pack_types = 0
        fixed_probs = 0
        i = 0
        stopped = False

        for m in pack_type_mismatches:
            i += 1
            tag = "NEW" if m["is_new"] else "MISMATCH"
            prompt = (
                f"[{i}/{total}] [{tag}] {m['generation']}/{m['pack_type']}: "
                f"occurrence local={m['local_occurrence']} "
                f"flib={m['flib_occurrence']}, slot_count "
                f"local={m['local_slot_count']} flib={m['flib_slot_count']} "
                "— fix? [y/N/q] "
            )
            answer = _read_key(prompt)
            if answer == "q":
                stopped = True
                break
            if answer == "y":
                current = existing_pack_types.get(m["key"], {})
                existing_pack_types[m["key"]] = {
                    "generation": m["generation"],
                    "pack_type": m["pack_type"],
                    "display_name": current.get("display_name", m["pack_type"]),
                    "slot_count": m["flib_slot_count"],
                    "occurrence_probability": _fmt_number(m["flib_occurrence"]),
                    "description": current.get("description", ""),
                }
                fixed_pack_types += 1

        if not stopped:
            for m in prob_mismatches:
                i += 1
                tag = "NEW" if m["is_new"] else "MISMATCH"
                prompt = (
                    f"[{i}/{total}] [{tag}] {m['generation']}/{m['pack_type']}/"
                    f"{_rarity_label(m['rarity'], m['is_foil'])}: "
                    f"local={m['local_slots']} "
                    f"flib={m['flib_slots']} — fix? [y/N/q] "
                )
                answer = _read_key(prompt)
                if answer == "q":
                    stopped = True
                    break
                if answer == "y":
                    row = {
                        "generation": m["generation"],
                        "pack_type": m["pack_type"],
                        "rarity": m["rarity"],
                        "is_foil": int(m["is_foil"]),
                    }
                    for idx, value in enumerate(m["flib_slots"], start=1):
                        row[f"probability_slot{idx}"] = _fmt_number(value)
                    existing_rarity_probs[m["key"]] = row
                    fixed_probs += 1

        if stopped:
            self.stdout.write(f"Stopped reviewing ({total - i + 1} left unreviewed).")

        if fixed_pack_types:
            _write_csv(
                DATA_DIR / "pack_types.csv",
                PACK_TYPE_FIELDS,
                existing_pack_types.values(),
            )
        if fixed_probs:
            _write_csv(
                DATA_DIR / "rarity_probabilities.csv",
                RARITY_PROBABILITY_FIELDS,
                existing_rarity_probs.values(),
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Fixed {fixed_pack_types} pack_type row(s) and {fixed_probs} "
                f"probability row(s) of {total} mismatch(es)."
            )
        )

    # ------------------------------------------------------------------
    # German names
    # ------------------------------------------------------------------

    def _sync_translations(
        self, all_sets, cards, cards_de, set_names, card_names
    ) -> None:
        """Add German set and card names this project has none for yet, and
        report the ones that disagree with flibustier."""
        self.stdout.write("\nChecking German names…")
        existing_sets = {
            english: row["german_name"].strip()
            for english, row in _read_csv_as_dict(
                DATA_DIR / "set_translations.csv", ("english_name",)
            ).items()
        }
        existing_cards = {
            english.strip(): row["card_german_name"].strip()
            for english, row in _read_csv_as_dict(
                DATA_DIR / "card_translations.csv", ("card_english_name",)
            ).items()
        }

        new_set_rows, set_mismatches = _collect_set_translations(
            all_sets, set_names, existing_sets
        )
        new_card_rows, card_mismatches, conflicts = _collect_card_translations(
            card_names, _flib_german_card_names(cards, cards_de), existing_cards
        )
        _append_csv(
            DATA_DIR / "set_translations.csv", SET_TRANSLATION_FIELDS, new_set_rows
        )
        _append_csv(
            DATA_DIR / "card_translations.csv", CARD_TRANSLATION_FIELDS, new_card_rows
        )

        if new_set_rows or new_card_rows:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added {len(new_set_rows)} German set name(s) and "
                    f"{len(new_card_rows)} German card name(s) from flibustier:"
                )
            )
            for row in new_set_rows:
                self.stdout.write(f"  set {row['english_name']}: {row['german_name']}")
            for row in new_card_rows:
                self.stdout.write(
                    f"  card {row['card_english_name']}: {row['card_german_name']}"
                )

        mismatches = self._drop_known_translation_overrides(
            set_mismatches + card_mismatches
        )
        if mismatches:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(mismatches)} German name(s) disagree with "
                    "flibustier. Not auto-fixed, please check the official name "
                    "and either correct data/*_translations.csv or record it in "
                    "KNOWN_*_TRANSLATION_OVERRIDES:"
                )
            )
            for m in mismatches:
                self.stdout.write(
                    f"  {m['kind']} {m['english']}: local={m['local']} "
                    f"flibustier={m['flib_german']}"
                )
        for c in conflicts:
            self.stdout.write(
                self.style.WARNING(
                    f"  flibustier has several German names for card "
                    f"{c['english']} ({', '.join(c['flib_german'])}), not added"
                )
            )

        set_lookup = existing_sets | {
            r["english_name"]: r["german_name"] for r in new_set_rows
        }
        card_lookup = existing_cards | {
            r["card_english_name"]: r["card_german_name"] for r in new_card_rows
        }
        untranslated = [
            f"set {name}" for name in sorted(set(set_names)) if name not in set_lookup
        ] + [
            f"card {name}"
            for name in sorted(set(card_names))
            if derive_translation(name, card_lookup) is None
        ]
        if untranslated:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(untranslated)} name(s) have no German name yet and "
                    "flibustier has none either; add them by hand to "
                    "data/set_translations.csv / data/card_translations.csv:"
                )
            )
            for name in untranslated:
                self.stdout.write(f"  {name}")

    def _drop_known_translation_overrides(self, mismatches: list) -> list:
        """Remove mismatches listed in KNOWN_*_TRANSLATION_OVERRIDES, noting each."""
        known_by_kind = {
            "set": KNOWN_SET_TRANSLATION_OVERRIDES,
            "card": KNOWN_CARD_TRANSLATION_OVERRIDES,
        }
        remaining = []
        for m in mismatches:
            known = known_by_kind[m["kind"]].get(m["english"])
            if known is not None and known["flib_german"] == m["flib_german"]:
                self.stdout.write(
                    f"  known difference kept: {m['kind']} {m['english']} "
                    f"({known['reason']})"
                )
            else:
                remaining.append(m)
        return remaining

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _fetch_json(self, filename: str):
        resp = self._session.get(f"{BASE_URL}/{filename}", timeout=20)
        resp.raise_for_status()
        return resp.json()


def _read_key(prompt: str) -> str:
    """
    Print *prompt* and read a single y/n/q keypress with no Enter required.

    Falls back to line-buffered input() when stdin isn't a real terminal
    (e.g. piped input in scripts/tests). A bare Enter counts as "n".
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    if not sys.stdin.isatty():
        answer = input().strip().lower()
        return answer[:1] or "n"

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            if not ch or ch in ("\r", "\n"):
                ch = "n" if ch else "q"  # EOF (Ctrl-D) stops the review
                break
            ch = ch.lower()
            if ch in ("y", "n", "q"):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    sys.stdout.write(ch + "\n")
    sys.stdout.flush()
    return ch


def _sorted_slots(pack_data: dict) -> list[dict]:
    """Return a pack's slot dicts in positional order.

    flibustier's slot keys are inconsistently 0- or 1-indexed depending on
    the set, so only their relative order is meaningful.
    """
    slots = pack_data["slots"]
    return [slots[k] for k in sorted(slots, key=int)]


def _classify_pull_rate_pack(pack_name: str, pack_data: dict) -> str | None:
    """
    Map a flibustier pull-rate pack name to this project's pack_type name,
    or None if it's a one-off bonus pack this project doesn't model.

    "Regular Pack +1" is ambiguous by name alone: for most G4 sets it's the
    guaranteed-shiny bonus pack, but for A4/A4a it's an unrelated
    guaranteed-Rare/Art-Rare "baby slot" bonus pack (no shiny rarity codes
    at all). Only the former is treated as this project's "shiny" pack_type.
    """
    if pack_name == "Regular Pack":
        return "normal"
    if pack_name == "Rare Pack":
        return "god"
    if pack_name == "Regular Pack +1":
        bonus_slot_codes = set(_sorted_slots(pack_data)[-1].keys())
        if bonus_slot_codes & {"S", "SSR"}:
            return "shiny"
    return None


def _pool_key(code: str) -> tuple[str, bool]:
    """Map a flibustier pull-rate code to this project's (rarity, is_foil)."""
    if code in FOIL_RARITY_MAP:
        return FOIL_RARITY_MAP[code], True
    return RARITY_MAP[code], False


def _is_foil_print(card: dict, generation: str) -> bool:
    """Return True if *card* is the parallel-foil print of a deluxe set card.

    flibustier's image names end in ``_<dex>_<variant>_<NAME>_<RARITY>.webp``;
    the standard print is variant ``00``. Other sets also have non-``00``
    variants (alternate arts), so only deluxe generations are considered.
    """
    if generation not in DELUXE_GENERATIONS or card["rarity"] not in _FOIL_RARITY_CODES:
        return False
    parts = (card.get("image") or "").split("_")
    return len(parts) > 3 and parts[3] != "00"


def _parse_flag(value) -> bool:
    """Parse a 0/1 CSV flag column; missing or empty is False."""
    return str(value or "").strip().lower() in ("1", "true", "yes")


def _rarity_label(rarity: str, is_foil: bool) -> str:
    return f"{rarity} (foil)" if is_foil else rarity


def _fmt_number(value: float):
    """Return *value* as an int when it has no fractional part, matching
    this project's existing CSV convention of writing whole numbers (e.g.
    zero probabilities) without a trailing ".0"."""
    return int(value) if float(value).is_integer() else value


def _cluster_consensus(values: list, is_close) -> tuple:
    """
    Group *values* by the *is_close(a, b)* predicate and return
    ``(representative, is_majority)`` for the largest cluster.

    Used instead of requiring exact/unanimous agreement because a few sets
    have a known, explained reason to deviate slightly from the rest of
    their generation (e.g. A4/A4a's ignored "baby slot" bonus pack reduces
    their Regular Pack's own share; B2b's "Mega Shine" theme genuinely
    boosts its shiny odds) — the generation-wide value should still win by
    majority rather than the whole comparison being thrown out.
    """
    clusters: list[list] = []
    for v in values:
        for cluster in clusters:
            if is_close(cluster[0], v):
                cluster.append(v)
                break
        else:
            clusters.append([v])
    largest = max(clusters, key=len)
    return largest[0], len(largest) * 2 > len(values)


def _reprint_links(cards: list[dict], all_sets: list[dict]) -> dict:
    """Map (set, number) of each reprint to the "SET/NUMBER" of its original.

    A print with the same image (artwork) as an earlier one is the same card
    in the game: it keeps the original's id, so both share one collection
    entry. B4b introduced this, it was backported to A4b, and it also holds
    for A1a's Old Amber. The earliest-released print is the original.
    Parallel-foil prints have their own image and stay separate cards.
    """
    release = {s["code"]: s.get("releaseDate", "") for s in all_sets}
    prints_by_image: dict[str, list[dict]] = {}
    for c in cards:
        if (
            _is_promo(c["set"])
            or c["rarity"] in SKIPPED_RARITY_CODES
            or c["rarity"] not in RARITY_MAP
            or not c.get("image")
        ):
            continue
        prints_by_image.setdefault(c["image"], []).append(c)

    links = {}
    for prints in prints_by_image.values():
        if len(prints) < 2:
            continue
        prints.sort(key=lambda c: (release.get(c["set"], ""), c["set"], c["number"]))
        original = prints[0]
        target = f"{original['set']}/{str(original['number']).zfill(3)}"
        for c in prints[1:]:
            if c["set"] != original["set"]:
                links[(c["set"], str(c["number"]).zfill(3))] = target
    return links


def _fill_reprint_links(existing_cards: dict, links: dict) -> tuple[list, list]:
    """Set reprint_of on existing rows that have none yet (in place), and list
    rows whose reprint_of disagrees with *links*."""
    linked, conflicts = [], []
    for key, row in existing_cards.items():
        local = (row.get("reprint_of") or "").strip()
        flib = links.get(key, "")
        if local == flib:
            continue
        if not local:
            row["reprint_of"] = flib
            linked.append((key, flib))
        else:
            conflicts.append((key, local, flib))
    return linked, conflicts


def _to_local_german_style(english: str, german: str) -> str:
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


def _flib_german_card_names(cards: list[dict], cards_de: list[dict]) -> dict:
    """Map each English card name to the set of German names flibustier
    gives its prints, in this project's spelling."""
    german_by_print = {(c["set"], c["number"]): c["name"] for c in cards_de}
    result: dict[str, set[str]] = {}
    for c in cards:
        if _is_promo(c["set"]) or c["rarity"] in SKIPPED_RARITY_CODES:
            continue
        german = german_by_print.get((c["set"], c["number"]))
        if not german:
            continue
        english = _normalise_apostrophe(c["name"])
        result.setdefault(english, set()).add(
            _to_local_german_style(english, _normalise_apostrophe(german))
        )
    return result


def _collect_set_translations(
    all_sets: list[dict], set_names, existing: dict
) -> tuple[list, list]:
    """German names for local sets that have none yet, and those that
    disagree with flibustier."""
    wanted = set(set_names)
    new_rows, mismatches = [], []
    for s in all_sets:
        english = _normalise_apostrophe(s["name"]["en"])
        german = s["name"].get("de")
        if _is_promo(s["code"]) or english not in wanted or not german:
            continue
        german = _normalise_apostrophe(german)
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


def _collect_card_translations(
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


def _is_promo(set_code: str) -> bool:
    """Return True if the set code belongs to a promotional set."""
    return set_code.upper().startswith("PROMO")


def _normalise_apostrophe(text: str) -> str:
    """Replace the curly apostrophe used by the source data with a straight
    one, matching this project's existing naming convention (e.g. "Farfetch'd",
    "Clemont's Backpack")."""
    return text.replace("’", "'")


def _read_csv_as_dict(path: Path, key_cols: tuple[str, ...]) -> dict:
    """
    Read a CSV file and return a dict keyed by the tuple of values in
    *key_cols*. Single-key tuples are unwrapped to plain strings.
    """
    result = {}
    if not path.exists():
        return result
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key_vals = tuple(row[k] for k in key_cols)
            key = key_vals[0] if len(key_vals) == 1 else key_vals
            result[key] = row
    return result


def _append_csv(path: Path, fieldnames: list[str], rows) -> None:
    """Append *rows* to the CSV at *path* (file must already exist)."""
    rows = list(rows)
    if not rows:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        for row in rows:
            writer.writerow(row)


def _write_csv(path: Path, fieldnames: list[str], rows) -> None:
    """Overwrite *path* with *rows*, replacing its current contents."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
