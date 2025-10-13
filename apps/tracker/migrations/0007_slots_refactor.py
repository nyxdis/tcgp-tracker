# Generated manually for slot probability refactor
from django.db import migrations, models


def copy_legacy_probabilities(apps, schema_editor):
    RarityProbability = apps.get_model("tracker", "RarityProbability")
    for rp in RarityProbability.objects.all():
        # Previously slots 1-3 shared probability_first; copy it into slot2/slot3 if zero.
        changed = False
        if getattr(rp, "probability_slot2", 0.0) in (0, 0.0):
            rp.probability_slot2 = rp.probability_first
            changed = True
        if getattr(rp, "probability_slot3", 0.0) in (0, 0.0):
            rp.probability_slot3 = rp.probability_first
            changed = True
        if changed:
            rp.save(update_fields=["probability_slot2", "probability_slot3"])


def noop_reverse(apps, schema_editor):
    # No reverse action (fields will still exist)
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0006_packnametranslation_pokemonsetnametranslation"),
    ]

    operations = [
        migrations.AddField(
            model_name="version",
            name="slot_count",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="How many card slots a pack of this version contains",
                verbose_name="Number of Slots",
            ),
        ),
        migrations.AddField(
            model_name="rarityprobability",
            name="probability_slot2",
            field=models.FloatField(
                default=0.0, help_text="", verbose_name="Slot 2 Probability"
            ),
        ),
        migrations.AddField(
            model_name="rarityprobability",
            name="probability_slot3",
            field=models.FloatField(
                default=0.0, help_text="", verbose_name="Slot 3 Probability"
            ),
        ),
        migrations.AlterField(
            model_name="rarityprobability",
            name="probability_first",
            field=models.FloatField(verbose_name="Slot 1 Probability"),
        ),
        migrations.AlterField(
            model_name="rarityprobability",
            name="probability_fourth",
            field=models.FloatField(default=0.0, verbose_name="Slot 4 Probability"),
        ),
        migrations.AlterField(
            model_name="rarityprobability",
            name="probability_fifth",
            field=models.FloatField(default=0.0, verbose_name="Slot 5 Probability"),
        ),
        migrations.RunPython(copy_legacy_probabilities, noop_reverse),
    ]
