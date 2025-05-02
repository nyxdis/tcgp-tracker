from django.contrib import admin
from .models import PokemonSet, Pack, Card, UserCard, RarityProbability, Version, Rarity

@admin.register(PokemonSet)
class SetAdmin(admin.ModelAdmin):
    list_display = ('name', 'release_date')
    inlines = [
        type('PacksInline', (admin.TabularInline,), dict(model=Pack, extra=1)),
        type('CardsInline', (admin.TabularInline,), dict(model=Card, extra=1))
    ]
    search_fields = ('name',)

@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ('name', 'set')
    search_fields = ('name', 'set__name')
    autocomplete_fields = ['set']

@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('name', 'number', 'rarity', 'set')
    list_filter = ('rarity', 'set')
    search_fields = ('name', 'number', 'set__name')
    autocomplete_fields = ['set']

@admin.register(UserCard)
class UserCardAdmin(admin.ModelAdmin):
    list_display = ('user', 'card', 'quantity')
    search_fields = ('user__username', 'card__name')
    autocomplete_fields = ['user', 'card']

@admin.register(RarityProbability)
class RarityProbabilityAdmin(admin.ModelAdmin):
    list_display = ('version', 'rarity', 'probability_first', 'probability_fourth', 'probability_fifth')
    search_fields = ('rarity',)

@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_name')
    inlines = [
        type('RarityProbabilitiesInline', (admin.TabularInline,), dict(model=RarityProbability, extra=1))
    ]

@admin.register(Rarity)
class RarityAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_name', 'order')