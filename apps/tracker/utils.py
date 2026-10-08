"""Tracker app utilities: pull probability calculation."""

import logging
from collections import defaultdict

from apps.tracker.models.cards import (
    SLOT_FIELD_COUNT,
    RarityProbability,
    god_pack_slot_table,
)
from apps.tracker.models.users import UserCard

logger = logging.getLogger("tracker.utils")


def load_rarity_tables(generation):
    """Load the stored rarity tables of a generation in a single query.

    Args:
        generation: The Generation whose RarityProbability rows to load.

    Returns:
        dict: ``{pack_type_id: {rarity_name: [slot1, ..., slot6]}}`` for every
        pack type that has stored probabilities (god packs have none; their
        table is derived from the pack's card pool).
    """
    tables = defaultdict(dict)
    rows = RarityProbability.objects.filter(generation=generation).exclude(
        pack_type__isnull=True
    )
    for row in rows:
        tables[row.pack_type_id][row.rarity_id] = row.get_slot_probabilities()
    return tables


def _god_pack_table(generation, cards_by_rarity, slot_count):
    """Derive the god pack rarity table from the pack's own card pool."""
    counts = {
        name: len(cards_by_rarity.get(name, ()))
        for name in generation.god_pack_eligible_rarity_names()
    }
    return god_pack_slot_table(counts, slot_count)


def _rarity_table(generation, pack_type, cards_by_rarity, rarity_tables):
    """Resolve the ``{rarity_name: [slot probs]}`` table for a pack type."""
    if pack_type.is_god_pack:
        return _god_pack_table(generation, cards_by_rarity, pack_type.slot_count)
    if rarity_tables is None:
        rarity_tables = load_rarity_tables(generation)
    return rarity_tables.get(pack_type.id, {})


def _default_pack_type(generation):
    pack_type = generation.pack_types.filter(name="normal").first()
    return pack_type or generation.pack_types.first()


def _slot_no_new_factor(table, slot, cards_by_rarity, owned_card_ids):
    """P(slot yields no new card), renormalised over rarities present in the pack.

    Returns ``None`` when nothing the slot can draw exists in the pack.
    """
    slot_mass = 0.0
    slot_no_new = 0.0
    for rarity_name, slot_probs in table.items():
        prob = slot_probs[slot]
        pool = cards_by_rarity.get(rarity_name)
        if prob <= 0 or not pool:
            continue
        owned = sum(1 for card in pool if card.id in owned_card_ids)
        slot_mass += prob
        slot_no_new += prob * owned / len(pool)
    if slot_mass <= 0:
        return None
    return slot_no_new / slot_mass


def prob_at_least_one_new_card(  # pylint: disable=too-many-arguments
    pack,
    user,
    pack_type=None,
    *,
    cards=None,
    owned_card_ids=None,
    rarity_tables=None,
):
    """Probability that a pack of the given type yields at least one card the user lacks.

    Model: slots are drawn independently; each slot draws a rarity according to
    the pack type's table and then a card uniformly from the pack's cards of
    that rarity. ``P(new) = 1 - prod_slots sum_rarity P(rarity) * owned/total``.

    Rarities that appear in the table but have no cards in this pack cannot be
    drawn from it, so each slot's distribution is renormalised over the
    rarities that are actually present. A slot with no present rarity at all
    is treated as never yielding a new card.

    Args:
        pack: The Pack to open.
        user: The user whose collection is checked.
        pack_type: PackType to evaluate. Defaults to the generation's
            ``normal`` pack type (or its first pack type).
        cards: Optional pre-fetched list of the pack's cards.
        owned_card_ids: Optional pre-fetched set of card ids the user owns.
        rarity_tables: Optional result of :func:`load_rarity_tables` for the
            pack's generation, to avoid re-querying per pack.

    Returns:
        float: Probability in ``[0, 1]`` rounded to 4 decimals.
    """
    generation = pack.rarity_version
    if pack_type is None:
        pack_type = _default_pack_type(generation)
    if pack_type is None:
        logger.warning("No pack type defined for generation %s", generation.name)
        return 0.0

    if cards is None:
        cards = list(pack.cards.all())
    if not cards:
        return 0.0
    if owned_card_ids is None:
        owned_card_ids = set(
            UserCard.objects.filter(user=user, card__in=cards).values_list(
                "card_id", flat=True
            )
        )

    # Rarity's primary key is its name, so rarity_id needs no join.
    cards_by_rarity = defaultdict(list)
    for card in cards:
        cards_by_rarity[card.rarity_id].append(card)

    table = _rarity_table(generation, pack_type, cards_by_rarity, rarity_tables)
    if not table:
        logger.warning(
            "No rarity probabilities for %s / %s", generation.name, pack_type.name
        )
        return 0.0

    missing = [name for name in table if name not in cards_by_rarity]
    if missing:
        logger.debug(
            "%s/%s: rarities %s have no cards in pack %s, renormalising per slot",
            generation.name,
            pack_type.name,
            missing,
            pack,
        )

    prob_no_new = 1.0
    for slot in range(min(pack_type.slot_count, SLOT_FIELD_COUNT)):
        factor = _slot_no_new_factor(table, slot, cards_by_rarity, owned_card_ids)
        if factor is None:
            # Nothing this slot can draw exists in the pack: it yields nothing new.
            continue
        prob_no_new *= factor

    return round(min(max(1.0 - prob_no_new, 0.0), 1.0), 4)


def prob_new_card_any_pack_type(  # pylint: disable=too-many-arguments
    pack,
    user,
    *,
    pack_types=None,
    cards=None,
    owned_card_ids=None,
    rarity_tables=None,
):
    """Probability of at least one new card from a pack, over all its pack types.

    Applies the law of total probability: each pack type's result is weighted
    by its ``occurrence_probability``. Weights are normalised so that tables
    whose occurrence probabilities do not sum exactly to 1 still yield a
    proper probability.

    Args:
        pack: The Pack to open.
        user: The user whose collection is checked.
        pack_types: Optional pre-fetched list of the generation's PackTypes.
        cards, owned_card_ids, rarity_tables: See
            :func:`prob_at_least_one_new_card`.

    Returns:
        float: Probability in ``[0, 1]`` rounded to 4 decimals.
    """
    if pack_types is None:
        pack_types = list(pack.rarity_version.pack_types.all())
    if not pack_types:
        return prob_at_least_one_new_card(
            pack,
            user,
            cards=cards,
            owned_card_ids=owned_card_ids,
            rarity_tables=rarity_tables,
        )

    total_weight = sum(pt.occurrence_probability for pt in pack_types)
    if total_weight <= 0:
        return 0.0
    weighted = sum(
        pt.occurrence_probability
        * prob_at_least_one_new_card(
            pack,
            user,
            pt,
            cards=cards,
            owned_card_ids=owned_card_ids,
            rarity_tables=rarity_tables,
        )
        for pt in pack_types
    )
    return round(min(max(weighted / total_weight, 0.0), 1.0), 4)
