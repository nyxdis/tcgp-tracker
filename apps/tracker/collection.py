"""A user's card collection, with reprints that share their original's entry.

From B4b on, the game treats a reprint as the same card as its original
(Card.reprint_of). A collection entry (UserCard) is therefore stored once, on
the original, and every print of the card counts as owned when it exists.
All ownership checks should go through this module rather than querying
UserCard per print.
"""

from django.db.models import Q

from apps.tracker.models.cards import Card
from apps.tracker.models.users import UserCard


def owned_q(user):
    """Q() matching the cards *user* owns, including reprints of owned originals."""
    entries = UserCard.objects.filter(user=user).values("card_id")
    return Q(id__in=entries) | Q(reprint_of_id__in=entries)


def owned_card_ids(user):
    """Ids of all cards *user* owns, including reprints of owned originals."""
    return set(Card.objects.filter(owned_q(user)).values_list("id", flat=True))


def owned_quantities(user, cards):
    """Map each of *cards* to the quantity *user* owns (0 if none)."""
    quantities = dict(
        UserCard.objects.filter(
            user=user, card_id__in={card.collection_card_id for card in cards}
        ).values_list("card_id", "quantity")
    )
    return {card.id: quantities.get(card.collection_card_id, 0) for card in cards}


def collect(user, card):
    """Add *card* to the collection; a reprint is stored on its original."""
    UserCard.objects.get_or_create(
        user=user, card_id=card.collection_card_id, defaults={"quantity": 1}
    )


def uncollect(user, card_id):
    """Remove the card with *card_id* (and so all its prints) from the collection."""
    reprint_of_id = (
        Card.objects.filter(id=card_id).values_list("reprint_of_id", flat=True).first()
    )
    UserCard.objects.filter(
        user=user, card_id__in={card_id, reprint_of_id} - {None}
    ).delete()


def merge_reprint_entries():
    """Move collection entries recorded on reprints to their originals.

    Needed when a card becomes linked as a reprint after users already
    collected it separately. If a user has both prints, the higher quantity
    is kept: it's one card in-game, so both entries most likely counted the
    same copies. Returns the number of entries moved or merged.
    """
    on_reprints = UserCard.objects.filter(
        card__reprint_of__isnull=False
    ).select_related("card")
    merged = 0
    for entry in on_reprints:
        original_id = entry.card.reprint_of_id
        existing = UserCard.objects.filter(user_id=entry.user_id, card_id=original_id)
        if existing.exists():
            existing.filter(quantity__lt=entry.quantity).update(quantity=entry.quantity)
            entry.delete()
        else:
            entry.card_id = original_id
            entry.save(update_fields=["card"])
        merged += 1
    return merged
