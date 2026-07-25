"""
health app views -- patient-facing vitals, medications, lifestyle,
mental health, sharing, and the caregiver's read-only view.

Every context dict below is placeholder/demo data. The health app's
models (VitalRecord, Medication, LifestyleLog, MentalHealthLog) are
still empty on purpose -- they get built in the sprint's Lane 1
sessions. These views exist now purely to preview the pages.
"""
from django.shortcuts import render


def dashboard(request):
    context = {
        'vitals_summary': [
            {'label': 'Blood pressure', 'value': '128/82 mmHg', 'status': 'watch'},
            {'label': 'Blood sugar (fasting)', 'value': '96 mg/dL', 'status': 'normal'},
            {'label': 'Weight', 'value': '71.4 kg', 'status': 'normal'},
            {'label': 'Resting heart rate', 'value': '104 bpm', 'status': 'high'},
        ],
        'medication_reminders': [
            {'name': 'Metformin 500mg', 'time': '8:00 AM', 'taken': True},
            {'name': 'Amlodipine 5mg', 'time': '9:00 PM', 'taken': False},
        ],
        'upcoming_appointments': [
            {'provider': 'Dr. Anjali Nair', 'specialty': 'General Physician', 'when': 'Fri, 4 Jul - 10:30 AM'},
        ],
        'recommendation': "Your last two blood-pressure readings trended high -- consider a low-sodium diet and "
                           "recheck in 3 days. This suggestion is informational, not a diagnosis.",
        'alerts': [
            {'level': 'warning', 'text': 'Resting heart rate has been above 100 bpm for 2 consecutive readings.'},
        ],
    }
    return render(request, 'health/dashboard.html', context)


def vitals(request):
    context = {
        'entries': [
            {'date': '01 Jul 2026', 'bp': '128/82', 'sugar': '96', 'weight': '71.4', 'hr': '104', 'status': 'watch'},
            {'date': '28 Jun 2026', 'bp': '124/80', 'sugar': '101', 'weight': '71.6', 'hr': '98', 'status': 'normal'},
            {'date': '25 Jun 2026', 'bp': '119/78', 'sugar': '94', 'weight': '71.8', 'hr': '88', 'status': 'normal'},
            {'date': '22 Jun 2026', 'bp': '132/86', 'sugar': '108', 'weight': '72.0', 'hr': '110', 'status': 'high'},
        ],
    }
    return render(request, 'health/vitals.html', context)


def medications(request):
    context = {
        'active': [
            {'name': 'Metformin', 'dose': '500 mg', 'schedule': 'Twice daily, with meals', 'refill_in': '6 days'},
            {'name': 'Amlodipine', 'dose': '5 mg', 'schedule': 'Once daily, night', 'refill_in': '14 days'},
        ],
        'extraction_demo': {
            'raw_text': "Tab. Metform 500mg 1-0-1 x 30 days\nTab. Amlogard 5mg 0-0-1 x 30 days",
            'extracted': [
                {'medicine': 'Metformin', 'dose': '500 mg', 'duration': '30 days', 'confidence': 'High'},
                {'medicine': 'Amlodipine', 'dose': '5 mg', 'duration': '30 days', 'confidence': 'Medium'},
            ],
        },
        'interaction_warning': {
            'drug_a': 'Amlodipine',
            'drug_b': 'Simvastatin',
            'note': 'Concurrent use may increase simvastatin levels -- flagged from db_drug_interactions.csv.',
        },
    }
    return render(request, 'health/medications.html', context)


def lifestyle(request):
    context = {
        'entries': [
            {'date': '01 Jul 2026', 'sleep': '6.5 hrs', 'water': '1.8 L', 'activity': '20 min walk'},
            {'date': '30 Jun 2026', 'sleep': '7.2 hrs', 'water': '2.1 L', 'activity': '35 min walk'},
            {'date': '29 Jun 2026', 'sleep': '5.8 hrs', 'water': '1.4 L', 'activity': 'Rest day'},
        ],
    }
    return render(request, 'health/lifestyle.html', context)


def mental_health(request):
    context = {
        'entries': [
            {'date': '01 Jul 2026', 'mood': 'Calm', 'note': 'Slept well, felt steady through the day.'},
            {'date': '29 Jun 2026', 'mood': 'Stressed', 'note': 'Work deadline, trouble winding down at night.'},
            {'date': '27 Jun 2026', 'mood': 'Good', 'note': 'Long walk with a friend, mood lifted.'},
        ],
    }
    return render(request, 'health/mental_health.html', context)


def share_records(request):
    context = {
        'active_shares': [
            {'with': 'Dr. Anjali Nair', 'scope': 'Vitals + Medications', 'expires': 'in 2 hours', 'code': 'SHC-7F2K9'},
        ],
        'history': [
            {'with': 'Caregiver -- Priya T', 'scope': 'Vitals only', 'action': 'Revoked', 'when': '18 Jun 2026'},
        ],
    }
    return render(request, 'health/share_records.html', context)


def caregiver_dashboard(request):
    context = {
        'patient_name': 'Sreenanda T',
        'linked_since': '12 Jun 2026',
        'vitals_summary': [
            {'label': 'Blood pressure', 'value': '128/82 mmHg', 'status': 'watch'},
            {'label': 'Weight', 'value': '71.4 kg', 'status': 'normal'},
            {'label': 'Resting heart rate', 'value': '104 bpm', 'status': 'high'},
        ],
        'critical_alerts': [
            {'text': 'Missed evening Amlodipine dose on 30 Jun 2026.'},
        ],
        'weekly_summary': "Vitals were mostly stable this week with one high heart-rate reading and one missed "
                           "medication dose. No critical trends detected.",
    }
    return render(request, 'health/caregiver_dashboard.html', context)
