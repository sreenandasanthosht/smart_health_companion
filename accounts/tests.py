"""
Tests for the CareNest registration / onboarding and caregiver specs.

These cover the parts of the two design documents that are easy to break
silently: the three ways a caregiver can name a patient, the fact that
approval grants the everyday categories but not the restricted ones, and
the new-device gate.
"""
import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    CaregiverInvite, CaregiverLink, Notification, TrustedDevice, User,
)
from health.models import ConsentGrant, consent_matrix

PASSWORD = 'Str0ng-Pass!123'


class CaregiverReferenceTests(TestCase):
    """A caregiver may identify their patient three different ways."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='pat@example.com', email='pat@example.com',
            password=PASSWORD, role=User.Role.PATIENT, first_name='Pat')

    def _register(self, ref, email='care@example.com'):
        return self.client.post(reverse('register'), {
            'full_name': 'Casey Carer', 'email': email, 'phone_number': '+91 90000 00000',
            'role': User.Role.CAREGIVER, 'password': PASSWORD,
            'confirm_password': PASSWORD, 'caregiver_patient_ref': ref,
        })

    def test_links_by_patient_id(self):
        self._register(self.patient.unique_id)
        self.assertTrue(CaregiverLink.objects.filter(patient=self.patient).exists())

    def test_links_by_patient_email(self):
        self._register('PAT@example.com')  # case-insensitive
        self.assertTrue(CaregiverLink.objects.filter(patient=self.patient).exists())

    def test_links_by_invite_code_and_consumes_it(self):
        invite = CaregiverInvite.objects.create(patient=self.patient)
        self._register(invite.code)
        invite.refresh_from_db()
        self.assertTrue(CaregiverLink.objects.filter(patient=self.patient).exists())
        self.assertIsNotNone(invite.used_at, 'invite should be single-use')

    def test_used_invite_is_rejected(self):
        invite = CaregiverInvite.objects.create(patient=self.patient)
        invite.consume(self.patient)
        self._register(invite.code)
        self.assertFalse(CaregiverLink.objects.filter(patient=self.patient).exists())

    def test_expired_invite_is_rejected(self):
        invite = CaregiverInvite.objects.create(
            patient=self.patient, expires_at=timezone.now() - datetime.timedelta(days=1))
        self._register(invite.code)
        self.assertFalse(CaregiverLink.objects.filter(patient=self.patient).exists())

    def test_patient_is_notified_of_the_request(self):
        self._register(self.patient.unique_id)
        self.assertTrue(
            Notification.objects.filter(
                user=self.patient, kind=Notification.Kind.CAREGIVER_REQUEST).exists())


class CaregiverApprovalTests(TestCase):
    """Approval hands over the everyday categories, and only those."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='pat@example.com', email='pat@example.com',
            password=PASSWORD, role=User.Role.PATIENT)
        self.caregiver = User.objects.create_user(
            username='care@example.com', email='care@example.com',
            password=PASSWORD, role=User.Role.CAREGIVER)
        self.link = CaregiverLink.objects.create(patient=self.patient, caregiver=self.caregiver)

    def _approve(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('health_caregiver_requests'),
                         {'link_id': self.link.id, 'decision': 'approve'})
        self.client.logout()

    def test_approval_grants_standard_scopes_only(self):
        self._approve()
        matrix = consent_matrix(self.patient, self.caregiver)
        for scope in ConsentGrant.STANDARD_SCOPES:
            self.assertTrue(matrix[scope], f'{scope} should be granted on approval')
        for scope in ConsentGrant.RESTRICTED_SCOPES:
            self.assertFalse(matrix[scope], f'{scope} must stay restricted')

    def test_no_consent_before_approval(self):
        matrix = consent_matrix(self.patient, self.caregiver)
        self.assertFalse(any(matrix.values()))

    def test_mental_health_has_no_scope(self):
        """The hard exclusion: no scope value can ever cover mood logs."""
        values = {s.value for s in ConsentGrant.Scope}
        self.assertNotIn('MENTAL_HEALTH', values)

    def test_rejection_notifies_the_caregiver(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('health_caregiver_requests'),
                         {'link_id': self.link.id, 'decision': 'reject'})
        self.assertTrue(
            Notification.objects.filter(
                user=self.caregiver, kind=Notification.Kind.CAREGIVER_DECISION).exists())

    def test_dashboard_hides_ungranted_modules(self):
        self._approve()
        # Withdraw appointments, keep the rest.
        grant = ConsentGrant.objects.get(patient=self.patient, recipient=self.caregiver)
        grant.scope_appointments = False
        grant.save(update_fields=['scope_appointments'])

        self.client.force_login(self.caregiver)
        response = self.client.get(reverse('health_caregiver_dashboard'))
        self.assertTrue(response.context['can_see_vitals'])
        self.assertFalse(response.context['can_see_appointments'])
        self.assertNotContains(response, 'Upcoming appointments')


class DeviceApprovalTests(TestCase):
    """A caregiver on an unrecognised device sees nothing about the patient."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username='pat@example.com', email='pat@example.com',
            password=PASSWORD, role=User.Role.PATIENT)
        self.caregiver = User.objects.create_user(
            username='care@example.com', email='care@example.com',
            password=PASSWORD, role=User.Role.CAREGIVER)
        CaregiverLink.objects.create(
            patient=self.patient, caregiver=self.caregiver,
            status=CaregiverLink.Status.APPROVED, decided_at=timezone.now())

    def _login(self):
        return self.client.post(reverse('login'), {
            'email': 'care@example.com', 'password': PASSWORD})

    def _login_from_new_browser(self):
        self.client.logout()
        self.client.cookies.pop(TrustedDevice.COOKIE_NAME, None)
        return self._login()

    def test_first_device_is_trusted_implicitly(self):
        self._login()
        device = TrustedDevice.objects.get(user=self.caregiver)
        self.assertEqual(device.status, TrustedDevice.Status.APPROVED)

    def test_second_device_is_held_pending(self):
        self._login()
        self._login_from_new_browser()

        pending = TrustedDevice.objects.filter(
            user=self.caregiver, status=TrustedDevice.Status.PENDING)
        self.assertEqual(pending.count(), 1)
        self.assertTrue(
            Notification.objects.filter(
                user=self.patient, kind=Notification.Kind.DEVICE_APPROVAL).exists())

    def test_pending_device_cannot_see_patient_data(self):
        self._login()
        self._login_from_new_browser()

        response = self.client.get(reverse('health_caregiver_dashboard'))
        self.assertTrue(response.context['device_blocked'])
        self.assertNotIn('can_see_vitals', response.context)

    def test_patient_can_approve_the_device(self):
        self._login()
        self._login_from_new_browser()
        device = TrustedDevice.objects.get(user=self.caregiver, status=TrustedDevice.Status.PENDING)

        approver = self.client_class()
        approver.force_login(self.patient)
        approver.post(reverse('health_caregiver_requests'),
                      {'action': 'device', 'device_id': device.id, 'decision': 'approve'})

        device.refresh_from_db()
        self.assertEqual(device.status, TrustedDevice.Status.APPROVED)
        # And the caregiver's view opens up again.
        response = self.client.get(reverse('health_caregiver_dashboard'))
        self.assertNotIn('device_blocked', response.context)


class RegistrationRoleTests(TestCase):
    """Admin and Nurse accounts are created internally, never self-registered."""

    def test_privileged_roles_cannot_self_register(self):
        for role in (User.Role.ADMIN, User.Role.NURSE):
            self.client.post(reverse('register'), {
                'full_name': 'Sneaky', 'email': f'{role.lower()}@example.com',
                'phone_number': '+91 90000 00000', 'role': role,
                'password': PASSWORD, 'confirm_password': PASSWORD,
            })
            self.assertFalse(
                User.objects.filter(email=f'{role.lower()}@example.com').exists(),
                f'{role} must not be self-registerable')
