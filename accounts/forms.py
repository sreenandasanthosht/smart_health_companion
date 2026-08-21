"""
accounts app forms -- registration, login, and password reset.
"""
import re

from django import forms
from django.contrib.auth.forms import (
    PasswordResetForm as DjangoPasswordResetForm,
    SetPasswordForm as DjangoSetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from accounts.models import User


def validate_phone_number(value):
    """
    10 digits (a plain Indian mobile number), or up to 12 with a country
    code in front (e.g. 91 98765 43210) -- counting DIGITS only, not
    characters. A regex like `{7,20}` on the raw string was the wrong
    check: "+91 98765 43210" is 10 digits of number but 16 characters once
    you count the spaces and the +, so a length-of-string rule either
    rejects real numbers with a code or accepts far too much. Stripping
    everything but digits first and counting those is the actual rule
    "10 digits, optionally with a short country code" is describing.
    Rejects what used to slip straight through -- letters, e.g. "aaaaaaa".
    """
    digits = re.sub(r'\D', '', value or '')
    if not (10 <= len(digits) <= 12):
        raise ValidationError('Enter a valid phone number.')

# Only these three roles can self-register. ADMIN and NURSE accounts are
# created by an administrator (via /admin/) -- they are deliberately left
# out of the choices a visitor can submit, so a crafted POST can't grant
# either role (Django's ChoiceField rejects any value not in this list).
PUBLIC_ROLE_CHOICES = [
    (User.Role.PATIENT, 'Patient'),
    (User.Role.CAREGIVER, 'Caregiver'),
    (User.Role.PROVIDER, 'Provider'),
]

def provider_type_choices():
    """
    The service a provider picks at registration, grouped by module.

    Built from `ProviderProfile` rather than repeated here, so the list can
    never drift from the model. The <optgroup> headings are the six service
    groups, which is how the provider learns which dashboard they will get
    before they submit.
    """
    from providers.models import ProviderProfile as P

    grouped = []
    for group, group_label in P.ServiceGroup.choices:
        options = [(t, P.ProviderType(t).label) for t in P.types_in_group(group)]
        if options:
            grouped.append((group_label, options))
    return [('', 'Select the service you provide')] + grouped


def public_role_choices():
    """
    The roles a visitor may pick, honouring platform settings.

    A Super Admin can close provider self-registration; when they do,
    Provider disappears from the form *and* becomes an invalid submission,
    because ChoiceField validates against exactly this list.
    """
    from adminpanel.models import PlatformSettings

    if PlatformSettings.load().provider_self_registration_open:
        return list(PUBLIC_ROLE_CHOICES)
    return [c for c in PUBLIC_ROLE_CHOICES if c[0] != User.Role.PROVIDER]


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Full name'}))
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    phone_number = forms.CharField(
        max_length=20, validators=[validate_phone_number],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}))
    role = forms.ChoiceField(
        choices=PUBLIC_ROLE_CHOICES, widget=forms.RadioSelect,
        error_messages={'required': 'Select whether you’re a patient, caregiver, or provider.'})
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Create a password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))
    # Only required when role == CAREGIVER.
    # The onboarding spec accepts any of three identifiers here -- the
    # patient's ID, their email address, or a single-use invite code they
    # generated -- so this is one field that resolves three ways rather
    # than three fields the caregiver has to choose between.
    caregiver_patient_ref = forms.CharField(
        max_length=254, required=False, label="Patient ID, email or invite code",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 4F2A9C1B77, them@example.com or CN-1A2B3C4D',
        }))
    # Only required when role == PROVIDER. Choices are resolved per-request
    # in __init__ so they always match the model.
    provider_type = forms.ChoiceField(
        choices=(), required=False,
        widget=forms.Select(attrs={'class': 'form-control'}))
    # Required on every registration, whatever the role. BooleanField is
    # required=True by default and Django treats an unchecked checkbox as
    # simply absent from POST data, so this alone is enough to reject a
    # submission where the box was left unticked -- no clean() needed.
    agree_to_terms = forms.BooleanField(
        required=True, label='I agree to the Terms of Service and Privacy Policy',
        error_messages={'required': 'You must agree to the Terms of Service and Privacy Policy to continue.'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Resolved per-request rather than at import time, so a settings
        # change takes effect without a restart. Was previously sandwiched
        # between two field declarations mid-class-body; moved below all of
        # them so the class reads as "fields, then behaviour" like every
        # other form here.
        self.fields['role'].choices = public_role_choices()
        self.fields['provider_type'].choices = provider_type_choices()

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')

        if role == User.Role.CAREGIVER and not cleaned.get('caregiver_patient_ref'):
            self.add_error(
                'caregiver_patient_ref',
                "Enter the patient's ID, their email address, or an invite code they sent you.")
        if role == User.Role.PROVIDER and not cleaned.get('provider_type'):
            self.add_error('provider_type', 'Select the type of provider you are registering as.')

        # Password match + strength used to be checked in the view, after
        # form.is_valid() had already returned True -- which meant the form
        # itself never actually enforced them, and it had no way to tell a
        # caller "this password is too weak" without going through
        # register_view's manual add_error() calls. Moved here so the form
        # is self-contained and testable on its own.
        password = cleaned.get('password')
        confirm_password = cleaned.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords don't match.")
        elif password:
            try:
                validate_password(password)
            except ValidationError as exc:
                for err in exc.messages:
                    self.add_error('password', err)

        return cleaned


class CaregiverOnboardingForm(forms.Form):
    """
    The caregiver's one onboarding step. Used to live as raw
    `request.POST.get()` reads in `onboarding_view` with no validation at
    all -- an empty relationship or a garbage phone number saved straight
    to the database. Reuses `validate_phone_number` so this phone field
    enforces the exact same rule as the one on the registration form.
    """
    relationship = forms.CharField(
        max_length=100, label='Relationship to patient',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': 'e.g. Daughter, Spouse, Son'}))
    phone_number = forms.CharField(
        max_length=20, validators=[validate_phone_number], label='Contact number',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': '+91 98765 43210'}))


class ProviderOnboardingForm(forms.Form):
    """
    The provider's credential-submission step -- same story as
    `CaregiverOnboardingForm`: previously unvalidated `request.POST.get()`
    reads, including `years_experience` silently turning into `None`
    whenever it wasn't a plain digit string.
    """
    specialty = forms.CharField(
        max_length=150, label='Specialty or service',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': 'e.g. General Physician'}))
    clinic_name = forms.CharField(
        max_length=200, label='Clinic / organisation name',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': 'e.g. City Care Clinic'}))
    years_experience = forms.IntegerField(
        min_value=0, max_value=70, label='Years of experience',
        widget=forms.NumberInput(attrs={'class': 'inp', 'placeholder': 'e.g. 9'}))
    registration_number = forms.CharField(
        max_length=100, label='Registration / licence number',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': 'e.g. KMC-2014-88213'}))
    address = forms.CharField(
        max_length=300, label='Address',
        widget=forms.TextInput(attrs={'class': 'inp', 'placeholder': 'Street, area, city'}))


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}))


class PasswordResetForm(DjangoPasswordResetForm):
    """
    Django's built-in PasswordResetForm, restyled to match every other form
    on the site -- it ships with no CSS classes on its widgets at all.

    Deliberately NOT overriding get_users() or save(): the base
    implementation already avoids confirming or denying whether an email is
    registered (password_reset_done.html shows the same message either
    way), which is the right behaviour now that email is unique -- it means
    exactly one account per address instead of the "which one did they
    mean" ambiguity that motivated migration 0009.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'form-control', 'placeholder': 'you@example.com'})


class SetPasswordForm(DjangoSetPasswordForm):
    """Django's built-in SetPasswordForm, restyled to match the site."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control', 'placeholder': 'New password'})
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control', 'placeholder': 'Confirm new password'})
