"""Management command to update Pack rarity_version references from old versions to new generations."""

from django.core.management.base import BaseCommand

from apps.tracker.models.cards import Generation, Pack


class Command(BaseCommand):
    help = "Update Pack rarity_version references from old versions (v1, v2, etc.) to new generations (G1, G2, etc.)"

    def handle(self, *args, **options):
        # Define the mapping from old version names to new generation names
        version_to_generation_map = {
            "v1": "G1",
            "v2": "G2",
            "v3": "G3",
            "v4": "G4",
        }

        updated_count = 0

        for old_name, new_name in version_to_generation_map.items():
            try:
                # Get the old generation (version)
                old_generation = Generation.objects.get(name=old_name)
                # Get the new generation
                new_generation = Generation.objects.get(name=new_name)

                # Update all packs that reference the old generation
                packs_to_update = Pack.objects.filter(rarity_version=old_generation)
                count = packs_to_update.count()

                if count > 0:
                    packs_to_update.update(rarity_version=new_generation)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated {count} packs from {old_name} to {new_name}"
                        )
                    )
                    updated_count += count
                else:
                    self.stdout.write(f"No packs found referencing {old_name}")

            except Generation.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Generation {old_name} or {new_name} not found, skipping"
                    )
                )
                continue

        self.stdout.write(
            self.style.SUCCESS(f"Successfully updated {updated_count} packs total")
        )
