"""
accounts app -- everything about USERS.

We define ONE custom user that covers all user types via a `role` field,
and give every user a short unique_id (patients share this with a
caregiver so the caregiver can request a link).

Also here, because they all hang off the user rather than off health data:
  * CaregiverInvite -- the third way a caregiver can reach a patient
    (CareNest_User_Registration_and_Onboarding_Flow: "Patient ID /
    Patient Email / Invite Code")
  * Notification    -- the in-app notification the Caregiver Module
    proposal calls for ("The patient receives a notification requesting
    approval or rejection of the caregiver request")
  * TrustedDevice   -- the new-device login approval from that same
    proposal's "Secure Login" section
"""
import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class CareNestUserManager(UserManager):
    """
    Makes `createsuperuser` produce a CareNest Super Admin.

    Without this, the first account on a fresh install gets the model's
    default role (Patient) and is redirected to the patient dashboard
    after login -- which contradicts the Admin Module proposal's "The
    first Super Admin account is created during system setup."

    Only `create_superuser` is overridden. `create_user` keeps Django's
    behaviour, so registration and the seed command are unaffected.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', self.model.Role.ADMIN)
        extra_fields.setdefault('is_super_admin', True)
        return super().create_superuser(username, email, password, **extra_fields)


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

    # AbstractUser's email is blank=True but NOT unique -- that gap is what
    # forced accounts/views.py::_username_for_login to exist (it has to
    # disambiguate when more than one account shares an email). We always
    # register with username == email, so a non-unique email is really a
    # non-unique login identity. Overridden here to close that gap; emails
    # are also lower-cased on save so the DB-level constraint matches the
    # case-insensitive (__iexact) lookups used everywhere else in the app.
    email = models.EmailField('email address', unique=True)

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
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_relation = models.CharField(max_length=60, blank=True)
    # Free-text for now: the onboarding spec lists these as things a patient
    # "can later complete" from the dashboard, not structured registration
    # fields, so a note per line is the right shape.
    allergies = models.TextField(blank=True)
    medical_conditions = models.TextField(blank=True)

    # Admins can suspend an account without deleting it.
    is_suspended = models.BooleanField(default=False)

    # Super Admin is a *tier within* the Admin role, not a sixth role.
    #
    # The Admin Module proposal gives both tiers the same surface ("Admins
    # log in using normal login credentials and are automatically
    # redirected to the Admin Dashboard") and differs only in what they may
    # do once there. A separate role would mean every existing
    # @role_required(ADMIN) check had to list two values and would keep
    # drifting; a flag means a Super Admin simply *is* an Admin with more
    # permissions.
    #
    # Deliberately not reusing Django's `is_superuser`: that grants access
    # to the /admin/ site, which is a different question from who may
    # create CareNest Admin accounts. Keeping them separate means one can
    # be granted without the other.
    is_super_admin = models.BooleanField(
        default=False,
        help_text='Only meaningful when role is Admin. Super Admins manage other Admin accounts.',
    )

    objects = CareNestUserManager()

    PROFILE_FIELDS = [
        'first_name', 'phone_number', 'date_of_birth', 'sex',
        'blood_group', 'height_cm', 'address', 'emergency_contact',
        'allergies', 'medical_conditions',
    ]

    def save(self, *args, **kwargs):
        # auto-generate a unique id the first time the user is saved
        if not self.unique_id:
            self.unique_id = uuid.uuid4().hex[:10].upper()
        # Normalise case so the `unique=True` constraint above actually
        # matches "same email" the way a human -- and every __iexact lookup
        # in this codebase -- means it.
        if self.email:
            self.email = self.email.strip().lower()
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
            'allergies': 'Allergies',
            'medical_conditions': 'Medical conditions',
        }
        return [labels[f] for f in self.PROFILE_FIELDS if not getattr(self, f, None)]

    @property
    def is_platform_admin(self):
        """Either tier of Admin. Django superusers count, for demo access."""
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_platform_super_admin(self):
        return (self.is_super_admin and self.role == self.Role.ADMIN) or self.is_superuser

    @property
    def admin_tier_label(self):
        if not self.is_platform_admin:
            return ''
        return 'Super Admin' if self.is_platform_super_admin else 'Admin'

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


class CaregiverInvite(models.Model):
    """
    A single-use invite code a patient generates for someone they already
    trust. It is the third accepted identifier at caregiver sign-up, next
    to the patient's ID and email address.

    Unlike the patient's `unique_id` -- which is permanent and reusable --
    an invite is consumed the moment a caregiver registers with it, so a
    code that leaks after the fact is worthless.
    """
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='caregiver_invites')
    code = models.CharField(max_length=16, unique=True, blank=True)
    label = models.CharField(max_length=80, blank=True, help_text='Who this code was meant for.')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='caregiver_invites_used',
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = 'CN-' + uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    def is_valid(self):
        if self.used_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True

    def consume(self, caregiver):
        self.used_at = timezone.now()
        self.used_by = caregiver
        self.save(update_fields=['used_at', 'used_by'])

    def status_label(self):
        if self.used_at is not None:
            return 'Used'
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return 'Expired'
        return 'Active'

    def __str__(self):
        return f"{self.code} ({self.patient})"


class Notification(models.Model):
    """
    An in-app notification. The caregiver module is built on the patient
    being *asked*, so the approval request, the decision that follows and
    any device-approval prompt all need somewhere visible to land.
    """
    class Kind(models.TextChoices):
        CAREGIVER_REQUEST = 'CAREGIVER_REQUEST', 'Caregiver access request'
        CAREGIVER_DECISION = 'CAREGIVER_DECISION', 'Caregiver request decision'
        DEVICE_APPROVAL = 'DEVICE_APPROVAL', 'New device sign-in'
        CONSENT = 'CONSENT', 'Sharing permission changed'
        ALERT = 'ALERT', 'Health alert'
        GENERAL = 'GENERAL', 'General'

    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        ACTION = 'ACTION', 'Needs your action'
        WARNING = 'WARNING', 'Warning'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERAL)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=255, blank=True)
    # Where clicking through should take the user, e.g. 'health_caregiver_requests'.
    action_url_name = models.CharField(max_length=80, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def send(cls, user, title, body='', kind=Kind.GENERAL, level=Level.INFO, action_url_name=''):
        """Create one notification. Safe to call from anywhere."""
        if user is None:
            return None
        return cls.objects.create(
            user=user, title=title, body=body, kind=kind,
            level=level, action_url_name=action_url_name,
        )

    @property
    def is_unread(self):
        return self.read_at is None

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])

    def __str__(self):
        return f"{self.user} -- {self.title}"


class TrustedDevice(models.Model):
    """
    Implements "Secure Login" from the Caregiver Module proposal: a
    caregiver signing in from a device the patient hasn't seen before is
    held at PENDING until the patient approves it.

    The device is identified by a random token stored in a cookie on the
    caregiver's browser -- deliberately not a fingerprint of the browser
    itself, which would be both less reliable and more invasive.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Awaiting patient approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    COOKIE_NAME = 'carenest_device'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    # The patient whose data this device is being trusted to reach.
    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='devices_to_approve',
        null=True, blank=True,
    )
    token = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('user', 'token')]
        ordering = ['-last_seen_at']

    @staticmethod
    def new_token():
        return uuid.uuid4().hex

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    def approve(self):
        self.status = self.Status.APPROVED
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decided_at'])

    def reject(self):
        self.status = self.Status.REJECTED
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decided_at'])

    def __str__(self):
        return f"{self.label or 'Device'} for {self.user} ({self.status})"
