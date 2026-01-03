"""Admin configuration for tracker app."""

from django import forms
from django.contrib import admin

from apps.tracker.models.cards import (
    Card,
    CardNameTranslation,
    Generation,
    Pack,
    PackNameTranslation,
    PackType,
    PokemonSet,
    PokemonSetNameTranslation,
    Rarity,
    RarityProbability,
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
    """Inline admin for RarityProbabilities with soft sum warnings.

    Note: God pack probabilities are calculated dynamically and not stored in database.
    """

    model = RarityProbability
    extra = 0
    show_change_link = True

    def get_queryset(self, request):
        """Exclude god pack probability entries since they're calculated dynamically."""
        qs = super().get_queryset(request)
        return qs.exclude(pack_type__name__icontains="god")

    def get_formset(self, request, obj=None, **kwargs):  # type: ignore[override]
        from django.contrib import messages

        ParentFormSet = super().get_formset(request, obj, **kwargs)
        generation_obj = obj  # capture for closure

        # If no parent object (e.g. add form), just return original
        if not generation_obj:
            return ParentFormSet

        orig_clean = getattr(ParentFormSet, "clean", None)

        def clean(self):  # type: ignore[override]
            if orig_clean:
                orig_clean(self)
            # Only warn if no per-form errors
            if any(f.errors for f in self.forms):
                return
            generation = getattr(self, "instance", None) or generation_obj

            # Get pack types for validation (excluding god packs)
            pack_types = generation.pack_types.exclude(name__icontains="god")

            # Validate probabilities for each pack type separately
            for pack_type in pack_types:
                slot_fields = [
                    "probability_slot1",
                    "probability_slot2",
                    "probability_slot3",
                    "probability_slot4",
                    "probability_slot5",
                ][: pack_type.slot_count]

                sums = {sf: 0.0 for sf in slot_fields}
                count = 0

                for form in self.forms:
                    if not getattr(form, "cleaned_data", None):
                        continue
                    if form.cleaned_data.get("DELETE"):
                        continue
                    # Only check forms for this pack type
                    if form.cleaned_data.get("pack_type") != pack_type:
                        continue
                    count += 1
                    for sf in slot_fields:
                        sums[sf] += form.cleaned_data.get(sf, 0.0) or 0.0

                if not count:
                    continue

                epsilon = 1e-5
                drift = {
                    sf: total
                    for sf, total in sums.items()
                    if abs(total - 1.0) > epsilon
                }
                if drift:
                    msg = ", ".join(f"{sf}={total:.6f}" for sf, total in drift.items())
                    messages.warning(
                        request,
                        f"Rarity probability sums for {generation.name} - {pack_type.name} are off (expected 1.0): {msg}",
                    )

        ParentFormSet.clean = clean  # type: ignore[assignment]
        return ParentFormSet


class SentFriendRequestsInline(admin.TabularInline):
    """Inline admin for sent FriendRequests."""

    model = FriendRequest
    fk_name = "from_user"
    extra = 0
    show_change_link = True
    fields = ("to_user", "accepted", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


class ReceivedFriendRequestsInline(admin.TabularInline):
    """Inline admin for received FriendRequests."""

    model = FriendRequest
    fk_name = "to_user"
    extra = 0
    show_change_link = True
    fields = ("from_user", "accepted", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


class CardNameTranslationInline(admin.TabularInline):
    """Inline admin for CardNameTranslation."""

    model = CardNameTranslation
    extra = 1
    show_change_link = True


class PokemonSetNameTranslationInline(admin.TabularInline):
    """Inline admin for PokemonSetNameTranslation."""

    model = PokemonSetNameTranslation
    extra = 1
    show_change_link = True


class PackNameTranslationInline(admin.TabularInline):
    """Inline admin for PackNameTranslation."""

    model = PackNameTranslation
    extra = 1
    show_change_link = True


@admin.register(PokemonSet)
class SetAdmin(admin.ModelAdmin):
    """Admin for PokemonSet."""

    list_display = (
        "name",
        "release_date",
        "generation",
        "available_until",
        "is_available_status",
        "view_cards_link",
    )
    inlines = [PacksInline, PokemonSetNameTranslationInline]
    search_fields = ("name", "generation__name")
    list_per_page = 25
    ordering = ("release_date",)
    list_filter = ("available_until", "generation")

    @staticmethod
    def view_cards_link(obj):
        from django.urls import reverse
        from django.utils.html import format_html

        url = reverse("admin:tracker_card_changelist") + f"?set__id__exact={obj.id}"
        return format_html('<a href="{}">View Cards</a>', url)

    @staticmethod
    def is_available_status(obj):
        from django.utils.html import format_html

        if obj.is_available:
            return format_html('<span style="color: green;">✓ Available</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')

    view_cards_link.short_description = "Cards"
    is_available_status.short_description = "Status"


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
    inlines = [PackNameTranslationInline]

    # Note: rarity_version field still references Generation model
    # Consider renaming this field in a future migration


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
        "generation",
        "pack_type",
        "rarity",
        "probability_slot1_percent",
        "probability_slot2_percent",
        "probability_slot3_percent",
        "probability_slot4_percent",
        "probability_slot5_percent",
        "probability_slot6_percent",
    )
    search_fields = ("rarity__name", "generation__name", "pack_type__name")
    autocomplete_fields = ["generation", "pack_type", "rarity"]
    list_select_related = ("generation", "pack_type", "rarity")
    list_filter = ("generation", "pack_type", "rarity")
    list_per_page = 25
    ordering = ("generation", "pack_type", "rarity")

    class Form(forms.ModelForm):
        class Meta:
            model = RarityProbability
            fields = [
                "generation",
                "pack_type",
                "rarity",
                "probability_slot1",
                "probability_slot2",
                "probability_slot3",
                "probability_slot4",
                "probability_slot5",
                "probability_slot6",
            ]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Pack type validation could be added here if needed

    form = Form

    def _probability_percent(self, obj, field):
        value = getattr(obj, field, None)
        return f"{value * 100:.3f}%" if value is not None else "-"

    def probability_slot1_percent(self, obj):
        return self._probability_percent(obj, "probability_slot1")

    probability_slot1_percent.short_description = "Probability Slot1"

    def probability_slot4_percent(self, obj):
        return self._probability_percent(obj, "probability_slot4")

    probability_slot4_percent.short_description = "Probability Slot4"

    def probability_slot5_percent(self, obj):
        return self._probability_percent(obj, "probability_slot5")

    probability_slot5_percent.short_description = "Probability Slot5"

    def probability_slot2_percent(self, obj):
        return self._probability_percent(obj, "probability_slot2")

    probability_slot2_percent.short_description = "Probability Slot2"

    def probability_slot3_percent(self, obj):
        return self._probability_percent(obj, "probability_slot3")

    probability_slot3_percent.short_description = "Probability Slot3"

    def probability_slot6_percent(self, obj):
        return self._probability_percent(obj, "probability_slot6")

    probability_slot6_percent.short_description = "Probability Slot6"


class PackTypesInline(admin.TabularInline):
    """Inline admin for PackTypes."""

    model = PackType
    extra = 0
    show_change_link = True
    readonly_fields = ("is_god_pack_display",)

    def is_god_pack_display(self, obj):
        """Show if this is a god pack type."""
        if obj.is_god_pack:
            return "✓ God Pack (probabilities calculated dynamically)"
        return "Normal Pack (probabilities stored in database)"

    is_god_pack_display.short_description = "Pack Type"


@admin.register(Generation)
class GenerationAdmin(admin.ModelAdmin):
    """Admin for Generation."""

    list_display = ("name", "display_name", "total_pack_types")
    inlines = [PackTypesInline, RarityProbabilitiesInline]
    search_fields = ("name", "display_name")
    list_per_page = 25
    ordering = ("name",)

    def get_readonly_fields(self, request, obj=None):
        """Add helpful information about god pack calculations."""
        return ("god_pack_info",) if obj else ()

    def god_pack_info(self, obj):
        """Display information about god pack probability calculations."""
        god_packs = obj.pack_types.filter(name__icontains="god")
        if not god_packs.exists():
            return "No god packs configured for this generation."

        info = [
            "God pack probabilities are calculated dynamically based on card counts:"
        ]

        eligible_rarities = obj.get_god_pack_eligible_rarities()
        rarity_names = list(eligible_rarities.values_list("name", flat=True))

        if obj.name in ["G2", "G3"]:
            info.append(
                f"• Eligible rarities: {', '.join(rarity_names)} (includes shinies)"
            )
        else:
            info.append(f"• Eligible rarities: {', '.join(rarity_names)} (no shinies)")

        info.append("• Each individual rare card has equal probability")
        info.append(
            "• Rarity probability = (cards of that rarity) / (total rare cards)"
        )

        return "\n".join(info)

    god_pack_info.short_description = "God Pack Calculation Info"


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


@admin.register(PackType)
class PackTypeAdmin(admin.ModelAdmin):
    """Admin for PackType."""

    list_display = (
        "generation",
        "name",
        "display_name",
        "slot_count",
        "occurrence_probability_percent",
        "is_god_pack_display",
        "description",
    )
    search_fields = ("name", "display_name", "description", "generation__name")
    list_filter = ("generation", "name")
    autocomplete_fields = ["generation"]
    ordering = ("generation", "-occurrence_probability")
    readonly_fields = ("occurrence_probability_percent", "is_god_pack_display")

    def occurrence_probability_percent(self, obj):
        """Display occurrence probability as percentage."""
        return f"{obj.occurrence_probability * 100:.3f}%"

    occurrence_probability_percent.short_description = "Occurrence %"

    def is_god_pack_display(self, obj):
        """Display if this is a god pack."""
        return obj.is_god_pack

    is_god_pack_display.short_description = "Is God Pack"
    is_god_pack_display.boolean = True


@admin.register(CardNameTranslation)
class CardNameTranslationAdmin(admin.ModelAdmin):
    """Admin for CardNameTranslation."""

    list_display = ("card", "language_code", "localized_name")
    search_fields = ("localized_name", "language_code", "card__name")
    autocomplete_fields = ["card"]
    list_filter = ("language_code",)
    ordering = ("language_code", "localized_name")
