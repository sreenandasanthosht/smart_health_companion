"""
health app models -- the patient's health data (physical + mental) and the
consent records that control who else may see it.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class VitalRecord(models.Model):
    class Status(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        WATCH = 'WATCH', 'Watch'
        HIGH = 'HIGH', 'High'

    class Source(models.TextChoices):
        # Answers the open question in NURSING_ROLE_DESIGN.md section 6:
        # nurse-entered readings are provenance-tagged, and live in this
        # same table rather than a separate one.
        SELF = 'SELF', 'Self-recorded'
        NURSE = 'NURSE', 'Nurse visit'
        CAREGIVER = 'CAREGIVER', 'Caregiver'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vital_records')
    recorded_at = models.DateTimeField(default=timezone.now)
    bp_systolic = models.PositiveIntegerField()
    bp_diastolic = models.PositiveIntegerField()
    blood_sugar = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    heart_rate = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NORMAL)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SELF)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='vitals_entered',
    )

    class Meta:
        ordering = ['-recorded_at']

    def compute_status(self):
        """
        Rule-based flagging -- deliberately simple and explainable.

        Thresholds follow standard adult reference ranges: >=140/90 is
        stage-2 hypertension territory, 130-139/85-89 is elevated. This is
        the interpretable baseline the CRISP-DM write-up (task 4.8)
        compares any later trained model against.
        """
        if self.bp_systolic >= 140 or self.bp_diastolic >= 90 or (self.heart_rate and self.heart_rate >= 110):
            return self.Status.HIGH
        if self.bp_systolic >= 130 or self.bp_diastolic >= 85 or (self.heart_rate and self.heart_rate >= 100):
            return self.Status.WATCH
        return self.Status.NORMAL

    def save(self, *args, **kwargs):
        self.status = self.compute_status()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} -- {self.recorded_at:%d %b %Y}"


class Medication(models.Model):
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=120)
    dose = models.CharField(max_length=60)
    schedule = models.CharField(max_length=120)
    start_date = models.DateField()
    next_refill_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.patient})"


class MedicationDose(models.Model):
    """One 'taken / missed' tick for a medication on a given day."""
    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name='doses')
    date = models.DateField(default=timezone.localdate)
    taken = models.BooleanField(default=False)
    taken_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('medication', 'date')]
        ordering = ['-date']

    def __str__(self):
        return f"{self.medication.name} on {self.date} ({'taken' if self.taken else 'missed'})"


class LifestyleLog(models.Model):
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lifestyle_logs')
    date = models.DateField(default=timezone.localdate)
    sleep_hours = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    water_litres = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    steps = models.PositiveIntegerField(null=True, blank=True)
    activity_note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = [('patient', 'date')]
        ordering = ['-date']

    def __str__(self):
        return f"{self.patient} -- {self.date}"


class MoodLog(models.Model):
    """
    Mental health check-ins.

    Per CONSENT_FRAMEWORK_DESIGN.md section 2, this data is a HARD
    EXCLUSION: it is never shareable with anyone, under any consent grant.
    There is deliberately no ConsentGrant scope that covers it.
    """
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mood_logs')
    date = models.DateField(default=timezone.localdate)
    mood = models.CharField(max_length=40)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.patient} -- {self.date} ({self.mood})"


class ConsentGrant(models.Model):
    """
    The `Consent` entity from CONSENT_FRAMEWORK_DESIGN.md section 3.

    One row per grant. Scope is per-category (section 2), always scoped to
    one named recipient (never "anyone"), and either open-ended or
    time-boxed. Revoking sets `revoked_at` rather than deleting the row, so
    the audit trail shows both the grant and the withdrawal.
    """
    class Scope(models.TextChoices):
        VITALS = 'VITALS', 'Vitals'
        MEDICATIONS = 'MEDICATIONS', 'Medications'
        RECORDS = 'RECORDS', 'Lab / prescription records'
        LIFESTYLE = 'LIFESTYLE', 'Lifestyle logs'
        # NOTE: there is intentionally no MENTAL_HEALTH scope.

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consents_given')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consents_received')
    scope_vitals = models.BooleanField(default=True)
    scope_medications = models.BooleanField(default=True)
    scope_records = models.BooleanField(default=False)
    scope_lifestyle = models.BooleanField(default=False)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    action_context = models.CharField(max_length=120, blank=True)
    passcode = models.CharField(max_length=12, blank=True)

    class Meta:
        ordering = ['-granted_at']

    def save(self, *args, **kwargs):
        if not self.passcode:
            import uuid
            self.passcode = 'CN-' + uuid.uuid4().hex[:5].upper()
        super().save(*args, **kwargs)

    def is_active(self):
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])

    def scope_list(self):
        names = []
        if self.scope_vitals:
            names.append('Vitals')
        if self.scope_medications:
            names.append('Medications')
        if self.scope_records:
            names.append('Records')
        if self.scope_lifestyle:
            names.append('Lifestyle')
        return names

    def scope_label(self):
        return ' + '.join(self.scope_list()) or 'Nothing'

    def status_label(self):
        if self.revoked_at is not None:
            return 'Revoked'
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return 'Expired'
        return 'Active'

    def __str__(self):
        return f"{self.patient} -> {self.recipient} ({self.scope_label()})"


def has_consent(patient, recipient, scope):
    """
    The enforcement check from CONSENT_FRAMEWORK_DESIGN.md section 5.

    Returns True if an un-revoked, un-expired grant exists covering
    (patient, recipient, scope). Mental health is never covered here --
    there is no scope value that can return True for it.
    """
    field = {
        ConsentGrant.Scope.VITALS: 'scope_vitals',
        ConsentGrant.Scope.MEDICATIONS: 'scope_medications',
        ConsentGrant.Scope.RECORDS: 'scope_records',
        ConsentGrant.Scope.LIFESTYLE: 'scope_lifestyle',
    }.get(scope)
    if field is None:
        return False
    now = timezone.now()
    return ConsentGrant.objects.filter(
        patient=patient, recipient=recipient, revoked_at__isnull=True, **{field: True},
    ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)).exists()


class HealthInsight(models.Model):
    """
    A generated observation about a patient's data -- the output of
    health/analytics.py. Stored (rather than computed on every page load)
    so the dashboard is fast and so insights can be audited later.
    """
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='insights')
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    text = models.CharField(max_length=255)
    # Why the rule fired -- keeps the system explainable (CRISP-DM task 4.8).
    evidence = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level}] {self.text}"
