"""Tracker app utilities."""

from apps.tracker.models.cards import RarityProbability
from apps.tracker.models.users import UserCard


def prob_at_least_one_new_card(pack, user):
    """
    Calculate the probability that at least one new card is drawn from a pack for a user.

    Args:
        pack: The pack object containing cards and rarity version.
        user: The user object.

    Returns:
        float: Probability rounded to 4 decimals.
    """
    rarity_probs = RarityProbability.objects.filter(
        version=pack.rarity_version
    ).select_related("rarity")
    rarities = {rp.rarity: rp for rp in rarity_probs}

    cards_in_pack = pack.cards.select_related("rarity").all()

    owned_card_ids = set(
        UserCard.objects.filter(user=user, card__in=cards_in_pack).values_list(
            "card_id", flat=True
        )
    )

    # Build a mapping of rarity to all cards and owned cards
    cards_by_rarity = {}
    owned_by_rarity = {}
    for card in cards_in_pack:
        cards_by_rarity.setdefault(card.rarity, []).append(card)
        if card.id in owned_card_ids:
            owned_by_rarity.setdefault(card.rarity, set()).add(card.id)

    # Build slot field list dynamically based on the version slot_count
    version = pack.rarity_version
    base_fields = [
        "probability_slot1",  # slot 1
        "probability_slot2",  # slot 2
        "probability_slot3",  # slot 3
        "probability_slot4",  # slot 4
        "probability_slot5",  # slot 5
    ]
    slot_fields = base_fields[: int(version.slot_count)]

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
