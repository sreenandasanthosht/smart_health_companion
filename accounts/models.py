"""
accounts app -- everything about USERS.

We define ONE custom user that covers all user types via a `role` field,
and give every user a short unique_id (patients share this with a
caregiver so the caregiver can request a link).
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        PATIENT = 'PATIENT', 'Patient'
        CAREGIVER = 'CAREGIVER', 'Caregiver'
        PROVIDER = 'PROVIDER', 'Provider'
        ADMIN = 'ADMIN', 'Admin'
        NURSE = 'NURSE', 'Nurse'

    class Sex(models.TextChoices):
        FEMALE = 'F', 'Female'
        MALE = 'M', 'Male'
        OTHER = 'O', 'Other'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    unique_id = models.CharField(max_length=12, unique=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    # --- Profile details, filled in progressively after sign-up ---
    # All optional: the CareNest flow lets a patient reach their dashboard
    # immediately and complete these later. `profile_completion` turns them
    # into the percentage shown on the dashboard.
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    emergency_contact = models.CharField(max_length=20, blank=True)

    # Admins can suspend an account without deleting it.
    is_suspended = models.BooleanField(default=False)

    PROFILE_FIELDS = [
        'first_name', 'phone_number', 'date_of_birth', 'sex',
        'blood_group', 'height_cm', 'address', 'emergency_contact',
    ]

    def save(self, *args, **kwargs):
        # auto-generate a unique id the first time the user is saved
        if not self.unique_id:
            self.unique_id = uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    def profile_completion(self):
        """Percentage of profile fields filled in (0-100)."""
        filled = sum(1 for f in self.PROFILE_FIELDS if getattr(self, f, None))
        return int(round(filled / len(self.PROFILE_FIELDS) * 100))

    def missing_profile_fields(self):
        """Human-readable labels of the profile fields still empty."""
        labels = {
            'first_name': 'Name',
            'phone_number': 'Phone number',
            'date_of_birth': 'Date of birth',
            'sex': 'Sex',
            'blood_group': 'Blood group',
            'height_cm': 'Height',
            'address': 'Address',
            'emergency_contact': 'Emergency contact',
        }
        return [labels[f] for f in self.PROFILE_FIELDS if not getattr(self, f, None)]

    @property
    def display_name(self):
        full = self.get_full_name().strip()
        return full or self.username

    @property
    def initials(self):
        parts = [p for p in self.display_name.replace('@', ' ').split() if p]
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class CaregiverLink(models.Model):
    """
    Links a Caregiver account to the Patient they support.

    Created as PENDING when a caregiver registers with a patient's unique
    ID. The PATIENT must approve it before the caregiver can see anything
    -- that approval is the gate enforced in health.views.caregiver_dashboard.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='caregiver_links')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_links')
    relationship = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('patient', 'caregiver')]
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.caregiver} -> {self.patient} ({self.status})"
