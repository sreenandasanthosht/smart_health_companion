"""
accounts app views -- registration, login and onboarding.

These are UI-preview versions: the forms are real and validate, but
submitting does not create a User row or start a real session yet.
That backend wiring (Django's built-in auth + RBAC) is Phase 3 work.
Doing it this way now means the pages, navigation and role-specific
onboarding flow can all be demoed without depending on migrations
having been run against a live database.
"""
from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, RegisterForm
from accounts.models import User

ONBOARDING_CONTENT = {
    'PATIENT': {
        'label': 'Patient',
        'heading': 'Tell us about your health baseline',
        'steps': [
            {
                'title': 'Demographics',
                'fields': ['Date of birth', 'Sex', 'Height', 'Blood group'],
            },
            {
                'title': 'Hereditary / existing conditions',
                'fields': ['Family history (diabetes, hypertension, heart disease...)', 'Existing diagnoses', 'Known allergies'],
            },
            {
                'title': 'Baseline vitals',
                'fields': ['Blood pressure', 'Blood sugar (fasting)', 'Weight', 'Resting heart rate'],
            },
        ],
        'next_url_name': 'health_dashboard',
        'next_label': 'Go to my dashboard',
    },
    'CAREGIVER': {
        'label': 'Caregiver',
        'heading': 'Link to the patient you support',
        'steps': [
            {
                'title': 'Your details',
                'fields': ['Relationship to patient (parent, child, spouse...)', 'Contact number'],
            },
            {
                'title': 'Link a patient',
                'fields': ["Patient's unique ID (shared by the patient)", 'Request sent -- patient must approve the link'],
            },
        ],
        'next_url_name': 'health_caregiver_dashboard',
        'next_label': 'Go to caregiver dashboard',
    },
    'PROVIDER': {
        'label': 'Provider',
        'heading': 'Submit your credentials for verification',
        'steps': [
            {
                'title': 'Professional details',
                'fields': ['Specialty', 'Years of experience', 'Clinic / hospital affiliation'],
            },
            {
                'title': 'Licence & qualifications',
                'fields': ['Medical licence number', 'Upload licence document', 'Upload qualification certificate'],
            },
            {
                'title': 'Awaiting admin approval',
                'fields': ['An administrator reviews every submission before your listing goes live'],
            },
        ],
        'next_url_name': 'provider_pending',
        'next_label': 'See verification status',
    },
}


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']
            messages.info(
                request,
                "Demo mode: this doesn't create a real account yet -- account creation is wired up in the next "
                "build session. Here's the onboarding flow that would follow."
            )
            return redirect('onboarding', role=role.lower())
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form, 'roles': User.Role.choices})


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            messages.info(
                request,
                "Demo mode: sign-in isn't wired to the database yet. Taking you to the patient dashboard preview."
            )
            return redirect('health_dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def onboarding_view(request, role):
    role_key = role.upper()
    content = ONBOARDING_CONTENT.get(role_key, ONBOARDING_CONTENT['PATIENT'])
    if request.method == 'POST':
        return redirect(content['next_url_name'])
    return render(request, 'accounts/onboarding.html', {'content': content, 'role': role_key})
