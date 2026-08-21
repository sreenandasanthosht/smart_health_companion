"""
core app views -- the "chef" that prepares pages.

`home` is the front door at "/". It does not render a page of its own for the
usual visitor: signed-out visitors are sent to the login page (which is also
the public landing page), and signed-in users go straight to the dashboard for
their role. The marketing template below is kept as a fallback for the rare
account whose role has no dashboard mapped, so no one ever hits a dead end.
"""
from django.shortcuts import redirect, render


def home(request):
    if not request.user.is_authenticated:
        return redirect('login')

    # Imported here rather than at module level: accounts imports several other
    # apps, and a top-level import would tie core's load order to theirs.
    from accounts.views import ROLE_DASHBOARD_URL

    dashboard = ROLE_DASHBOARD_URL.get(request.user.role)
    if dashboard:
        return redirect(dashboard)

    context = {
        'project_name': 'CareNest',
        'tagline': 'Where Care Continues',
        'features': [
            {
                'icon': '\U0001FA7A',
                'title': 'Vitals Tracking',
                'text': 'Log blood pressure, sugar, weight and heart rate over time, with trend and out-of-range alerts.',
                'url_name': 'health_vitals',
            },
            {
                'icon': '\U0001F48A',
                'title': 'Medication & AI Prescription Reader',
                'text': 'Upload a prescription photo; OCR + LLM extract the medicine, dose and duration for you to confirm.',
                'url_name': 'health_medications',
            },
            {
                'icon': '\U0001F6B4',
                'title': 'Lifestyle & Wellness',
                'text': 'Track sleep, water intake and activity alongside your vitals for a fuller picture of your health.',
                'url_name': 'health_lifestyle',
            },
            {
                'icon': '\U0001F512',
                'title': 'Private Mental Health Log',
                'text': 'Mood and mental-health entries stay in a private silo -- never visible to caregivers or providers.',
                'url_name': 'health_mental_health',
            },
            {
                'icon': '\U0001F4C5',
                'title': 'Appointments & Provider Directory',
                'text': 'Browse verified providers and book appointments; providers manage requests from their own dashboard.',
                'url_name': 'provider_directory',
            },
            {
                'icon': '\U0001F46A',
                'title': 'Caregiver Monitoring',
                'text': 'Caregivers get a secure, read-only view of physical vitals and critical alerts for the patient they support.',
                'url_name': 'health_caregiver_dashboard',
            },
        ],
        'roles': [
            {
                'name': 'Patient',
                'desc': 'Logs vitals & lifestyle, uploads prescriptions, books appointments, controls what is shared.',
                'url_name': 'health_dashboard',
                'cta': 'View patient dashboard',
            },
            {
                'name': 'Caregiver',
                'desc': 'Read-only monitoring of a linked patient’s physical vitals and critical alerts.',
                'url_name': 'health_caregiver_dashboard',
                'cta': 'View caregiver dashboard',
            },
            {
                'name': 'Provider',
                'desc': 'Manages appointment requests and notes once verified by an administrator.',
                'url_name': 'provider_dashboard',
                'cta': 'View provider dashboard',
            },
        ],
    }
    return render(request, 'core/home.html', context)
