"""
providers app -- provider listings, verification and appointments.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class ProviderProfile(models.Model):
    """
    The professional details behind a role=PROVIDER user, plus the
    verification state an Admin moves through. Provider types and required
    documents follow the CareNest registration & onboarding spec.
    """
    class ProviderType(models.TextChoices):
        DOCTOR = 'DOCTOR', 'Doctor'
        CLINIC = 'CLINIC', 'Clinic'
        HOSPITAL = 'HOSPITAL', 'Hospital'
        DIAGNOSTIC_LAB = 'DIAGNOSTIC_LAB', 'Diagnostic Lab'
        PHARMACY = 'PHARMACY', 'Pharmacy'
        DIETICIAN = 'DIETICIAN', 'Dietician'
        FITNESS_CENTRE = 'FITNESS_CENTRE', 'Fitness Centre'
        WELLNESS_CENTRE = 'WELLNESS_CENTRE', 'Wellness Centre'

    class Verification(models.TextChoices):
        PENDING = 'PENDING', 'Pending Verification'
        VERIFIED = 'VERIFIED', 'Verified'
        NEEDS_INFO = 'NEEDS_INFO', 'Verification Required'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider_profile')
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    specialty = models.CharField(max_length=120, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    clinic_name = models.CharField(max_length=150, blank=True)
    address = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=60, blank=True)

    # Required documents. Booleans rather than FileFields keeps the review
    # demo free of upload plumbing while still driving the Admin queue.
    doc_registration_certificate = models.BooleanField(default=False)
    doc_government_id = models.BooleanField(default=False)
    doc_organization_info = models.BooleanField(default=False)
    doc_address_proof = models.BooleanField(default=False)

    verification_status = models.CharField(max_length=12, choices=Verification.choices, default=Verification.PENDING)
    verification_note = models.CharField(max_length=255, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    @property
    def is_verified(self):
        return self.verification_status == self.Verification.VERIFIED

    def documents_submitted(self):
        return [
            ('Registration certificate', self.doc_registration_certificate),
            ('Government ID', self.doc_government_id),
            ('Clinic / organisation info', self.doc_organization_info),
            ('Address proof', self.doc_address_proof),
        ]

    def documents_complete(self):
        return all(flag for _, flag in self.documents_submitted())

    def approve(self):
        self.verification_status = self.Verification.VERIFIED
        self.verified_at = timezone.now()
        self.verification_note = ''
        self.save(update_fields=['verification_status', 'verified_at', 'verification_note'])

    def request_more_info(self, note=''):
        self.verification_status = self.Verification.NEEDS_INFO
        self.verification_note = note
        self.save(update_fields=['verification_status', 'verification_note'])

    def display_name(self):
        return self.clinic_name or self.user.display_name

    def __str__(self):
        return f"{self.display_name()} ({self.get_provider_type_display()})"


class Appointment(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments_as_patient')
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='appointments')
    scheduled_for = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    provider_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_for']

    @property
    def is_upcoming(self):
        return self.scheduled_for >= timezone.now() and self.status in {
            self.Status.REQUESTED, self.Status.CONFIRMED,
        }

    def __str__(self):
        return f"{self.patient} with {self.provider} on {self.scheduled_for:%d %b %Y}"
