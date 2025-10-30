# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0008_normalize_probability_field_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="pokemonset",
            name="available_until",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Date when this set's packs are no longer available (leave empty if still available)",
                null=True,
                verbose_name="Available Until",
            ),
        ),
    ]
