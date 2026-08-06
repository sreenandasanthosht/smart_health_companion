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
    class ServiceGroup(models.TextChoices):
        """
        Providers are grouped by what a patient *does* with them, not by
        what they are called. Each group gets its own dashboard, because
        each group has a genuinely different core flow. Similar providers
        (a gym, a dietician and a yoga centre all run programmes) share
        one dashboard rather than getting three near-identical copies.
        """
        CLINICAL = 'CLINICAL', 'Clinical Care'
        MENTAL_HEALTH = 'MENTAL_HEALTH', 'Mental Health'
        DIAGNOSTICS = 'DIAGNOSTICS', 'Diagnostics'
        PHARMACY = 'PHARMACY', 'Pharmacy'
        WELLNESS = 'WELLNESS', 'Wellness Programmes'
        HOME_CARE = 'HOME_CARE', 'Home Care'

    class ProviderType(models.TextChoices):
        CLINIC = 'CLINIC', 'Small Clinic'
        HOSPITAL = 'HOSPITAL', 'Small Hospital'
        PSYCHOLOGIST = 'PSYCHOLOGIST', 'Psychologist / Counsellor'
        DIAGNOSTIC_LAB = 'DIAGNOSTIC_LAB', 'Diagnostic Lab'
        PHARMACY = 'PHARMACY', 'Pharmacy'
        FITNESS_CENTRE = 'FITNESS_CENTRE', 'Fitness Centre / Gym'
        DIETICIAN = 'DIETICIAN', 'Dietician / Nutritionist'
        YOGA_CENTRE = 'YOGA_CENTRE', 'Yoga Centre'
        HOME_NURSE = 'HOME_NURSE', 'Home Nurse Provider'

    # The single source of truth for the grouping. Everything else --
    # dashboard routing, the directory filter, the sidebar -- reads this,
    # so adding a provider type is a one-line change here.
    GROUP_OF_TYPE = {
        ProviderType.CLINIC: ServiceGroup.CLINICAL,
        ProviderType.HOSPITAL: ServiceGroup.CLINICAL,
        ProviderType.PSYCHOLOGIST: ServiceGroup.MENTAL_HEALTH,
        ProviderType.DIAGNOSTIC_LAB: ServiceGroup.DIAGNOSTICS,
        ProviderType.PHARMACY: ServiceGroup.PHARMACY,
        ProviderType.FITNESS_CENTRE: ServiceGroup.WELLNESS,
        ProviderType.DIETICIAN: ServiceGroup.WELLNESS,
        ProviderType.YOGA_CENTRE: ServiceGroup.WELLNESS,
        ProviderType.HOME_NURSE: ServiceGroup.HOME_CARE,
    }

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

    # ---- service grouping -------------------------------------------------

    @property
    def service_group(self):
        """Which of the six provider modules this profile belongs to."""
        return self.GROUP_OF_TYPE.get(self.provider_type, self.ServiceGroup.CLINICAL)

    @property
    def service_group_label(self):
        return self.ServiceGroup(self.service_group).label

    @classmethod
    def types_in_group(cls, group):
        """The provider types that belong to one service group."""
        return [t for t, g in cls.GROUP_OF_TYPE.items() if g == group]

    @property
    def is_hospital(self):
        """Only small hospitals get departments; a small clinic does not."""
        return self.provider_type == self.ProviderType.HOSPITAL

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

    # Clinical Care module additions. All optional, so every appointment
    # booked before this existed stays valid.
    department = models.ForeignKey(
        'Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='appointments',
        help_text='Small hospitals only -- which department the visit is under.')
    service = models.ForeignKey(
        'ServiceOffering', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='appointments')
    diagnosis = models.CharField(max_length=200, blank=True)
    advice = models.TextField(blank=True)
    follow_up_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['scheduled_for']

    @property
    def is_upcoming(self):
        return self.scheduled_for >= timezone.now() and self.status in {
            self.Status.REQUESTED, self.Status.CONFIRMED,
        }

    def __str__(self):
        return f"{self.patient} with {self.provider} on {self.scheduled_for:%d %b %Y}"


# ==========================================================================
# Shared across every service group
# ==========================================================================

class ServiceOffering(models.Model):
    """
    One line on a provider's service list.

    Every group needs "here is what I offer and what it costs" -- a
    consultation, a blood test, a 12-week diet plan, a night nursing
    shift. Rather than four near-identical models, one model carries the
    common fields and each group's own model carries what is genuinely
    specific to it.
    """
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [('provider', 'name')]

    def __str__(self):
        return f"{self.name} ({self.provider.display_name()})"


# ==========================================================================
# 1. Clinical Care -- small clinics and small hospitals
# ==========================================================================

class Department(models.Model):
    """
    A department inside a small hospital.

    Deliberately the *only* thing that separates a small hospital from a
    small clinic in this project. Beds, admissions and inpatient billing
    are out of scope -- they are a system of their own and add nothing to
    the outpatient flow CareNest actually models.
    """
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    head_name = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=255, blank=True)
    consulting_hours = models.CharField(max_length=120, blank=True,
                                        help_text='e.g. Mon-Sat, 9:00 AM - 1:00 PM')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('provider', 'name')]

    def __str__(self):
        return f"{self.name} - {self.provider.display_name()}"


# ==========================================================================
# 2. Mental Health -- psychologists and counsellors
# ==========================================================================

class CounsellingSession(models.Model):
    """
    A counselling appointment, kept apart from `Appointment` on purpose.

    The consent rules here are different from every other provider: the
    patient's mood journal is structurally excluded from ordinary sharing,
    and session notes are more sensitive than a clinic's visit note.
    Giving mental health its own model keeps that exception in one place
    instead of spreading `if provider_type == PSYCHOLOGIST` branches
    through the clinical views.
    """
    class Mode(models.TextChoices):
        IN_PERSON = 'IN_PERSON', 'In person'
        VIDEO = 'VIDEO', 'Video call'
        PHONE = 'PHONE', 'Phone call'

    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='counselling_sessions')
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='counselling_sessions')
    scheduled_for = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=50)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.IN_PERSON)
    session_number = models.PositiveIntegerField(default=1)
    concern = models.CharField(max_length=200, blank=True,
                               help_text='What the patient wants to talk about, in their words.')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)

    # Never rendered on any patient- or caregiver-facing page. Only the
    # counsellor who wrote it can read it back.
    private_notes = models.TextField(blank=True)
    shared_summary = models.TextField(
        blank=True,
        help_text='The only part of a session the patient is shown.')
    follow_up_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_for']

    @property
    def is_upcoming(self):
        return self.scheduled_for >= timezone.now() and self.status in {
            self.Status.REQUESTED, self.Status.CONFIRMED,
        }

    def __str__(self):
        return f"Session {self.session_number} - {self.patient} ({self.get_status_display()})"


# ==========================================================================
# 3. Diagnostics -- diagnostic labs
# ==========================================================================

class LabTest(models.Model):
    """One test on a lab's catalogue."""
    class Category(models.TextChoices):
        BLOOD = 'BLOOD', 'Blood'
        URINE = 'URINE', 'Urine'
        IMAGING = 'IMAGING', 'Imaging / Scan'
        CARDIAC = 'CARDIAC', 'Cardiac'
        PACKAGE = 'PACKAGE', 'Health package'
        OTHER = 'OTHER', 'Other'

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='lab_tests')
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.BLOOD)
    sample_type = models.CharField(max_length=60, blank=True, help_text='e.g. Blood, Urine, N/A')
    preparation = models.CharField(max_length=200, blank=True,
                                   help_text='e.g. 10 hours fasting required')
    price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    report_hours = models.PositiveIntegerField(null=True, blank=True,
                                               help_text='Turnaround time in hours.')
    home_collection = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']
        unique_together = [('provider', 'name')]

    def __str__(self):
        return f"{self.name} - {self.provider.display_name()}"


class TestBooking(models.Model):
    """A patient's booking of one test, through to the released report."""
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COLLECTED = 'COLLECTED', 'Sample collected'
        READY = 'READY', 'Report ready'
        CANCELLED = 'CANCELLED', 'Cancelled'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='test_bookings')
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='test_bookings')
    test = models.ForeignKey(LabTest, on_delete=models.PROTECT, related_name='bookings')
    scheduled_for = models.DateTimeField()
    home_collection = models.BooleanField(default=False)
    collection_address = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    collected_at = models.DateTimeField(null=True, blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)
    summary = models.CharField(max_length=255, blank=True,
                               help_text="The lab's one-line interpretation.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_for']

    @property
    def is_reported(self):
        return self.status == self.Status.READY

    def release_report(self):
        self.status = self.Status.READY
        self.reported_at = timezone.now()
        self.save(update_fields=['status', 'reported_at'])

    def __str__(self):
        return f"{self.test.name} for {self.patient} ({self.get_status_display()})"


class TestResultValue(models.Model):
    """
    One measured value on a report.

    Results are stored as structured numbers, not as an uploaded PDF.
    That keeps the diagnostics module inside the project's
    process-and-discard rule -- there is no document to store -- and it
    lets a released result flow into the patient's existing trend charts
    instead of sitting in a file they have to open.
    """
    class Flag(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        LOW = 'LOW', 'Low'
        HIGH = 'HIGH', 'High'

    booking = models.ForeignKey(TestBooking, on_delete=models.CASCADE, related_name='values')
    analyte = models.CharField(max_length=100, help_text='e.g. Haemoglobin')
    value = models.CharField(max_length=40)
    unit = models.CharField(max_length=30, blank=True, help_text='e.g. g/dL')
    reference_range = models.CharField(max_length=60, blank=True, help_text='e.g. 12.0 - 15.5')
    flag = models.CharField(max_length=6, choices=Flag.choices, default=Flag.NORMAL)

    class Meta:
        ordering = ['analyte']

    def __str__(self):
        return f"{self.analyte}: {self.value} {self.unit}".strip()


# ==========================================================================
# 4. Pharmacy
# ==========================================================================

class MedicineOrder(models.Model):
    """
    A patient's order to a pharmacy.

    This is where the prescription extraction module pays off: the
    medicines a patient confirmed after OCR become the lines of an order,
    so nothing has to be typed twice.
    """
    class Status(models.TextChoices):
        PLACED = 'PLACED', 'Placed'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        PREPARING = 'PREPARING', 'Preparing'
        READY = 'READY', 'Ready'
        DISPATCHED = 'DISPATCHED', 'Dispatched'
        DELIVERED = 'DELIVERED', 'Delivered'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class Fulfilment(models.TextChoices):
        PICKUP = 'PICKUP', 'Collect from pharmacy'
        DELIVERY = 'DELIVERY', 'Home delivery'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medicine_orders')
    pharmacy = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='medicine_orders')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLACED)
    fulfilment = models.CharField(max_length=8, choices=Fulfilment.choices, default=Fulfilment.PICKUP)
    delivery_address = models.CharField(max_length=255, blank=True)
    prescription_reference = models.CharField(
        max_length=120, blank=True,
        help_text='Which prescription these medicines came from, if any.')
    patient_note = models.CharField(max_length=200, blank=True)
    pharmacy_note = models.CharField(max_length=200, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-placed_at']

    @property
    def total(self):
        return sum((line.line_total for line in self.items.all()), 0)

    @property
    def is_open(self):
        return self.status not in {
            self.Status.DELIVERED, self.Status.REJECTED, self.Status.CANCELLED,
        }

    def __str__(self):
        return f"Order #{self.pk} - {self.patient} ({self.get_status_display()})"


class OrderItem(models.Model):
    """One medicine on an order."""
    order = models.ForeignKey(MedicineOrder, on_delete=models.CASCADE, related_name='items')
    medicine_name = models.CharField(max_length=120)
    strength = models.CharField(max_length=60, blank=True, help_text='e.g. 500 mg')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    substitute_note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['medicine_name']

    @property
    def line_total(self):
        if self.unit_price is None:
            return 0
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.medicine_name} x{self.quantity}"


# ==========================================================================
# 5. Wellness Programmes -- gyms, dieticians, yoga centres
# ==========================================================================

class WellnessProgramme(models.Model):
    """
    A programme a wellness provider runs.

    A gym's training plan, a dietician's diet chart and a yoga centre's
    course are the same shape: enrol a client, run sessions over weeks,
    track progress. Only the *content* differs, which is what `kind` is
    for -- not three separate modules.
    """
    class Kind(models.TextChoices):
        FITNESS = 'FITNESS', 'Fitness / training plan'
        DIET = 'DIET', 'Diet / nutrition plan'
        YOGA = 'YOGA', 'Yoga course'
        GENERAL = 'GENERAL', 'General wellness'

    class Level(models.TextChoices):
        BEGINNER = 'BEGINNER', 'Beginner'
        INTERMEDIATE = 'INTERMEDIATE', 'Intermediate'
        ADVANCED = 'ADVANCED', 'Advanced'

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='programmes')
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.GENERAL)
    level = models.CharField(max_length=12, choices=Level.choices, default=Level.BEGINNER)
    description = models.TextField(blank=True)
    duration_weeks = models.PositiveIntegerField(default=4)
    sessions_per_week = models.PositiveIntegerField(default=3)
    fee = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [('provider', 'name')]

    @property
    def active_enrolments(self):
        return self.enrolments.filter(status=ProgrammeEnrolment.Status.ACTIVE).count()

    @property
    def seats_left(self):
        if self.capacity is None:
            return None
        return max(self.capacity - self.active_enrolments, 0)

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class ProgrammeEnrolment(models.Model):
    """A patient enrolled on one programme."""
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        DROPPED = 'DROPPED', 'Dropped out'
        DECLINED = 'DECLINED', 'Declined'

    programme = models.ForeignKey(WellnessProgramme, on_delete=models.CASCADE, related_name='enrolments')
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='programme_enrolments')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    goal = models.CharField(max_length=200, blank=True,
                            help_text="The client's own goal, e.g. 'lose 5 kg', 'reduce back pain'.")
    started_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    plan_notes = models.TextField(blank=True, help_text='The assigned diet chart / workout / asana routine.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('programme', 'patient')]

    @property
    def sessions_done(self):
        return self.sessions.count()

    @property
    def progress_percent(self):
        target = self.programme.duration_weeks * self.programme.sessions_per_week
        if not target:
            return 0
        return min(round(self.sessions_done / target * 100), 100)

    def __str__(self):
        return f"{self.patient} on {self.programme.name}"


class ProgrammeSession(models.Model):
    """One attended session, logged by the provider."""
    enrolment = models.ForeignKey(ProgrammeEnrolment, on_delete=models.CASCADE, related_name='sessions')
    on_date = models.DateField(default=timezone.localdate)
    duration_minutes = models.PositiveIntegerField(default=60)
    activity = models.CharField(max_length=200, blank=True,
                                help_text='What was covered in this session.')
    attended = models.BooleanField(default=True)
    trainer_note = models.CharField(max_length=200, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-on_date']

    def __str__(self):
        return f"{self.enrolment.patient} - {self.on_date:%d %b %Y}"


# ==========================================================================
# 6. Home Care -- home nurse providers
# ==========================================================================

class HomeCareStaff(models.Model):
    """
    A nurse employed by a home nurse provider.

    The `nursing` app already models what a nurse *does* at a patient's
    home. This model only records who employs them, so the agency can
    allocate its own staff instead of a platform administrator doing it.
    """
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='care_staff')
    nurse = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='home_care_employment')
    designation = models.CharField(max_length=80, blank=True,
                                   help_text='e.g. Registered Nurse, Home Attendant')
    qualification = models.CharField(max_length=120, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nurse__first_name']
        unique_together = [('provider', 'nurse')]

    def __str__(self):
        return f"{self.nurse.display_name} ({self.provider.display_name()})"


class HomeCareRequest(models.Model):
    """A patient's request for home nursing, and the staff assigned to it."""
    class CareType(models.TextChoices):
        ELDERLY = 'ELDERLY', 'Elderly care'
        POST_OP = 'POST_OP', 'Post-operative care'
        CHRONIC = 'CHRONIC', 'Chronic illness care'
        PALLIATIVE = 'PALLIATIVE', 'Palliative care'
        MOTHER_BABY = 'MOTHER_BABY', 'Mother and baby care'
        OTHER = 'OTHER', 'Other'

    class Shift(models.TextChoices):
        DAY = 'DAY', 'Day (12 hours)'
        NIGHT = 'NIGHT', 'Night (12 hours)'
        FULL = 'FULL', 'Full day (24 hours)'
        VISIT = 'VISIT', 'Short visit'

    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        ASSIGNED = 'ASSIGNED', 'Nurse assigned'
        ONGOING = 'ONGOING', 'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='home_care_requests')
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='home_care_requests')
    care_type = models.CharField(max_length=12, choices=CareType.choices, default=CareType.ELDERLY)
    shift = models.CharField(max_length=6, choices=Shift.choices, default=Shift.DAY)
    starts_on = models.DateField()
    days_required = models.PositiveIntegerField(default=1)
    address = models.CharField(max_length=255, blank=True)
    requirements = models.CharField(max_length=255, blank=True,
                                    help_text='e.g. wound dressing, insulin, mobility support')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    assigned_staff = models.ForeignKey(HomeCareStaff, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='assignments')
    provider_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_open(self):
        return self.status in {self.Status.REQUESTED, self.Status.ASSIGNED, self.Status.ONGOING}

    def __str__(self):
        return f"{self.get_care_type_display()} for {self.patient} ({self.get_status_display()})"
