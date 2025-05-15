import json
from collections import defaultdict

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count

from .models import PokemonSet, Card, UserCard, Pack
from .utils import prob_at_least_one_new_card

@login_required
def home(request):
    sets = PokemonSet.objects.all().order_by('release_date')
    user_cards = UserCard.objects.filter(user=request.user)

    # Berechne Sammelfortschritt je Set
    progress_by_set = (
        user_cards
        .values('card__set')
        .annotate(collected=Count('card'))
    )
    progress_dict = {entry['card__set']: entry['collected'] for entry in progress_by_set}

    # Anzahl Karten pro Set
    card_counts = (
        Card.objects.values('set')
        .annotate(total=Count('id'))
    )
    total_dict = {entry['set']: entry['total'] for entry in card_counts}

    # Kombiniere beides
    sets_with_progress = []
    for s in sets:
        collected = progress_dict.get(s.id, 0)
        total = total_dict.get(s.id, 0)
        progress_percent = round((collected / total) * 100, 2) if total > 0 else 0
        sets_with_progress.append({
            'set': s,
            'collected': collected,
            'total': total,
            'progress_percent': progress_percent,
        })

    return render(request, 'tracker/home.html', {'sets': sets_with_progress})

@login_required
def set_detail(request, set_number):
    set_obj = get_object_or_404(PokemonSet, number=set_number)
    cards = Card.objects.filter(set=set_obj).select_related('rarity').order_by('number')

    if request.method == 'POST':
        card_id = int(request.POST.get('card_id'))
        action = request.POST.get('action')

        if action == 'collect':
            obj, created = UserCard.objects.get_or_create(user=request.user, card_id=card_id, defaults={'quantity': 1})
        elif action == 'uncollect':
            UserCard.objects.filter(user=request.user, card_id=card_id).delete()

        # If AJAX, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'collected': action == 'collect'})
        # Otherwise, fallback to redirect
        return redirect('set_detail', set_number=set_number)

    user_cards = {
        uc.card_id: uc.quantity
        for uc in UserCard.objects.filter(user=request.user, card__set=set_obj)
    }

    for card in cards:
        card.collected_quantity = user_cards.get(card.id, 0)

    return render(request, 'tracker/set_detail.html', {
        'set': set_obj,
        'cards': cards,
    })

@login_required
def pack_list(request):
    packs = list(
        Pack.objects.all()
        .select_related('set', 'rarity_version')
        .prefetch_related('cards__rarity')
    )

    # Hole alle Karten, die der Nutzer besitzt
    owned_card_ids = set(
        UserCard.objects.filter(user=request.user).values_list('card_id', flat=True)
    )

    # Berechne Daten pro Pack
    pack_data = []
    for pack in packs:
        cards = list(pack.cards.all())
        total = len(cards)
        owned = sum(1 for c in cards if c.id in owned_card_ids)
        chance = prob_at_least_one_new_card(pack, request.user) * 100

        pack_data.append({
            'pack': pack,
            'chance': round(chance, 2),
            'total': total,
            'owned': owned,
            'progress_percent': round((owned / total) * 100 if total > 0 else 0, 2),
        })

    # Beste Wahl markieren
    if pack_data:
        best_pack = max(pack_data, key=lambda p: p['chance'])
        best_pack['is_best'] = True

    # Gruppiere nach Set
    grouped_packs = defaultdict(list)
    for entry in sorted(pack_data, key=lambda p: (-p['chance'], p['pack'].name)):
        grouped_packs[entry['pack'].set].append(entry)

    return render(request, 'tracker/pack_list.html', {
        'grouped_packs': grouped_packs.items(),  # list of (set, [packs])
    })