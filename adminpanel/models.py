"""
adminpanel app -- the platform Admin's management surface.

Models here:
  * AuditLog          -- append-only record of accountable actions
  * Complaint         -- the "Reports & Complaints" queue
  * Announcement      -- platform notices the Admin publishes
  * PlatformSettings  -- the Super-Admin-only system settings

Health camps and wellness events live in `providers` instead, next to the
ProviderProfile that submits them -- they follow the same submit-then-be-
reviewed shape as verification itself.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    class Tag(models.TextChoices):
        OK = 'ok', 'Success'
        WARN = 'warn', 'Warning'
        DANGER = 'danger', 'Critical'
        MUTED = 'muted', 'Routine'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_entries',
    )
    actor_label = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=150)
    target = models.CharField(max_length=200, blank=True)
    tag = models.CharField(max_length=10, choices=Tag.choices, default=Tag.MUTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def record(cls, actor, action, target='', tag=Tag.MUTED):
        """Write one audit entry. Safe to call from anywhere."""
        return cls.objects.create(
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            actor_label=getattr(actor, 'display_name', '') or 'System',
            action=action,
            target=target,
            tag=tag,
        )

    def __str__(self):
        return f"{self.created_at:%d %b %Y %H:%M} -- {self.actor_label}: {self.action}"


class Complaint(models.Model):
    """
    A report raised by any user, for an Admin to review.

    `against_user` is optional: plenty of complaints are about the
    platform itself rather than a person, and forcing every report to name
    a target would push people into blaming whoever is nearest.
    """
    class Category(models.TextChoices):
        PROVIDER = 'PROVIDER', 'About a provider'
        CAREGIVER = 'CAREGIVER', 'About a caregiver'
        PRIVACY = 'PRIVACY', 'Privacy or data concern'
        TECHNICAL = 'TECHNICAL', 'Technical problem'
        OTHER = 'OTHER', 'Something else'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_REVIEW = 'IN_REVIEW', 'In review'
        RESOLVED = 'RESOLVED', 'Resolved'
        DISMISSED = 'DISMISSED', 'Dismissed'

    # An open complaint is one nobody has finished with yet.
    OPEN_STATUSES = [Status.OPEN, Status.IN_REVIEW]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints_raised',
    )
    against_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints_received',
    )
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    subject = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.CharField(max_length=255, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints_handled',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def resolve(self, admin, status, note=''):
        self.status = status
        self.resolution_note = note
        self.handled_by = admin
        self.resolved_at = timezone.now() if status not in self.OPEN_STATUSES else None
        self.save(update_fields=['status', 'resolution_note', 'handled_by', 'resolved_at'])

    def __str__(self):
        return f"{self.subject} ({self.status})"


class Announcement(models.Model):
    """
    A notice an Admin publishes to some or all of the platform.

    Publishing fans the announcement out as a Notification per recipient
    rather than being read live: the notification list is already where
    users look, and a stored copy means editing the announcement later
    doesn't silently rewrite what people were told.
    """
    class Audience(models.TextChoices):
        ALL = 'ALL', 'Everyone'
        PATIENTS = 'PATIENT', 'Patients'
        CAREGIVERS = 'CAREGIVER', 'Caregivers'
        PROVIDERS = 'PROVIDER', 'Providers'
        NURSES = 'NURSE', 'Nurses'

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='announcements',
    )
    title = models.CharField(max_length=150)
    body = models.TextField()
    audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.ALL)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    recipients_notified = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def audience_queryset(self):
        """The users this announcement is addressed to."""
        from accounts.models import User
        people = User.objects.filter(is_suspended=False).exclude(role=User.Role.ADMIN)
        if self.audience != self.Audience.ALL:
            people = people.filter(role=self.audience)
        return people

    def publish(self):
        """Send it, once. Returns the number of people notified."""
        from accounts.models import Notification

        if self.is_published:
            return 0
        recipients = list(self.audience_queryset())
        Notification.objects.bulk_create([
            Notification(
                user=person, title=self.title, body=self.body[:255],
                kind=Notification.Kind.GENERAL, level=Notification.Level.INFO,
            )
            for person in recipients
        ])
        self.is_published = True
        self.published_at = timezone.now()
        self.recipients_notified = len(recipients)
        self.save(update_fields=['is_published', 'published_at', 'recipients_notified'])
        return len(recipients)

    def __str__(self):
        return self.title


class PlatformSettings(models.Model):
    """
    System settings, editable by the Super Admin only.

    A single row -- `load()` creates it on first use. Every field here
    gates real behaviour somewhere; a settings page full of switches that
    do nothing is worse than no settings page.
    """
    provider_self_registration_open = models.BooleanField(
        default=True,
        help_text='When off, Provider disappears from the public sign-up form.',
    )
    caregiver_device_approval_required = models.BooleanField(
        default=True,
        help_text='When off, caregivers are not held for new-device approval.',
    )
    platform_notice = models.CharField(
        max_length=255, blank=True,
        help_text='Shown as a banner on every signed-in page. Leave blank for none.',
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='settings_updates',
    )

    class Meta:
        verbose_name = 'Platform settings'
        verbose_name_plural = 'Platform settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce the singleton
        super().save(*args, **kwargs)

    def __str__(self):
        return 'Platform settings'
