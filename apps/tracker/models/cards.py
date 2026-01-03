"""Tracker app cards models."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import get_language


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

    def get_god_pack_eligible_rarities(self):
        """Get rarities eligible for god packs in this generation.

        Returns rarities with illustration_rare or higher, including shinies for G2/G3.
        """
        base_rarities = [
            "illustration_rare",
            "special_art",
            "immersive_rare",
            "crown_rare",
        ]

        # G2 and G3 include shinies in god packs
        if self.name in ["G2", "G3"]:
            base_rarities.extend(["shiny_rare", "double_shiny_rare"])

        # Access Rarity model using Django's model registry to avoid circular reference
        from django.apps import apps

        rarity_model = apps.get_model("tracker", "Rarity")
        return rarity_model.objects.filter(name__in=base_rarities)

    def calculate_god_pack_probabilities(self, pack_type, pokemon_set):
        """Calculate probabilities for god pack rarities based on actual card counts.

        Args:
            pack_type: The god pack type to calculate probabilities for
            pokemon_set: The PokemonSet to count cards from

        Returns:
            dict: Mapping of rarity names to probability values for each slot
        """
        if not pack_type.is_god_pack:
            return {}

        eligible_rarities = self.get_god_pack_eligible_rarities()

        if eligible_rarities.count() == 0:
            return {}

        # Count cards of each eligible rarity in this set
        from django.apps import apps

        card_model = apps.get_model("tracker", "Card")

        rarity_card_counts = {}
        total_rare_cards = 0

        for rarity in eligible_rarities:
            card_count = card_model.objects.filter(
                set=pokemon_set, rarity=rarity
            ).count()
            rarity_card_counts[rarity.name] = card_count
            total_rare_cards += card_count

        if total_rare_cards == 0:
            return {}

        # Calculate probability for each rarity based on card count
        probabilities = {}
        for rarity_name, card_count in rarity_card_counts.items():
            if card_count > 0:
                rarity_prob = card_count / total_rare_cards

                slot_probs = []
                for _ in range(pack_type.slot_count):
                    slot_probs.append(rarity_prob)
                # Pad with zeros for unused slots (up to 6)
                while len(slot_probs) < 6:
                    slot_probs.append(0.0)

                probabilities[rarity_name] = slot_probs

        return probabilities

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
        """Get rarity probabilities for this set's generation.

        Args:
            pack_type: Optional PackType to get probabilities for. If god pack,
                      returns calculated probabilities instead of stored ones.

        Returns:
            QuerySet or dict: RarityProbability objects for normal/shiny packs,
                            or calculated probabilities dict for god packs
        """
        if not self.generation:
            return RarityProbability.objects.none()

        if pack_type and pack_type.is_god_pack:
            return self.generation.calculate_god_pack_probabilities(pack_type, self)

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

        return f"{self.rarity} ({generation_name} - {pack_type_name}): {shown}"

    def clean(self):
        """Validate that probabilities for each slot sum to 1.0 across all rarities for this generation/pack_type combination."""
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
        unique_together = ("generation", "pack_type", "rarity")
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
