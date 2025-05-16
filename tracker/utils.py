"""Utility functions for probability calculations in tcgptracker."""

from .models import RarityProbability, UserCard

def prob_at_least_one_new_card(pack, user):
    """
    Calculate the probability that at least one new card is drawn from a pack for a user.

    Args:
        pack: The pack object containing cards and rarity version.
        user: The user object.

    Returns:
        float: Probability rounded to 4 decimals.
    """
    from collections import Counter

    rarity_probs = (
        RarityProbability.objects
        .filter(version=pack.rarity_version)
        .select_related('rarity')
    )
    rarities = {rp.rarity: rp for rp in rarity_probs}

    cards_in_pack = (
        pack.cards
        .select_related('rarity')
        .all()
    )

    owned_card_ids = set(
        UserCard.objects
        .filter(user=user, card__in=cards_in_pack)
        .values_list('card_id', flat=True)
    )

    # Build a mapping of rarity to all cards and owned cards
    cards_by_rarity = {}
    owned_by_rarity = {}
    for card in cards_in_pack:
        cards_by_rarity.setdefault(card.rarity, []).append(card)
        if card.id in owned_card_ids:
            owned_by_rarity.setdefault(card.rarity, set()).add(card.id)

    # Define the slots and their corresponding probability fields
    slot_names = ["first", "first", "first", "fourth", "fifth"]
    slot_fields = [f'probability_{name}' for name in slot_names]

    # For each slot, calculate the probability that the drawn card is already owned
    prob_no_new = 1.0
    for slot_field in slot_fields:
        slot_prob_no_new = 0.0
        for rarity, rp in rarities.items():
            prob = getattr(rp, slot_field)
            cards = cards_by_rarity.get(rarity, [])
            owned = owned_by_rarity.get(rarity, set())
            total = len(cards)
            owned_count = len(owned)
            if total == 0:
                continue
            slot_prob_no_new += prob * (owned_count / total)
        prob_no_new *= slot_prob_no_new

    return round(1.0 - prob_no_new, 4)