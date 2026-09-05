"""Management command to sync data/ CSV files from the flibustier
pokemon-tcg-pocket-database JSON dataset (github.com/flibustier/pokemon-tcg-pocket-database).

Fetches sets.json and cards.json and appends any new sets/cards to
data/sets.csv and data/cards.csv. Only rows that do not already exist are
added; existing rows are never modified.

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

        self.stdout.write("Fetching flibustier dataset…")
        sets_by_series = self._fetch_json("sets.json")
        cards = self._fetch_json("cards.json")
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
