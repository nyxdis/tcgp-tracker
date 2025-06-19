"""Tracker app views for friends."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.tracker.models.users import FriendRequest, UserProfile


@login_required
def send_friend_request(request, user_id):
    """Send a friend request from the current user to another public profile."""
    to_profile = get_object_or_404(UserProfile, id=user_id, public=True)
    from_profile = request.user.profile
    if to_profile != from_profile:
        FriendRequest.objects.get_or_create(from_user=from_profile, to_user=to_profile)
        messages.success(request, f"Friend request sent to {to_profile.user.username}!")
    next_url = (
        request.POST.get("next") or request.META.get("HTTP_REFERER") or "user_search"
    )
    return redirect(next_url)


@login_required
def accept_friend_request(request, request_id):
    """Accept a pending friend request for the current user."""
    friend_request = get_object_or_404(
        FriendRequest, id=request_id, to_user=request.user.profile, accepted=False
    )
    friend_request.accepted = True
    friend_request.save()
    messages.success(
        request, f"{friend_request.from_user.user.username} is now your friend!"
    )
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "profile"
    return redirect(next_url)


def public_profile(request, username):
    """Show a public profile and allow sending a friend request if eligible."""
    profile = get_object_or_404(UserProfile, user__username=username, public=True)
    can_send_request = False
    already_sent = False
    if request.user.is_authenticated and request.user.profile != profile:
        can_send_request = True
        already_sent = FriendRequest.objects.filter(
            from_user=request.user.profile, to_user=profile
        ).exists()
    return render(
        request,
        "tracker/public_profile.html",
        {
            "profile": profile,
            "can_send_request": can_send_request,
            "already_sent": already_sent,
        },
    )
