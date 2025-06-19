"""Admin configuration for tracker app."""

from django.contrib import admin

from apps.tracker.models.cards import (
    Card,
    CardNameTranslation,
    Pack,
    PokemonSet,
    Rarity,
    RarityProbability,
    Version,
)
from apps.tracker.models.users import FriendRequest, UserCard, UserProfile


# Inline classes for better readability
class PacksInline(admin.TabularInline):
    """Inline admin for Packs."""

    model = Pack
    extra = 0
    show_change_link = True


class CardsInline(admin.TabularInline):
    """Inline admin for Cards."""

    model = Card
    extra = 0
    show_change_link = True


class RarityProbabilitiesInline(admin.TabularInline):
    """Inline admin for RarityProbabilities."""

    model = RarityProbability
    extra = 0
    show_change_link = True


class SentFriendRequestsInline(admin.TabularInline):
    """Inline admin for sent FriendRequests."""

    model = FriendRequest
    fk_name = "from_user"
    extra = 0
    show_change_link = True


class ReceivedFriendRequestsInline(admin.TabularInline):
    """Inline admin for received FriendRequests."""

    model = FriendRequest
    fk_name = "to_user"
    extra = 0
    show_change_link = True


class CardNameTranslationInline(admin.TabularInline):
    """Inline admin for CardNameTranslation."""

    model = CardNameTranslation
    extra = 1
    show_change_link = True


@admin.register(PokemonSet)
class SetAdmin(admin.ModelAdmin):
    """Admin for PokemonSet."""

    list_display = ("name", "release_date", "view_cards_link")
    inlines = [PacksInline]
    search_fields = ("name",)
    list_per_page = 25
    ordering = ("release_date",)

    @staticmethod
    def view_cards_link(obj):
        from django.urls import reverse
        from django.utils.html import format_html

        url = reverse("admin:tracker_card_changelist") + f"?set__id__exact={obj.id}"
        return format_html('<a href="{}">View Cards</a>', url)

    view_cards_link.short_description = "Cards"


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    """Admin for Pack."""

    list_display = ("name", "set", "rarity_version")
    search_fields = ("name", "set__name")
    autocomplete_fields = ["set", "rarity_version"]
    list_filter = ("set", "rarity_version")
    list_select_related = ("set", "rarity_version")
    list_per_page = 25
    ordering = ("set", "name")


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    """Admin for Card."""

    list_display = ("name", "number", "rarity", "set")
    list_filter = ("rarity", "set")
    search_fields = ("name", "number", "set__name")
    autocomplete_fields = ["set", "rarity", "packs"]
    list_select_related = ("set", "rarity")
    list_per_page = 25
    ordering = ("set", "number")
    inlines = [CardNameTranslationInline]


@admin.register(UserCard)
class UserCardAdmin(admin.ModelAdmin):
    """Admin for UserCard."""

    list_display = ("user", "card", "quantity")
    search_fields = ("user__username", "card__name")
    autocomplete_fields = ["user", "card"]
    list_select_related = ("user", "card")
    list_per_page = 25
    ordering = ("user__username", "card__set", "card__number")


@admin.register(RarityProbability)
class RarityProbabilityAdmin(admin.ModelAdmin):
    """Admin for RarityProbability."""

    list_display = (
        "version",
        "rarity",
        "probability_first_percent",
        "probability_fourth_percent",
        "probability_fifth_percent",
    )
    search_fields = ("rarity__name", "version__name")
    autocomplete_fields = ["version", "rarity"]
    list_select_related = ("version", "rarity")
    list_per_page = 25
    ordering = ("version", "rarity")

    def _probability_percent(self, obj, field):
        value = getattr(obj, field, None)
        return f"{value * 100:.3f}%" if value is not None else "-"

    def probability_first_percent(self, obj):
        return self._probability_percent(obj, "probability_first")

    probability_first_percent.short_description = "Probability First"

    def probability_fourth_percent(self, obj):
        return self._probability_percent(obj, "probability_fourth")

    probability_fourth_percent.short_description = "Probability Fourth"

    def probability_fifth_percent(self, obj):
        return self._probability_percent(obj, "probability_fifth")

    probability_fifth_percent.short_description = "Probability Fifth"


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    """Admin for Version."""

    list_display = ("name", "display_name")
    inlines = [RarityProbabilitiesInline]
    search_fields = ("name", "display_name")
    list_per_page = 25
    ordering = ("name",)


@admin.register(Rarity)
class RarityAdmin(admin.ModelAdmin):
    """Admin for Rarity."""

    list_display = ("name", "display_name", "order")
    search_fields = ("name", "display_name")
    list_per_page = 25
    ordering = ("order",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile."""

    list_display = ("user", "public", "friend_code")
    search_fields = ("user__username", "friend_code")
    autocomplete_fields = ["user"]
    list_filter = ("public",)
    ordering = ("user__username",)
    inlines = [SentFriendRequestsInline, ReceivedFriendRequestsInline]
    list_select_related = ("user",)
    list_per_page = 25


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    """Admin for FriendRequest."""

    list_display = ("from_user", "to_user", "created_at", "accepted")
    search_fields = ("from_user__user__username", "to_user__user__username")
    autocomplete_fields = ["from_user", "to_user"]
    list_filter = ("accepted", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    list_select_related = ("from_user", "to_user")
    date_hierarchy = "created_at"
    list_per_page = 25


@admin.register(CardNameTranslation)
class CardNameTranslationAdmin(admin.ModelAdmin):
    """Admin for CardNameTranslation."""

    list_display = ("card", "language_code", "localized_name")
    search_fields = ("localized_name", "language_code", "card__name")
    autocomplete_fields = ["card"]
    list_filter = ("language_code",)
    ordering = ("language_code", "localized_name")
