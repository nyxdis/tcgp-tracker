"""Tracker app views for users."""

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import models
from django.db.models import Q
from django.shortcuts import redirect, render

from apps.tracker.forms import RegisterForm, UserProfileForm
from apps.tracker.models.users import FriendRequest, UserProfile


def register(request):
    """Handle user registration, log in new users, and redirect to home."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def account(request):
    """Allow users to change their password or delete their account."""
    if request.method == "POST":
        if "password_change" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Ihr Passwort wurde erfolgreich geändert!")
            else:
                messages.error(request, "Bitte korrigieren Sie die Fehler unten.")
        elif "delete_account" in request.POST:
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, "Ihr Account wurde erfolgreich gelöscht.")
            return redirect("home")
    else:
        password_form = PasswordChangeForm(request.user)
    return render(request, "tracker/account.html", {"password_form": password_form})


@login_required
def profile(request):
    """Display and update the user's profile, show friends and friend requests."""
    user_profile = request.user.profile
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
    else:
        form = UserProfileForm(instance=user_profile)
    friends = UserProfile.objects.filter(
        Q(
            sent_friend_requests__to_user=user_profile,
            sent_friend_requests__accepted=True,
        )
        | Q(
            received_friend_requests__from_user=user_profile,
            received_friend_requests__accepted=True,
        )
    ).distinct()
    friend_requests = FriendRequest.objects.filter(to_user=user_profile, accepted=False)
    return render(
        request,
        "tracker/profile.html",
        {
            "profile": user_profile,
            "form": form,
            "friends": friends,
            "friend_requests": friend_requests,
        },
    )


@login_required
def user_search(request):
    """Allow users to search for public profiles by username or friend code."""
    query = request.GET.get("q", "").strip()
    results = []
    if query:
        results = (
            UserProfile.objects.filter(public=True)
            .filter(
                models.Q(user__username__icontains=query)
                | models.Q(friend_code__icontains=query)
            )
            .exclude(user=request.user)
        )
    sent_requests = FriendRequest.objects.filter(from_user=request.user.profile)
    sent_to_ids = set(fr.to_user_id for fr in sent_requests)
    received_requests = list(
        FriendRequest.objects.filter(to_user=request.user.profile, accepted=False)
    )
    received_from_ids = set(fr.from_user_id for fr in received_requests)
    friends = UserProfile.objects.filter(
        Q(
            sent_friend_requests__to_user=request.user.profile,
            sent_friend_requests__accepted=True,
        )
        | Q(
            received_friend_requests__from_user=request.user.profile,
            received_friend_requests__accepted=True,
        )
    ).values_list("id", flat=True)
    return render(
        request,
        "tracker/user_search.html",
        {
            "query": query,
            "results": results,
            "sent_to_ids": sent_to_ids,
            "received_from_ids": received_from_ids,
            "friends": friends,
            "received_requests": received_requests,
        },
    )
