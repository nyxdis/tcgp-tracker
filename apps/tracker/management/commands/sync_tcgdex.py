from django.core.management.base import BaseCommand
from tcgdexsdk import Language, TCGdex

from apps.tracker.models.cards import Card, Pack, PokemonSet, Rarity, Version


class Command(BaseCommand):
    help = "Sync TCG data from tcgdex API"

    def handle(self, *args, **options):
        sdk = TCGdex(Language.EN)
        serie = sdk.serie.getSync("tcgp")
        db_set_numbers = set(PokemonSet.objects.values_list("number", flat=True))

        new_sets = [s for s in serie.sets if s.id not in db_set_numbers]

        if new_sets:
            self.stdout.write(self.style.WARNING("New sets found:"))
            for s in new_sets:
                if s.id == "P-A":
                    continue  # Skip the special 'P-A' set
                self.import_new_sets(s.id)

        # Compare card counts for each set and import missing cards if needed
        for s in serie.sets:
            if s.id == "P-A":
                continue  # Skip the special 'P-A' set

            sdk_card_count = s.cardCount.total
            local_card_count = Card.objects.filter(set__number=s.id).count()
            self.stdout.write(
                f"Set {s.id}: SDK={sdk_card_count}, Local={local_card_count}"
            )
            if sdk_card_count != local_card_count:
                self.stdout.write(
                    self.style.WARNING(
                        f"Card count mismatch for set {s.id}. Importing missing cards..."
                    )
                )
                # Get or create the set object
                set_obj, _ = PokemonSet.objects.get_or_create(
                    number=s.id,
                    defaults={
                        "name": s.name,
                        "release_date": getattr(s, "releaseDate", None),
                    },
                )
                # Import all cards from SDK for this set
                sdk_set = sdk.set.getSync(s.id)
                for card in sdk_set.cards:
                    # Only import if not already present
                    if not Card.objects.filter(
                        set=set_obj, number=card.localId
                    ).exists():
                        self.import_card(set_obj, card.id)

    def import_new_sets(self, set_number):
        sdk = TCGdex(Language.EN)
        s = sdk.set.getSync(set_number)
        self.stdout.write(f"- {s.id} - {s.name} (released {s.releaseDate})")

        set_obj = PokemonSet.objects.create(
            number=s.id, name=s.name, release_date=s.releaseDate
        )

        for pack in s.boosters:
            rarity_version = Version.objects.order_by("-name").first()
            self.stdout.write(f"  - {pack.id} - {pack.name} - {rarity_version}")
            Pack.objects.create(
                set=set_obj,
                name=pack.name,
                rarity_version=rarity_version,
            )

        for card in s.cards:
            self.import_card(set_obj, card.id)

    def import_card(self, set_obj, card_id):
        sdk = TCGdex(Language.EN)
        card = sdk.card.getSync(card_id)

        booster_names = []
        if card.boosters:
            booster_names = [booster.name for booster in card.boosters]
        else:
            booster_names = [card.set.name]

        # Map SDK rarity to your Rarity model
        rarity_map = {
            "One Diamond": "common",
            "Two Diamond": "uncommon",
            "Three Diamond": "rare",
            "Four Diamond": "double_rare",
            "One Star": "illustration_rare",
            "Two Star": "special_art",
            "Three Star": "immersive_rare",
            "One Shiny": "shiny_rare",
            "Two Shiny": "double_shiny_rare",
            "Crown": "crown_rare",
        }
        mapped_rarity = rarity_map.get(card.rarity)

        self.stdout.write(
            f"  - {card.set.id} - {card.localId} - {card.name} - {mapped_rarity} - {booster_names}"
        )

        card_obj = Card.objects.create(
            set=set_obj,
            number=card.localId,
            name=card.name,
            rarity=Rarity.objects.get(name=mapped_rarity),
        )
        card_obj.packs.set(
            Pack.objects.filter(set__number=card.set.id, name__in=booster_names)
        )
