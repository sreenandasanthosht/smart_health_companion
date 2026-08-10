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
    phone_number = forms.CharField(max_length=20, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}))
    role = forms.ChoiceField(choices=PUBLIC_ROLE_CHOICES, widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Resolved per-request rather than at import time, so a settings
        # change takes effect without a restart.
        self.fields['role'].choices = public_role_choices()
        self.fields['provider_type'].choices = provider_type_choices()
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

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        if role == User.Role.CAREGIVER and not cleaned.get('caregiver_patient_ref'):
            self.add_error(
                'caregiver_patient_ref',
                "Enter the patient's ID, their email address, or an invite code they sent you.")
        if role == User.Role.PROVIDER and not cleaned.get('provider_type'):
            self.add_error('provider_type', 'Select the type of provider you are registering as.')
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(
        attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}))
