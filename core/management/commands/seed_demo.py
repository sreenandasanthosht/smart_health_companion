"""
Populate the database with realistic demo data.

    python manage.py seed_demo

Creates one account per role, a few weeks of vitals/lifestyle/medication
history, verified and pending providers, appointments, a caregiver link,
consent grants and a nursing assignment -- so every page in the app has
something real to show during a review or demo.

Safe to run more than once: it looks accounts up by email and tops up
missing data rather than duplicating it. Pass --reset to wipe the demo
data first.
"""
import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    CaregiverInvite, CaregiverLink, Notification, TrustedDevice,
)
from adminpanel.models import Announcement, AuditLog, Complaint, PlatformSettings
from health import analytics
from health.models import (
    ConsentGrant, HealthDocument, LifestyleLog, Medication, MedicationDose,
    MoodLog, VitalRecord,
)
from nursing.models import NurseAssignment, NursingVisit
from providers.models import Appointment, HealthEvent, ProviderProfile

User = get_user_model()

PASSWORD = 'CareNest#2026'

PEOPLE = [
    # (email, first, last, role, phone)
    ('latha@example.com', 'Latha', 'Ramesh', User.Role.PATIENT, '+91 98450 11223'),
    ('ramesh@example.com', 'Ramesh', 'Kumar', User.Role.PATIENT, '+91 98450 33445'),
    ('meera@example.com', 'Meera', 'Ramesh', User.Role.CAREGIVER, '+91 98450 55667'),
    ('dr.nair@example.com', 'Anjali', 'Nair', User.Role.PROVIDER, '+91 98450 77889'),
    ('dr.mehta@example.com', 'Rohan', 'Mehta', User.Role.PROVIDER, '+91 98450 99001'),
    ('prakashlab@example.com', 'Prakash', 'Diagnostics', User.Role.PROVIDER, '+91 98450 22114'),
    ('nurse.priya@example.com', 'Priya', 'Suresh', User.Role.NURSE, '+91 98450 44226'),
    ('admin@example.com', 'CareNest', 'Admin', User.Role.ADMIN, '+91 98450 66338'),
    ('staffadmin@example.com', 'Sunil', 'Kamath', User.Role.ADMIN, '+91 98450 66339'),
]

PROVIDER_SETUP = {
    'dr.nair@example.com': dict(
        provider_type=ProviderProfile.ProviderType.DOCTOR, specialty='General Physician',
        years_experience=9, clinic_name='City Care Clinic', address='Indiranagar, Bengaluru',
        registration_number='KMC-2016-44821', verified=True),
    'dr.mehta@example.com': dict(
        provider_type=ProviderProfile.ProviderType.DOCTOR, specialty='Cardiologist',
        years_experience=14, clinic_name='HeartFirst Centre', address='Koramangala, Bengaluru',
        registration_number='KMC-2011-77310', verified=True),
    'prakashlab@example.com': dict(
        provider_type=ProviderProfile.ProviderType.DIAGNOSTIC_LAB, specialty='Pathology & Imaging',
        years_experience=None, clinic_name='Prakash Diagnostics', address='Jayanagar, Bengaluru',
        registration_number='NABL-2019-0233', verified=False),
}


class Command(BaseCommand):
    help = 'Create realistic demo data for every role and page.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete existing demo accounts and their data first.')

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20260731)  # fixed seed -> reproducible demo

        if options['reset']:
            emails = [p[0] for p in PEOPLE]
            User.objects.filter(email__in=emails).delete()
            AuditLog.objects.all().delete()
            self.stdout.write(self.style.WARNING('Existing demo data removed.'))

        users = {}
        for email, first, last, role, phone in PEOPLE:
            user, created = User.objects.get_or_create(
                username=email,
                defaults=dict(email=email, first_name=first, last_name=last,
                              role=role, phone_number=phone),
            )
            if created:
                user.set_password(PASSWORD)
                # Give the demo accounts a filled-in profile.
                user.date_of_birth = datetime.date(1968 + rng.randint(0, 25), rng.randint(1, 12), rng.randint(1, 28))
                user.sex = rng.choice(['F', 'M'])
                user.blood_group = rng.choice(['O+', 'A+', 'B+', 'AB+'])
                user.height_cm = rng.randint(150, 182)
                user.address = 'Bengaluru, Karnataka'
                user.emergency_contact = '+91 98450 00000'
                if role == User.Role.ADMIN:
                    user.is_staff = True
                    # Only the first admin is the Super Admin created
                    # "during system setup", per the Admin Module proposal.
                    # The second is a standard Admin, so the demo shows
                    # what the tier actually restricts.
                    if email == 'admin@example.com':
                        user.is_superuser = True
                        user.is_super_admin = True
                user.save()
            users[email] = user
        self.stdout.write(self.style.SUCCESS(f'{len(users)} accounts ready.'))

        # --- Providers -------------------------------------------------
        for email, setup in PROVIDER_SETUP.items():
            user = users[email]
            profile, _ = ProviderProfile.objects.get_or_create(
                user=user,
                defaults=dict(
                    provider_type=setup['provider_type'], specialty=setup['specialty'],
                    years_experience=setup['years_experience'], clinic_name=setup['clinic_name'],
                    address=setup['address'], registration_number=setup['registration_number'],
                    doc_registration_certificate=True, doc_government_id=True,
                    doc_organization_info=True, doc_address_proof=setup['verified'],
                ),
            )
            if setup['verified'] and not profile.is_verified:
                profile.approve()
                AuditLog.record(users['admin@example.com'], 'Approved provider',
                                profile.display_name(), AuditLog.Tag.OK)
        self.stdout.write(self.style.SUCCESS('Provider profiles ready (2 verified, 1 pending).'))

        # --- Patient health history -----------------------------------
        latha = users['latha@example.com']
        ramesh = users['ramesh@example.com']

        for patient, base_sys, base_dia, base_hr, base_sugar, base_weight in [
            (latha, 134, 86, 96, 118, 71.5),
            (ramesh, 122, 79, 74, 99, 78.0),
        ]:
            if not VitalRecord.objects.filter(patient=patient).exists():
                for days_ago in range(21, -1, -3):
                    drift = rng.randint(-6, 8)
                    VitalRecord.objects.create(
                        patient=patient,
                        recorded_at=timezone.now() - datetime.timedelta(days=days_ago, hours=rng.randint(0, 8)),
                        bp_systolic=base_sys + drift,
                        bp_diastolic=base_dia + rng.randint(-4, 5),
                        heart_rate=base_hr + rng.randint(-6, 12),
                        blood_sugar=round(base_sugar + rng.uniform(-9, 12), 1),
                        weight_kg=round(base_weight + rng.uniform(-0.8, 0.6), 1),
                        source=VitalRecord.Source.SELF,
                        entered_by=patient,
                    )

            if not LifestyleLog.objects.filter(patient=patient).exists():
                for days_ago in range(10, -1, -1):
                    LifestyleLog.objects.create(
                        patient=patient,
                        date=timezone.localdate() - datetime.timedelta(days=days_ago),
                        sleep_hours=round(rng.uniform(5.5, 8.2), 1),
                        water_litres=round(rng.uniform(1.2, 2.6), 1),
                        steps=rng.randint(3200, 11000),
                        activity_note=rng.choice(['30 min walk', 'Rest day', 'Yoga', 'Cycling', 'Gardening']),
                    )

        if not Medication.objects.filter(patient=latha).exists():
            meds = [
                ('Metformin', '500 mg', 'Twice daily, with meals', 9),
                ('Amlodipine', '5 mg', 'Once daily, at night', 16),
            ]
            for name, dose, schedule, refill_in in meds:
                med = Medication.objects.create(
                    patient=latha, name=name, dose=dose, schedule=schedule,
                    start_date=timezone.localdate() - datetime.timedelta(days=60),
                    next_refill_date=timezone.localdate() + datetime.timedelta(days=refill_in),
                )
                for days_ago in range(13, -1, -1):
                    day = timezone.localdate() - datetime.timedelta(days=days_ago)
                    MedicationDose.objects.create(
                        medication=med, date=day,
                        taken=rng.random() > 0.18,
                        taken_at=timezone.now() - datetime.timedelta(days=days_ago),
                    )

        if not Medication.objects.filter(patient=ramesh).exists():
            med = Medication.objects.create(
                patient=ramesh, name='Atorvastatin', dose='10 mg', schedule='Once daily, at night',
                start_date=timezone.localdate() - datetime.timedelta(days=30),
                next_refill_date=timezone.localdate() + datetime.timedelta(days=22),
            )
            for days_ago in range(13, -1, -1):
                MedicationDose.objects.create(
                    medication=med, date=timezone.localdate() - datetime.timedelta(days=days_ago),
                    taken=rng.random() > 0.05,
                    taken_at=timezone.now() - datetime.timedelta(days=days_ago))

        if not MoodLog.objects.filter(patient=latha).exists():
            for days_ago, mood, note in [
                (0, 'Calm', 'Slept well, felt steady through the day.'),
                (2, 'Stressed', 'Worried about the BP readings.'),
                (5, 'Good', 'Long walk with Meera, mood lifted.'),
                (8, 'Low', 'Tired, did not feel like doing much.'),
            ]:
                MoodLog.objects.create(
                    patient=latha, date=timezone.localdate() - datetime.timedelta(days=days_ago),
                    mood=mood, note=note)
        self.stdout.write(self.style.SUCCESS('Vitals, medicines, lifestyle and mood history created.'))

        # --- Caregiver link + consent ----------------------------------
        meera = users['meera@example.com']
        link, created = CaregiverLink.objects.get_or_create(
            patient=latha, caregiver=meera,
            defaults=dict(relationship='Daughter', status=CaregiverLink.Status.APPROVED,
                          decided_at=timezone.now()),
        )
        if not ConsentGrant.objects.filter(patient=latha, recipient=meera, revoked_at__isnull=True).exists():
            # The everyday categories, matching what approving a link grants.
            # The restricted ones stay off so the demo shows the distinction.
            ConsentGrant.objects.create(
                patient=latha, recipient=meera,
                scope_vitals=True, scope_medications=True, scope_appointments=True,
                scope_alerts=True, scope_emergency=True, scope_lifestyle=True,
                action_context='Caregiver monitoring')
            AuditLog.record(latha, 'Approved a caregiver link', meera.display_name, AuditLog.Tag.OK)

        # A device Meera signed in from that Latha hasn't confirmed yet, so
        # the new-device approval queue isn't empty in the demo.
        if not TrustedDevice.objects.filter(user=meera).exists():
            TrustedDevice.objects.create(
                user=meera, patient=latha, token=TrustedDevice.new_token(),
                label='Chrome on Android', status=TrustedDevice.Status.PENDING)
            Notification.send(
                latha, title=f'New sign-in by {meera.display_name}',
                body='Chrome on Android tried to open your caregiver view.',
                kind=Notification.Kind.DEVICE_APPROVAL,
                level=Notification.Level.WARNING,
                action_url_name='health_caregiver_requests')

        # An unused invite code the patient can hand out.
        if not CaregiverInvite.objects.filter(patient=latha).exists():
            CaregiverInvite.objects.create(
                patient=latha, label='For my son Rahul',
                expires_at=timezone.now() + datetime.timedelta(days=7))

        # A couple of documents, to show the restricted categories have
        # something behind them.
        if not HealthDocument.objects.filter(patient=latha).exists():
            HealthDocument.objects.create(
                patient=latha, title='Lipid profile', kind=HealthDocument.Kind.LAB,
                note='Fasting sample', issued_on=timezone.localdate() - datetime.timedelta(days=21))
            HealthDocument.objects.create(
                patient=latha, title='Cardiology consult summary',
                kind=HealthDocument.Kind.REPORT,
                issued_on=timezone.localdate() - datetime.timedelta(days=40))

        # A time-boxed share with a provider, plus one already revoked.
        nair = users['dr.nair@example.com']
        if not ConsentGrant.objects.filter(patient=latha, recipient=nair).exists():
            ConsentGrant.objects.create(
                patient=latha, recipient=nair, scope_vitals=True, scope_medications=True,
                expires_at=timezone.now() + datetime.timedelta(hours=24),
                action_context='Pre-visit snapshot')
            AuditLog.record(latha, 'Granted a record share',
                            f"{nair.display_name} -- Vitals + Medications", AuditLog.Tag.OK)

            revoked = ConsentGrant.objects.create(
                patient=latha, recipient=users['dr.mehta@example.com'],
                scope_vitals=True, action_context='Second opinion')
            revoked.revoke()
            AuditLog.record(latha, 'Revoked a record share',
                            f"{users['dr.mehta@example.com'].display_name} -- Vitals", AuditLog.Tag.WARN)
        self.stdout.write(self.style.SUCCESS('Caregiver link and consent grants created.'))

        # --- Appointments ----------------------------------------------
        nair_profile = ProviderProfile.objects.get(user=nair)
        mehta_profile = ProviderProfile.objects.get(user=users['dr.mehta@example.com'])
        if not Appointment.objects.exists():
            Appointment.objects.create(
                patient=latha, provider=nair_profile,
                scheduled_for=timezone.now() + datetime.timedelta(days=2, hours=3),
                reason='Follow-up on blood pressure', status=Appointment.Status.CONFIRMED)
            Appointment.objects.create(
                patient=ramesh, provider=nair_profile,
                scheduled_for=timezone.now() + datetime.timedelta(days=4),
                reason='General check-up', status=Appointment.Status.REQUESTED)
            Appointment.objects.create(
                patient=latha, provider=mehta_profile,
                scheduled_for=timezone.now() - datetime.timedelta(days=20),
                reason='Cardiology review', status=Appointment.Status.COMPLETED,
                provider_note='ECG normal. Continue current medication and recheck in 3 months.')
        self.stdout.write(self.style.SUCCESS('Appointments created.'))

        # --- Nursing ----------------------------------------------------
        nurse = users['nurse.priya@example.com']
        assignment, _ = NurseAssignment.objects.get_or_create(
            nurse=nurse, patient=latha,
            defaults=dict(assigned_by=users['admin@example.com'],
                          start_date=timezone.localdate() - datetime.timedelta(days=14),
                          notes='Weekly home visits for BP monitoring'),
        )
        if not NursingVisit.objects.filter(nurse=nurse).exists():
            visit_vital = VitalRecord.objects.create(
                patient=latha, recorded_at=timezone.now() - datetime.timedelta(days=4),
                bp_systolic=146, bp_diastolic=92, heart_rate=88, blood_sugar=124, weight_kg=71.4,
                source=VitalRecord.Source.NURSE, entered_by=nurse)
            NursingVisit.objects.create(
                nurse=nurse, patient=latha,
                visited_at=timezone.now() - datetime.timedelta(days=4),
                notes='Patient reported headaches. BP elevated at time of visit.',
                medications_administered='None administered',
                vitals=visit_vital, escalated=True,
                severity=NursingVisit.Severity.URGENT,
                escalation_reason='BP 146/92 with headache -- needs provider review')
            AuditLog.record(nurse, 'Raised a nursing escalation',
                            f"{latha.display_name} -- BP 146/92 with headache", AuditLog.Tag.DANGER)
            NursingVisit.objects.create(
                nurse=nurse, patient=latha,
                visited_at=timezone.now() - datetime.timedelta(days=11),
                notes='Routine check. Patient comfortable, medicines taken as prescribed.')
        self.stdout.write(self.style.SUCCESS('Nursing assignment and visits created.'))

        # --- Health camps & wellness events ------------------------------
        # One of each status, so the approval queue and the public listing
        # both have something to show.
        nair_profile = ProviderProfile.objects.get(user=users['dr.nair@example.com'])
        lab_profile = ProviderProfile.objects.get(user=users['prakashlab@example.com'])
        if not HealthEvent.objects.exists():
            HealthEvent.objects.create(
                provider=nair_profile, title='Free blood pressure screening camp',
                kind=HealthEvent.Kind.SCREENING,
                description='Walk-in BP and blood sugar checks. No appointment needed.',
                venue='Community Hall, Jayanagar, Bengaluru',
                starts_at=timezone.now() + datetime.timedelta(days=9),
                capacity=120, is_free=True,
                status=HealthEvent.Status.APPROVED,
                reviewed_by=users['admin@example.com'], reviewed_at=timezone.now())
            HealthEvent.objects.create(
                provider=lab_profile, title='Diabetes awareness workshop',
                kind=HealthEvent.Kind.AWARENESS,
                description='Diet, exercise and monitoring for newly diagnosed patients.',
                venue='Prakash Diagnostics, Indiranagar',
                starts_at=timezone.now() + datetime.timedelta(days=16),
                capacity=40, is_free=True)  # left PENDING for the admin queue
            HealthEvent.objects.create(
                provider=nair_profile, title='Weekend wellness retreat',
                kind=HealthEvent.Kind.WELLNESS,
                description='Two-day residential programme.',
                venue='Nandi Hills',
                starts_at=timezone.now() + datetime.timedelta(days=30),
                is_free=False,
                status=HealthEvent.Status.REJECTED,
                review_note='Residential events are outside platform scope for now.',
                reviewed_by=users['admin@example.com'], reviewed_at=timezone.now())

        # --- Complaints ---------------------------------------------------
        if not Complaint.objects.exists():
            Complaint.objects.create(
                reporter=latha, against_user=users['dr.mehta@example.com'],
                category=Complaint.Category.PROVIDER,
                subject='Appointment started 40 minutes late',
                description='Booked for 10:00, was seen at 10:40 with no explanation.')
            Complaint.objects.create(
                reporter=ramesh, category=Complaint.Category.TECHNICAL,
                subject='Vitals chart not loading on mobile',
                description='The trend line is blank on my phone but fine on a laptop.',
                status=Complaint.Status.IN_REVIEW, handled_by=users['admin@example.com'])
            Complaint.objects.create(
                reporter=latha, category=Complaint.Category.PRIVACY,
                subject='Wanted to check who can see my records',
                description='Asked for confirmation that my mood log is not shared.',
                status=Complaint.Status.RESOLVED,
                resolution_note='Confirmed: mental-health entries are never shareable.',
                handled_by=users['admin@example.com'], resolved_at=timezone.now())

        # --- Announcements ------------------------------------------------
        if not Announcement.objects.exists():
            published = Announcement.objects.create(
                author=users['admin@example.com'],
                title='Scheduled maintenance this Sunday',
                body='CareNest will be unavailable from 02:00 to 04:00 IST on Sunday for '
                     'planned maintenance. Your data is unaffected.',
                audience=Announcement.Audience.ALL)
            published.publish()
            Announcement.objects.create(
                author=users['admin@example.com'],
                title='New verification documents required',
                body='From next month, providers must upload a current address proof.',
                audience=Announcement.Audience.PROVIDERS)  # left as a draft

        PlatformSettings.load()
        self.stdout.write(self.style.SUCCESS('Events, complaints and announcements created.'))

        # --- Generate insights so dashboards are populated --------------
        for patient in (latha, ramesh):
            analytics.generate_insights(patient)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Demo data ready. Log in with any of these:'))
        self.stdout.write('')
        for email, first, last, role, _phone in PEOPLE:
            label = User.Role(role).label
            if role == User.Role.ADMIN and email == 'admin@example.com':
                label = 'Super Admin'
            self.stdout.write(f"  {label:<11} {email:<28} password: {PASSWORD}")
        self.stdout.write('')
        self.stdout.write('admin@example.com is the Super Admin (and a Django superuser, so /admin/ works).')
        self.stdout.write('staffadmin@example.com is a standard Admin -- no Admin Management or Settings.')
