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
from django.core.cache import cache
from django.db import IntegrityError
from django.shortcuts import redirect, render

from accounts.forms import (
    CaregiverOnboardingForm, LoginForm, ProviderOnboardingForm,
    PUBLIC_ROLE_CHOICES, RegisterForm,
)
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
        'form_class': CaregiverOnboardingForm,
        'next_url_name': 'health_caregiver_dashboard',
        'next_label': 'Go to caregiver dashboard',
    },
    'PROVIDER': {
        'label': 'Provider',
        'heading': 'Submit your credentials for verification',
        'intro': 'An administrator reviews every submission before your listing goes live.',
        'form_class': ProviderOnboardingForm,
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
            # Normalised once, here, so the duplicate check below and the
            # account actually created always agree on what "this email"
            # means -- User.save() would lower-case it anyway, but doing it
            # before the pre-check avoids a false negative on mixed case.
            #
            # Password match and strength are now enforced in
            # RegisterForm.clean() -- form.is_valid() above already ran
            # them, so getting here means both already passed. Only the
            # duplicate-email check remains a view-level concern: it needs
            # a DB query at submit time, not something a form's clean()
            # should be doing on every partial validation pass.
            email = form.cleaned_data['email'].strip().lower()
            password = form.cleaned_data['password']
            role = form.cleaned_data['role']
            full_name = form.cleaned_data['full_name'].strip()
            phone_number = form.cleaned_data['phone_number']

            if User.objects.filter(email__iexact=email).exists():
                form.add_error('email', 'An account with this email already exists.')

            if not form.errors:
                first_name, _, last_name = full_name.partition(' ')
                try:
                    user = User.objects.create_user(
                        username=email, email=email, password=password,
                        first_name=first_name, last_name=last_name,
                        role=role, phone_number=phone_number,
                    )
                except IntegrityError:
                    # Belt-and-braces against a second request winning a race
                    # on the same email between the check above and this
                    # insert -- now that email is unique at the DB level,
                    # the second request must fail cleanly, not 500.
                    form.add_error('email', 'An account with this email already exists.')
                    return render(request, 'accounts/register.html', {
                        'form': form, 'roles': form.fields['role'].choices,
                    })

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
                # form.is_valid() already required agree_to_terms to be
                # checked, so reaching here means consent was given -- this
                # is a separate, explicitly-labelled audit entry rather than
                # folding it into the line above, so "did this user accept
                # the terms, and when" can be answered on its own later.
                AuditLog.record(user, 'Accepted Terms of Service and Privacy Policy', '', AuditLog.Tag.MUTED)

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
    no matching username. That case is unrelated to email uniqueness, so
    this helper is still needed even now that email is a unique column.

    What migration 0009 (email uniqueness) DID remove is the ambiguity this
    used to have to handle: `email__iexact` can now match at most one row,
    never several, so there is no "which one did they mean" case left --
    only "did we find one, or not."

    If nothing matches, we fall back to treating the input as the username,
    which keeps the normal case working even before any User rows exist.
    """
    match = User.objects.filter(email__iexact=typed_email).first()
    return match.username if match else typed_email


# --- Login lockout ---------------------------------------------------------
#
# Unlimited password guesses were possible before this: no rate limit and no
# lockout on failed logins. This adds one without a new dependency (no
# django-axes) -- a small counter in Django's cache, keyed two ways at once:
#
#   * per EMAIL, so a bot can't grind through passwords for one account
#   * per IP,    so a bot can't grind through many accounts from one source
#
# Both must clear for a login attempt to be allowed through. A genuine user
# who mistypes their password five times only trips the per-email lock,
# which self-clears after LOGIN_LOCKOUT_SECONDS -- nobody has to contact an
# admin to get back in.
#
# Caveat worth stating plainly: Django's default cache backend is
# per-process local memory, so this lockout is only real protection when the
# app runs as a single process (exactly this project's deployment). A
# multi-worker production deployment would need a shared cache (Redis/
# memcached) for the same counters to mean anything across workers.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', 'unknown')


def _lockout_keys(email, request):
    return f'loginfail:email:{email.strip().lower()}', f'loginfail:ip:{_client_ip(request)}'


def _is_locked_out(email, request):
    email_key, ip_key = _lockout_keys(email, request)
    return (cache.get(email_key, 0) >= LOGIN_MAX_ATTEMPTS
            or cache.get(ip_key, 0) >= LOGIN_MAX_ATTEMPTS)


def _record_failed_login(email, request):
    for key in _lockout_keys(email, request):
        try:
            cache.incr(key)
        except ValueError:
            # incr() raises when the key doesn't exist yet (or just expired)
            # -- this is the "first failure" case, so start the window.
            cache.set(key, 1, timeout=LOGIN_LOCKOUT_SECONDS)


def _clear_failed_logins(email, request):
    for key in _lockout_keys(email, request):
        cache.delete(key)


def login_view(request):
    if request.user.is_authenticated:
        return redirect(ROLE_DASHBOARD_URL.get(request.user.role, 'home'))

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            if _is_locked_out(email, request):
                form.add_error(
                    None,
                    'Too many failed attempts. Please wait 15 minutes before trying again.')
                return render(request, 'accounts/login.html', {'form': form})

            user = authenticate(request, username=_username_for_login(email), password=password)
            if user is None:
                _record_failed_login(email, request)
                form.add_error(None, 'Incorrect email or password.')
            elif user.is_suspended:
                form.add_error(None, 'This account has been suspended. Please contact support.')
            else:
                _clear_failed_logins(email, request)
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

    form_class = content['form_class']

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            if role_key == 'CAREGIVER':
                request.user.phone_number = data['phone_number']
                request.user.save(update_fields=['phone_number'])
                CaregiverLink.objects.filter(caregiver=request.user).update(
                    relationship=data['relationship'])

            elif role_key == 'PROVIDER':
                profile = getattr(request.user, 'provider_profile', None)
                if profile:
                    profile.specialty = data['specialty']
                    profile.clinic_name = data['clinic_name']
                    profile.registration_number = data['registration_number']
                    profile.address = data['address']
                    profile.years_experience = data['years_experience']
                    profile.save()

            return redirect(content['next_url_name'])
    else:
        form = form_class()

    return render(request, 'accounts/onboarding.html', {
        'content': content, 'role': role_key, 'form': form,
    })


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
