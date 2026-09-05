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

The dataset has no German localisation, so data/set_translations.csv,
data/pack_translations.csv and data/card_translations.csv are left untouched;
translations for anything newly added must be filled in by hand.
"""

import csv
import sys
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

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

# All sets this command can add postdate the introduction of generation G4.
_DEFAULT_GENERATION = "G4"

PACK_TYPE_FIELDS = [
    "generation",
    "pack_type",
    "display_name",
    "slot_count",
    "occurrence_probability",
    "description",
]
RARITY_PROBABILITY_FIELDS = ["generation", "pack_type", "rarity"] + [
    f"probability_slot{i}" for i in range(1, 7)
]

# Probabilities are compared as fractions; ~0.01 percentage points of drift
# in the source data (rounding noise) is not worth flagging as a mismatch.
_PROB_TOLERANCE = 1e-4


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
            ("generation", "pack_type", "rarity"),
        )

        self.stdout.write("Fetching flibustier dataset…")
        sets_by_series = self._fetch_json("sets.json")
        cards = self._fetch_json("cards.json")
        pull_rates = self._fetch_json("pullRates.json")
        all_sets = [s for series in sets_by_series.values() for s in series]

        new_sets = self._collect_new_sets(all_sets, existing_sets)
        new_cards, mismatches = self._collect_cards(
            cards, existing_cards, existing_sets
        )

        if not new_sets and not new_cards:
            self.stdout.write(
                self.style.SUCCESS("All sets are up to date. Nothing to do.")
            )
        else:
            _append_csv(
                DATA_DIR / "sets.csv",
                ["number", "name", "release_date", "generation"],
                new_sets,
            )
            _append_csv(
                DATA_DIR / "cards.csv",
                ["set_number", "number", "card", "pack", "rarity"],
                new_cards,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Added {len(new_sets)} set(s), {len(new_cards)} card(s)."
                )
            )
            if new_sets:
                self.stdout.write(
                    "New sets need German translations added by hand to "
                    "data/set_translations.csv (and data/pack_translations.csv "
                    "for their packs):"
                )
                for s in new_sets:
                    self.stdout.write(f"  {s['number']} - {s['name']}")

        if options["interactive"]:
            self._review_mismatches_interactively(mismatches, existing_cards)
        else:
            self._report_mismatches(mismatches)

        self.stdout.write("\nChecking pull-rate probabilities…")
        pack_type_mismatches, prob_mismatches = self._collect_probability_data(
            pull_rates, existing_sets, existing_pack_types, existing_rarity_probs
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
        for c in cards:
            set_code = c["set"]
            if _is_promo(set_code):
                continue
            number = str(c["number"]).zfill(3)
            key = (set_code, number)
            rarity = RARITY_MAP.get(c["rarity"], c["rarity"])
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
                    }
                )
            elif existing["rarity"] != rarity:
                set_name = existing_sets.get(set_code, {}).get("name", "")
                mismatches.append(
                    {
                        "key": key,
                        "set_code": set_code,
                        "set_name": set_name,
                        "number": number,
                        "name": existing["card"],
                        "local_rarity": existing["rarity"],
                        "flib_rarity": rarity,
                    }
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
                f"local={m['local_rarity']} flibustier={m['flib_rarity']}"
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
                f"#{m['number']} {m['name']}: local={m['local_rarity']} "
                f"flibustier={m['flib_rarity']} — fix? [y/N/q] "
            )
            answer = _read_key(prompt)
            if answer == "q":
                self.stdout.write(
                    f"Stopped reviewing ({len(mismatches) - i + 1} left unreviewed)."
                )
                break
            if answer == "y":
                existing_cards[m["key"]]["rarity"] = m["flib_rarity"]
                fixed += 1

        if fixed:
            _write_csv(
                DATA_DIR / "cards.csv",
                ["set_number", "number", "card", "pack", "rarity"],
                existing_cards.values(),
            )
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

    def _collect_slot_mismatches(
        self,
        generation: str,
        pack_type: str,
        entries: list[tuple[str, dict]],
        existing_rarity_probs: dict,
    ) -> list:
        slot_vectors = [_sorted_slots(pack_data) for _set_code, pack_data in entries]
        all_codes = {code for slots in slot_vectors for slot in slots for code in slot}

        unrecognized = sorted(all_codes - RARITY_MAP.keys())
        if unrecognized:
            self.stdout.write(
                self.style.WARNING(
                    f"  skipping {generation}/{pack_type}: uses rarity code(s) "
                    f"{unrecognized} this project has no equivalent for "
                    "(needs manual review, possibly a schema gap)"
                )
            )
            return []

        mismatches = []
        for code in sorted(all_codes):
            rarity = RARITY_MAP[code]
            per_set_values = [
                tuple(slot.get(code, 0.0) for slot in slots) for slots in slot_vectors
            ]
            value, is_majority = _cluster_consensus(
                per_set_values,
                lambda a, b: all(abs(x - y) <= 0.01 for x, y in zip(a, b)),
            )
            if not is_majority:
                self.stdout.write(
                    self.style.WARNING(
                        f"  conflict: {generation}/{pack_type}/{rarity} sets "
                        "disagree on slot percentages, skipping: "
                        f"{list(zip((s for s, _ in entries), per_set_values))}"
                    )
                )
                continue

            flib_slots = [round(v / 100, 6) for v in value]
            while len(flib_slots) < 6:
                flib_slots.append(0.0)

            rp_key = (generation, pack_type, rarity)
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
                f"  [{tag}] {m['generation']}/{m['pack_type']}/{m['rarity']}: "
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
                    f"{m['rarity']}: local={m['local_slots']} "
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
