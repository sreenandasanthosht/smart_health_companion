"""
health app models -- the patient's health data (physical + mental) and the
consent records that control who else may see it.
"""
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
        LAB_REPORT = 'LAB', 'From a lab report'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vital_records')
    recorded_at = models.DateTimeField(default=timezone.now)
    # Optional since a lab report often carries a blood sugar or a weight
    # with no blood pressure on it at all. A reading with only the fields
    # the report actually contained is honest; inventing 0/0 would not be.
    bp_systolic = models.PositiveIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveIntegerField(null=True, blank=True)
    blood_sugar = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    heart_rate = models.PositiveIntegerField(null=True, blank=True)
    # Blood oxygen saturation, percent. Optional for the same reason every
    # other vital here is: a reading only ever carries what was actually
    # measured. Bounded 0-100 at the field level so a typo can't produce a
    # value compute_status() would silently misread (e.g. "990").
    spo2 = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Blood oxygen saturation (%)',
    )
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

        SpO2 is the one vital here where LOWER is worse, not higher --
        <90% is hypoxemia (treated the same as a HIGH-severity reading),
        90-94% is a WATCH-worthy value on its own even with every other
        vital normal (per standard pulse-oximetry guidance). A missing
        SpO2 reading never contributes to either branch.
        """
        sys_bp = self.bp_systolic or 0
        dia_bp = self.bp_diastolic or 0
        sugar = float(self.blood_sugar) if self.blood_sugar is not None else 0.0

        if (sys_bp >= 140 or dia_bp >= 90
                or (self.heart_rate and self.heart_rate >= 110)
                or sugar >= 180
                or (self.spo2 is not None and self.spo2 < 90)):
            return self.Status.HIGH
        if (sys_bp >= 130 or dia_bp >= 85
                or (self.heart_rate and self.heart_rate >= 100)
                or sugar >= 126
                or (self.spo2 is not None and self.spo2 < 95)):
            return self.Status.WATCH
        return self.Status.NORMAL

    @property
    def bp_display(self):
        """'120/80', or a dash when this reading carried no blood pressure."""
        if self.bp_systolic is None or self.bp_diastolic is None:
            return '—'
        return f'{self.bp_systolic}/{self.bp_diastolic}'

    @property
    def has_bp(self):
        return self.bp_systolic is not None and self.bp_diastolic is not None

    def save(self, *args, **kwargs):
        self.status = self.compute_status()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} -- {self.recorded_at:%d %b %Y}"


class Medication(models.Model):
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=120)
    dose = models.CharField(max_length=60)
    # The schedule as it was written on the prescription. Kept for display
    # and for the patient to check against; the machine-readable version
    # lives in the related `DoseTime` rows.
    schedule = models.CharField(max_length=120)
    start_date = models.DateField()
    next_refill_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    # ---- course length and stock, which is what makes a restock alert
    # possible. Without a quantity there is nothing to count down.
    duration_days = models.PositiveIntegerField(
        null=True, blank=True, help_text='How many days the course runs, if it is time-limited.')
    quantity_dispensed = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True,
        help_text='How many tablets/units were handed over.')
    stock_on_hand = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True,
        help_text='How many are left at home right now. Counts down as doses are taken.')
    restock_threshold_days = models.PositiveIntegerField(
        default=3, help_text='Warn this many days before the supply runs out.')

    # Set when a written schedule could not be read into dose times. The
    # medications page asks the patient to fix these, rather than the app
    # quietly reminding at the wrong hour.
    needs_schedule_review = models.BooleanField(default=False)
    # Stops the low-stock warning being raised again every time a page loads.
    restock_alerted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']

    # ---- scheduling ------------------------------------------------------

    @property
    def daily_quantity(self):
        """Units consumed per day across all dose times."""
        return sum((dt.quantity for dt in self.dose_times.all()), Decimal('0'))

    @property
    def doses_per_day(self):
        return self.dose_times.count()

    @property
    def has_schedule(self):
        return self.dose_times.exists()

    # ---- stock -----------------------------------------------------------

    @property
    def days_of_stock_left(self):
        """
        Whole days of supply remaining, or None when it cannot be known.

        Returns None rather than 0 when stock or the schedule is missing --
        "we don't know" and "you have run out" are different answers and
        must not be shown as the same thing.
        """
        if self.stock_on_hand is None:
            return None
        per_day = self.daily_quantity
        if per_day <= 0:
            return None
        return int(self.stock_on_hand // per_day)

    @property
    def projected_runout_date(self):
        days = self.days_of_stock_left
        if days is None:
            return None
        return timezone.localdate() + datetime.timedelta(days=days)

    @property
    def is_low_stock(self):
        days = self.days_of_stock_left
        return days is not None and days <= self.restock_threshold_days

    @property
    def is_out_of_stock(self):
        return self.stock_on_hand is not None and self.stock_on_hand <= 0

    def recompute_refill_date(self, save=True):
        """
        Derive the refill date from stock and consumption.

        `next_refill_date` used to be a date somebody typed. Now it is the
        day the supply is projected to run out, so it cannot drift out of
        step with what has actually been taken.
        """
        projected = self.projected_runout_date
        if projected and projected != self.next_refill_date:
            self.next_refill_date = projected
            if save:
                self.save(update_fields=['next_refill_date'])
        return self.next_refill_date

    def consume(self, quantity, save=True):
        """Take `quantity` units out of stock, never going below zero."""
        if self.stock_on_hand is None:
            return
        self.stock_on_hand = max(self.stock_on_hand - Decimal(quantity), Decimal('0'))
        if save:
            self.save(update_fields=['stock_on_hand'])
            self.recompute_refill_date()

    def restore(self, quantity, save=True):
        """Put `quantity` units back -- used when a dose tick is undone."""
        if self.stock_on_hand is None:
            return
        self.stock_on_hand = self.stock_on_hand + Decimal(quantity)
        if save:
            self.save(update_fields=['stock_on_hand'])
            self.recompute_refill_date()

    def set_schedule_from_text(self, text=None):
        """
        Rebuild this medication's dose times from a written schedule.

        Returns the `ParsedSchedule` so the caller can tell the patient what
        happened. A schedule that could not be read leaves the medication
        with no dose times and `needs_schedule_review` set -- never with
        guessed ones.
        """
        from health import schedules

        parsed = schedules.parse_schedule(text if text is not None else self.schedule)
        self.dose_times.all().delete()
        if parsed.confident and parsed.slots:
            for slot, quantity in parsed.slots.items():
                DoseTime.objects.create(
                    medication=self, slot=slot,
                    at_time=DoseTime.DEFAULT_TIMES[slot], quantity=quantity)
            self.needs_schedule_review = False
        else:
            self.needs_schedule_review = True
        self.save(update_fields=['needs_schedule_review'])
        return parsed

    def __str__(self):
        return f"{self.name} ({self.patient})"


class DoseTime(models.Model):
    """
    One time of day this medicine is taken, and how much.

    This is the piece that makes reminders possible. "1-0-1" becomes two
    rows -- morning 08:00 x1 and night 21:00 x1 -- and each row is what an
    alert fires against.
    """
    class Slot(models.TextChoices):
        MORNING = 'MORNING', 'Morning'
        AFTERNOON = 'AFTERNOON', 'Afternoon'
        EVENING = 'EVENING', 'Evening'
        NIGHT = 'NIGHT', 'Night'

    # Sensible starting times. The patient can change any of them; nobody
    # should have to accept 8 AM because the software said so.
    DEFAULT_TIMES = {
        Slot.MORNING: datetime.time(8, 0),
        Slot.AFTERNOON: datetime.time(13, 0),
        Slot.EVENING: datetime.time(18, 0),
        Slot.NIGHT: datetime.time(21, 0),
    }

    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name='dose_times')
    slot = models.CharField(max_length=10, choices=Slot.choices)
    at_time = models.TimeField()
    quantity = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1'))

    class Meta:
        ordering = ['at_time']
        unique_together = [('medication', 'slot')]

    def scheduled_datetime(self, on_date=None):
        """This dose time as an aware datetime on a given date."""
        on_date = on_date or timezone.localdate()
        naive = datetime.datetime.combine(on_date, self.at_time)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def __str__(self):
        return f"{self.medication.name} {self.get_slot_display()} {self.at_time:%H:%M}"


class MedicationDose(models.Model):
    """
    One 'taken / missed' tick for a medication at one time on one day.

    This used to be one row per medication per *day*, which meant a
    medicine taken three times a day could only be ticked once -- so
    adherence was wrong and a missed evening dose was invisible. It is now
    one row per dose time, which is also what the reminder fires against.

    `dose_time` is nullable so the rows recorded under the old one-per-day
    scheme survive the change instead of being thrown away.
    """
    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name='doses')
    dose_time = models.ForeignKey(DoseTime, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name='doses')
    date = models.DateField(default=timezone.localdate)
    taken = models.BooleanField(default=False)
    taken_at = models.DateTimeField(null=True, blank=True)

    # Stamps so a reminder and a missed-dose alert are each raised once,
    # however many times the alert job runs.
    reminded_at = models.DateTimeField(null=True, blank=True)
    missed_alerted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('medication', 'date', 'dose_time')]
        ordering = ['-date']

    # How long after the scheduled time a dose is still "due" rather than
    # "missed". Two hours is forgiving enough for a real morning.
    GRACE = datetime.timedelta(hours=2)

    @property
    def scheduled_at(self):
        if self.dose_time is None:
            return None
        return self.dose_time.scheduled_datetime(self.date)

    @property
    def is_due(self):
        """Time to take it: the hour has arrived but the grace period hasn't run out."""
        when = self.scheduled_at
        if when is None or self.taken:
            return False
        return when <= timezone.now() < when + self.GRACE

    @property
    def is_missed(self):
        when = self.scheduled_at
        if when is None or self.taken:
            return False
        return timezone.now() >= when + self.GRACE

    @property
    def is_upcoming(self):
        when = self.scheduled_at
        if when is None or self.taken:
            return False
        return timezone.now() < when

    def mark_taken(self):
        self.taken = True
        self.taken_at = timezone.now()
        self.save(update_fields=['taken', 'taken_at'])
        if self.dose_time:
            self.medication.consume(self.dose_time.quantity)

    def mark_not_taken(self):
        self.taken = False
        self.taken_at = None
        self.save(update_fields=['taken', 'taken_at'])
        if self.dose_time:
            self.medication.restore(self.dose_time.quantity)

    def __str__(self):
        label = self.dose_time.get_slot_display() if self.dose_time else 'day'
        return f"{self.medication.name} {label} on {self.date} ({'taken' if self.taken else 'not taken'})"


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


class HealthDocument(models.Model):
    """
    A document the patient holds against their own record -- a lab result,
    a discharge summary, a scan.

    Both specs treat these as sensitive: the onboarding flow lists "health
    documents" among the things a patient adds *later*, at their own pace,
    and the caregiver proposal names Health Documents and Medical Reports
    as restricted items that stay hidden without an explicit grant. They
    are therefore covered only by the DOCUMENTS / REPORTS scopes, never by
    the baseline consent an approved caregiver link creates.
    """
    class Kind(models.TextChoices):
        REPORT = 'REPORT', 'Medical report'
        LAB = 'LAB', 'Lab result'
        PRESCRIPTION = 'PRESCRIPTION', 'Prescription'
        SCAN = 'SCAN', 'Scan / imaging'
        OTHER = 'OTHER', 'Other'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.OTHER)
    note = models.CharField(max_length=255, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def is_report(self):
        """Reports and labs sit behind the REPORTS scope; the rest behind DOCUMENTS."""
        return self.kind in {self.Kind.REPORT, self.Kind.LAB}

    def __str__(self):
        return f"{self.title} ({self.patient})"


class ConsentGrant(models.Model):
    """
    The `Consent` entity from CONSENT_FRAMEWORK_DESIGN.md section 3.

    One row per grant. Scope is per-category (section 2), always scoped to
    one named recipient (never "anyone"), and either open-ended or
    time-boxed. Revoking sets `revoked_at` rather than deleting the row, so
    the audit trail shows both the grant and the withdrawal.
    """
    class Scope(models.TextChoices):
        # --- Standard categories a patient can share ---
        VITALS = 'VITALS', 'Vital signs'
        MEDICATIONS = 'MEDICATIONS', 'Medication status'
        APPOINTMENTS = 'APPOINTMENTS', 'Appointments'
        ALERTS = 'ALERTS', 'Health alerts'
        EMERGENCY = 'EMERGENCY', 'Emergency contacts'
        LIFESTYLE = 'LIFESTYLE', 'Lifestyle tracking'
        # --- Restricted categories: hidden unless explicitly granted ---
        RECORDS = 'RECORDS', 'Lab / prescription records'
        DOCUMENTS = 'DOCUMENTS', 'Health documents'
        REPORTS = 'REPORTS', 'Medical reports'
        AI_SUMMARY = 'AI_SUMMARY', 'AI health summary'
        # NOTE: there is intentionally no MENTAL_HEALTH scope.

    # The Caregiver Module proposal splits permissions into two tiers: the
    # everyday ones a patient is likely to hand over, and the sensitive
    # ones that "remain hidden unless permission is granted". The UI reads
    # these two lists so the split is declared once, here.
    STANDARD_SCOPES = [
        Scope.VITALS, Scope.MEDICATIONS, Scope.APPOINTMENTS,
        Scope.ALERTS, Scope.EMERGENCY, Scope.LIFESTYLE,
    ]
    RESTRICTED_SCOPES = [
        Scope.RECORDS, Scope.DOCUMENTS, Scope.REPORTS, Scope.AI_SUMMARY,
    ]

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consents_given')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='consents_received')
    scope_vitals = models.BooleanField(default=True)
    scope_medications = models.BooleanField(default=True)
    scope_appointments = models.BooleanField(default=False)
    scope_alerts = models.BooleanField(default=False)
    scope_emergency = models.BooleanField(default=False)
    scope_lifestyle = models.BooleanField(default=False)
    # Restricted -- never on by default, including for an approved caregiver.
    scope_records = models.BooleanField(default=False)
    scope_documents = models.BooleanField(default=False)
    scope_reports = models.BooleanField(default=False)
    scope_ai_summary = models.BooleanField(default=False)
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
        """Human-readable names of every category this grant covers."""
        return [
            self.Scope(scope).label
            for scope, field in SCOPE_FIELDS.items()
            if getattr(self, field, False)
        ]

    def restricted_scope_list(self):
        """Only the sensitive categories -- shown separately in the UI."""
        return [
            self.Scope(scope).label
            for scope in self.RESTRICTED_SCOPES
            if getattr(self, SCOPE_FIELDS[scope], False)
        ]

    def covers(self, scope):
        """True if this grant includes `scope` (ignoring expiry/revocation)."""
        field = SCOPE_FIELDS.get(scope)
        return bool(field and getattr(self, field, False))

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


# The single mapping from a Scope value to the boolean column that stores
# it. Everything else -- the grant form, scope_list(), has_consent() --
# derives from this, so adding a category means editing one place.
SCOPE_FIELDS = {
    ConsentGrant.Scope.VITALS: 'scope_vitals',
    ConsentGrant.Scope.MEDICATIONS: 'scope_medications',
    ConsentGrant.Scope.APPOINTMENTS: 'scope_appointments',
    ConsentGrant.Scope.ALERTS: 'scope_alerts',
    ConsentGrant.Scope.EMERGENCY: 'scope_emergency',
    ConsentGrant.Scope.LIFESTYLE: 'scope_lifestyle',
    ConsentGrant.Scope.RECORDS: 'scope_records',
    ConsentGrant.Scope.DOCUMENTS: 'scope_documents',
    ConsentGrant.Scope.REPORTS: 'scope_reports',
    ConsentGrant.Scope.AI_SUMMARY: 'scope_ai_summary',
}


def has_consent(patient, recipient, scope):
    """
    The enforcement check from CONSENT_FRAMEWORK_DESIGN.md section 5.

    Returns True if an un-revoked, un-expired grant exists covering
    (patient, recipient, scope). Mental health is never covered here --
    there is no scope value that can return True for it.
    """
    field = SCOPE_FIELDS.get(scope)
    if field is None:
        return False
    now = timezone.now()
    return ConsentGrant.objects.filter(
        patient=patient, recipient=recipient, revoked_at__isnull=True, **{field: True},
    ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)).exists()


def consent_matrix(patient, recipient):
    """
    Every scope resolved in one pass, as {Scope value: bool}.

    A caregiver dashboard needs to know about eight or nine categories at
    once; asking has_consent() once per category would be eight queries
    for what is really one question.
    """
    now = timezone.now()
    grants = ConsentGrant.objects.filter(
        patient=patient, recipient=recipient, revoked_at__isnull=True,
    ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))
    matrix = {scope: False for scope in SCOPE_FIELDS}
    for grant in grants:
        for scope, field in SCOPE_FIELDS.items():
            if getattr(grant, field, False):
                matrix[scope] = True
    return matrix


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


class ExtractionJob(models.Model):
    """
    One prescription / lab-report upload, processed and discarded.

    The uploaded FILE is never written to storage. It is read into memory,
    OCR'd, parsed, and the bytes go out of scope when the request ends.
    Only the structured result and a short audit record persist.

    `raw_text` holds the OCR output while the patient verifies it, and is
    cleared the moment they confirm or discard -- so even the transcribed
    text does not linger after it has served its purpose.
    """
    class Source(models.TextChoices):
        PRESCRIPTION = 'PRESCRIPTION', 'Prescription'
        LAB_REPORT = 'LAB_REPORT', 'Lab report'

    class Status(models.TextChoices):
        EXTRACTED = 'EXTRACTED', 'Awaiting verification'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        DISCARDED = 'DISCARDED', 'Discarded'
        FAILED = 'FAILED', 'Extraction failed'

    class Parser(models.TextChoices):
        LLM = 'LLM', 'LLM'
        RULES = 'RULES', 'Rule-based'
        NONE = 'NONE', 'None'

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='extraction_jobs')
    source_type = models.CharField(max_length=12, choices=Source.choices, default=Source.PRESCRIPTION)
    # Filename only, never a path -- we keep it so the patient can recognise
    # which upload this was, not so the file can be found again.
    original_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.EXTRACTED)
    raw_text = models.TextField(blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)
    # Which parser produced the result. Recorded so the report can compare
    # LLM extraction against the rule-based baseline on the same documents.
    parser_used = models.CharField(max_length=6, choices=Parser.choices, default=Parser.NONE)
    parser_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Proof of the process-and-discard promise: set the moment the in-memory
    # bytes are released, which is before the response is returned.
    file_deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def clear_text(self):
        """Drop the transcribed text once it is no longer needed."""
        if self.raw_text:
            self.raw_text = ''
            self.save(update_fields=['raw_text'])

    def __str__(self):
        return f"{self.get_source_type_display()} for {self.patient} ({self.status})"


class LabReport(models.Model):
    """
    A lab report the patient has confirmed, minus the report itself.

    The uploaded image is discarded exactly as a prescription's is. What
    persists is the structured values, which is the whole point: a number
    in a table can be charted and compared, where a stored PDF can only be
    opened and squinted at.
    """
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='lab_reports')
    reported_on = models.DateField(default=timezone.localdate)
    lab_name = models.CharField(max_length=150, blank=True)
    note = models.CharField(max_length=255, blank=True)
    # Set when some values on this report were routed into vitals tracking
    # instead of being kept here, so the patient can see where they went.
    vitals_record = models.ForeignKey(
        'VitalRecord', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_lab_reports')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reported_on', '-created_at']

    @property
    def abnormal_count(self):
        # UNKNOWN is not abnormal -- it means the report printed no range to
        # compare against. Counting it as a flag would tell the patient
        # something was wrong when nothing was actually assessed.
        return self.values.filter(
            flag__in=[LabResultValue.Flag.LOW, LabResultValue.Flag.HIGH]).count()

    def __str__(self):
        return f"Lab report for {self.patient} on {self.reported_on:%d %b %Y}"


class LabResultValue(models.Model):
    """
    One measured value on a confirmed lab report.

    Only values that are *not* vitals live here. Blood pressure, blood
    sugar, weight and pulse are written to `VitalRecord` instead, so they
    join the patient's existing trend charts rather than sitting in a
    second, parallel history of the same measurements.
    """
    class Flag(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        LOW = 'LOW', 'Low'
        HIGH = 'HIGH', 'High'
        UNKNOWN = 'UNKNOWN', 'Not known'

    report = models.ForeignKey(LabReport, on_delete=models.CASCADE, related_name='values')
    analyte = models.CharField(max_length=120)
    value = models.CharField(max_length=40)
    unit = models.CharField(max_length=30, blank=True)
    reference_range = models.CharField(max_length=60, blank=True)
    flag = models.CharField(max_length=8, choices=Flag.choices, default=Flag.UNKNOWN)

    class Meta:
        ordering = ['analyte']

    @property
    def is_abnormal(self):
        return self.flag in {self.Flag.LOW, self.Flag.HIGH}

    def __str__(self):
        return f"{self.analyte}: {self.value} {self.unit}".strip()


class ExtractedLabValue(models.Model):
    """
    One value read off a lab report, pending the patient's confirmation.

    The lab-report equivalent of `ExtractedMedication`. `vital_field`
    records which `VitalRecord` column this value would be written to, and
    is empty for everything that is not a vital -- that single field is
    what splits the two destinations at confirmation time.
    """
    job = models.ForeignKey(ExtractionJob, on_delete=models.CASCADE, related_name='lab_values')
    analyte = models.CharField(max_length=120)
    value = models.CharField(max_length=40)
    unit = models.CharField(max_length=30, blank=True)
    reference_range = models.CharField(max_length=60, blank=True)
    flag = models.CharField(max_length=8, choices=LabResultValue.Flag.choices,
                            default=LabResultValue.Flag.UNKNOWN)
    vital_field = models.CharField(
        max_length=20, blank=True,
        help_text="Which VitalRecord field this maps to, or blank if it is not a vital.")
    confidence = models.FloatField(default=0.0)
    confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-confidence', 'analyte']

    @property
    def is_vital(self):
        return bool(self.vital_field)

    def confidence_band(self):
        if self.confidence >= 0.8:
            return 'high'
        if self.confidence >= 0.5:
            return 'medium'
        return 'low'

    def __str__(self):
        return f"{self.analyte}: {self.value} {self.unit}".strip()


class ExtractedMedication(models.Model):
    """One medicine detected in an upload, pending the patient's confirmation."""
    job = models.ForeignKey(ExtractionJob, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=120)
    dose = models.CharField(max_length=60, blank=True)
    frequency = models.CharField(max_length=120, blank=True)
    duration = models.CharField(max_length=60, blank=True)
    # 0.0-1.0. Derived from which rule matched, or reported by the LLM.
    # Never invented: a field the parser could not read gets 0.0.
    confidence = models.FloatField(default=0.0)
    confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-confidence', 'name']

    def confidence_band(self):
        if self.confidence >= 0.8:
            return 'high'
        if self.confidence >= 0.5:
            return 'medium'
        return 'low'

    def __str__(self):
        return f"{self.name} {self.dose}".strip()
