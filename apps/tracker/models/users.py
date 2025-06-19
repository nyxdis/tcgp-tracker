"""Tracker app users models."""

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserCard(models.Model):
    """Represents a user's owned card and quantity."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_cards")
    card = models.ForeignKey(
        "Card", on_delete=models.CASCADE, related_name="user_cards"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")

    class Meta:
        unique_together = ("user", "card")
        indexes = [models.Index(fields=["user", "card"])]
        verbose_name = "User Card"
        verbose_name_plural = "User Cards"

    def __str__(self):
        return f"{self.user.username} hat {self.quantity}x {self.card.name}"


class UserProfile(models.Model):
    """Profile for a user, including friend code and privacy."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    public = models.BooleanField(default=True, verbose_name="Public Profile")
    friend_code = models.CharField(
        max_length=10, blank=True, null=True, verbose_name="Friend Code"
    )

    def __str__(self):
        return f"Profile of {self.user.username}"

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"


class FriendRequest(models.Model):
    """Represents a friend request between two user profiles."""

    from_user = models.ForeignKey(
        UserProfile, related_name="sent_friend_requests", on_delete=models.CASCADE
    )
    to_user = models.ForeignKey(
        UserProfile, related_name="received_friend_requests", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    accepted = models.BooleanField(default=False, verbose_name="Accepted")

    class Meta:
        unique_together = ("from_user", "to_user")
        verbose_name = "Friend Request"
        verbose_name_plural = "Friend Requests"

    def __str__(self):
        status = "Accepted" if self.accepted else "Pending"
        return (
            f"{self.from_user.user.username} → {self.to_user.user.username} ({status})"
        )
