"""Tracker app views for cards."""

from collections import defaultdict
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from apps.tracker.models.cards import Card, Pack, PokemonSet
from apps.tracker.models.users import UserCard
from apps.tracker.utils import load_rarity_tables, prob_new_card_any_pack_type


def _parse_card_id(request):
    """Return the POSTed card_id as an int, or None if missing/invalid."""
    try:
        return int(request.POST.get("card_id"))
    except (TypeError, ValueError):
        return None


def _series_options(sets):
    """Series codes of the given sets (newest release first), newest series first."""
    return list(dict.fromkeys(s.series for s in sets))


def _default_series(sets):
    """Series of the newest released set, so a preloaded upcoming set doesn't
    switch the default early. Falls back to the newest set overall."""
    today = timezone.localdate()
    released = [s for s in sets if s.release_date <= today]
    newest = (released or sets)[0] if sets else None
    return newest.series if newest else "all"


@login_required
def home(request):
    """Render the home page with the sets of the selected series and the user's cards."""
    all_sets = list(PokemonSet.objects.all().order_by("-release_date"))
    series_options = _series_options(all_sets)
    selected_series = request.GET.get("series") or request.POST.get("series")
    if selected_series != "all" and selected_series not in series_options:
        selected_series = _default_series(all_sets)
    sets = [s for s in all_sets if selected_series in ("all", s.series)]
    user_cards = UserCard.objects.filter(user=request.user)
    if request.method == "POST":
        card_id = _parse_card_id(request)
        if card_id is None:
            return HttpResponseBadRequest("Invalid card_id")
        action = request.POST.get("action")
        if action == "collect":
            card = get_object_or_404(Card, id=card_id)
            UserCard.objects.get_or_create(
                user=request.user, card=card, defaults={"quantity": 1}
            )
        elif action == "uncollect":
            UserCard.objects.filter(user=request.user, card_id=card_id).delete()
        params = {"series": selected_series}
        q = request.POST.get("q", "")
        if q:
            params["q"] = q
        return redirect(f"{reverse('home')}?{urlencode(params)}")
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
    total_cards = sum(total_dict.get(s.id, 0) for s in sets)
    total_collected = sum(progress_dict.get(s.id, 0) for s in sets)
    return render(
        request,
        "tracker/home.html",
        {
            "sets": sets_with_progress,
            "series_options": series_options,
            "selected_series": selected_series,
            "search_query": search_query,
            "search_results": search_results,
            "user_card_ids": user_card_ids,
            "total_cards": total_cards,
            "total_collected": total_collected,
            "total_progress_percent": (
                round((total_collected / total_cards) * 100, 2)
                if total_cards > 0
                else 0
            ),
        },
    )


def _get_sets_with_progress(sets, user_cards, progress_dict, total_dict):
    """Helper to calculate set progress and rarity stats."""
    sets_with_progress = []
    # order_by() clears Card's default ("set", "number") ordering, which
    # Django would otherwise fold into the SELECT and silently defeat
    # distinct() here (each row would be per-card, not per rarity).
    rarities = (
        Card.objects.order_by()
        .values("rarity__image_name", "rarity__name", "rarity__order", "is_foil")
        .distinct()
    )
    # Group by (image_name, is_foil): parallel-foil prints share their base
    # rarity's symbol but are counted separately.
    rarity_groups = defaultdict(lambda: {"order": 999, "names": []})
    for rarity in rarities:
        group = rarity_groups[(rarity["rarity__image_name"], rarity["is_foil"])]
        if rarity["rarity__name"] not in group["names"]:
            group["names"].append(rarity["rarity__name"])
        # Use the lowest order found for the group
        if "rarity__order" in rarity and rarity["rarity__order"] is not None:
            group["order"] = min(group["order"], rarity["rarity__order"])
    # Sort by order, each foil group right after its standard counterpart
    rarity_groups = dict(
        sorted(
            ((k, v["names"]) for k, v in rarity_groups.items()),
            key=lambda item: (rarity_groups[item[0]]["order"], item[0][1]),
        )
    )
    rarity_labels = {
        group_key: ", ".join(name.replace("_", " ").title() for name in names)
        + (f" ({_('Foil')})" if group_key[1] else "")
        for group_key, names in rarity_groups.items()
    }
    rarity_totals = {}
    for group_key, rarity_names in rarity_groups.items():
        group_totals = (
            Card.objects.filter(rarity__in=rarity_names, is_foil=group_key[1])
            .values("set")
            .annotate(total=Count("id"))
        )
        rarity_totals[group_key] = {
            entry["set"]: entry["total"] for entry in group_totals
        }
    rarity_progress = {}
    for group_key, rarity_names in rarity_groups.items():
        group_progress = (
            user_cards.filter(card__rarity__in=rarity_names, card__is_foil=group_key[1])
            .values("card__set")
            .annotate(collected=Count("card"))
        )
        rarity_progress[group_key] = {
            entry["card__set"]: entry["collected"] for entry in group_progress
        }
    for s in sets:
        collected = progress_dict.get(s.id, 0)
        total = total_dict.get(s.id, 0)
        progress_percent = round((collected / total) * 100, 2) if total > 0 else 0
        rarity_data = {
            group_key: {
                "image": group_key[0],
                "is_foil": group_key[1],
                "collected": rarity_progress[group_key].get(s.id, 0),
                "total": rarity_totals[group_key].get(s.id, 0),
                "label": rarity_labels[group_key],
            }
            for group_key in rarity_groups
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
        card_id = _parse_card_id(request)
        if card_id is None:
            return HttpResponseBadRequest("Invalid card_id")
        action = request.POST.get("action")
        if action == "collect":
            card = get_object_or_404(Card, id=card_id)
            UserCard.objects.get_or_create(
                user=request.user, card=card, defaults={"quantity": 1}
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
    # Pack types and rarity tables are per generation: load each once.
    generations = {pack.rarity_version_id: pack.rarity_version for pack in packs}
    pack_types_by_generation = {
        gen_id: list(gen.pack_types.all()) for gen_id, gen in generations.items()
    }
    rarity_tables_by_generation = {
        gen_id: load_rarity_tables(gen) for gen_id, gen in generations.items()
    }
    BASE_RARITIES = {"common", "uncommon", "rare", "double_rare"}
    pack_data = []
    for pack in packs:
        cards = list(pack.cards.all())
        total = len(cards)
        owned = sum(1 for c in cards if c.id in owned_card_ids)

        if total == 0 or not rarity_tables_by_generation[pack.rarity_version_id]:
            # No card data for this pack yet (e.g. an announced-but-unreleased
            # set) or no published slot odds for its generation - there's
            # nothing to compute odds from.
            pack_data.append(
                {
                    "pack": pack,
                    "chance": None,
                    "total": total,
                    "owned": owned,
                    "progress_percent": 0,
                    "incomplete_base": False,
                }
            )
            continue

        # Chance over all pack types of the generation, weighted by occurrence.
        chance = (
            prob_new_card_any_pack_type(
                pack,
                request.user,
                pack_types=pack_types_by_generation[pack.rarity_version_id],
                cards=cards,
                owned_card_ids=owned_card_ids,
                rarity_tables=rarity_tables_by_generation[pack.rarity_version_id],
            )
            * 100
        )

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

    # Pick the single best pack to recommend. Ties on chance (very common,
    # since the odds saturate near 100% once a set is mostly uncollected)
    # are broken by preferring the pack with the most cards still missing,
    # so the recommendation is deterministic instead of depending on
    # queryset order.
    ratable_packs = [p for p in pack_data if p["chance"] is not None]
    if ratable_packs:
        best_pack = max(ratable_packs, key=lambda p: (p["chance"], -p["owned"]))
        best_pack["is_best"] = True

    groups = defaultdict(list)
    # Sort packs within each set: packs with missing base cards first, then
    # by chance desc, then name. Packs with no data sort last.
    for entry in sorted(
        pack_data,
        key=lambda p: (
            p["chance"] is None,
            not p["incomplete_base"],  # False (missing) sorts before True (complete)
            -(p["chance"] or 0),
            p["pack"].name,
        ),
    ):
        groups[entry["pack"].set].append(entry)

    sort_by = request.GET.get("sort", "best")
    if sort_by == "release":
        ordered_sets = sorted(groups, key=lambda s: s.release_date, reverse=True)
    elif sort_by == "az":
        ordered_sets = sorted(groups, key=lambda s: s.localized_name.lower())
    else:
        sort_by = "best"
        # Groups were inserted in the order their best-ranked pack was
        # encountered above, i.e. "sets with the most worthwhile pack first".
        ordered_sets = list(groups)

    return render(
        request,
        "tracker/pack_list.html",
        {
            "grouped_packs": [(s, groups[s]) for s in ordered_sets],
            "sort_by": sort_by,
        },
    )
