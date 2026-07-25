"""
providers app views -- the provider directory (marketplace), appointments,
the provider's own dashboard, and the pending-verification state.

All context below is placeholder/demo data. The providers app's models
(ProviderProfile, Appointment, ProviderNote) are still empty on purpose --
they get built in the sprint's Lane 1 sessions.
"""
from django.shortcuts import render


def directory(request):
    context = {
        'providers': [
            {'name': 'Dr. Anjali Nair', 'specialty': 'General Physician', 'experience': '9 yrs', 'verified': True},
            {'name': 'Dr. Rohan Mehta', 'specialty': 'Cardiologist', 'experience': '14 yrs', 'verified': True},
            {'name': 'Dr. Kavya Suresh', 'specialty': 'Endocrinologist', 'experience': '6 yrs', 'verified': True},
            {'name': 'Dr. Farhan Ali', 'specialty': 'Psychiatrist', 'experience': '11 yrs', 'verified': True},
            {'name': 'Dr. Meera Iyer', 'specialty': 'Dietitian', 'experience': '5 yrs', 'verified': True},
            {'name': 'Dr. Sanjay Kulkarni', 'specialty': 'Cardiologist', 'experience': '20 yrs', 'verified': True},
        ],
    }
    return render(request, 'providers/directory.html', context)


def appointments(request):
    context = {
        'upcoming': [
            {'provider': 'Dr. Anjali Nair', 'specialty': 'General Physician', 'when': 'Fri, 4 Jul - 10:30 AM', 'status': 'Confirmed'},
        ],
        'past': [
            {'provider': 'Dr. Kavya Suresh', 'specialty': 'Endocrinologist', 'when': '15 Jun 2026', 'status': 'Completed'},
        ],
        'providers': [
            'Dr. Anjali Nair -- General Physician',
            'Dr. Rohan Mehta -- Cardiologist',
            'Dr. Kavya Suresh -- Endocrinologist',
            'Dr. Farhan Ali -- Psychiatrist',
        ],
    }
    return render(request, 'providers/appointments.html', context)


def dashboard(request):
    context = {
        'provider_name': 'Dr. Anjali Nair',
        'requests': [
            {'patient': 'Sreenanda T', 'requested_for': 'Mon, 7 Jul - 9:00 AM', 'reason': 'Follow-up on blood pressure'},
        ],
        'upcoming': [
            {'patient': 'Terese M', 'when': 'Fri, 4 Jul - 10:30 AM', 'reason': 'General check-up'},
        ],
    }
    return render(request, 'providers/dashboard.html', context)


def pending(request):
    context = {
        'submitted_on': '30 Jun 2026',
        'documents': ['Medical licence number', 'Licence document', 'Qualification certificate'],
    }
    return render(request, 'providers/pending.html', context)
