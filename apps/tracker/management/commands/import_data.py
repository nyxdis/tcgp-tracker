"""Management command to import data for tracker app."""

import csv

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from apps.tracker.models.cards import (
    Card,
    PokemonSet,
    Rarity,
    RarityProbability,
    Version,
)


class Command(BaseCommand):
    help = (
        "Imports Pokémon sets, cards, rarities and rarity probabilities from CSV files"
    )

    def add_arguments(self, parser):
        parser.add_argument("--sets", type=str, help="Path to CSV file with set data")
        parser.add_argument("--cards", type=str, help="Path to CSV file with card data")
        parser.add_argument(
            "--rarities", type=str, help="Path to CSV file with rarity data"
        )
        parser.add_argument(
            "--rarityprob",
            type=str,
            help="Path to CSV file with rarity probability data",
        )
        parser.add_argument(
            "--settranslations",
            type=str,
            help="Path to CSV file with set name translations",
        )
        parser.add_argument(
            "--packtranslations",
            type=str,
            help="Path to CSV file with pack name translations",
        )
        parser.add_argument(
            "--cardtranslations",
            type=str,
            help="Path to CSV file with card name translations",
        )

    def handle(self, *args, **options):
        # If no arguments are supplied, import everything from the data directory
        if not any(
            [
                options["rarities"],
                options["rarityprob"],
                options["sets"],
                options["cards"],
                options["settranslations"],
                options["packtranslations"],
                options["cardtranslations"],
            ]
        ):
            base = "data/"
            options["rarities"] = base + "rarities.csv"
            options["rarityprob"] = base + "rarity_probabilities.csv"
            options["sets"] = base + "sets.csv"
            options["cards"] = base + "cards.csv"
            options["settranslations"] = base + "set_translations.csv"
            options["packtranslations"] = base + "pack_translations.csv"
            options["cardtranslations"] = base + "card_translations.csv"

        if options["rarities"]:
            self.import_rarities(options["rarities"])
        if options["rarityprob"]:
            self.import_rarity_probabilities(options["rarityprob"])
        if options["sets"]:
            self.import_sets(options["sets"])
        if options["cards"]:
            self.import_cards(options["cards"])
        if options["settranslations"]:
            self.import_set_translations(options["settranslations"])
        if options["packtranslations"]:
            self.import_pack_translations(options["packtranslations"])
        if options["cardtranslations"]:
            self.import_card_translations(options["cardtranslations"])

    def import_sets(self, filepath):
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                obj, created = PokemonSet.objects.update_or_create(
                    number=row["number"],
                    defaults={"name": row["name"], "release_date": row["release_date"]},
                )
                action = "Created" if created else "Updated"
                self.stdout.write(f"{action} Set: {obj.name}")

    def import_cards(self, filepath):
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    pset = PokemonSet.objects.get(number=row["set_number"])
                    rarity = Rarity.objects.get(name=row["rarity"])
                except ObjectDoesNotExist as e:
                    self.stderr.write(f"Skipping card {row['card']}: {e}")
                    continue

                # Card erstellen oder aktualisieren
                card_obj, created = Card.objects.update_or_create(
                    set=pset,
                    number=row["number"],
                    defaults={"name": row["card"], "rarity": rarity},
                )
                action = "Created" if created else "Updated"
                self.stdout.write(f"{action} Card: {card_obj.name}")

                # Pack behandeln
                pack_names = row.get("pack")
                if pack_names:
                    for pack_name in pack_names.split("|"):
                        pack_name = pack_name.strip()
                        if not pack_name:
                            continue

                        # Versuche Pack zu finden
                        pack_obj = pset.packs.filter(name=pack_name).first()
                        if not pack_obj:
                            # Neueste Version ermitteln
                            version = Version.objects.order_by("-name").first()
                            if not version:
                                self.stderr.write(
                                    f"No Version found, cannot create pack '{pack_name}' for card '{card_obj.name}'"
                                )
                                continue
                            # Pack neu anlegen
                            pack_obj = pset.packs.create(
                                name=pack_name, rarity_version=version
                            )
                            self.stdout.write(
                                f"→ Created new pack '{pack_name}' with version '{version.name}'"
                            )

                        # Karte zu Pack hinzufügen
                        card_obj.packs.add(pack_obj)
                        self.stdout.write(f"→ Assigned to pack: {pack_name}")

    def import_rarities(self, filepath):
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                obj, created = Rarity.objects.update_or_create(
                    name=row["name"],
                    defaults={
                        "display_name": row["display_name"],
                        "order": row["order"],
                    },
                )
                action = "Created" if created else "Updated"
                self.stdout.write(f"{action} Rarity: {obj.display_name}")

    def import_rarity_probabilities(self, filepath):
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    rarity = Rarity.objects.get(name=row["rarity"])
                except ObjectDoesNotExist as e:
                    self.stderr.write(
                        f"Skipping probability for rarity={row['rarity']} version={row['version']}: {e}"
                    )
                    continue
                version, created = Version.objects.get_or_create(name=row["version"])

                _obj, created = RarityProbability.objects.update_or_create(
                    rarity=rarity,
                    version=version,
                    defaults={
                        "probability_first": row["probability_first"],
                        "probability_fourth": row["probability_fourth"],
                        "probability_fifth": row["probability_fifth"],
                    },
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} RarityProbability: {rarity.name} / {version.name}"
                )

    def import_set_translations(self, filepath):
        from apps.tracker.models.cards import PokemonSet, PokemonSetNameTranslation

        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                set_obj = PokemonSet.objects.filter(name=row["english_name"]).first()
                if not set_obj:
                    self.stderr.write(f"Set not found: {row['english_name']}")
                    continue
                obj, created = PokemonSetNameTranslation.objects.update_or_create(
                    set=set_obj,
                    language_code="de",
                    defaults={"localized_name": row["german_name"]},
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} translation for set '{set_obj.name}': {row['german_name']}"
                )

    def import_pack_translations(self, filepath):
        from apps.tracker.models.cards import Pack, PackNameTranslation, PokemonSet

        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                set_obj = PokemonSet.objects.filter(
                    name=row["set_english_name"]
                ).first()
                if not set_obj:
                    self.stderr.write(f"Set not found: {row['set_english_name']}")
                    continue
                pack_obj = Pack.objects.filter(
                    set=set_obj, name=row["pack_english_name"]
                ).first()
                if not pack_obj:
                    self.stderr.write(
                        f"Pack not found: {row['pack_english_name']} in set {set_obj.name}"
                    )
                    continue
                _, created = PackNameTranslation.objects.update_or_create(
                    pack=pack_obj,
                    language_code="de",
                    defaults={"localized_name": row["pack_german_name"]},
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} translation for pack '{pack_obj.name}' in set '{set_obj.name}': {row['pack_german_name']}"
                )

    def import_card_translations(self, filepath):
        from apps.tracker.models.cards import Card, CardNameTranslation

        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                english_name = row["card_english_name"].strip()
                german_name = row["card_german_name"].strip()
                if not english_name or not german_name:
                    continue
                # Find all cards with this English name
                cards = Card.objects.filter(name=english_name)
                if not cards.exists():
                    self.stderr.write(f"Card not found: {english_name}")
                    continue
                for card in cards:
                    obj, created = CardNameTranslation.objects.update_or_create(
                        card=card,
                        language_code="de",
                        defaults={"localized_name": german_name},
                    )
                    action = "Created" if created else "Updated"
                    self.stdout.write(
                        f"{action} translation for card '{card.name}' ({card.set.name} {card.number}): {german_name}"
                    )
