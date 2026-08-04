"""
accounts app views -- registration, login, logout, onboarding and profile.

Registration creates a real User (plus a CaregiverLink or ProviderProfile
where relevant) and starts a real session.

Post-signup routing follows the CareNest onboarding spec:
  * Patient   -> straight to the dashboard; profile is completed gradually
  * Caregiver -> onboarding, then waits for the patient to approve the link
  * Provider  -> onboarding, then the verification-pending page
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, PUBLIC_ROLE_CHOICES, RegisterForm
from accounts.devices import register_device, set_device_cookie
from accounts.linking import create_link_request, resolve_patient
from accounts.models import (
    CaregiverInvite, CaregiverLink, Notification, TrustedDevice, User,
)
from adminpanel.models import AuditLog

ONBOARDING_CONTENT = {
    'CAREGIVER': {
        'label': 'Caregiver',
        'heading': 'Link to the patient you support',
        'intro': "You'll get read-only access once the patient approves your request.",
        'fields': [
            {'name': 'relationship', 'label': 'Relationship to patient', 'type': 'text',
             'placeholder': 'e.g. Daughter, Spouse, Son'},
            {'name': 'phone_number', 'label': 'Contact number', 'type': 'text',
             'placeholder': '+91 98765 43210'},
        ],
        'next_url_name': 'health_caregiver_dashboard',
        'next_label': 'Go to caregiver dashboard',
    },
    'PROVIDER': {
        'label': 'Provider',
        'heading': 'Submit your credentials for verification',
        'intro': 'An administrator reviews every submission before your listing goes live.',
        'fields': [
            {'name': 'specialty', 'label': 'Specialty or service', 'type': 'text',
             'placeholder': 'e.g. General Physician'},
            {'name': 'clinic_name', 'label': 'Clinic / organisation name', 'type': 'text',
             'placeholder': 'e.g. City Care Clinic'},
            {'name': 'years_experience', 'label': 'Years of experience', 'type': 'number',
             'placeholder': 'e.g. 9'},
            {'name': 'registration_number', 'label': 'Registration / licence number', 'type': 'text',
             'placeholder': 'e.g. KMC-2014-88213'},
            {'name': 'address', 'label': 'Address', 'type': 'text',
             'placeholder': 'Street, area, city'},
        ],
        'next_url_name': 'provider_pending',
        'next_label': 'Submit for verification',
    },
}

ROLE_DASHBOARD_URL = {
    User.Role.PATIENT: 'health_dashboard',
    User.Role.CAREGIVER: 'health_caregiver_dashboard',
    User.Role.PROVIDER: 'provider_dashboard',
    User.Role.ADMIN: 'admin_dashboard',
    User.Role.NURSE: 'nurse_dashboard',
}


def register_view(request):
    if request.user.is_authenticated:
        return redirect(ROLE_DASHBOARD_URL.get(request.user.role, 'home'))

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            confirm_password = form.cleaned_data['confirm_password']
            role = form.cleaned_data['role']
            full_name = form.cleaned_data['full_name'].strip()
            phone_number = form.cleaned_data['phone_number']

            if password != confirm_password:
                form.add_error('confirm_password', "Passwords don't match.")
            elif User.objects.filter(username__iexact=email).exists():
                form.add_error('email', 'An account with this email already exists.')
            else:
                try:
                    validate_password(password)
                except ValidationError as exc:
                    for err in exc.messages:
                        form.add_error('password', err)

            if not form.errors:
                first_name, _, last_name = full_name.partition(' ')
                user = User.objects.create_user(
                    username=email, email=email, password=password,
                    first_name=first_name, last_name=last_name,
                    role=role, phone_number=phone_number,
                )

                if role == User.Role.CAREGIVER:
                    patient, invite, error = resolve_patient(form.cleaned_data['caregiver_patient_ref'])
                    if patient:
                        create_link_request(patient, user, invite=invite)
                        messages.info(request, f'Request sent to {patient.display_name}. They need to approve it.')
                    else:
                        messages.warning(
                            request,
                            f'{error} You can send the request again from your dashboard.')

                if role == User.Role.PROVIDER:
                    from providers.models import ProviderProfile
                    ProviderProfile.objects.create(
                        user=user, provider_type=form.cleaned_data['provider_type'])

                login(request, user)
                AuditLog.record(user, 'Registered an account', user.get_role_display(), AuditLog.Tag.MUTED)

                # Patients skip the wizard and land on their dashboard, with a
                # profile-completion prompt waiting for them there.
                if role == User.Role.PATIENT:
                    messages.success(
                        request,
                        f"Welcome to CareNest, {first_name or full_name}! Complete your profile when you get a moment.")
                    return redirect('health_dashboard')

                messages.success(request, f"Welcome, {first_name or full_name}!")
                return redirect('onboarding', role=role.lower())
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {
        'form': form, 'roles': form.fields['role'].choices,
    })


def _username_for_login(typed_email):
    """
    Turn the email someone typed into the username Django must authenticate.

    Accounts created through registration always have username == email, so
    the two are interchangeable. Accounts created with `createsuperuser`
    do not: that command asks for a username and an email separately, so a
    superuser can end up as username='admin', email='admin@example.com'.
    Without this lookup such an account can never sign in to the app --
    typing the username fails email validation, and typing the email finds
    no matching username.

    Matching on email is tried first; if nothing matches we fall back to
    treating the input as the username, which keeps the normal case working
    even before any User rows exist.
    """
    match = User.objects.filter(email__iexact=typed_email)
    if match.count() == 1:
        return match.first().username
    if match.count() > 1:
        # Shouldn't happen (registration blocks duplicate emails), but if it
        # does, prefer the account whose username is also the email.
        exact = match.filter(username__iexact=typed_email).first()
        if exact:
            return exact.username
    return typed_email


def login_view(request):
    if request.user.is_authenticated:
        return redirect(ROLE_DASHBOARD_URL.get(request.user.role, 'home'))

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=_username_for_login(email), password=password)
            if user is None:
                form.add_error(None, 'Incorrect email or password.')
            elif user.is_suspended:
                form.add_error(None, 'This account has been suspended. Please contact support.')
            else:
                login(request, user)
                response = redirect(ROLE_DASHBOARD_URL.get(user.role, 'home'))

                # Caregivers get the extra new-device check; nobody else
                # is reading someone else's data, so nobody else needs it.
                if user.role == User.Role.CAREGIVER:
                    device, new_token = register_device(request, user)
                    if device.status == TrustedDevice.Status.PENDING:
                        messages.warning(
                            request,
                            "We haven't seen this device before, so we've asked the patient to "
                            'approve it. You can sign in, but their data stays hidden until they do.')
                    return set_device_cookie(response, new_token)

                return response
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def onboarding_view(request, role):
    role_key = role.upper()
    content = ONBOARDING_CONTENT.get(role_key)
    if content is None:
        # Patients (and anyone else) have no wizard -- send them home.
        return redirect(ROLE_DASHBOARD_URL.get(request.user.role, 'home'))

    if request.method == 'POST':
        if role_key == 'CAREGIVER':
            relationship = request.POST.get('relationship', '').strip()
            phone = request.POST.get('phone_number', '').strip()
            if phone:
                request.user.phone_number = phone
                request.user.save(update_fields=['phone_number'])
            if relationship:
                CaregiverLink.objects.filter(caregiver=request.user).update(relationship=relationship)

        elif role_key == 'PROVIDER':
            profile = getattr(request.user, 'provider_profile', None)
            if profile:
                profile.specialty = request.POST.get('specialty', '').strip()
                profile.clinic_name = request.POST.get('clinic_name', '').strip()
                profile.registration_number = request.POST.get('registration_number', '').strip()
                profile.address = request.POST.get('address', '').strip()
                years = request.POST.get('years_experience', '').strip()
                profile.years_experience = int(years) if years.isdigit() else None
                profile.save()

        return redirect(content['next_url_name'])

    return render(request, 'accounts/onboarding.html', {'content': content, 'role': role_key})


@login_required
def profile_view(request):
    """Where any user completes or edits their profile details."""
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.phone_number = request.POST.get('phone_number', '').strip()
        user.blood_group = request.POST.get('blood_group', '').strip()
        user.sex = request.POST.get('sex', '').strip()
        user.address = request.POST.get('address', '').strip()
        user.emergency_contact = request.POST.get('emergency_contact', '').strip()
        user.emergency_contact_name = request.POST.get('emergency_contact_name', '').strip()
        user.emergency_contact_relation = request.POST.get('emergency_contact_relation', '').strip()
        user.allergies = request.POST.get('allergies', '').strip()
        user.medical_conditions = request.POST.get('medical_conditions', '').strip()

        dob = request.POST.get('date_of_birth', '').strip()
        height = request.POST.get('height_cm', '').strip()
        try:
            import datetime
            user.date_of_birth = datetime.date.fromisoformat(dob) if dob else None
            user.height_cm = int(height) if height else None
        except ValueError:
            messages.error(request, 'Please check the date of birth and height.')
            return redirect('profile')

        user.save()
        messages.success(request, 'Profile updated.')
        return redirect('profile')

    return render(request, 'accounts/profile.html', {
        'user_obj': user,
        'completion': user.profile_completion(),
        'missing': user.missing_profile_fields(),
        'sex_choices': User.Sex.choices,
    })
