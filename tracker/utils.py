from .models import RarityProbability, UserCard

def prob_at_least_one_new_card(pack, user):
    # Hole die Wahrscheinlichkeiten der Rarities für die aktuelle Version
    rarity_probs = RarityProbability.objects.filter(version=pack.rarity_version).select_related('rarity')
    rarities = {rp.rarity: rp for rp in rarity_probs}

    # Alle Karten im Pack laden
    cards_in_pack = pack.cards.select_related('rarity').all()

    # IDs der bereits vom Nutzer besessenen Karten in diesem Pack
    owned_card_ids = set(
        UserCard.objects.filter(user=user, card__in=cards_in_pack)
        .values_list('card_id', flat=True)
    )

    # Gesamte Wahrscheinlichkeit, dass *keine einzige* neue Karte gezogen wird
    prob_no_new_total = 1.0

    # Wir berechnen das für alle 5 Slots im Pack
    for slot_index in range(1, 6):
        slot_field = f'probability_{["first", "first", "first", "fourth", "fifth"][slot_index - 1]}'
        slot_prob_no_new = 0.0

        for rarity, rp in rarities.items():
            # Karten dieser Rarity in diesem Pack
            cards_of_rarity = [card for card in cards_in_pack if card.rarity == rarity]
            total = len(cards_of_rarity)
            if total == 0:
                continue

            owned = sum(1 for c in cards_of_rarity if c.id in owned_card_ids)
            if owned == total:
                continue
            prob = getattr(rp, slot_field)

            # Wahrscheinlichkeit, dass gezogene Karte dieser Rarity bereits im Besitz ist
            slot_prob_no_new += prob * (owned / total)

        if slot_prob_no_new == 0.0:
            slot_prob_no_new = 1.0

        # Multipliziere die Wahrscheinlichkeit, dass in diesem Slot keine neue Karte gezogen wird
        prob_no_new_total *= slot_prob_no_new

    # Wahrscheinlichkeit, dass mindestens eine neue Karte gezogen wird
    return round(1.0 - prob_no_new_total, 4)