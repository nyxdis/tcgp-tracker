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

    def handle(self, *args, **options):
        if options["sets"]:
            self.import_sets(options["sets"])
        if options["cards"]:
            self.import_cards(options["cards"])
        if options["rarities"]:
            self.import_rarities(options["rarities"])
        if options["rarityprob"]:
            self.import_rarity_probabilities(options["rarityprob"])

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
