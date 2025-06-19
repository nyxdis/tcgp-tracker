"""Forms for tracker app."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.tracker.models.users import UserCard, UserProfile


class RegisterForm(UserCreationForm):
    """User registration form."""

    email = forms.EmailField()

    class Meta:
        """Meta options for RegisterForm."""

        model = get_user_model()
        fields = ["username", "email", "password1", "password2"]


class UserCardForm(forms.ModelForm):
    """Form for editing user card quantity."""

    class Meta:
        """Meta options for UserCardForm."""

        model = UserCard
        fields = ["quantity"]


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile."""

    class Meta:
        """Meta options for UserProfileForm."""

        model = UserProfile
        fields = ["friend_code", "public"]
