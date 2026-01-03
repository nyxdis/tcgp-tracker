"""Management command to import data for tracker app."""

import csv

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from apps.tracker.models.cards import (
    Card,
    Generation,
    PackType,
    PokemonSet,
    Rarity,
    RarityProbability,
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
            "--packtypes", type=str, help="Path to CSV file with pack type data"
        )
        parser.add_argument(
            "--generations", type=str, help="Path to CSV file with generation data"
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
                options.get("rarities"),
                options.get("generations"),
                options.get("packtypes"),
                options.get("rarityprob"),
                options.get("sets"),
                options.get("cards"),
                options.get("settranslations"),
                options.get("packtranslations"),
                options.get("cardtranslations"),
            ]
        ):
            base = "data/"
            options["rarities"] = base + "rarities.csv"
            options["generations"] = base + "generations.csv"
            options["packtypes"] = base + "pack_types.csv"
            options["rarityprob"] = base + "rarity_probabilities.csv"
            options["sets"] = base + "sets.csv"
            options["cards"] = base + "cards.csv"
            options["settranslations"] = base + "set_translations.csv"
            options["packtranslations"] = base + "pack_translations.csv"
            options["cardtranslations"] = base + "card_translations.csv"

        if options["rarities"]:
            self.import_rarities(options["rarities"])
        if options["generations"]:
            self.import_generations(options["generations"])
        if options["packtypes"]:
            self.import_pack_types(options["packtypes"])
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
                defaults = {"name": row["name"], "release_date": row["release_date"]}

                # Handle generation field
                if "generation" in row and row["generation"]:
                    try:
                        generation = Generation.objects.get(name=row["generation"])
                        defaults["generation"] = generation
                    except ObjectDoesNotExist:
                        self.stderr.write(
                            f"Skipping set {row['number']}: Generation {row['generation']} not found"
                        )
                        continue

                obj, created = PokemonSet.objects.update_or_create(
                    number=row["number"],
                    defaults=defaults,
                )
                action = "Created" if created else "Updated"
                generation_info = (
                    f" (generation: {obj.generation})" if obj.generation else ""
                )
                self.stdout.write(f"{action} Set: {obj.name}{generation_info}")

    def import_generations(self, filepath):
        """Import generations from CSV file."""
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                obj, created = Generation.objects.update_or_create(
                    name=row["name"],
                    defaults={
                        "display_name": row["display_name"],
                        "description": row.get("description", ""),
                    },
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} Generation: {obj.name} - {obj.display_name}"
                )

    def import_pack_types(self, filepath):
        """Import pack types from CSV file."""
        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    generation = Generation.objects.get(name=row["generation"])
                except ObjectDoesNotExist:
                    self.stderr.write(
                        f"Skipping pack type {row['pack_type']}: Generation {row['generation']} not found"
                    )
                    continue

                obj, created = PackType.objects.update_or_create(
                    generation=generation,
                    name=row["pack_type"],
                    defaults={
                        "display_name": row["display_name"],
                        "slot_count": int(row["slot_count"]),
                        "occurrence_probability": float(row["occurrence_probability"]),
                        "description": row["description"],
                    },
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} PackType: {obj.generation.name} - {obj.display_name}"
                )

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
                            # Neueste Generation ermitteln
                            generation = Generation.objects.order_by("-name").first()
                            if not generation:
                                self.stderr.write(
                                    f"No Generation found, cannot create pack '{pack_name}' for card '{card_obj.name}'"
                                )
                                continue
                            # Pack neu anlegen
                            pack_obj = pset.packs.create(
                                name=pack_name, rarity_version=generation
                            )
                            self.stdout.write(
                                f"→ Created new pack '{pack_name}' with generation '{generation.name}'"
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
                    generation = Generation.objects.get(name=row["generation"])
                    pack_type = PackType.objects.get(
                        name=row["pack_type"], generation=generation
                    )
                except ObjectDoesNotExist as e:
                    self.stderr.write(
                        f"Skipping probability for rarity={row['rarity']} generation={row['generation']} pack_type={row['pack_type']}: {e}"
                    )
                    continue

                # Skip god pack probabilities - they are calculated dynamically
                if pack_type.is_god_pack:
                    self.stdout.write(
                        f"Skipping god pack probability: {generation.name} - {pack_type.name} - {rarity.name} (calculated dynamically)"
                    )
                    continue

                try:
                    # Normalized naming: probability_slot1..probability_slot6
                    prob_slot1 = float(row.get("probability_slot1", 0))
                    prob_slot2 = float(row.get("probability_slot2", 0))
                    prob_slot3 = float(row.get("probability_slot3", 0))
                    prob_slot4 = float(row.get("probability_slot4", 0))
                    prob_slot5 = float(row.get("probability_slot5", 0))
                    prob_slot6 = float(row.get("probability_slot6", 0))

                    # First, delete any conflicting records to prevent unique constraint violations
                    # Remove records that would conflict with the new unique constraint
                    RarityProbability.objects.filter(
                        rarity=rarity, generation=generation, pack_type=pack_type
                    ).delete()

                    # Also clean up any orphaned records with null generation/pack_type for this rarity
                    RarityProbability.objects.filter(
                        rarity=rarity, generation__isnull=True, pack_type__isnull=True
                    ).delete()

                    # Create the new record with proper values
                    _obj = RarityProbability.objects.create(
                        rarity=rarity,
                        generation=generation,
                        pack_type=pack_type,
                        probability_slot1=prob_slot1,
                        probability_slot2=prob_slot2,
                        probability_slot3=prob_slot3,
                        probability_slot4=prob_slot4,
                        probability_slot5=prob_slot5,
                        probability_slot6=prob_slot6,
                    )
                    action = "Created"

                    self.stdout.write(
                        f"{action} RarityProbability: {generation.name} - {pack_type.name} - {rarity.name}"
                    )

                except ValueError as e:
                    self.stderr.write(f"Invalid probability value: {e}")

    def import_set_translations(self, filepath):
        from apps.tracker.models.cards import PokemonSetNameTranslation

        with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                set_obj = PokemonSet.objects.filter(name=row["english_name"]).first()
                if not set_obj:
                    self.stderr.write(f"Set not found: {row['english_name']}")
                    continue
                _obj, created = PokemonSetNameTranslation.objects.update_or_create(
                    set=set_obj,
                    language_code="de",
                    defaults={"localized_name": row["german_name"]},
                )
                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action} translation for set '{set_obj.name}': {row['german_name']}"
                )

    def import_pack_translations(self, filepath):
        from apps.tracker.models.cards import Pack, PackNameTranslation

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
        from apps.tracker.models.cards import CardNameTranslation

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
                    _obj, created = CardNameTranslation.objects.update_or_create(
                        card=card,
                        language_code="de",
                        defaults={"localized_name": german_name},
                    )
                    action = "Created" if created else "Updated"
                    self.stdout.write(
                        f"{action} translation for card '{card.name}' ({card.set.name} {card.number}): {german_name}"
                    )
