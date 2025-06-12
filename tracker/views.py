from collections import defaultdict

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import JsonResponse
from django.db.models import Count

from .forms import RegisterForm
from .models import PokemonSet, Card, UserCard, Pack
from .utils import prob_at_least_one_new_card

@login_required
def home(request):
    sets = PokemonSet.objects.all().order_by('-release_date')
    user_cards = UserCard.objects.filter(user=request.user)

    # Handle collect/uncollect POST from search results
    if request.method == 'POST':
        card_id = int(request.POST.get('card_id'))
        action = request.POST.get('action')
        if action == 'collect':
            UserCard.objects.get_or_create(user=request.user, card_id=card_id, defaults={'quantity': 1})
        elif action == 'uncollect':
            UserCard.objects.filter(user=request.user, card_id=card_id).delete()
        # Redirect to home with search query preserved
        q = request.POST.get('q', '')
        if q:
            return redirect(f'/?q={q}')
        return redirect('home')

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

    # Gruppiere Karten nach Seltenheit basierend auf dem Bild aus dem Rarity-Modell
    rarities = Card.objects.values('rarity__image_name', 'rarity__name').distinct()
    rarity_groups = defaultdict(list)
    for rarity in rarities:
        rarity_groups[rarity['rarity__image_name']].append(rarity['rarity__name'])

    rarity_totals = {}
    for group_name, rarity_names in rarity_groups.items():
        group_totals = (
            Card.objects
            .filter(rarity__in=rarity_names)
            .values('set')
            .annotate(total=Count('id'))
        )
        rarity_totals[group_name] = {entry['set']: entry['total'] for entry in group_totals}

    rarity_progress = {}
    for group_name, rarities in rarity_groups.items():
        group_progress = (
            user_cards
            .filter(card__rarity__in=rarities)
            .values('card__set')
            .annotate(collected=Count('card'))
        )
        rarity_progress[group_name] = {entry['card__set']: entry['collected'] for entry in group_progress}

    # Kombiniere Fortschritt und Seltenheitsgruppen
    sets_with_progress = []
    for s in sets:
        collected = progress_dict.get(s.id, 0)
        total = total_dict.get(s.id, 0)
        progress_percent = round((collected / total) * 100, 2) if total > 0 else 0

        rarity_data = {
            group_name: {
                'collected': rarity_progress[group_name].get(s.id, 0),
                'total': rarity_totals[group_name].get(s.id, 0)
            }
            for group_name in rarity_groups
        }

        sets_with_progress.append({
            'set': s,
            'collected': collected,
            'total': total,
            'progress_percent': progress_percent,
            'rarity_progress': rarity_data,
        })

    # Card search logic
    search_query = request.GET.get('q', '').strip()
    search_results = []
    if search_query:
        search_results = Card.objects.filter(
            name__icontains=search_query
        ).select_related('set').order_by('set__release_date', 'set__name', 'number')

    user_card_ids = set(user_cards.values_list('card_id', flat=True))

    return render(request, 'tracker/home.html', {
        'sets': sets_with_progress,
        'search_query': search_query,
        'search_results': search_results,
        'user_card_ids': user_card_ids,
    })

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

    # Add rarities for JS sorting
    rarities = list(
        Card.objects.values('rarity__name', 'rarity__order')
        .filter(set=set_obj)
        .distinct()
        .order_by('rarity__order')
    )
    # Rename keys for template clarity
    rarities = [
        {'name': r['rarity__name'], 'order': r['rarity__order']} for r in rarities
    ]

    return render(request, 'tracker/set_detail.html', {
        'set': set_obj,
        'cards': cards,
        'rarities': rarities,
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

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def account(request):
    if request.method == 'POST':
        # Passwort ändern
        if 'password_change' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Ihr Passwort wurde erfolgreich geändert!')
            else:
                messages.error(request, 'Bitte korrigieren Sie die Fehler unten.')

        # Account löschen
        elif 'delete_account' in request.POST:
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, 'Ihr Account wurde erfolgreich gelöscht.')
            return redirect('home')

    else:
        password_form = PasswordChangeForm(request.user)

    return render(request, 'tracker/account.html', {'password_form': password_form})
