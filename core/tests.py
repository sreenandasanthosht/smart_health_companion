"""
End-to-end smoke tests for CareNest.

These walk the real flows a marker or reviewer would: register, log in,
save data, and open every page as each role. If any page 500s, or role
gating breaks, or the consent rules leak data, these fail.

Run with:  python manage.py test
"""
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CaregiverLink
from health.models import (
    ConsentGrant, ExtractionJob, LifestyleLog, Medication, MedicationDose,
    MoodLog, VitalRecord,
)
from nursing.models import NurseAssignment, NursingVisit
from providers.models import Appointment, CarePlan, ProviderAvailability, ProviderProfile
from adminpanel.models import AuditLog

User = get_user_model()
PW = 'TestPass#2026'


def make(email, role, **extra):
    return User.objects.create_user(
        username=email, email=email, password=PW, role=role,
        first_name=email.split('@')[0].title(), **extra)


class RegistrationFlowTests(TestCase):
    def test_patient_registers_and_lands_on_dashboard(self):
        resp = self.client.post(reverse('register'), {
            'full_name': 'Asha Menon', 'email': 'asha@example.com',
            'phone_number': '+91 98450 10101', 'role': 'PATIENT',
            'password': PW, 'confirm_password': PW,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email='asha@example.com')
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertEqual(user.phone_number, '+91 98450 10101')
        self.assertTrue(user.unique_id)
        # Patients skip the wizard entirely.
        self.assertEqual(resp.redirect_chain[-1][0], reverse('health_dashboard'))

    def test_caregiver_registration_links_to_patient_by_id(self):
        patient = make('pat@example.com', User.Role.PATIENT)
        self.client.post(reverse('register'), {
            'full_name': 'Care Giver', 'email': 'cg@example.com',
            'phone_number': '+91 1', 'role': 'CAREGIVER',
            'caregiver_patient_ref': patient.unique_id,
            'password': PW, 'confirm_password': PW,
        })
        link = CaregiverLink.objects.get(caregiver__email='cg@example.com')
        self.assertEqual(link.patient, patient)
        self.assertEqual(link.status, CaregiverLink.Status.PENDING)

    def test_provider_registration_creates_pending_profile(self):
        self.client.post(reverse('register'), {
            'full_name': 'Doc Tor', 'email': 'doc@example.com',
            'phone_number': '+91 2', 'role': 'PROVIDER',
            'provider_type': 'CLINIC',
            'password': PW, 'confirm_password': PW,
        })
        profile = ProviderProfile.objects.get(user__email='doc@example.com')
        self.assertEqual(profile.verification_status, ProviderProfile.Verification.PENDING)

    def test_cannot_self_register_as_admin_or_nurse(self):
        for role in ('ADMIN', 'NURSE'):
            self.client.post(reverse('register'), {
                'full_name': 'Sneaky Person', 'email': f'{role.lower()}@example.com',
                'phone_number': '+91 3', 'role': role,
                'password': PW, 'confirm_password': PW,
            })
            self.assertFalse(User.objects.filter(email=f'{role.lower()}@example.com').exists(),
                             f'{role} should not be self-registerable')

    def test_login_routes_each_role_to_its_own_dashboard(self):
        expected = {
            User.Role.PATIENT: reverse('health_dashboard'),
            User.Role.CAREGIVER: reverse('health_caregiver_dashboard'),
            User.Role.ADMIN: reverse('admin_dashboard'),
            User.Role.NURSE: reverse('nurse_dashboard'),
        }
        for role, target in expected.items():
            email = f'{role.lower()}route@example.com'
            make(email, role)
            resp = self.client.post(reverse('login'), {'email': email, 'password': PW})
            self.assertRedirects(resp, target, fetch_redirect_response=False)
            self.client.logout()

    def test_login_works_when_username_differs_from_email(self):
        # createsuperuser lets username and email diverge. Such an account
        # must still be able to sign in with its email address.
        u = User.objects.create_user(
            username='admin', email='admin.shc@email.com', password=PW,
            role=User.Role.ADMIN)
        resp = self.client.post(reverse('login'),
                                {'email': 'admin.shc@email.com', 'password': PW})
        self.assertRedirects(resp, reverse('admin_dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), u.pk)

    def test_login_is_case_insensitive_on_email(self):
        make('MixedCase@Example.com', User.Role.PATIENT)
        resp = self.client.post(reverse('login'),
                                {'email': 'mixedcase@example.com', 'password': PW})
        self.assertRedirects(resp, reverse('health_dashboard'), fetch_redirect_response=False)

    def test_suspended_user_cannot_log_in(self):
        make('susp@example.com', User.Role.PATIENT, is_suspended=True)
        resp = self.client.post(reverse('login'), {'email': 'susp@example.com', 'password': PW})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'suspended')


class PatientDataTests(TestCase):
    def setUp(self):
        self.patient = make('p@example.com', User.Role.PATIENT)
        self.client.force_login(self.patient)

    def test_saving_vitals_creates_row_and_flags_status(self):
        self.client.post(reverse('health_vitals'), {
            'bp': '152/96', 'blood_sugar': '140', 'weight_kg': '70.5', 'heart_rate': '112'})
        record = VitalRecord.objects.get(patient=self.patient)
        self.assertEqual(record.bp_systolic, 152)
        self.assertEqual(record.status, VitalRecord.Status.HIGH)
        self.assertEqual(record.source, VitalRecord.Source.SELF)

    def test_normal_reading_is_flagged_normal(self):
        self.client.post(reverse('health_vitals'), {'bp': '118/76', 'heart_rate': '70'})
        self.assertEqual(VitalRecord.objects.get(patient=self.patient).status,
                         VitalRecord.Status.NORMAL)

    def test_malformed_blood_pressure_is_rejected_not_crashed(self):
        resp = self.client.post(reverse('health_vitals'), {'bp': 'abc'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(VitalRecord.objects.count(), 0)

    def test_adding_medicine_and_ticking_a_dose(self):
        self.client.post(reverse('health_medications'), {
            'action': 'add', 'name': 'Metformin', 'dose': '500 mg',
            'schedule': 'Twice daily', 'start_date': timezone.localdate().isoformat()})
        med = Medication.objects.get(patient=self.patient)
        self.client.get(reverse('health_medications'))  # creates today's dose row
        dose = MedicationDose.objects.get(medication=med, date=timezone.localdate())
        self.assertFalse(dose.taken)
        self.client.post(reverse('health_medications'), {'action': 'toggle_dose', 'dose_id': dose.id})
        dose.refresh_from_db()
        self.assertTrue(dose.taken)

    def test_lifestyle_log_updates_rather_than_duplicating(self):
        for water in ('1.5', '2.2'):
            self.client.post(reverse('health_lifestyle'), {
                'date': timezone.localdate().isoformat(), 'sleep_hours': '7',
                'water_litres': water, 'steps': '8000', 'activity_note': 'Walk'})
        self.assertEqual(LifestyleLog.objects.filter(patient=self.patient).count(), 1)
        self.assertEqual(float(LifestyleLog.objects.get(patient=self.patient).water_litres), 2.2)

    def test_mood_entry_saves(self):
        self.client.post(reverse('health_mental_health'), {'mood': 'Calm', 'note': 'Steady day'})
        self.assertEqual(MoodLog.objects.filter(patient=self.patient).count(), 1)

    def test_dashboard_renders_with_no_data_at_all(self):
        self.assertEqual(self.client.get(reverse('health_dashboard')).status_code, 200)

    def test_dashboard_renders_with_data_and_flags_high_bp(self):
        VitalRecord.objects.create(patient=self.patient, bp_systolic=145, bp_diastolic=95, heart_rate=105)
        VitalRecord.objects.create(patient=self.patient, bp_systolic=142, bp_diastolic=91, heart_rate=103)
        resp = self.client.get(reverse('health_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.patient.insights.filter(level='CRITICAL').exists())


class ConsentTests(TestCase):
    def setUp(self):
        self.patient = make('cp@example.com', User.Role.PATIENT)
        self.caregiver = make('cc@example.com', User.Role.CAREGIVER)
        CaregiverLink.objects.create(
            patient=self.patient, caregiver=self.caregiver,
            status=CaregiverLink.Status.APPROVED, decided_at=timezone.now())
        VitalRecord.objects.create(patient=self.patient, bp_systolic=120, bp_diastolic=80, heart_rate=70)

    def test_caregiver_sees_nothing_without_a_consent_grant(self):
        self.client.force_login(self.caregiver)
        resp = self.client.get(reverse('health_caregiver_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['can_see_vitals'])

    def test_caregiver_sees_vitals_once_granted(self):
        ConsentGrant.objects.create(patient=self.patient, recipient=self.caregiver, scope_vitals=True)
        self.client.force_login(self.caregiver)
        self.assertTrue(self.client.get(reverse('health_caregiver_dashboard')).context['can_see_vitals'])

    def test_revoking_cuts_access_immediately(self):
        grant = ConsentGrant.objects.create(patient=self.patient, recipient=self.caregiver, scope_vitals=True)
        self.client.force_login(self.patient)
        self.client.post(reverse('health_share'), {'action': 'revoke', 'grant_id': grant.id})
        grant.refresh_from_db()
        self.assertIsNotNone(grant.revoked_at)
        self.client.force_login(self.caregiver)
        self.assertFalse(self.client.get(reverse('health_caregiver_dashboard')).context['can_see_vitals'])

    def test_expired_grant_is_not_active(self):
        grant = ConsentGrant.objects.create(
            patient=self.patient, recipient=self.caregiver, scope_vitals=True,
            expires_at=timezone.now() - datetime.timedelta(hours=1))
        self.assertFalse(grant.is_active())

    def test_mental_health_is_never_shareable(self):
        # There is no scope that grants mood data, and the caregiver view
        # must never expose it even with every other scope granted.
        MoodLog.objects.create(patient=self.patient, mood='Low', note='Private note text')
        ConsentGrant.objects.create(
            patient=self.patient, recipient=self.caregiver, scope_vitals=True,
            scope_medications=True, scope_records=True, scope_lifestyle=True)
        self.client.force_login(self.caregiver)
        resp = self.client.get(reverse('health_caregiver_dashboard'))
        self.assertNotContains(resp, 'Private note text')

    def test_patient_approving_caregiver_creates_the_grant(self):
        other = make('cg2@example.com', User.Role.CAREGIVER)
        link = CaregiverLink.objects.create(patient=self.patient, caregiver=other)
        self.client.force_login(self.patient)
        self.client.post(reverse('health_caregiver_requests'),
                         {'link_id': link.id, 'decision': 'approve'})
        link.refresh_from_db()
        self.assertEqual(link.status, CaregiverLink.Status.APPROVED)
        self.assertTrue(ConsentGrant.objects.filter(patient=self.patient, recipient=other).exists())


class MentalHealthCalendarTests(TestCase):
    """The mood journal's calendar view -- month grid, navigation, and the
    no-emoji requirement (a past version of this page used emoji per-mood
    icons; this guards against that regressing back in)."""

    def setUp(self):
        self.patient = make('cal-patient@example.com', User.Role.PATIENT)
        self.client.force_login(self.patient)

    def test_calendar_marks_a_logged_day_with_its_mood_colour(self):
        today = timezone.localdate()
        MoodLog.objects.create(patient=self.patient, date=today, mood='Calm', note='')
        resp = self.client.get(reverse('health_mental_health'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'cal-mood-dot')
        self.assertContains(resp, '#0d9488')  # Calm's colour

    def test_calendar_handles_an_invalid_month_param_without_crashing(self):
        resp = self.client.get(reverse('health_mental_health'), {'month': 'not-a-month'})
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get(reverse('health_mental_health'), {'month': '2026-13'})
        self.assertEqual(resp2.status_code, 200)

    def test_month_navigation_links_are_present(self):
        resp = self.client.get(reverse('health_mental_health'))
        self.assertContains(resp, '?month=')

    def test_page_never_renders_an_emoji_character(self):
        MoodLog.objects.create(patient=self.patient, mood='Anxious', note='a note')
        resp = self.client.get(reverse('health_mental_health'))
        content = resp.content.decode()
        self.assertFalse(any(ord(ch) >= 0x1F000 for ch in content))


class ProviderFlowTests(TestCase):
    def setUp(self):
        self.patient = make('pp@example.com', User.Role.PATIENT)
        self.provider = make('pv@example.com', User.Role.PROVIDER)
        self.profile = ProviderProfile.objects.create(
            user=self.provider, provider_type=ProviderProfile.ProviderType.CLINIC,
            specialty='General Physician', clinic_name='Test Clinic')
        self.admin = make('ad@example.com', User.Role.ADMIN)

    def test_unverified_provider_is_hidden_from_directory(self):
        self.client.force_login(self.patient)
        self.assertEqual(len(self.client.get(reverse('provider_directory')).context['providers']), 0)

    def test_admin_approval_puts_provider_in_directory(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_verification'),
                         {'profile_id': self.profile.id, 'action': 'approve'})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_verified)
        self.client.force_login(self.patient)
        self.assertEqual(len(self.client.get(reverse('provider_directory')).context['providers']), 1)

    def test_booking_and_provider_accepting(self):
        self.profile.approve()
        self.client.force_login(self.patient)
        when = timezone.localdate() + datetime.timedelta(days=3)
        self.client.post(reverse('provider_appointments'), {
            'action': 'book', 'provider': self.profile.id,
            'date': when.isoformat(), 'time': '10:30', 'reason': 'Check-up'})
        appt = Appointment.objects.get()
        self.assertEqual(appt.status, Appointment.Status.REQUESTED)

        self.client.force_login(self.provider)
        self.client.post(reverse('provider_dashboard'),
                         {'appointment_id': appt.id, 'action': 'accept'})
        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.CONFIRMED)

    def test_booking_in_the_past_is_rejected(self):
        self.profile.approve()
        self.client.force_login(self.patient)
        past = timezone.localdate() - datetime.timedelta(days=1)
        self.client.post(reverse('provider_appointments'), {
            'action': 'book', 'provider': self.profile.id,
            'date': past.isoformat(), 'time': '10:30'})
        self.assertEqual(Appointment.objects.count(), 0)

    def test_unverified_provider_is_sent_to_the_pending_page(self):
        self.client.force_login(self.provider)
        self.assertRedirects(self.client.get(reverse('provider_dashboard')), reverse('provider_pending'))


class NursingTests(TestCase):
    def setUp(self):
        self.patient = make('np@example.com', User.Role.PATIENT)
        self.nurse = make('nn@example.com', User.Role.NURSE)
        NurseAssignment.objects.create(nurse=self.nurse, patient=self.patient)
        self.client.force_login(self.nurse)

    def test_nurse_logs_a_visit_with_vitals_tagged_as_nurse_entered(self):
        self.client.post(reverse('nurse_log_visit', args=[self.patient.id]), {
            'bp': '146/92', 'heart_rate': '88', 'notes': 'Headache reported',
            'escalated': 'on', 'escalation_reason': 'High BP with headache'})
        visit = NursingVisit.objects.get()
        self.assertTrue(visit.escalated)
        self.assertEqual(visit.severity, NursingVisit.Severity.URGENT)
        vital = VitalRecord.objects.get(patient=self.patient)
        self.assertEqual(vital.source, VitalRecord.Source.NURSE)
        self.assertEqual(vital.entered_by, self.nurse)
        self.assertEqual(vital.status, VitalRecord.Status.HIGH)

    def test_nurse_cannot_open_a_patient_they_are_not_assigned_to(self):
        stranger = make('stranger@example.com', User.Role.PATIENT)
        self.assertEqual(self.client.get(reverse('nurse_patient_detail', args=[stranger.id])).status_code, 404)


class AccessControlTests(TestCase):
    """A user of one role must not be able to open another role's pages."""

    def setUp(self):
        self.patient = make('acp@example.com', User.Role.PATIENT)
        self.provider = make('acv@example.com', User.Role.PROVIDER)
        self.admin = make('aca@example.com', User.Role.ADMIN)
        self.nurse = make('acn@example.com', User.Role.NURSE)

    def test_patient_blocked_from_admin_provider_and_nurse_pages(self):
        self.client.force_login(self.patient)
        for name in ('admin_dashboard', 'admin_users', 'admin_verification',
                     'admin_audit_log', 'admin_nursing', 'provider_dashboard', 'nurse_dashboard'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302,
                             f'{name} should redirect a patient away')

    def test_provider_blocked_from_patient_pages(self):
        self.client.force_login(self.provider)
        for name in ('health_dashboard', 'health_vitals', 'health_share'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_anonymous_visitor_is_sent_to_login(self):
        for name in ('health_dashboard', 'admin_dashboard', 'nurse_dashboard', 'provider_dashboard'):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/accounts/login/', resp.url)

    def test_admin_can_suspend_and_reinstate(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_users'), {'user_id': self.patient.id, 'action': 'suspend'})
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.is_suspended)
        self.client.post(reverse('admin_users'), {'user_id': self.patient.id, 'action': 'reinstate'})
        self.patient.refresh_from_db()
        self.assertFalse(self.patient.is_suspended)

    def test_admin_cannot_suspend_themselves(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_users'), {'user_id': self.admin.id, 'action': 'suspend'})
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_suspended)


class EveryPageRendersTests(TestCase):
    """Open every page as the role that owns it and assert a clean 200."""

    def test_public_pages(self):
        for name in ('home', 'login', 'register'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_patient_pages(self):
        self.client.force_login(make('epp@example.com', User.Role.PATIENT))
        for name in ('health_dashboard', 'health_vitals', 'health_medications',
                     'health_lifestyle', 'health_mental_health', 'health_share',
                     'health_caregiver_requests', 'provider_directory',
                     'provider_appointments', 'profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{name} failed')

    def test_caregiver_pages(self):
        self.client.force_login(make('epc@example.com', User.Role.CAREGIVER))
        for name in ('health_caregiver_dashboard', 'provider_directory', 'profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{name} failed')

    def test_provider_pages(self):
        provider = make('epv@example.com', User.Role.PROVIDER)
        profile = ProviderProfile.objects.create(
            user=provider, provider_type=ProviderProfile.ProviderType.CLINIC)
        profile.approve()
        self.client.force_login(provider)
        for name in ('provider_dashboard', 'provider_pending', 'profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{name} failed')

    def test_nurse_pages(self):
        self.client.force_login(make('epn@example.com', User.Role.NURSE))
        for name in ('nurse_dashboard', 'nurse_visits', 'profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{name} failed')

    def test_admin_pages(self):
        self.client.force_login(make('epa@example.com', User.Role.ADMIN))
        for name in ('admin_dashboard', 'admin_verification', 'admin_users',
                     'admin_providers', 'admin_audit_log', 'admin_nursing', 'profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{name} failed')


class SeedCommandTests(TestCase):
    def test_seed_demo_runs_and_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command
        call_command('seed_demo', stdout=StringIO())
        first = User.objects.count()
        self.assertGreater(first, 0)
        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(User.objects.count(), first, 'seed_demo should not duplicate accounts')


class ExtractionTests(TestCase):
    """
    Prescription extraction, including the privacy guarantee.

    OCR is stubbed so these tests do not need Tesseract installed and do not
    depend on image recognition quality. What they verify is the pipeline:
    consent gating, the parser, the verify-then-save flow, and above all that
    no uploaded file survives the request.
    """

    def setUp(self):
        self.patient = make('rx@example.com', User.Role.PATIENT)
        self.client.force_login(self.patient)
        self.sample_text = (
            'Dr. A Nair, City Care Clinic\n'
            'Tab. Metformin 500mg 1-0-1 x 30 days\n'
            'Cap. Amlodipine 5mg OD x 30 days\n'
            'Follow up after 1 month\n'
        )

    def _upload(self, consent=True, name='rx.jpg', content=b'\xff\xd8\xff\xe0fakejpeg'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = {'document': SimpleUploadedFile(name, content, content_type='image/jpeg'),
                'source_type': 'PRESCRIPTION'}
        if consent:
            data['consent'] = '1'
        return self.client.post(reverse('health_prescription_upload'), data, follow=True)

    # --- the privacy guarantee -------------------------------------------

    def test_uploaded_file_is_never_written_to_disk(self):
        """Walk the project tree before and after; no new file may appear."""
        import os
        from unittest.mock import patch

        root = settings.BASE_DIR

        def snapshot():
            found = set()
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames
                               if d not in {'venv', '.venv', '__pycache__', '.git', 'node_modules'}]
                for fn in filenames:
                    found.add(os.path.join(dirpath, fn))
            return found

        before = snapshot()
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        after = snapshot()

        new_files = {f for f in after - before if not f.endswith(('.pyc', '.log'))}
        self.assertEqual(new_files, set(),
                         f'Upload left files behind: {new_files}')

    def test_job_records_that_the_file_was_released(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        job = ExtractionJob.objects.get(patient=self.patient)
        self.assertIsNotNone(job.file_deleted_at)
        self.assertEqual(job.original_filename, 'rx.jpg')

    def test_settings_force_uploads_to_stay_in_memory(self):
        # If this ever changes, large uploads silently start hitting disk and
        # the process-and-discard claim quietly becomes false.
        self.assertEqual(settings.FILE_UPLOAD_HANDLERS,
                         ['django.core.files.uploadhandler.MemoryFileUploadHandler'])

    # --- consent gating ---------------------------------------------------

    def test_upload_without_consent_is_rejected_and_nothing_is_processed(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text') as ocr:
            self._upload(consent=False)
            ocr.assert_not_called()
        self.assertEqual(ExtractionJob.objects.count(), 0)

    def test_refused_consent_is_written_to_the_audit_log(self):
        from adminpanel.models import AuditLog
        self._upload(consent=False)
        self.assertTrue(AuditLog.objects.filter(action__icontains='Refused consent').exists())

    # --- parsing ----------------------------------------------------------

    def test_rule_based_parser_reads_a_typical_prescription(self):
        from health.extraction import parse_medications_rules
        items = parse_medications_rules(self.sample_text)
        names = {i['name'].lower() for i in items}
        self.assertIn('metformin', names)
        self.assertIn('amlodipine', names)
        # Clinic and follow-up lines must not be mistaken for medicines.
        self.assertNotIn('city care clinic', names)
        metformin = next(i for i in items if i['name'].lower() == 'metformin')
        self.assertEqual(metformin['dose'].replace(' ', ''), '500mg')
        self.assertEqual(metformin['frequency'], 'Morning and night')
        self.assertGreaterEqual(metformin['confidence'], 0.8)

    def test_rule_based_parser_reads_a_numbered_indian_style_prescription(self):
        """
        Regression test for a real upload that returned 0 medicines.

        Two things about this format previously broke the parser: (1) each
        medicine line starts with a list number ("1)", "2)") which sat in
        front of "TAB." and defeated the anchored form-prefix match, and
        (2) frequency was written in plain words ("1 Morning", "4 Morning,
        1 Night") rather than a coded notation like OD/BD/1-0-1.
        """
        from health.extraction import parse_medications_rules
        text = (
            "'Medicine Name: Dosage 'Duration\n"
            "1) TAB. ABCOINA 1 Morning 8 bays\n"
            "(Tot8 Tab)\n"
            "2) TAB. VOMIAST 4 Morning, 1 Night 'Days\n"
        )
        items = parse_medications_rules(text)
        names = {i['name'].lower() for i in items}
        self.assertIn('abcoina', names)
        self.assertIn('vomiast', names)
        abcoina = next(i for i in items if i['name'].lower() == 'abcoina')
        self.assertEqual(abcoina['frequency'], '1 Morning')
        self.assertIn('8', abcoina['duration'])

    def test_parser_falls_back_to_rules_when_the_llm_fails(self):
        from unittest.mock import patch
        from health import extraction
        with patch.object(extraction, 'llm_available', return_value=True), \
             patch.object(extraction, 'parse_medications_llm',
                          side_effect=extraction.ExtractionError('boom')):
            items, parser, note = extraction.parse_medications(self.sample_text)
        self.assertEqual(parser, 'RULES')
        self.assertIn('boom', note)
        self.assertTrue(items, 'fallback should still return medicines')

    def test_parser_is_recorded_on_the_job(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        job = ExtractionJob.objects.get(patient=self.patient)
        self.assertIn(job.parser_used, {'LLM', 'RULES'})

    # --- verify-then-save flow -------------------------------------------

    def test_nothing_is_added_to_medicines_until_confirmed(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        self.assertEqual(Medication.objects.filter(patient=self.patient).count(), 0)

    def test_confirming_creates_medicines_and_clears_the_text(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        job = ExtractionJob.objects.get(patient=self.patient)
        self.assertTrue(job.raw_text)
        post = {'action': 'confirm'}
        for item in job.medications.all():
            post[f'keep_{item.id}'] = '1'
            post[f'name_{item.id}'] = item.name
            post[f'dose_{item.id}'] = item.dose
            post[f'frequency_{item.id}'] = item.frequency
        self.client.post(reverse('health_extraction_verify', args=[job.id]), post)
        job.refresh_from_db()
        self.assertEqual(job.status, ExtractionJob.Status.CONFIRMED)
        self.assertEqual(job.raw_text, '', 'transcribed text should be cleared on confirm')
        self.assertGreater(Medication.objects.filter(patient=self.patient).count(), 0)

    def test_discarding_saves_nothing_and_clears_the_text(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        job = ExtractionJob.objects.get(patient=self.patient)
        self.client.post(reverse('health_extraction_verify', args=[job.id]), {'action': 'discard'})
        job.refresh_from_db()
        self.assertEqual(job.status, ExtractionJob.Status.DISCARDED)
        self.assertEqual(job.raw_text, '')
        self.assertEqual(Medication.objects.filter(patient=self.patient).count(), 0)

    # --- isolation and failure handling ----------------------------------

    def test_a_patient_cannot_open_another_patients_extraction(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=(self.sample_text, 88.0)):
            self._upload()
        job = ExtractionJob.objects.get(patient=self.patient)
        other = make('nosy@example.com', User.Role.PATIENT)
        self.client.force_login(other)
        resp = self.client.get(reverse('health_extraction_verify', args=[job.id]))
        self.assertEqual(resp.status_code, 404)

    def test_unreadable_image_fails_gracefully(self):
        resp = self._upload(content=b'not an image at all')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Medication.objects.filter(patient=self.patient).count(), 0)

    def test_blank_ocr_result_is_reported_not_crashed(self):
        from unittest.mock import patch
        with patch('health.extraction.extract_text', return_value=('', 0.0)):
            resp = self._upload()
        self.assertEqual(resp.status_code, 200)
        job = ExtractionJob.objects.get(patient=self.patient)
        self.assertEqual(job.status, ExtractionJob.Status.FAILED)

    def test_oversized_upload_is_rejected(self):
        from health.extraction import ExtractionError, validate_upload

        class Fake:
            size = 40 * 1024 * 1024
            content_type = 'image/jpeg'
        with self.assertRaises(ExtractionError):
            validate_upload(Fake())

    def test_non_patient_cannot_reach_the_upload_page(self):
        self.client.force_login(make('prov2@example.com', User.Role.PROVIDER))
        self.assertEqual(self.client.get(reverse('health_prescription_upload')).status_code, 302)


class CareLoopTests(TestCase):
    """Phase 3 -- pre-visit snapshot, care plans, and availability-checked booking."""

    def setUp(self):
        self.patient = make('loop-patient@example.com', User.Role.PATIENT)
        self.provider = make('loop-provider@example.com', User.Role.PROVIDER)
        self.profile = ProviderProfile.objects.create(
            user=self.provider, provider_type=ProviderProfile.ProviderType.CLINIC,
            specialty='Cardiology', clinic_name='Loop Clinic')
        self.profile.approve()
        self.appt = Appointment.objects.create(
            patient=self.patient, provider=self.profile,
            scheduled_for=timezone.now() + datetime.timedelta(days=2),
            status=Appointment.Status.CONFIRMED,
        )

    def test_provider_without_consent_sees_the_not_shared_panel(self):
        self.client.force_login(self.provider)
        resp = self.client.get(reverse('provider_previsit_snapshot', args=[self.appt.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['can_see_vitals'])
        self.assertFalse(resp.context['can_see_meds'])
        self.assertContains(resp, "hasn't shared")

    def test_sharing_a_snapshot_grants_only_vitals_and_medications(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_previsit_share'), {
            'appointment_id': self.appt.id, 'next': reverse('provider_appointments'),
        })
        grant = ConsentGrant.objects.get(patient=self.patient, recipient=self.provider)
        self.assertTrue(grant.scope_vitals)
        self.assertTrue(grant.scope_medications)
        self.assertFalse(grant.scope_records)
        self.assertIsNotNone(grant.expires_at)
        self.assertEqual(grant.expires_at, self.appt.scheduled_for + datetime.timedelta(hours=24))

    def test_provider_sees_data_only_after_consent_is_shared(self):
        VitalRecord.objects.create(patient=self.patient, bp_systolic=118, bp_diastolic=76)
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_previsit_share'), {'appointment_id': self.appt.id})

        self.client.force_login(self.provider)
        resp = self.client.get(reverse('provider_previsit_snapshot', args=[self.appt.id]))
        self.assertTrue(resp.context['can_see_vitals'])
        self.assertContains(resp, '118')

    def test_snapshot_never_contains_mood_log_text(self):
        MoodLog.objects.create(patient=self.patient, mood='Anxious', note='very private note xyzzy')
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_previsit_share'), {'appointment_id': self.appt.id})
        self.client.force_login(self.provider)
        resp = self.client.get(reverse('provider_previsit_snapshot', args=[self.appt.id]))
        self.assertNotContains(resp, 'very private note xyzzy')

    def test_provider_cannot_open_a_snapshot_for_someone_elses_appointment(self):
        other_provider = make('loop-other-provider@example.com', User.Role.PROVIDER)
        ProviderProfile.objects.create(
            user=other_provider, provider_type=ProviderProfile.ProviderType.CLINIC).approve()
        self.client.force_login(other_provider)
        resp = self.client.get(reverse('provider_previsit_snapshot', args=[self.appt.id]))
        self.assertEqual(resp.status_code, 404)

    def test_viewing_a_snapshot_writes_an_audit_log_entry(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_previsit_share'), {'appointment_id': self.appt.id})
        before = AuditLog.objects.count()
        self.client.force_login(self.provider)
        self.client.get(reverse('provider_previsit_snapshot', args=[self.appt.id]))
        self.assertGreater(AuditLog.objects.count(), before)
        self.assertTrue(AuditLog.objects.filter(action__icontains='pre-visit snapshot').exists())

    def test_care_plan_cannot_be_created_for_an_unrelated_patient(self):
        stranger = make('loop-stranger@example.com', User.Role.PATIENT)
        self.client.force_login(self.provider)
        self.client.post(reverse('provider_care_plans'), {
            'patient_id': stranger.id, 'metric': CarePlan.Metric.WEIGHT,
            'target_value': '70', 'target_direction': CarePlan.Direction.BELOW,
        })
        self.assertEqual(CarePlan.objects.filter(patient=stranger).count(), 0)

    def test_care_plan_can_be_created_for_a_treated_patient_and_shows_on_dashboard(self):
        self.client.force_login(self.provider)
        self.client.post(reverse('provider_care_plans'), {
            'patient_id': self.patient.id, 'metric': CarePlan.Metric.BP_SYSTOLIC,
            'target_value': '130', 'target_direction': CarePlan.Direction.BELOW,
        })
        self.assertEqual(CarePlan.objects.filter(patient=self.patient).count(), 1)

        self.client.force_login(self.patient)
        resp = self.client.get(reverse('health_dashboard'))
        self.assertEqual(len(resp.context['care_plans']), 1)

    def test_booking_outside_availability_is_rejected(self):
        # Monday 9am-12pm only.
        ProviderAvailability.objects.create(
            provider=self.profile, weekday=ProviderAvailability.Weekday.MONDAY,
            start_time=datetime.time(9, 0), end_time=datetime.time(12, 0))
        # Find the next Tuesday, which is outside the window on any week.
        day = timezone.localdate() + datetime.timedelta(days=1)
        while day.weekday() != 1:
            day += datetime.timedelta(days=1)
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_appointments'), {
            'action': 'book', 'provider': self.profile.id,
            'date': day.isoformat(), 'time': '10:00',
        })
        # Compare in Python, not with a `__date` DB lookup: MySQL needs its
        # named time zone tables loaded (mysql_tzinfo_to_sql) for Django's
        # USE_TZ-aware date extraction to work; a fresh Windows install
        # usually doesn't have them, and CONVERT_TZ() then silently returns
        # NULL, matching nothing even though the row exists.
        new_appts = Appointment.objects.exclude(pk=self.appt.pk)
        self.assertFalse(any(timezone.localtime(a.scheduled_for).date() == day for a in new_appts))

    def test_booking_inside_availability_succeeds(self):
        ProviderAvailability.objects.create(
            provider=self.profile, weekday=ProviderAvailability.Weekday.MONDAY,
            start_time=datetime.time(9, 0), end_time=datetime.time(12, 0))
        day = timezone.localdate() + datetime.timedelta(days=1)
        while day.weekday() != 0:
            day += datetime.timedelta(days=1)
        self.client.force_login(self.patient)
        self.client.post(reverse('provider_appointments'), {
            'action': 'book', 'provider': self.profile.id,
            'date': day.isoformat(), 'time': '10:00',
        })
        new_appts = Appointment.objects.exclude(pk=self.appt.pk)
        self.assertTrue(any(timezone.localtime(a.scheduled_for).date() == day for a in new_appts))


class DataScienceTests(TestCase):
    """
    Phase 5 (task 4.1-4.7) -- the synthetic cohort generator and the
    recommendation engine built on top of it. Kept to a small cohort so
    the suite stays fast; the numbers themselves are not meaningful at
    this size, only the mechanics being tested are.
    """

    def _generate(self, patients=6, days=20, seed=7, reset=False):
        from django.core.management import call_command
        call_command('generate_cohort', patients=patients, days=days, seed=seed, reset=reset, verbosity=0)

    def test_generate_cohort_creates_the_expected_number_of_patients(self):
        from datascience.models import SyntheticPatient
        self._generate(patients=6, days=15, seed=3)
        self.assertEqual(SyntheticPatient.objects.count(), 6)

    def test_generate_cohort_is_reproducible_under_a_fixed_seed(self):
        from datascience.models import SyntheticPatient
        self._generate(patients=4, days=10, seed=99)
        first_run = list(
            SyntheticPatient.objects.order_by('id')
            .values_list('sleep_tendency', 'adherence_tendency', 'activity_tendency',
                          'hydration_tendency', 'engagement_tendency', 'chronic_hypertension',
                          'chronic_diabetes', 'age')
        )
        self._generate(patients=4, days=10, seed=99, reset=True)
        second_run = list(
            SyntheticPatient.objects.order_by('id')
            .values_list('sleep_tendency', 'adherence_tendency', 'activity_tendency',
                          'hydration_tendency', 'engagement_tendency', 'chronic_hypertension',
                          'chronic_diabetes', 'age')
        )
        self.assertEqual(first_run, second_run)

    def test_generate_cohort_without_reset_leaves_existing_cohort_untouched(self):
        from datascience.models import SyntheticPatient
        self._generate(patients=5, days=10, seed=1)
        self._generate(patients=9, days=10, seed=2, reset=False)  # should be a no-op
        self.assertEqual(SyntheticPatient.objects.count(), 5)

    def test_no_patient_appears_in_both_a_fold_train_and_test_split(self):
        from sklearn.model_selection import GroupKFold

        from datascience.recommend import build_training_table
        self._generate(patients=8, days=15, seed=11)
        X, _y_by_candidate, groups = build_training_table()

        # One feature row per synthetic patient -- a precondition for any
        # patient-grouped split to be leak-free.
        self.assertEqual(len(groups), len(set(groups)))

        gkf = GroupKFold(n_splits=4)
        for train_idx, test_idx in gkf.split(X, groups=groups):
            train_patients = {groups[i] for i in train_idx}
            test_patients = {groups[i] for i in test_idx}
            self.assertEqual(train_patients & test_patients, set())

    def test_recommender_trains_and_predicts_without_error(self):
        from datascience.recommend import CANDIDATES, recommend_for_patient, train_recommender
        self._generate(patients=8, days=25, seed=21)
        models = train_recommender()
        self.assertEqual(set(models.keys()), set(CANDIDATES.keys()))

        # A real (non-synthetic) patient with some logged data.
        patient = make('ds-patient@example.com', User.Role.PATIENT)
        VitalRecord.objects.create(patient=patient, bp_systolic=118, bp_diastolic=76)
        LifestyleLog.objects.create(patient=patient, date=timezone.localdate(),
                                     sleep_hours=5.0, water_litres=1.0, steps=2000)

        recs = recommend_for_patient(patient)
        self.assertLessEqual(len(recs), 3)
        for r in recs:
            self.assertIn(r['key'], CANDIDATES)
            self.assertTrue(r['title'])
            self.assertTrue(r['reason'])

    def test_recommender_falls_back_gracefully_with_no_trained_model(self):
        # No generate_cohort / train_recommender call in this test -- the
        # dashboard must never break just because the model hasn't been
        # trained yet on a fresh checkout of the project.
        from datascience.recommend import recommend_for_patient
        patient = make('ds-fresh@example.com', User.Role.PATIENT)
        LifestyleLog.objects.create(patient=patient, date=timezone.localdate(),
                                     sleep_hours=4.5, water_litres=0.8, steps=1500)
        recs = recommend_for_patient(patient)  # should use the rule-based fallback, not raise
        self.assertIsInstance(recs, list)

    def test_recommendation_engine_never_reads_or_mentions_mood_data(self):
        from datascience.features import FEATURE_ORDER
        from datascience.recommend import CANDIDATES
        self.assertNotIn('mood', [f.lower() for f in FEATURE_ORDER])
        for cfg in CANDIDATES.values():
            self.assertNotIn('mood', cfg['title'].lower())

    def test_suggestions_are_patient_only_and_never_reach_a_provider_view(self):
        self._generate(patients=6, days=15, seed=5)
        from django.core.management import call_command
        call_command('train_models', verbosity=0)

        patient = make('ds-loop-patient@example.com', User.Role.PATIENT)
        provider = make('ds-loop-provider@example.com', User.Role.PROVIDER)
        profile = ProviderProfile.objects.create(
            user=provider, provider_type=ProviderProfile.ProviderType.CLINIC,
            specialty='Cardiology', clinic_name='DS Test Clinic')
        profile.approve()
        appt = Appointment.objects.create(
            patient=patient, provider=profile,
            scheduled_for=timezone.now() + datetime.timedelta(days=2),
            status=Appointment.Status.CONFIRMED,
        )
        LifestyleLog.objects.create(patient=patient, date=timezone.localdate(),
                                     sleep_hours=4.0, water_litres=0.8, steps=1200)

        self.client.force_login(patient)
        self.client.post(reverse('provider_previsit_share'), {'appointment_id': appt.id})

        self.client.force_login(provider)
        resp = self.client.get(reverse('provider_previsit_snapshot', args=[appt.id]))
        self.assertNotIn('suggestions', resp.context)
        self.assertNotContains(resp, 'Suggestions for you')

        # But the patient's own dashboard does show them.
        self.client.force_login(patient)
        resp = self.client.get(reverse('health_dashboard'))
        self.assertContains(resp, 'Suggestions for you')
