"""
accounts app forms -- presentational only for now.
These render real Bootstrap-styled forms so the pages look and feel final,
but the views don't save anything to the database yet (that wiring is a
Phase 3 task). Keeping them as plain forms.Form (not ModelForm) means they
have zero dependency on migrations having been run.
"""
from django import forms
from accounts.models import User


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Full name'}))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    role = forms.ChoiceField(choices=User.Role.choices, widget=forms.RadioSelect)
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Create a password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}))
