"""
Tests for the Admin Module spec.

The parts worth guarding are the access rules -- who may reach what --
and the two workflows where an approval gate is the whole point: provider
verification and public event approval.
"""
import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Notification, User
from adminpanel.models import Announcement, AuditLog, Complaint, PlatformSettings
from providers.models import HealthEvent, ProviderProfile

PASSWORD = 'Str0ng-Pass!123'

SUPER_ONLY_URLS = ['admin_accounts', 'admin_settings']
ADMIN_URLS = [
    'admin_dashboard', 'admin_verification', 'admin_users', 'admin_providers',
    'admin_audit_log', 'admin_nursing', 'admin_caregivers', 'admin_complaints',
    'admin_events', 'admin_announcements', 'admin_analytics',
]


def make(email, role, **extra):
    return User.objects.create_user(
        username=email, email=email, password=PASSWORD, role=role, **extra)


class AdminAccessTests(TestCase):
    """"No public admin registration" and "role-based access control"."""

    def setUp(self):
        self.super_admin = make('super@example.com', User.Role.ADMIN, is_super_admin=True)
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.patient = make('pat@example.com', User.Role.PATIENT)

    def test_admin_reaches_every_standard_page(self):
        self.client.force_login(self.admin)
        for name in ADMIN_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_patient_is_bounced_from_admin_pages(self):
        self.client.force_login(self.patient)
        for name in ADMIN_URLS + SUPER_ONLY_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)

    def test_standard_admin_cannot_reach_super_admin_pages(self):
        self.client.force_login(self.admin)
        for name in SUPER_ONLY_URLS:
            response = self.client.get(reverse(name), follow=True)
            self.assertContains(response, 'restricted to the Super Admin')

    def test_super_admin_reaches_everything(self):
        self.client.force_login(self.super_admin)
        for name in ADMIN_URLS + SUPER_ONLY_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_createsuperuser_produces_a_super_admin(self):
        """"The first Super Admin account is created during system setup." """
        first = User.objects.create_superuser(
            username='setup@example.com', email='setup@example.com', password=PASSWORD)
        self.assertEqual(first.role, User.Role.ADMIN)
        self.assertTrue(first.is_super_admin)

        # And they land on the admin dashboard, not the patient one.
        response = self.client.post(reverse('login'),
                                    {'email': 'setup@example.com', 'password': PASSWORD})
        self.assertRedirects(response, reverse('admin_dashboard'))

    def test_admin_is_not_a_signup_role(self):
        self.client.post(reverse('register'), {
            'full_name': 'Sneaky Admin', 'email': 'sneak@example.com',
            'phone_number': '+91 90000 00000', 'role': User.Role.ADMIN,
            'password': PASSWORD, 'confirm_password': PASSWORD,
        })
        self.assertFalse(User.objects.filter(email='sneak@example.com').exists())

    def test_only_super_admin_can_create_an_admin(self):
        # A standard Admin's POST is rejected before it reaches the view body.
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_accounts'), {
            'action': 'create', 'full_name': 'New Admin',
            'email': 'new@example.com', 'password': PASSWORD,
        })
        self.assertFalse(User.objects.filter(email='new@example.com').exists())

        self.client.force_login(self.super_admin)
        self.client.post(reverse('admin_accounts'), {
            'action': 'create', 'full_name': 'New Admin',
            'email': 'new@example.com', 'password': PASSWORD,
        })
        created = User.objects.get(email='new@example.com')
        self.assertEqual(created.role, User.Role.ADMIN)
        self.assertFalse(created.is_super_admin)

    def test_super_admin_cannot_demote_themselves(self):
        self.client.force_login(self.super_admin)
        self.client.post(reverse('admin_accounts'),
                         {'action': 'demote', 'user_id': self.super_admin.id})
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_super_admin)

    def test_revoking_admin_returns_them_to_patient(self):
        self.client.force_login(self.super_admin)
        self.client.post(reverse('admin_accounts'),
                         {'action': 'revoke', 'user_id': self.admin.id})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.PATIENT)
        self.assertFalse(self.admin.is_super_admin)


class ProviderVerificationTests(TestCase):
    """"Only verified providers become searchable and can receive appointments." """

    def setUp(self):
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.provider_user = make('doc@example.com', User.Role.PROVIDER)
        self.profile = ProviderProfile.objects.create(
            user=self.provider_user, provider_type=ProviderProfile.ProviderType.CLINIC,
            clinic_name='Test Clinic')
        self.patient = make('pat@example.com', User.Role.PATIENT)

    def test_unverified_provider_is_not_in_the_directory(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse('provider_directory'))
        self.assertNotContains(response, 'Test Clinic')

    def test_approval_lists_them_and_notifies_them(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_verification'),
                         {'profile_id': self.profile.id, 'action': 'approve'})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_verified)
        self.assertTrue(Notification.objects.filter(user=self.provider_user).exists())

        self.client.force_login(self.patient)
        self.assertContains(self.client.get(reverse('provider_directory')), 'Test Clinic')

    def test_rejection_is_distinct_from_requesting_more_info(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_verification'), {
            'profile_id': self.profile.id, 'action': 'reject', 'note': 'Licence not valid.'})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.verification_status, ProviderProfile.Verification.REJECTED)
        self.assertFalse(self.profile.is_verified)
        self.assertIn('Licence not valid', self.profile.verification_note)

    def test_every_decision_is_audited(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_verification'),
                         {'profile_id': self.profile.id, 'action': 'approve'})
        self.assertTrue(AuditLog.objects.filter(action='Approved provider').exists())


class HealthEventApprovalTests(TestCase):
    """"Only approved events are visible to users." """

    def setUp(self):
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.provider_user = make('doc@example.com', User.Role.PROVIDER)
        self.profile = ProviderProfile.objects.create(
            user=self.provider_user, provider_type=ProviderProfile.ProviderType.CLINIC,
            clinic_name='Test Clinic',
            verification_status=ProviderProfile.Verification.VERIFIED)
        self.patient = make('pat@example.com', User.Role.PATIENT)

    def _submit(self):
        self.client.force_login(self.provider_user)
        self.client.post(reverse('provider_events'), {
            'title': 'Free screening camp', 'kind': HealthEvent.Kind.SCREENING,
            'starts_at': (timezone.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            'venue': 'Community Hall',
        })
        return HealthEvent.objects.get(title='Free screening camp')

    def test_submission_always_starts_pending(self):
        event = self._submit()
        self.assertEqual(event.status, HealthEvent.Status.PENDING)

    def test_pending_event_is_invisible_to_patients(self):
        self._submit()
        self.client.force_login(self.patient)
        self.assertNotContains(self.client.get(reverse('public_events')), 'Free screening camp')

    def test_approved_event_becomes_visible(self):
        event = self._submit()
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_events'), {'event_id': event.id, 'action': 'approve'})

        self.client.force_login(self.patient)
        self.assertContains(self.client.get(reverse('public_events')), 'Free screening camp')

    def test_rejected_event_stays_hidden_and_provider_is_told(self):
        event = self._submit()
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_events'),
                         {'event_id': event.id, 'action': 'reject', 'note': 'Out of scope.'})
        event.refresh_from_db()
        self.assertEqual(event.status, HealthEvent.Status.REJECTED)
        self.assertTrue(Notification.objects.filter(user=self.provider_user).exists())

        self.client.force_login(self.patient)
        self.assertNotContains(self.client.get(reverse('public_events')), 'Free screening camp')

    def test_approved_event_from_unverified_provider_stays_hidden(self):
        """Approval alone isn't enough -- the provider must also be verified."""
        event = self._submit()
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_events'), {'event_id': event.id, 'action': 'approve'})

        self.profile.verification_status = ProviderProfile.Verification.PENDING
        self.profile.save(update_fields=['verification_status'])

        self.client.force_login(self.patient)
        self.assertNotContains(self.client.get(reverse('public_events')), 'Free screening camp')

    def test_past_events_drop_off_the_public_listing(self):
        event = self._submit()
        event.approve(self.admin)
        event.starts_at = timezone.now() - datetime.timedelta(days=1)
        event.save(update_fields=['starts_at'])

        self.client.force_login(self.patient)
        self.assertNotContains(self.client.get(reverse('public_events')), 'Free screening camp')


class ComplaintTests(TestCase):
    def setUp(self):
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.patient = make('pat@example.com', User.Role.PATIENT)

    def test_user_can_file_a_report(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('report_problem'), {
            'category': Complaint.Category.TECHNICAL,
            'subject': 'Chart not loading', 'description': 'Blank on mobile.',
        })
        complaint = Complaint.objects.get(subject='Chart not loading')
        self.assertEqual(complaint.reporter, self.patient)
        self.assertEqual(complaint.status, Complaint.Status.OPEN)

    def test_resolving_notifies_the_reporter(self):
        complaint = Complaint.objects.create(
            reporter=self.patient, subject='Test', description='Test')
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_complaints'), {
            'complaint_id': complaint.id, 'action': 'resolve', 'note': 'Fixed.'})
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.RESOLVED)
        self.assertFalse(complaint.is_open)
        self.assertTrue(Notification.objects.filter(user=self.patient).exists())

    def test_patients_cannot_open_the_admin_queue(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse('admin_complaints')).status_code, 302)


class AnnouncementTests(TestCase):
    def setUp(self):
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.patient = make('pat@example.com', User.Role.PATIENT)
        self.provider = make('doc@example.com', User.Role.PROVIDER)

    def test_draft_sends_nothing(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_announcements'), {
            'action': 'create', 'title': 'Notice', 'body': 'Body',
            'audience': Announcement.Audience.ALL})
        self.assertEqual(Notification.objects.count(), 0)

    def test_publishing_reaches_the_audience_only(self):
        announcement = Announcement.objects.create(
            author=self.admin, title='For providers', body='Body',
            audience=Announcement.Audience.PROVIDERS)
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_announcements'), {
            'action': 'publish', 'announcement_id': announcement.id})

        self.assertTrue(Notification.objects.filter(user=self.provider).exists())
        self.assertFalse(Notification.objects.filter(user=self.patient).exists())

    def test_publishing_twice_does_not_double_send(self):
        announcement = Announcement.objects.create(
            author=self.admin, title='Notice', body='Body')
        announcement.publish()
        before = Notification.objects.count()
        announcement.publish()
        self.assertEqual(Notification.objects.count(), before)

    def test_published_announcement_cannot_be_deleted(self):
        announcement = Announcement.objects.create(
            author=self.admin, title='Notice', body='Body')
        announcement.publish()
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_announcements'), {
            'action': 'delete', 'announcement_id': announcement.id})
        self.assertTrue(Announcement.objects.filter(pk=announcement.pk).exists())


class PlatformSettingsTests(TestCase):
    """Every setting has to actually change something."""

    def setUp(self):
        self.super_admin = make('super@example.com', User.Role.ADMIN, is_super_admin=True)

    def test_settings_are_a_singleton(self):
        PlatformSettings.load()
        PlatformSettings.load()
        self.assertEqual(PlatformSettings.objects.count(), 1)

    def test_closing_provider_registration_removes_the_option(self):
        config = PlatformSettings.load()
        config.provider_self_registration_open = False
        config.save()

        response = self.client.get(reverse('register'))
        self.assertNotContains(response, 'value="PROVIDER"')

        # And a crafted POST is rejected, not merely hidden.
        self.client.post(reverse('register'), {
            'full_name': 'Doc Tor', 'email': 'doc@example.com',
            'phone_number': '+91 90000 00000', 'role': User.Role.PROVIDER,
            'provider_type': 'CLINIC',
            'password': PASSWORD, 'confirm_password': PASSWORD,
        })
        self.assertFalse(User.objects.filter(email='doc@example.com').exists())

    def test_patient_signup_still_works_when_provider_signup_is_closed(self):
        config = PlatformSettings.load()
        config.provider_self_registration_open = False
        config.save()

        self.client.post(reverse('register'), {
            'full_name': 'Asha P', 'email': 'asha@example.com',
            'phone_number': '+91 90000 00000', 'role': User.Role.PATIENT,
            'password': PASSWORD, 'confirm_password': PASSWORD,
        })
        self.assertTrue(User.objects.filter(email='asha@example.com').exists())


class CaregiverManagementTests(TestCase):
    """An Admin may revoke a caregiver link, but never approve one."""

    def setUp(self):
        from accounts.models import CaregiverLink
        from health.models import ConsentGrant

        self.CaregiverLink = CaregiverLink
        self.ConsentGrant = ConsentGrant
        self.admin = make('admin@example.com', User.Role.ADMIN)
        self.patient = make('pat@example.com', User.Role.PATIENT)
        self.caregiver = make('care@example.com', User.Role.CAREGIVER)
        self.link = CaregiverLink.objects.create(
            patient=self.patient, caregiver=self.caregiver,
            status=CaregiverLink.Status.APPROVED, decided_at=timezone.now())
        self.grant = ConsentGrant.objects.create(
            patient=self.patient, recipient=self.caregiver, scope_vitals=True)

    def test_revoking_a_link_also_withdraws_consent(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_caregivers'),
                         {'action': 'revoke', 'link_id': self.link.id})
        self.link.refresh_from_db()
        self.grant.refresh_from_db()
        self.assertEqual(self.link.status, self.CaregiverLink.Status.REJECTED)
        self.assertIsNotNone(self.grant.revoked_at)
        self.assertFalse(self.grant.is_active())

    def test_there_is_no_admin_approve_action(self):
        self.link.status = self.CaregiverLink.Status.PENDING
        self.link.save(update_fields=['status'])

        self.client.force_login(self.admin)
        self.client.post(reverse('admin_caregivers'),
                         {'action': 'approve', 'link_id': self.link.id})
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, self.CaregiverLink.Status.PENDING)
