"""Tracker app cards models."""

import re

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import get_language

SLOT_FIELD_COUNT = 6

# Rarities that can appear in a god pack: illustration rare and above. Shiny
# rarities are added for the generations that put shinies into normal packs.
GOD_PACK_BASE_RARITIES = (
    "illustration_rare",
    "special_art",
    "immersive_rare",
    "crown_rare",
)
GOD_PACK_SHINY_RARITIES = ("shiny_rare", "double_shiny_rare")
GOD_PACK_SHINY_GENERATIONS = ("G2", "G3")


def god_pack_slot_table(rarity_card_counts, slot_count):
    """Build a god pack rarity table from per-rarity card counts.

    A god pack draws every slot uniformly from the pack's eligible cards, so the
    probability of a rarity in any slot is its share of that pool.

    Args:
        rarity_card_counts: Mapping of rarity name to number of eligible cards
            of that rarity in the pack.
        slot_count: Number of card slots in the god pack.

    Returns:
        dict: ``{rarity_name: [p, ..., p, 0.0, ...]}`` padded to 6 slots. Empty
        when the pool is empty.
    """
    total = sum(rarity_card_counts.values())
    if total <= 0:
        return {}
    slot_count = min(slot_count, SLOT_FIELD_COUNT)
    table = {}
    for name, count in rarity_card_counts.items():
        if count <= 0:
            continue
        share = count / total
        table[name] = [share] * slot_count + [0.0] * (SLOT_FIELD_COUNT - slot_count)
    return table


class PackType(models.Model):
    """Represents different types of booster packs for a specific generation."""

    generation = models.ForeignKey(
        "Generation",
        on_delete=models.CASCADE,
        related_name="pack_types",
        verbose_name="Generation",
        help_text="The generation this pack type belongs to",
    )
    name = models.CharField(
        max_length=20,
        verbose_name="Pack Type Name",
        help_text="Internal pack type name, e.g. normal, shiny, god",
    )
    display_name = models.CharField(
        max_length=30,
        verbose_name="Display Name",
        help_text="Display name for the pack type",
    )
    slot_count = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="Number of Slots",
        help_text="How many card slots this pack type contains",
    )
    occurrence_probability = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="Occurrence Probability",
        help_text="Probability of getting this pack type (as decimal, e.g. 0.05238 for 5.238%)",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description",
        help_text="Optional description of this pack type",
    )

    def __str__(self):
        return f"{self.generation.name} - {self.display_name} ({self.occurrence_probability * 100:.3f}%)"

    @property
    def is_god_pack(self):
        """Check if this is a god pack type."""
        return "god" in str(self.name).lower()

    class Meta:
        verbose_name = "Pack Type"
        verbose_name_plural = "Pack Types"
        unique_together = ("generation", "name")
        ordering = ("generation", "-occurrence_probability")


class Generation(models.Model):
    """Represents a generation of rarity distribution and pack types."""

    name = models.CharField(
        max_length=3,
        primary_key=True,
        verbose_name="Short Name",
        help_text="Short code for the generation, e.g. G1",
    )
    display_name = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Display Name",
        help_text="Display name for the generation",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description",
        help_text="Optional description of this generation",
    )

    def __str__(self):
        return f"{self.display_name}"

    @property
    def total_pack_types(self):
        """Count of pack types using this generation."""
        return self.pack_types.count()

    def god_pack_eligible_rarity_names(self):
        """Names of the rarities that can appear in this generation's god packs."""
        names = list(GOD_PACK_BASE_RARITIES)
        if self.name in GOD_PACK_SHINY_GENERATIONS:
            names.extend(GOD_PACK_SHINY_RARITIES)
        return names

    def get_god_pack_eligible_rarities(self):
        """Rarities eligible for god packs: illustration rare and higher, plus
        shinies for the generations that have them in normal packs."""
        from django.apps import apps

        rarity_model = apps.get_model("tracker", "Rarity")
        return rarity_model.objects.filter(
            name__in=self.god_pack_eligible_rarity_names()
        )

    def calculate_god_pack_probabilities(self, pack_type, pack):
        """Calculate the god pack rarity table for one pack.

        A god pack draws from the pack's own pool of eligible cards, so the
        counts are taken per pack, not per set.

        Args:
            pack_type: The god pack type to calculate probabilities for.
            pack: The Pack whose cards form the pool.

        Returns:
            dict: Mapping of rarity name to probability per slot (6 entries).
        """
        if not pack_type.is_god_pack:
            return {}

        counts = {
            row["rarity_id"]: row["n"]
            for row in pack.cards.filter(
                rarity_id__in=self.god_pack_eligible_rarity_names()
            )
            .values("rarity_id")
            .annotate(n=models.Count("id"))
        }
        return god_pack_slot_table(counts, pack_type.slot_count)

    class Meta:
        verbose_name = "Generation"
        verbose_name_plural = "Generations"
        ordering = ("name",)


class PokemonSet(models.Model):
    """Represents a set of Pokémon cards."""

    number = models.CharField(
        max_length=10,
        db_index=True,
        verbose_name="Set Number",
        help_text="Set code or number",
    )
    name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Set Name",
        help_text="Name of the set",
    )
    release_date = models.DateField(
        db_index=True, verbose_name="Release Date", help_text="Release date of the set"
    )
    available_until = models.DateField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Available Until",
        help_text="Date when this set's packs are no longer available (leave empty if still available)",
    )
    generation = models.ForeignKey(
        Generation,
        on_delete=models.PROTECT,
        related_name="pokemon_sets",
        verbose_name="Generation",
        help_text="The generation this set belongs to (defines pack types and rarity probabilities)",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.name}"

    def get_localized_name(self, language_code):
        translation = self.translations.filter(language_code=language_code).first()
        if translation:
            return translation.localized_name
        return self.name

    @property
    def localized_name(self):
        language_code = get_language() or "en"
        return self.get_localized_name(language_code)

    @property
    def series(self):
        """Series letter(s) leading the set number, e.g. "B" for "B2a"."""
        return re.match(r"[A-Za-z]*", self.number).group().upper()

    @property
    def is_available(self):
        """Check if this set is currently available (not expired)."""
        from django.utils import timezone

        if self.available_until is None:
            return True
        return timezone.now().date() <= self.available_until

    def get_pack_types(self):
        """Get pack types for this set's generation."""
        if not self.generation:
            return PackType.objects.none()
        return self.generation.pack_types.all()

    def get_rarity_probabilities(self, pack_type=None):
        """Get the stored rarity probabilities for this set's generation.

        God pack tables are not stored; they depend on the individual pack's
        card pool, see :meth:`Generation.calculate_god_pack_probabilities`.

        Args:
            pack_type: Optional PackType to filter by.

        Returns:
            QuerySet: RarityProbability rows.
        """
        if not self.generation:
            return RarityProbability.objects.none()

        queryset = self.generation.rarity_probabilities.all()
        if pack_type:
            queryset = queryset.filter(pack_type=pack_type)

        return queryset

    class Meta:
        ordering = ("release_date",)
        indexes = [
            models.Index(fields=["release_date"]),
            models.Index(fields=["generation"]),
        ]
        verbose_name = "Pokémon Set"
        verbose_name_plural = "Pokémon Sets"


class PokemonSetNameTranslation(models.Model):
    """Stores localized names for Pokémon sets."""

    set = models.ForeignKey(
        PokemonSet, related_name="translations", on_delete=models.CASCADE
    )
    language_code = models.CharField(max_length=10, db_index=True)
    localized_name = models.CharField(max_length=100, db_index=True)

    class Meta:
        unique_together = ("set", "language_code")
        indexes = [models.Index(fields=["language_code", "localized_name"])]
        verbose_name = "Set Name Translation"
        verbose_name_plural = "Set Name Translations"

    def __str__(self):
        return f"{self.localized_name} ({self.language_code}) for {self.set}"


class Rarity(models.Model):
    """Represents the rarity of a card."""

    name = models.CharField(
        max_length=20,
        primary_key=True,
        verbose_name="Rarity Name",
        help_text="Internal rarity name",
    )
    display_name = models.CharField(
        max_length=4,
        unique=True,
        verbose_name="Display Name",
        help_text="Display name for rarity",
    )
    order = models.PositiveSmallIntegerField(
        unique=True, verbose_name="Order", help_text="Display order for rarity"
    )
    image_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Image Name",
        help_text="Optional image filename for rarity symbol",
    )
    repeat_count = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Repeat Count",
        help_text="How many times the rarity symbol repeats",
    )

    def __str__(self):
        return f"{self.display_name}"

    @property
    def label(self):
        """Human-readable rarity name, for use in alt text and other a11y contexts."""
        return self.name.replace("_", " ").title()

    class Meta:
        ordering = ("order",)
        indexes = [models.Index(fields=["order"])]
        verbose_name = "Rarity"
        verbose_name_plural = "Rarities"


class RarityProbability(models.Model):
    """Probability of drawing a rarity in each slot for a given generation and pack type.

    Normalized field names: probability_slot1 .. probability_slot6
    """

    rarity = models.ForeignKey(
        Rarity, on_delete=models.CASCADE, related_name="probabilities"
    )
    is_foil = models.BooleanField(
        default=False,
        verbose_name="Foil",
        help_text="Applies to the parallel-foil prints of this rarity (deluxe packs)",
    )
    generation = models.ForeignKey(
        Generation,
        on_delete=models.CASCADE,
        related_name="rarity_probabilities",
        null=True,  # Temporary for migration
        blank=True,  # Temporary for migration
    )
    pack_type = models.ForeignKey(
        PackType,
        on_delete=models.CASCADE,
        related_name="rarity_probabilities",
        verbose_name="Pack Type",
        help_text="The pack type this probability applies to",
        null=True,  # Temporary for migration
        blank=True,  # Temporary for migration
    )

    probability_slot1 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="Slot 1 Probability",
    )
    probability_slot2 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=0.0,
        verbose_name="Slot 2 Probability",
    )
    probability_slot3 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=0.0,
        verbose_name="Slot 3 Probability",
    )
    probability_slot4 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=0.0,
        verbose_name="Slot 4 Probability",
    )
    probability_slot5 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=0.0,
        verbose_name="Slot 5 Probability",
    )
    probability_slot6 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=0.0,
        verbose_name="Slot 6 Probability",
        help_text="For special pack types like shiny packs with extra cards",
    )

    def get_slot_probabilities(self):
        """Get probability values for all slots as a list."""
        return [
            self.probability_slot1,
            self.probability_slot2,
            self.probability_slot3,
            self.probability_slot4,
            self.probability_slot5,
            self.probability_slot6,
        ]

    def __str__(self):
        probabilities = self.get_slot_probabilities()
        shown = " / ".join(f"{p * 100:.3f}%" for p in probabilities if p > 0)

        # Handle nullable pack_type during migration
        pack_type_name = self.pack_type.name if self.pack_type else "unknown"
        generation_name = self.generation.name if self.generation else "unknown"

        foil = " foil" if self.is_foil else ""
        return f"{self.rarity}{foil} ({generation_name} - {pack_type_name}): {shown}"

    def clean(self):
        """Validate that probabilities for each slot sum to 1.0 across all rarities
        for this generation/pack_type combination."""
        # Note: This validation could be expensive for large datasets
        # Consider moving to a management command for batch validation
        super().clean()

        if not (self.generation_id and self.pack_type_id):
            return  # Skip validation if foreign keys aren't set yet

        # Basic validation: ensure probabilities are reasonable
        slot_probs = self.get_slot_probabilities()
        for i, prob in enumerate(slot_probs, 1):
            if prob > 1.0:
                from django.core.exceptions import ValidationError

                raise ValidationError(f"Slot {i} probability cannot exceed 100%")

    class Meta:
        unique_together = ("generation", "pack_type", "rarity", "is_foil")
        verbose_name = "Rarity Probability"
        verbose_name_plural = "Rarity Probabilities"
        indexes = [models.Index(fields=["generation", "pack_type", "rarity"])]


class Pack(models.Model):
    """Represents a booster pack in a set."""

    set = models.ForeignKey(PokemonSet, related_name="packs", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True, verbose_name="Pack Name")
    rarity_version = models.ForeignKey(
        Generation, on_delete=models.PROTECT, related_name="packs"
    )

    def __str__(self):
        return f"{self.name}"

    def get_localized_name(self, language_code):
        translation = self.translations.filter(language_code=language_code).first()
        if translation:
            return translation.localized_name
        return self.name

    @property
    def localized_name(self):
        language_code = get_language() or "en"
        return self.get_localized_name(language_code)

    class Meta:
        ordering = ("set", "name")
        unique_together = ("set", "name")
        indexes = [models.Index(fields=["set", "name"])]
        verbose_name = "Pack"
        verbose_name_plural = "Packs"


class PackNameTranslation(models.Model):
    """Stores localized names for Packs."""

    pack = models.ForeignKey(
        Pack, related_name="translations", on_delete=models.CASCADE
    )
    language_code = models.CharField(max_length=10, db_index=True)
    localized_name = models.CharField(max_length=100, db_index=True)

    class Meta:
        unique_together = ("pack", "language_code")
        indexes = [models.Index(fields=["language_code", "localized_name"])]
        verbose_name = "Pack Name Translation"
        verbose_name_plural = "Pack Name Translations"

    def __str__(self):
        return f"{self.localized_name} ({self.language_code}) for {self.pack}"


class Card(models.Model):
    """Represents a Pokémon card."""

    set = models.ForeignKey(PokemonSet, related_name="cards", on_delete=models.CASCADE)
    number = models.CharField(max_length=10, db_index=True, verbose_name="Card Number")
    name = models.CharField(max_length=100, db_index=True, verbose_name="Card Name")
    rarity = models.ForeignKey(Rarity, on_delete=models.PROTECT, related_name="cards")
    is_foil = models.BooleanField(
        default=False,
        verbose_name="Foil",
        help_text=(
            "Parallel-foil print of a card that also exists as a standard print "
            "(deluxe packs draw the two from different slots)"
        ),
    )
    packs = models.ManyToManyField(Pack, related_name="cards", blank=True)

    def __str__(self):
        return f"{self.name} ({self.set.number} {self.number})"

    def get_localized_name(self, language_code):
        translation = self.translations.filter(language_code=language_code).first()
        if translation:
            return translation.localized_name
        return self.name

    @property
    def localized_name(self):
        language_code = get_language() or "en"
        return self.get_localized_name(language_code)

    class Meta:
        ordering = ("set", "number")
        unique_together = ("set", "number")
        indexes = [models.Index(fields=["set", "number"])]
        verbose_name = "Card"
        verbose_name_plural = "Cards"


class CardNameTranslation(models.Model):
    """Stores localized names for Pokémon cards."""

    card = models.ForeignKey(
        Card, related_name="translations", on_delete=models.CASCADE
    )
    language_code = models.CharField(max_length=10, db_index=True)
    localized_name = models.CharField(max_length=100, db_index=True)

    class Meta:
        unique_together = ("card", "language_code")
        indexes = [models.Index(fields=["language_code", "localized_name"])]
        verbose_name = "Card Name Translation"
        verbose_name_plural = "Card Name Translations"

    def __str__(self):
        return f"{self.localized_name} ({self.language_code}) for {self.card}"
