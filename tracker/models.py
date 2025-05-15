from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class Version(models.Model):
    name = models.CharField(max_length=3, primary_key=True)
    display_name = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return str(self.display_name)

class PokemonSet(models.Model):
    number = models.CharField(max_length=10, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    release_date = models.DateField(db_index=True)

    def __str__(self):
        return str(self.name)
    
    class Meta:
        ordering = ['release_date']
        indexes = [
            models.Index(fields=['release_date']),
        ]

class Rarity(models.Model):
    name = models.CharField(max_length=20, primary_key=True)
    display_name = models.CharField(max_length=4, unique=True)
    order = models.PositiveSmallIntegerField(unique=True)

    def __str__(self):
        return str(self.display_name)

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['order']),
        ]
        verbose_name_plural = "Rarities"

class RarityProbability(models.Model):
    rarity = models.ForeignKey(Rarity, on_delete=models.CASCADE)
    version = models.ForeignKey(Version, on_delete=models.CASCADE)
    probability_first = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    probability_fourth = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    probability_fifth = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    def __str__(self):
        return f"{self.rarity}: {self.probability_first * 100} % / {self.probability_fourth * 100} % / {self.probability_fifth * 100} %"

    class Meta:
        unique_together = ('version', 'rarity')
        verbose_name_plural = "Rarity Probabilities"
        indexes = [
            models.Index(fields=['version', 'rarity']),
        ]

class Pack(models.Model):
    set = models.ForeignKey(PokemonSet, related_name='packs', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True)
    rarity_version = models.ForeignKey(Version, on_delete=models.PROTECT)

    def __str__(self):
        return str(self.name)

    class Meta:
        ordering = ['set', 'name']
        unique_together = ('set', 'name')
        indexes = [
            models.Index(fields=['set', 'name']),
        ]

class Card(models.Model):
    set = models.ForeignKey(PokemonSet, related_name='cards', on_delete=models.CASCADE)
    number = models.CharField(max_length=10, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    rarity = models.ForeignKey(Rarity, on_delete=models.PROTECT)
    packs = models.ManyToManyField(Pack, related_name='cards', blank=True)

    def __str__(self):
        return f"{self.name} ({self.set.number} {self.number})"

    class Meta:
        ordering = ['set', 'number']
        unique_together = ('set', 'number')
        indexes = [
            models.Index(fields=['set', 'number']),
        ]

class UserCard(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('user', 'card')
        indexes = [
            models.Index(fields=["user", "card"]),
        ]

    def __str__(self):
        return f"{self.user.username} hat {self.quantity}x {self.card.name}"
