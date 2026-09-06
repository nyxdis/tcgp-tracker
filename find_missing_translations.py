import csv

from apps.tracker.card_name_rules import derive_translation

cards_file = "data/cards.csv"
card_translations_file = "data/card_translations.csv"
pack_translations_file = "data/pack_translations.csv"
set_translations_file = "data/set_translations.csv"
sets_file = "data/sets.csv"

# Build set_number to set_name mapping
set_number_to_name = {}
with open(sets_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        set_number_to_name[row["number"]] = row["name"]

# Get all unique card, pack, and set names from cards.csv
card_names = set()
pack_names = set()
set_names = set()
with open(cards_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        card_names.add(row["card"])
        # Packs can be separated by '|'
        for pack in row["pack"].split("|"):
            pack_names.add(pack)
        # Map set_number to set name
        set_name = set_number_to_name.get(row["set_number"])
        if set_name:
            set_names.add(set_name)

# Get all translated card names (english_name -> german_name, used both as
# the "is this translated" set and as the base lookup for derived names like
# "X ex"/"Team Rocket's X" that don't need their own row)
card_translations = {}
with open(card_translations_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        card_translations[row["card_english_name"]] = row["card_german_name"]

# Get all translated pack names
translated_packs = set()
with open(pack_translations_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        translated_packs.add(row["pack_english_name"])

# Get all translated set names
translated_sets = set()
with open(set_translations_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        translated_sets.add(row["english_name"])

# Find missing translations. Card names also count as translated if they're
# derivable from a base name (e.g. "Bulbasaur ex" from "Bulbasaur") — see
# apps/tracker/card_name_rules.py.
missing_cards = sorted(
    name for name in card_names if derive_translation(name, card_translations) is None
)
missing_packs = sorted(pack_names - translated_packs)
missing_sets = sorted(set_names - translated_sets)


def report(label, missing):
    print(f"{label} missing translation ({len(missing)}):")
    if not missing:
        print("  none")
    for name in missing:
        print(f"  {name}")


report("Cards", missing_cards)
print()
report("Packs", missing_packs)
print()
report("Sets", missing_sets)
