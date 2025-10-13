from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0007_slots_refactor"),
    ]

    operations = [
        migrations.RenameField(
            model_name="rarityprobability",
            old_name="probability_first",
            new_name="probability_slot1",
        ),
        migrations.RenameField(
            model_name="rarityprobability",
            old_name="probability_fourth",
            new_name="probability_slot4",
        ),
        migrations.RenameField(
            model_name="rarityprobability",
            old_name="probability_fifth",
            new_name="probability_slot5",
        ),
    ]
