"""
accounts app forms -- registration and login.
"""
from django import forms
from accounts.models import User

# Only these three roles can self-register. ADMIN and NURSE accounts are
# created by an administrator (via /admin/) -- they are deliberately left
# out of the choices a visitor can submit, so a crafted POST can't grant
# either role (Django's ChoiceField rejects any value not in this list).
PUBLIC_ROLE_CHOICES = [
    (User.Role.PATIENT, 'Patient'),
    (User.Role.CAREGIVER, 'Caregiver'),
    (User.Role.PROVIDER, 'Provider'),
]

PROVIDER_TYPE_CHOICES = [
    ('', 'Select provider type'),
    ('DOCTOR', 'Doctor'),
    ('CLINIC', 'Clinic'),
    ('HOSPITAL', 'Hospital'),
    ('DIAGNOSTIC_LAB', 'Diagnostic Lab'),
    ('PHARMACY', 'Pharmacy'),
    ('DIETICIAN', 'Dietician'),
    ('FITNESS_CENTRE', 'Fitness Centre'),
    ('WELLNESS_CENTRE', 'Wellness Centre'),
]


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Full name'}))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    phone_number = forms.CharField(max_length=20, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}))
    role = forms.ChoiceField(choices=PUBLIC_ROLE_CHOICES, widget=forms.RadioSelect)
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Create a password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))
    # Only required when role == CAREGIVER
    caregiver_patient_id = forms.CharField(
        max_length=12, required=False, label="Patient's unique ID",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Patient's unique ID (shared by the patient)"}))
    # Only required when role == PROVIDER
    provider_type = forms.ChoiceField(
        choices=PROVIDER_TYPE_CHOICES, required=False,
        widget=forms.Select(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        if role == User.Role.CAREGIVER and not cleaned.get('caregiver_patient_id'):
            self.add_error('caregiver_patient_id', "Enter the patient's unique ID to link your account.")
        if role == User.Role.PROVIDER and not cleaned.get('provider_type'):
            self.add_error('provider_type', 'Select the type of provider you are registering as.')
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}))
