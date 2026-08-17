"""
Medication reminders, missed-dose alerts and restock warnings.

Three rules, all driven off `DoseTime` and `Medication.stock_on_hand`:

  1. REMINDER  -- the scheduled hour has arrived and the dose isn't ticked.
  2. MISSED    -- the grace period has passed and it still isn't ticked.
  3. RESTOCK   -- the supply will run out within the medication's threshold.

Every rule is idempotent. Each dose carries `reminded_at` and
`missed_alerted_at`, and each medication carries `restock_alerted_at`, so
running this a hundred times a day produces the same notifications as
running it once. That matters because it is called from two places: a
scheduled command, and page loads.

Nothing here invents a time. A medication whose written schedule could not
be parsed has no dose times, so it raises no reminders at all -- it is
flagged for the patient to fix instead.
"""
import datetime
from decimal import Decimal

from django.utils import timezone

from accounts.models import Notification, User
from health.models import DoseTime, Medication, MedicationDose


# Don't nag about the same medicine running low more than once a day.
RESTOCK_QUIET_PERIOD = datetime.timedelta(hours=20)


def _n(value):
    """Format a quantity for a human: 1 not 1.00, 0.5 not 0.50."""
    if value is None:
        return '0'
    text = str(Decimal(value).normalize())
    # Decimal normalises 10 to '1E+1', which is not what anyone wants to read.
    return format(Decimal(text), 'f')


def ensure_dose_rows(patient=None, on_date=None):
    """
    Make sure today's tick-boxes exist.

    A dose row per (medication, date, dose time) is what both the
    medications page and the alert rules read, so it has to exist before
    either runs. Doing it here rather than in the view means the scheduled
    command works even if the patient never opens the app.
    """
    on_date = on_date or timezone.localdate()
    meds = Medication.objects.filter(active=True).prefetch_related('dose_times')
    if patient is not None:
        meds = meds.filter(patient=patient)

    created = 0
    for med in meds:
        if med.start_date > on_date:
            continue
        # A finished course stops generating doses.
        if med.duration_days:
            last_day = med.start_date + datetime.timedelta(days=med.duration_days - 1)
            if on_date > last_day:
                continue
        for dose_time in med.dose_times.all():
            _, made = MedicationDose.objects.get_or_create(
                medication=med, dose_time=dose_time, date=on_date)
            created += int(made)
    return created


def run_medication_alerts(patient=None, now=None):
    """
    Raise any reminders, missed-dose alerts and restock warnings that are due.

    Returns a dict of counts, which the management command prints.
    """
    now = now or timezone.now()
    today = timezone.localdate()
    ensure_dose_rows(patient=patient, on_date=today)

    counts = {'reminders': 0, 'missed': 0, 'restock': 0}
    counts['reminders'] += _reminders(patient, now, today)
    counts['missed'] += _missed(patient, now, today)
    counts['restock'] += _restock(patient, now)
    return counts


# --------------------------------------------------------------------------
# 1. It's time to take this
# --------------------------------------------------------------------------

def _reminders(patient, now, today):
    doses = (MedicationDose.objects
             .filter(date=today, taken=False, reminded_at__isnull=True,
                     dose_time__isnull=False, medication__active=True)
             .select_related('medication', 'dose_time', 'medication__patient'))
    if patient is not None:
        doses = doses.filter(medication__patient=patient)

    sent = 0
    for dose in doses:
        scheduled = dose.scheduled_at
        # Fire once the hour has arrived, but not for a dose so old that the
        # missed-dose rule should be handling it instead.
        if not (scheduled <= now < scheduled + dose.GRACE):
            continue
        med = dose.medication
        Notification.send(
            med.patient,
            title=f'Time for {med.name}',
            body=f'{dose.dose_time.get_slot_display()} dose '
                 f'({_n(dose.dose_time.quantity)} x {med.dose}) was due at '
                 f'{dose.dose_time.at_time:%H:%M}.',
            kind=Notification.Kind.ALERT,
            level=Notification.Level.ACTION,
            action_url_name='health_medications',
        )
        dose.reminded_at = now
        dose.save(update_fields=['reminded_at'])
        sent += 1
    return sent


# --------------------------------------------------------------------------
# 2. You missed this one
# --------------------------------------------------------------------------

def _missed(patient, now, today):
    # Yesterday is included so a dose missed late at night is still reported
    # the next morning rather than vanishing at midnight.
    since = today - datetime.timedelta(days=1)
    doses = (MedicationDose.objects
             .filter(date__gte=since, taken=False, missed_alerted_at__isnull=True,
                     dose_time__isnull=False, medication__active=True)
             .select_related('medication', 'dose_time', 'medication__patient'))
    if patient is not None:
        doses = doses.filter(medication__patient=patient)

    sent = 0
    for dose in doses:
        if now < dose.scheduled_at + dose.GRACE:
            continue
        med = dose.medication
        Notification.send(
            med.patient,
            title=f'Missed dose — {med.name}',
            body=f'The {dose.dose_time.get_slot_display().lower()} dose due at '
                 f'{dose.dose_time.at_time:%H:%M} on {dose.date:%d %b} was not ticked off. '
                 'Mark it if you did take it.',
            kind=Notification.Kind.ALERT,
            level=Notification.Level.WARNING,
            action_url_name='health_medications',
        )
        dose.missed_alerted_at = now
        dose.save(update_fields=['missed_alerted_at'])
        sent += 1
    return sent


# --------------------------------------------------------------------------
# 3. You're about to run out
# --------------------------------------------------------------------------

def _restock(patient, now):
    meds = (Medication.objects
            .filter(active=True, stock_on_hand__isnull=False)
            .select_related('patient').prefetch_related('dose_times'))
    if patient is not None:
        meds = meds.filter(patient=patient)

    sent = 0
    for med in meds:
        if not med.is_low_stock:
            continue
        if med.restock_alerted_at and now - med.restock_alerted_at < RESTOCK_QUIET_PERIOD:
            continue

        days = med.days_of_stock_left
        if med.is_out_of_stock:
            title = f'Out of stock — {med.name}'
            body = 'You have none left. Arrange a refill before the next dose.'
        else:
            title = f'Running low — {med.name}'
            body = (f'About {days} day{"s" if days != 1 else ""} left '
                    f'({_n(med.stock_on_hand)} remaining, {_n(med.daily_quantity)} a day). '
                    f'Expected to run out on {med.projected_runout_date:%d %b}.')

        Notification.send(
            med.patient, title=title, body=body,
            kind=Notification.Kind.ALERT,
            level=Notification.Level.WARNING,
            action_url_name='health_medications',
        )
        med.restock_alerted_at = now
        med.save(update_fields=['restock_alerted_at'])
        sent += 1
    return sent


# --------------------------------------------------------------------------
# What the medications page shows at the top
# --------------------------------------------------------------------------

def today_summary(patient):
    """Due now / missed / upcoming counts, for the patient's own screens."""
    today = timezone.localdate()
    doses = (MedicationDose.objects
             .filter(medication__patient=patient, date=today,
                     dose_time__isnull=False, medication__active=True)
             .select_related('dose_time', 'medication'))
    due = [d for d in doses if d.is_due]
    missed = [d for d in doses if d.is_missed]
    upcoming = [d for d in doses if d.is_upcoming]
    low_stock = [m for m in Medication.objects.filter(patient=patient, active=True)
                 .prefetch_related('dose_times') if m.is_low_stock]
    return {
        'due': due, 'missed': missed, 'upcoming': upcoming,
        'taken': [d for d in doses if d.taken],
        'low_stock': low_stock,
        'total': doses.count(),
    }
