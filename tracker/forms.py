from django import forms
from .models import UserCard

class UserCardForm(forms.ModelForm):
    class Meta:
        model = UserCard
        fields = ['quantity']
