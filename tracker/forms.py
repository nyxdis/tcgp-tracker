from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import UserCard

class RegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "password1", "password2"]

class UserCardForm(forms.ModelForm):
    class Meta:
        model = UserCard
        fields = ['quantity']
