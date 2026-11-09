"""Shared helpers for mapping the flibustier pokemon-tcg-pocket-database
dataset (github.com/flibustier/pokemon-tcg-pocket-database) onto this
project's data/ CSV files. Used by the sync_flibustier command.
"""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

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

# Rarity codes of cards this project deliberately doesn't track. AN
# ("Anomaly") is only used by the three unnumbered, untradeable RGB Mews in
# the SP1 special pack. Cards with any other unknown code are skipped too,
# but with a warning, so a new rarity is noticed instead of being written to
# data/cards.csv as a raw code that import_data can't resolve.
SKIPPED_RARITY_CODES = ("AN",)


def is_promo(set_code: str) -> bool:
    """Return True if the set code belongs to a promotional set."""
    return set_code.upper().startswith("PROMO")


def normalise_apostrophe(text: str) -> str:
    """Replace the curly apostrophe used by the source data with a straight
    one, matching this project's existing naming convention (e.g. "Farfetch'd",
    "Clemont's Backpack")."""
    return text.replace("’", "'")


# ----------------------------------------------------------------------
# Reprints
# ----------------------------------------------------------------------


def reprint_links(cards: list[dict], all_sets: list[dict]) -> dict:
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
            is_promo(c["set"])
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


def fill_reprint_links(existing_cards: dict, links: dict) -> tuple[list, list]:
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


# ----------------------------------------------------------------------
# CSV files
# ----------------------------------------------------------------------


def read_csv_as_dict(path: Path, key_cols: tuple[str, ...]) -> dict:
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


def append_csv(path: Path, fieldnames: list[str], rows) -> None:
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


def write_csv(path: Path, fieldnames: list[str], rows) -> None:
    """Overwrite *path* with *rows*, replacing its current contents."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
