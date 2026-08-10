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
        # Distinct from NEEDS_INFO: that pauses the review awaiting better
        # documents, this ends it. Both keep the provider out of the
        # directory, but only one is a decision.
        REJECTED = 'REJECTED', 'Rejected'

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

    def reject(self, note=''):
        self.verification_status = self.Verification.REJECTED
        self.verification_note = note
        self.verified_at = None
        self.save(update_fields=['verification_status', 'verification_note', 'verified_at'])

    def display_name(self):
        return self.clinic_name or self.user.display_name

    def __str__(self):
        return f"{self.display_name()} ({self.get_provider_type_display()})"


class HealthEvent(models.Model):
    """
    A health camp, awareness programme or wellness event a provider wants
    to run publicly.

    Same shape as provider verification, and for the same reason: the
    Admin Module proposal requires that "All public health camps and
    wellness programs require admin approval", so an event is submitted,
    sits at PENDING, and only becomes visible to patients once an Admin
    approves it. Nothing a provider can do puts an event in front of users
    on its own.
    """
    class Kind(models.TextChoices):
        CAMP = 'CAMP', 'Health camp'
        AWARENESS = 'AWARENESS', 'Awareness programme'
        SCREENING = 'SCREENING', 'Screening drive'
        WELLNESS = 'WELLNESS', 'Wellness event'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CAMP)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_free = models.BooleanField(default=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    review_note = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='events_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['starts_at']

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    @property
    def is_upcoming(self):
        return self.starts_at >= timezone.now()

    @classmethod
    def public(cls):
        """
        The only queryset that should ever reach a patient-facing page:
        approved, still upcoming, and run by a verified provider.
        """
        return cls.objects.filter(
            status=cls.Status.APPROVED,
            starts_at__gte=timezone.now(),
            provider__verification_status=ProviderProfile.Verification.VERIFIED,
        ).select_related('provider', 'provider__user')

    def approve(self, admin, note=''):
        self.status = self.Status.APPROVED
        self.review_note = note
        self.reviewed_by = admin
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at'])

    def reject(self, admin, note=''):
        self.status = self.Status.REJECTED
        self.review_note = note
        self.reviewed_by = admin
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at'])

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


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


class ProviderAvailability(models.Model):
    """
    A weekly recurring window a provider is bookable in.

    Deliberately a recurring pattern (weekday + start/end time) rather than
    individually generated bookable slots -- the Phase 3 plan flags that as
    the simplest thing that works for this project, and slot generation
    adds complexity (holidays, exceptions, timezone edge cases) that isn't
    needed to demonstrate the feature.
    """
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='availability')
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveIntegerField(default=30)

    class Meta:
        ordering = ['weekday', 'start_time']
        verbose_name_plural = 'Provider availability'

    def covers(self, when):
        """True if the given aware datetime falls within this window's day and time."""
        local = timezone.localtime(when)
        return local.weekday() == self.weekday and self.start_time <= local.time() < self.end_time

    def __str__(self):
        return f"{self.provider} -- {self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class CarePlan(models.Model):
    """
    A small, measurable target a provider sets for a patient after a visit.

    Kept deliberately narrow per the Phase 3 plan: one metric, one target,
    a review date and a note -- not a full clinical care plan. `progress()`
    reads the patient's own recent data and never invents a number; it
    returns None when there isn't enough data to say anything.
    """
    class Metric(models.TextChoices):
        BP_SYSTOLIC = 'BP_SYSTOLIC', 'Blood pressure (systolic)'
        WEIGHT = 'WEIGHT', 'Weight'
        STEPS = 'STEPS', 'Daily steps'
        SLEEP_HOURS = 'SLEEP_HOURS', 'Sleep hours'
        BLOOD_SUGAR = 'BLOOD_SUGAR', 'Blood sugar'

    class Direction(models.TextChoices):
        BELOW = 'BELOW', 'At or below target'
        ABOVE = 'ABOVE', 'At or above target'
        WITHIN = 'WITHIN', 'Within range of target'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='care_plans')
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='care_plans')
    created_at = models.DateTimeField(auto_now_add=True)
    metric = models.CharField(max_length=20, choices=Metric.choices)
    target_value = models.DecimalField(max_digits=6, decimal_places=1)
    target_direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.BELOW)
    review_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def _latest_value(self):
        """The patient's most recent reading for this plan's metric, or None."""
        from health.models import LifestyleLog, VitalRecord

        if self.metric == self.Metric.BP_SYSTOLIC:
            row = VitalRecord.objects.filter(patient=self.patient).first()
            return row.bp_systolic if row else None
        if self.metric == self.Metric.WEIGHT:
            row = VitalRecord.objects.filter(patient=self.patient, weight_kg__isnull=False).first()
            return row.weight_kg if row else None
        if self.metric == self.Metric.BLOOD_SUGAR:
            row = VitalRecord.objects.filter(patient=self.patient, blood_sugar__isnull=False).first()
            return row.blood_sugar if row else None
        if self.metric == self.Metric.STEPS:
            row = LifestyleLog.objects.filter(patient=self.patient, steps__isnull=False).first()
            return row.steps if row else None
        if self.metric == self.Metric.SLEEP_HOURS:
            row = LifestyleLog.objects.filter(patient=self.patient, sleep_hours__isnull=False).first()
            return row.sleep_hours if row else None
        return None

    def progress(self):
        """
        {'current_value', 'on_target', 'explanation'} built from real data,
        or None when there is nothing recorded yet for this metric --
        never a guessed number.
        """
        current = self._latest_value()
        if current is None:
            return None
        current = float(current)
        target = float(self.target_value)
        if self.target_direction == self.Direction.BELOW:
            on_target = current <= target
            explanation = f"{current:g} is {'at or below' if on_target else 'above'} the target of {target:g}."
        elif self.target_direction == self.Direction.ABOVE:
            on_target = current >= target
            explanation = f"{current:g} is {'at or above' if on_target else 'below'} the target of {target:g}."
        else:
            tolerance = max(target * 0.1, 1)
            on_target = abs(current - target) <= tolerance
            explanation = f"{current:g} is {'within' if on_target else 'outside'} range of the target {target:g}."
        return {'current_value': current, 'on_target': on_target, 'explanation': explanation}

    def __str__(self):
        return f"{self.get_metric_display()} target for {self.patient} by {self.provider}"
