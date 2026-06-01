from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.tracker.models.cards import PackType, RarityProbability


class Command(BaseCommand):
    help = "Validate that for every pack type each active slot (1..slot_count) sums to 1.0 across rarities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-fast", action="store_true", help="Stop at first error and exit"
        )
        parser.add_argument(
            "--show-all", action="store_true", help="Show all slot sums even if valid"
        )

    def handle(self, *args, **options):
        fail_fast = options["fail_fast"]
        show_all = options["show_all"]
        errors = 0
        for pack_type in PackType.objects.select_related("generation").order_by(
            "generation__name", "name"
        ):
            slot_fields = [
                "probability_slot1",
                "probability_slot2",
                "probability_slot3",
                "probability_slot4",
                "probability_slot5",
                "probability_slot6",
            ][: pack_type.slot_count]
            agg = RarityProbability.objects.filter(
                generation=pack_type.generation, pack_type=pack_type
            ).aggregate(**{f: Sum(f) for f in slot_fields})
            label = f"{pack_type.generation.name}/{pack_type.name}"
            for f in slot_fields:
                total = agg.get(f) or 0.0
                if abs(total - 1.0) > 1e-5:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"{label} slot {f[-1]} sum={total:.6f} (!= 1.0)"
                        )
                    )
                    if fail_fast:
                        break
                elif show_all:
                    self.stdout.write(
                        self.style.SUCCESS(f"{label} slot {f[-1]} OK (sum={total:.6f})")
                    )
            if fail_fast and errors:
                break
        if errors:
            self.stderr.write(
                self.style.ERROR(f"Validation FAILED: {errors} issue(s).")
            )
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All rarity probability slot sums valid."))
