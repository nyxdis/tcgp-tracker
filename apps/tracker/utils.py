"""Tracker app utilities."""

import logging

from apps.tracker.models.cards import RarityProbability
from apps.tracker.models.users import UserCard

logger = logging.getLogger("tracker.utils")


def prob_at_least_one_new_card(pack, user, pack_type=None):
    """
    Calculate the probability that at least one new card is drawn from a pack for a user.

    Args:
        pack: The pack object containing cards and generation.
        user: The user object.
        pack_type: Optional PackType object. If not provided, uses normal pack type.

    Returns:
        float: Probability rounded to 4 decimals.
    """
    # Get the generation and pack type
    generation = pack.rarity_version  # Note: still called rarity_version in Pack model

    # Default to normal pack if no pack_type specified
    if pack_type is None:
        pack_type = generation.pack_types.filter(name="normal").first()
        if not pack_type:
            # Fallback to first available pack type
            pack_type = generation.pack_types.first()

    if not pack_type:
        logger.debug("No pack type found for generation %s", generation.name)
        available_types = list(generation.pack_types.all())
        logger.debug("Available pack types: %s", available_types)
        return 0.0

    # Get rarity probabilities - handle god packs specially
    if pack_type.is_god_pack:
        # For god packs, get probabilities from the set's generation
        pack_set = pack.set
        rarity_probs_dict = pack_set.get_rarity_probabilities(pack_type)
        # Convert dict format to object-like structure for compatibility
        rarities = {}
        for rarity_name, slot_probs in rarity_probs_dict.items():
            # Create a simple object to hold probabilities
            class RarityProb:
                def __init__(self, rarity_name, slot_probs):
                    self.rarity_name = rarity_name
                    self.probability_slot1 = slot_probs[0]
                    self.probability_slot2 = slot_probs[1]
                    self.probability_slot3 = slot_probs[2]
                    self.probability_slot4 = slot_probs[3]
                    self.probability_slot5 = slot_probs[4]
                    self.probability_slot6 = slot_probs[5]

            from apps.tracker.models.cards import Rarity

            rarity = Rarity.objects.get(name=rarity_name)
            rarities[rarity] = RarityProb(rarity_name, slot_probs)
    else:
        # For normal/shiny packs, get stored probabilities
        rarity_probs = RarityProbability.objects.filter(
            generation=generation, pack_type=pack_type
        ).select_related("rarity")
        rarities = {rp.rarity: rp for rp in rarity_probs}
        logger.debug(
            "Found %d rarity probabilities for %s - %s",
            len(rarities),
            generation.name,
            pack_type.name,
        )
        if not rarities:
            # Try without pack_type filter to see what's available
            all_probs = RarityProbability.objects.filter(
                generation=generation
            ).select_related("rarity", "pack_type")
            logger.debug(
                "All probabilities for generation: %s",
                [
                    (rp.rarity.name, rp.pack_type.name if rp.pack_type else None)
                    for rp in all_probs
                ],
            )

    cards_in_pack = pack.cards.select_related("rarity").all()
    logger.debug("Pack has %d cards", len(cards_in_pack))

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

    # Build slot field list dynamically based on the pack_type slot_count
    base_fields = [
        "probability_slot1",  # slot 1
        "probability_slot2",  # slot 2
        "probability_slot3",  # slot 3
        "probability_slot4",  # slot 4
        "probability_slot5",  # slot 5
        "probability_slot6",  # slot 6
    ]
    slot_fields = base_fields[: pack_type.slot_count]

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
            logger.debug(
                "%s - %s: prob=%s, owned=%d/%d",
                slot_field,
                rarity.name,
                prob,
                owned_count,
                total,
            )
        prob_no_new *= slot_prob_no_new
        logger.debug(
            "%s - slot_prob_no_new=%s, prob_no_new=%s",
            slot_field,
            slot_prob_no_new,
            prob_no_new,
        )

    result = round(1.0 - prob_no_new, 4)
    logger.debug("Final result: %s", result)
    return result
