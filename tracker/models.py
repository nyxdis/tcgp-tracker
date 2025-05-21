from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class Version(models.Model):
    """Represents a generation of rarity distribution."""
    name = models.CharField(max_length=3, primary_key=True, verbose_name="Short Name", help_text="Short code for the version, e.g. V1")
    display_name = models.CharField(max_length=10, unique=True, verbose_name="Display Name", help_text="Display name for the version")

    def __str__(self):
        return f"{self.display_name}"

    class Meta:
        verbose_name = "Version"
        verbose_name_plural = "Versions"

class PokemonSet(models.Model):
    """Represents a set of Pokémon cards."""
    number = models.CharField(max_length=10, db_index=True, verbose_name="Set Number", help_text="Set code or number")
    name = models.CharField(max_length=100, db_index=True, verbose_name="Set Name", help_text="Name of the set")
    release_date = models.DateField(db_index=True, verbose_name="Release Date", help_text="Release date of the set")

    def __str__(self):
        return f"{self.name}"

    class Meta:
        ordering = ("release_date",)
        indexes = [
            models.Index(fields=["release_date"]),
        ]
        verbose_name = "Pokémon Set"
        verbose_name_plural = "Pokémon Sets"

class Rarity(models.Model):
    """Represents the rarity of a card."""
    name = models.CharField(max_length=20, primary_key=True, verbose_name="Rarity Name", help_text="Internal rarity name")
    display_name = models.CharField(max_length=4, unique=True, verbose_name="Display Name", help_text="Display name for rarity")
    order = models.PositiveSmallIntegerField(unique=True, verbose_name="Order", help_text="Display order for rarity")
    image_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Image Name", help_text="Optional image filename for rarity symbol")
    repeat_count = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name="Repeat Count", help_text="How many times the rarity symbol repeats")

    def __str__(self):
        return f"{self.display_name}"

    class Meta:
        ordering = ("order",)
        indexes = [
            models.Index(fields=["order"]),
        ]
        verbose_name = "Rarity"
        verbose_name_plural = "Rarities"

class RarityProbability(models.Model):
    """Probability of drawing a rarity in a given version."""
    rarity = models.ForeignKey(Rarity, on_delete=models.CASCADE, related_name="probabilities")
    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name="rarity_probabilities")
    probability_first = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], verbose_name="First Slot Probability")
    probability_fourth = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], verbose_name="Fourth Slot Probability")
    probability_fifth = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], verbose_name="Fifth Slot Probability")

    def __str__(self):
        return f"{self.rarity}: {self.probability_first * 100:.3f}% / {self.probability_fourth * 100:.3f}% / {self.probability_fifth * 100:.3f}%"

    def clean(self):
        from django.core.exceptions import ValidationError
        epsilon = 1e-5
        qs = type(self).objects.filter(version=self.version)  # type: ignore[attr-defined]
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        prob_first = sum(rp.probability_first for rp in qs) + self.probability_first
        prob_fourth = sum(rp.probability_fourth for rp in qs) + self.probability_fourth
        prob_fifth = sum(rp.probability_fifth for rp in qs) + self.probability_fifth
        errors = {}
        if abs(prob_first - 1.0) > epsilon:
            errors['probability_first'] = f"Sum of probability_first for version {self.version} is {prob_first}, should be 1.0"
        if abs(prob_fourth - 1.0) > epsilon:
            errors['probability_fourth'] = f"Sum of probability_fourth for version {self.version} is {prob_fourth}, should be 1.0"
        if abs(prob_fifth - 1.0) > epsilon:
            errors['probability_fifth'] = f"Sum of probability_fifth for version {self.version} is {prob_fifth}, should be 1.0"
        if errors:
            raise ValidationError(errors)

    class Meta:
        unique_together = ("version", "rarity")
        verbose_name = "Rarity Probability"
        verbose_name_plural = "Rarity Probabilities"
        indexes = [
            models.Index(fields=["version", "rarity"]),
        ]

class Pack(models.Model):
    """Represents a booster pack in a set."""
    set = models.ForeignKey(PokemonSet, related_name="packs", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True, verbose_name="Pack Name")
    rarity_version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="packs")

    def __str__(self):
        return f"{self.name}"

    class Meta:
        ordering = ("set", "name")
        unique_together = ("set", "name")
        indexes = [
            models.Index(fields=["set", "name"]),
        ]
        verbose_name = "Pack"
        verbose_name_plural = "Packs"

class Card(models.Model):
    """Represents a Pokémon card."""
    set = models.ForeignKey(PokemonSet, related_name="cards", on_delete=models.CASCADE)
    number = models.CharField(max_length=10, db_index=True, verbose_name="Card Number")
    name = models.CharField(max_length=100, db_index=True, verbose_name="Card Name")
    rarity = models.ForeignKey(Rarity, on_delete=models.PROTECT, related_name="cards")
    packs = models.ManyToManyField(Pack, related_name="cards", blank=True)

    def __str__(self):
        return f"{self.name} ({self.set.number} {self.number})"

    class Meta:
        ordering = ("set", "number")
        unique_together = ("set", "number")
        indexes = [
            models.Index(fields=["set", "number"]),
        ]
        verbose_name = "Card"
        verbose_name_plural = "Cards"

class UserCard(models.Model):
    """Represents a user's owned card and quantity."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_cards")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="user_cards")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")

    class Meta:
        unique_together = ("user", "card")
        indexes = [
            models.Index(fields=["user", "card"]),
        ]
        verbose_name = "User Card"
        verbose_name_plural = "User Cards"

    def __str__(self):
        return f"{self.user.username} hat {self.quantity}x {self.card.name}"

class UserProfile(models.Model):
    """Profile for a user, including friend code and privacy."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    public = models.BooleanField(default=True, verbose_name="Public Profile")
    friend_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="Friend Code")

    def __str__(self):
        return f"Profile of {self.user.username}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

class FriendRequest(models.Model):
    """Represents a friend request between two user profiles."""
    from_user = models.ForeignKey(UserProfile, related_name="sent_friend_requests", on_delete=models.CASCADE)
    to_user = models.ForeignKey(UserProfile, related_name="received_friend_requests", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    accepted = models.BooleanField(default=False, verbose_name="Accepted")

    class Meta:
        unique_together = ("from_user", "to_user")
        verbose_name = "Friend Request"
        verbose_name_plural = "Friend Requests"

    def __str__(self):
        status = "Accepted" if self.accepted else "Pending"
        return f"{self.from_user.user.username} → {self.to_user.user.username} ({status})"
