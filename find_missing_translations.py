import csv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

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

# Get all translated card names
translated_cards = set()
with open(card_translations_file, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        translated_cards.add(row["card_english_name"])

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

# Find missing translations
missing_cards = sorted(card_names - translated_cards)
missing_packs = sorted(pack_names - translated_packs)
missing_sets = sorted(set_names - translated_sets)

logger.info("Cards missing translation:")
for name in missing_cards:
    logger.info("  %s", name)

logger.info("\nPacks missing translation:")
for name in missing_packs:
    logger.info("  %s", name)

logger.info("\nSets missing translation:")
for name in missing_sets:
    logger.info("  %s", name)
