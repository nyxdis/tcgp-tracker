"""Tracker app cards models."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import get_language


class Version(models.Model):
    """Represents a generation of rarity distribution."""

    name = models.CharField(
        max_length=3,
        primary_key=True,
        verbose_name="Short Name",
        help_text="Short code for the version, e.g. V1",
    )
    display_name = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Display Name",
        help_text="Display name for the version",
    )
    slot_count = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="Number of Slots",
        help_text="How many card slots a pack of this version contains",
    )

    def __str__(self):
        return f"{self.display_name}"

    class Meta:
        verbose_name = "Version"
        verbose_name_plural = "Versions"


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

    class Meta:
        ordering = ("release_date",)
        indexes = [models.Index(fields=["release_date"])]
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
    """Probability of drawing a rarity in each slot for a given version.

    Normalized field names: probability_slot1 .. probability_slot5
    Slots above Version.slot_count are ignored for validation.
    """

    rarity = models.ForeignKey(
        Rarity, on_delete=models.CASCADE, related_name="probabilities"
    )
    version = models.ForeignKey(
        Version, on_delete=models.CASCADE, related_name="rarity_probabilities"
    )

    probability_slot1 = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="Slot 1 Probability",
    )
    # New explicit fields for slots 2 and 3 (were implicitly same as slot1 before)
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

    def __str__(self):
        fields = [
            self.probability_slot1,
            self.probability_slot2,
            self.probability_slot3,
            self.probability_slot4,
            self.probability_slot5,
        ]
        shown = " / ".join(f"{p * 100:.3f}%" for p in fields if p is not None)
        return f"{self.rarity}: {shown}"

    def clean(self):
        # Cross-rarity per-slot sum validation moved to admin inline formset &
        # management command. Intentionally left empty.
        pass

    class Meta:
        unique_together = ("version", "rarity")
        verbose_name = "Rarity Probability"
        verbose_name_plural = "Rarity Probabilities"
        indexes = [models.Index(fields=["version", "rarity"])]


class Pack(models.Model):
    """Represents a booster pack in a set."""

    set = models.ForeignKey(PokemonSet, related_name="packs", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True, verbose_name="Pack Name")
    rarity_version = models.ForeignKey(
        Version, on_delete=models.PROTECT, related_name="packs"
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
