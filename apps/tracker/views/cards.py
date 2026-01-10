"""Tracker app views for cards."""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language

from apps.tracker.models.cards import Card, Pack, PokemonSet
from apps.tracker.models.users import UserCard
from apps.tracker.utils import prob_at_least_one_new_card


@login_required
def home(request):
    """Render the home page with all sets and the user's cards."""
    sets = PokemonSet.objects.all().order_by("-release_date")
    user_cards = UserCard.objects.filter(user=request.user)
    if request.method == "POST":
        card_id = int(request.POST.get("card_id"))
        action = request.POST.get("action")
        if action == "collect":
            UserCard.objects.get_or_create(
                user=request.user, card_id=card_id, defaults={"quantity": 1}
            )
        elif action == "uncollect":
            UserCard.objects.filter(user=request.user, card_id=card_id).delete()
        q = request.POST.get("q", "")
        if q:
            return redirect(f"/?q={q}")
        return redirect("home")
    progress_by_set = user_cards.values("card__set").annotate(collected=Count("card"))
    progress_dict = {
        entry["card__set"]: entry["collected"] for entry in progress_by_set
    }
    card_counts = Card.objects.values("set").annotate(total=Count("id"))
    total_dict = {entry["set"]: entry["total"] for entry in card_counts}
    sets_with_progress = _get_sets_with_progress(
        sets, user_cards, progress_dict, total_dict
    )
    search_query = request.GET.get("q", "").strip()
    search_results = []
    language_code = get_language() or "en"
    if search_query:
        search_results = (
            Card.objects.filter(
                translations__localized_name__icontains=search_query,
                translations__language_code=language_code,
            )
            .select_related("set")
            .order_by("set__release_date", "set__name", "number")
            .distinct()
        )
        if not search_results:
            # fallback to default name if no translation found
            search_results = (
                Card.objects.filter(name__icontains=search_query)
                .select_related("set")
                .order_by("set__release_date", "set__name", "number")
            )
    user_card_ids = set(user_cards.values_list("card_id", flat=True))
    return render(
        request,
        "tracker/home.html",
        {
            "sets": sets_with_progress,
            "search_query": search_query,
            "search_results": search_results,
            "user_card_ids": user_card_ids,
        },
    )


def _get_sets_with_progress(sets, user_cards, progress_dict, total_dict):
    """Helper to calculate set progress and rarity stats."""
    sets_with_progress = []
    rarities = Card.objects.values(
        "rarity__image_name", "rarity__name", "rarity__order"
    ).distinct()
    # Build a mapping from image_name to (order, [names])
    rarity_groups = defaultdict(lambda: {"order": 999, "names": []})
    for rarity in rarities:
        group = rarity_groups[rarity["rarity__image_name"]]
        group["names"].append(rarity["rarity__name"])
        # Use the lowest order found for the group
        if "rarity__order" in rarity and rarity["rarity__order"] is not None:
            group["order"] = min(group["order"], rarity["rarity__order"])
    # Now sort rarity_groups by order
    sorted_rarity_groups = dict(
        sorted(
            ((k, v["names"]) for k, v in rarity_groups.items()),
            key=lambda item: rarity_groups[item[0]]["order"],
        )
    )
    rarity_groups = sorted_rarity_groups
    rarity_totals = {}
    for group_name, rarity_names in rarity_groups.items():
        group_totals = (
            Card.objects.filter(rarity__in=rarity_names)
            .values("set")
            .annotate(total=Count("id"))
        )
        rarity_totals[group_name] = {
            entry["set"]: entry["total"] for entry in group_totals
        }
    rarity_progress = {}
    for group_name, rarities in rarity_groups.items():
        group_progress = (
            user_cards.filter(card__rarity__in=rarities)
            .values("card__set")
            .annotate(collected=Count("card"))
        )
        rarity_progress[group_name] = {
            entry["card__set"]: entry["collected"] for entry in group_progress
        }
    for s in sets:
        collected = progress_dict.get(s.id, 0)
        total = total_dict.get(s.id, 0)
        progress_percent = round((collected / total) * 100, 2) if total > 0 else 0
        rarity_data = {
            group_name: {
                "collected": rarity_progress[group_name].get(s.id, 0),
                "total": rarity_totals[group_name].get(s.id, 0),
            }
            for group_name in rarity_groups
        }
        sets_with_progress.append(
            {
                "set": s,
                "collected": collected,
                "total": total,
                "progress_percent": progress_percent,
                "rarity_progress": rarity_data,
            }
        )
    return sets_with_progress


@login_required
def set_detail(request, set_number):
    """Display details for a specific set, handle card collection/uncollection for the user."""
    set_obj = get_object_or_404(PokemonSet, number=set_number)
    cards = (
        Card.objects.filter(set=set_obj)
        .select_related("rarity")
        .order_by("number")
        .prefetch_related("translations")
    )
    if request.method == "POST":
        card_id = int(request.POST.get("card_id"))
        action = request.POST.get("action")
        if action == "collect":
            UserCard.objects.get_or_create(
                user=request.user, card_id=card_id, defaults={"quantity": 1}
            )
        elif action == "uncollect":
            UserCard.objects.filter(user=request.user, card_id=card_id).delete()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"status": "success", "collected": action == "collect"})
        return redirect("set_detail", set_number=set_number)
    user_cards = UserCard.objects.filter(user=request.user, card__set=set_obj)
    user_cards_dict = {uc.card_id: uc.quantity for uc in user_cards}
    for card in cards:
        card.collected_quantity = user_cards_dict.get(card.id, 0)
    sets_with_progress = _get_sets_with_progress([set_obj], user_cards, {}, {})
    set_progress = sets_with_progress[0] if sets_with_progress else {}
    rarities = list(
        Card.objects.filter(set=set_obj)
        .values("rarity__name", "rarity__order")
        .distinct()
        .order_by("rarity__order")
    )
    rarities = [
        {"name": r["rarity__name"], "order": r["rarity__order"]} for r in rarities
    ]
    return render(
        request,
        "tracker/set_detail.html",
        {
            "set": set_obj,
            "cards": cards,
            "rarities": rarities,
            "rarity_progress": set_progress.get("rarity_progress", {}),
            "collected": set_progress.get("collected", 0),
            "total": set_progress.get("total", 0),
            "progress_percent": set_progress.get("progress_percent", 0),
        },
    )


@login_required
def pack_list(request):
    """Show a list of all packs with stats about owned cards and chance for new cards."""
    # Filter out packs from expired sets
    from django.utils import timezone

    today = timezone.now().date()

    packs = list(
        Pack.objects.filter(
            Q(set__available_until__isnull=True) | Q(set__available_until__gte=today)
        )
        .select_related("set", "rarity_version")
        .prefetch_related("cards__rarity")
    )
    owned_card_ids = set(
        UserCard.objects.filter(user=request.user).values_list("card_id", flat=True)
    )
    BASE_RARITIES = {"common", "uncommon", "rare", "double_rare"}
    pack_data = []
    for pack in packs:
        cards = list(pack.cards.all())
        total = len(cards)
        owned = sum(1 for c in cards if c.id in owned_card_ids)

        # Calculate weighted chance considering all pack types for this generation
        generation = pack.rarity_version
        available_pack_types = generation.pack_types.all()

        if available_pack_types.exists():
            # Calculate expected probability across all pack types
            expected_chance = 0.0
            for pack_type in available_pack_types:
                pack_type_chance = prob_at_least_one_new_card(
                    pack, request.user, pack_type
                )
                expected_chance += pack_type_chance * pack_type.occurrence_probability
            chance = expected_chance * 100
        else:
            # Fallback to default calculation if no pack types defined
            chance = prob_at_least_one_new_card(pack, request.user) * 100

        # Find base cards in this pack
        base_cards = [c for c in cards if c.rarity.name in BASE_RARITIES]
        owned_base = sum(1 for c in base_cards if c.id in owned_card_ids)
        incomplete_base = owned_base < len(base_cards)
        pack_data.append(
            {
                "pack": pack,
                "chance": round(chance, 2),
                "total": total,
                "owned": owned,
                "progress_percent": round((owned / total) * 100 if total > 0 else 0, 2),
                "incomplete_base": incomplete_base,
            }
        )
    if pack_data:
        best_pack = max(pack_data, key=lambda p: p["chance"])
        best_pack["is_best"] = True
    grouped_packs = defaultdict(list)
    # Sort: packs with missing base cards first, then by chance desc, then name
    for entry in sorted(
        pack_data,
        key=lambda p: (
            not p["incomplete_base"],  # False (missing) sorts before True (complete)
            -p["chance"],
            p["pack"].name,
        ),
    ):
        grouped_packs[entry["pack"].set].append(entry)
    return render(
        request,
        "tracker/pack_list.html",
        {
            "grouped_packs": grouped_packs.items(),
        },
    )
