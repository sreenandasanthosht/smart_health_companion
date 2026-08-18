"""
health app views -- patient-facing vitals, medications, lifestyle, mental
health, record sharing, and the caregiver's read-only view.

Everything here reads and writes real database rows. Nothing on these
pages is placeholder data any more.
"""
import calendar
import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.devices import current_device, device_is_trusted
from accounts.linking import create_link_request, resolve_patient
from accounts.models import (
    CaregiverInvite, CaregiverLink, Notification, TrustedDevice, User,
)
from adminpanel.models import AuditLog
from health import alerts
from health import analytics
from health import extraction
from health import labvalues
from health import schedules
from health.models import (
    ConsentGrant,
    DoseTime,
    ExtractedLabValue,
    ExtractedMedication,
    ExtractionJob,
    HealthDocument,
    LabReport,
    LabResultValue,
    LifestyleLog,
    Medication,
    MedicationDose,
    MoodLog,
    SCOPE_FIELDS,
    VitalRecord,
    consent_matrix,
    has_consent,
)

from providers.models import Appointment, CarePlan, ProviderProfile


def _refill_label(medication):
    if not medication.next_refill_date:
        return 'Not set'
    days_left = (medication.next_refill_date - timezone.localdate()).days
    if days_left < 0:
        return 'Overdue'
    if days_left == 0:
        return 'Today'
    return f"{days_left} days"


def _friendly_datetime(value):
    """
    Format a datetime as e.g. "4 Aug at 6:05 PM".

    Written without the %-d / %-I strftime flags: those strip leading zeros
    on Linux/macOS but raise ValueError('Invalid format string') on Windows.
    Building the no-leading-zero parts in Python keeps this working on any
    operating system.
    """
    if not value:
        return ''
    dt = timezone.localtime(value)          # settings.TIME_ZONE, since USE_TZ=True
    hour_12 = dt.hour % 12 or 12            # 0 -> 12 (midnight), 13 -> 1
    return f'{dt.day} {dt:%b} at {hour_12}:{dt:%M} {dt:%p}'


def _parse_decimal(raw):
    raw = (raw or '').strip()
    return float(raw) if raw else None


def _parse_int(raw):
    raw = (raw or '').strip()
    return int(raw) if raw else None


def _qty(raw):
    """
    A quantity as a Decimal, or None.

    Stock and dose quantities are Decimal columns, and mixing float with
    Decimal raises at runtime -- so these never go through `_parse_decimal`,
    which returns floats for the vitals forms. Bad input gives None rather
    than an exception.
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _safe_int(raw):
    raw = (raw or '').strip()
    return int(raw) if raw.isdigit() else None


# --------------------------------------------------------------------------
# Patient dashboard
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def dashboard(request):
    patient = request.user
    today = timezone.localdate()

    # Refresh the generated insights so the summary reflects current data.
    insights = analytics.generate_insights(patient)
    score, band = analytics.health_score(patient)
    series = analytics.vital_series(patient)

    # Today's medication doses -- one row per dose time, created here if the
    # scheduled alert command hasn't already made them, then any outstanding
    # reminders / missed-dose / restock notifications are raised.
    alerts.run_medication_alerts(patient=patient)
    todays_doses = (
        MedicationDose.objects.filter(medication__patient=patient, date=today,
                                      dose_time__isnull=False)
        .select_related('medication', 'dose_time')
        .order_by('dose_time__at_time', 'medication__name')
    )
    doses_due = todays_doses.filter(taken=False).count()
    med_summary = alerts.today_summary(patient)

    next_appointment = (
        Appointment.objects.filter(
            patient=patient, scheduled_for__gte=timezone.now(),
            status__in=[Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED],
        ).select_related('provider', 'provider__user').first()
    )

    upcoming_refill = (
        Medication.objects.filter(patient=patient, active=True, next_refill_date__isnull=False)
        .order_by('next_refill_date').first()
    )

    recent_vitals = VitalRecord.objects.filter(patient=patient)[:4]
    recent_moods = MoodLog.objects.filter(patient=patient)[:1]

    # Recent activity feed, merged from several sources.
    activity = []
    for v in VitalRecord.objects.filter(patient=patient)[:3]:
        activity.append({'icon': 'i-heart', 'tint': 'tint-green',
                         'title': f"Vitals logged -- {v.bp_display}",
                         'when': v.recorded_at})
    for d in MedicationDose.objects.filter(medication__patient=patient, taken=True).select_related('medication')[:3]:
        activity.append({'icon': 'i-pill', 'tint': 'tint-orange',
                         'title': f"Took {d.medication.name}",
                         'when': d.taken_at or timezone.now()})
    for a in Appointment.objects.filter(patient=patient).select_related('provider')[:2]:
        activity.append({'icon': 'i-calendar-check', 'tint': 'tint-purple',
                         'title': f"Appointment {a.get_status_display().lower()} -- {a.provider.display_name()}",
                         'when': a.created_at})
    activity.sort(key=lambda x: x['when'], reverse=True)

    # Lifestyle goals for today.
    lifestyle_today = LifestyleLog.objects.filter(patient=patient, date=today).first()

    def goal(value, target):
        if not value:
            return 0
        return min(100, int(round(float(value) / float(target) * 100)))

    goals = [
        {'name': 'Drink 2 litres of water', 'icon': 'i-droplet', 'colour': '#3b82f6',
         'value': f"{lifestyle_today.water_litres if lifestyle_today and lifestyle_today.water_litres else 0} / 2.0 L",
         'pct': goal(lifestyle_today.water_litres if lifestyle_today else 0, 2.0)},
        {'name': f'Walk {analytics.STEPS_TARGET:,} steps', 'icon': 'i-footprints', 'colour': '#22c55e',
         'value': f"{lifestyle_today.steps if lifestyle_today and lifestyle_today.steps else 0:,} / {analytics.STEPS_TARGET:,}",
         'pct': goal(lifestyle_today.steps if lifestyle_today else 0, analytics.STEPS_TARGET)},
        {'name': 'Sleep 7 hours', 'icon': 'i-moon', 'colour': '#8b5cf6',
         'value': f"{lifestyle_today.sleep_hours if lifestyle_today and lifestyle_today.sleep_hours else 0} / 7 h",
         'pct': goal(lifestyle_today.sleep_hours if lifestyle_today else 0, 7.0)},
        {'name': 'Take all medicines', 'icon': 'i-pill', 'colour': '#f59e0b',
         'value': f"{todays_doses.filter(taken=True).count()} / {todays_doses.count()}",
         'pct': goal(todays_doses.filter(taken=True).count(), max(1, todays_doses.count()))},
    ]

    context = {
        'patient': patient,
        'today': today,
        'insights': insights,
        'health_score': score,
        'health_band': band,
        # SVG ring: 195 is the full circumference; the offset is the unfilled part.
        'score_offset': int(195 - (195 * score / 100)),
        'series': series,
        'sparklines': {
            'bp': analytics.sparkline_path(series['bp']['points']),
            'heart_rate': analytics.sparkline_path(series['heart_rate']['points']),
            'blood_sugar': analytics.sparkline_path(series['blood_sugar']['points']),
            'weight': analytics.sparkline_path(series['weight']['points']),
        },
        'doses_due': doses_due,
        'todays_doses': todays_doses,
        'med_summary': med_summary,
        'next_appointment': next_appointment,
        'upcoming_refill': upcoming_refill,
        'recent_vitals': recent_vitals,
        'recent_mood': recent_moods[0] if recent_moods else None,
        'activity': activity[:5],
        'goals': goals,
        'adherence': analytics.medication_adherence(patient),
        'profile_completion': patient.profile_completion(),
        'missing_fields': patient.missing_profile_fields(),
        'show_profile_prompt': patient.profile_completion() < 100,
        'pending_caregivers': CaregiverLink.objects.filter(
            patient=patient, status=CaregiverLink.Status.PENDING).select_related('caregiver'),
        'care_plans': CarePlan.objects.filter(patient=patient, active=True).select_related('provider'),
        # Rule-plus-model recommendation engine (task 4.5). Patient-facing
        # only -- never routed into alerts, snapshots or any provider view.
        # Wrapped defensively: a missing/untrained model artifact must
        # degrade to "no suggestions shown", never break the dashboard.
        'suggestions': _safe_suggestions(patient),
    }
    return render(request, 'health/dashboard.html', context)


def _safe_suggestions(patient):
    try:
        from datascience.recommend import recommend_for_patient
        return recommend_for_patient(patient)
    except Exception:
        return []


# --------------------------------------------------------------------------
# Vitals
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def vitals(request):
    if request.method == 'POST':
        try:
            bp_raw = request.POST.get('bp', '')
            systolic_raw, sep, diastolic_raw = bp_raw.partition('/')
            if not sep:
                raise ValueError('Enter blood pressure as systolic/diastolic, for example 120/80.')
            bp_systolic = int(systolic_raw.strip())
            bp_diastolic = int(diastolic_raw.strip())
            blood_sugar = _parse_decimal(request.POST.get('blood_sugar'))
            weight_kg = _parse_decimal(request.POST.get('weight_kg'))
            heart_rate = _parse_int(request.POST.get('heart_rate'))
        except ValueError as exc:
            messages.error(request, str(exc) or 'Please check the values you entered.')
        else:
            record = VitalRecord.objects.create(
                patient=request.user,
                bp_systolic=bp_systolic, bp_diastolic=bp_diastolic,
                blood_sugar=blood_sugar, weight_kg=weight_kg, heart_rate=heart_rate,
                source=VitalRecord.Source.SELF, entered_by=request.user,
            )
            analytics.generate_insights(request.user)
            if record.status == VitalRecord.Status.HIGH:
                messages.warning(request, 'Reading saved -- it is outside the normal range, so it has been flagged as High.')
            else:
                messages.success(request, 'Vitals saved.')
        return redirect('health_vitals')

    records = VitalRecord.objects.filter(patient=request.user)[:20]
    series = analytics.vital_series(request.user)
    context = {
        'records': records,
        'series': series,
        'sparkline_bp': analytics.sparkline_path(series['bp']['points']),
        'sparkline_hr': analytics.sparkline_path(series['heart_rate']['points']),
    }
    return render(request, 'health/vitals.html', context)


# --------------------------------------------------------------------------
# Medications
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def medications(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'add')

        if action == 'toggle_dose':
            dose = get_object_or_404(MedicationDose, pk=request.POST.get('dose_id'),
                                     medication__patient=request.user)
            # mark_taken / mark_not_taken also move the stock count, which is
            # what makes the restock warning possible.
            if dose.taken:
                dose.mark_not_taken()
            else:
                dose.mark_taken()
            analytics.generate_insights(request.user)
            return redirect('health_medications')

        if action == 'stop':
            med = get_object_or_404(Medication, pk=request.POST.get('medication_id'), patient=request.user)
            med.active = False
            med.save(update_fields=['active'])
            messages.info(request, f'{med.name} marked as no longer active.')
            return redirect('health_medications')

        if action == 'set_times':
            med = get_object_or_404(Medication, pk=request.POST.get('medication_id'), patient=request.user)
            _save_dose_times(request, med)
            return redirect('health_medications')

        if action == 'update_stock':
            med = get_object_or_404(Medication, pk=request.POST.get('medication_id'), patient=request.user)
            stock = _qty(request.POST.get('stock_on_hand'))
            threshold = _safe_int(request.POST.get('restock_threshold_days'))
            med.stock_on_hand = stock
            if threshold and threshold > 0:
                med.restock_threshold_days = threshold
            # A fresh supply means the previous "running low" warning is
            # spent, so allow a new one to be raised when it next applies.
            med.restock_alerted_at = None
            med.save(update_fields=['stock_on_hand', 'restock_threshold_days', 'restock_alerted_at'])
            med.recompute_refill_date()
            messages.success(request, f'Stock updated for {med.name}.')
            return redirect('health_medications')

        name = request.POST.get('name', '').strip()
        dose_text = request.POST.get('dose', '').strip()
        schedule = request.POST.get('schedule', '').strip()
        start_date = request.POST.get('start_date', '').strip()

        # Two ways in, and the manual one wins. A patient who ticked the
        # times themselves has told us exactly what they want; there is no
        # reason to run their words through a parser as well.
        manual = _posted_dose_times(request)

        if not (name and dose_text and start_date):
            messages.error(request, 'Please fill in the medicine name, dose and start date.')
        elif not (schedule or manual):
            messages.error(request,
                           'Either write the schedule (e.g. 1-0-1) or set the times of day yourself.')
        else:
            try:
                start = datetime.date.fromisoformat(start_date)
            except ValueError:
                messages.error(request, 'Please enter a valid date.')
            else:
                med = Medication.objects.create(
                    patient=request.user, name=name, dose=dose_text,
                    schedule=schedule or _describe_slots(manual),
                    start_date=start,
                    duration_days=_safe_int(request.POST.get('duration_days')),
                    quantity_dispensed=_qty(request.POST.get('quantity_dispensed')),
                    stock_on_hand=_qty(request.POST.get('quantity_dispensed')),
                )

                if manual:
                    _save_dose_times(request, med, quiet=True)
                    med.refresh_from_db()
                    messages.success(
                        request,
                        f'{name} added — reminders set for {_describe_slots(manual)}.')
                else:
                    parsed = med.set_schedule_from_text()
                    if parsed.confident:
                        slot_names = ', '.join(
                            dt.get_slot_display() for dt in med.dose_times.all())
                        messages.success(
                            request, f'{name} added — reminders set for {slot_names}.')
                    else:
                        messages.warning(
                            request,
                            f'{name} added, but we could not work out the times from '
                            f'"{schedule}". Set them below so reminders can be sent.')
                med.recompute_refill_date()
        return redirect('health_medications')

    today = timezone.localdate()
    # Catch-up pass: the scheduled command is the real trigger, but this
    # means a patient who opens the page still sees anything outstanding
    # even if the scheduler isn't running on this machine.
    alerts.run_medication_alerts(patient=request.user)

    active_meds = list(
        Medication.objects.filter(patient=request.user, active=True)
        .prefetch_related('dose_times'))

    rows = []
    for med in active_meds:
        doses = list(MedicationDose.objects.filter(medication=med, date=today,
                                                   dose_time__isnull=False)
                     .select_related('dose_time').order_by('dose_time__at_time'))
        rows.append({
            'med': med,
            'refill_in': _refill_label(med),
            'doses': doses,
            'dose_times': list(med.dose_times.all()),
            'days_left': med.days_of_stock_left,
            'low_stock': med.is_low_stock,
        })

    context = {
        'rows': rows,
        'past': Medication.objects.filter(patient=request.user, active=False),
        'adherence': analytics.medication_adherence(request.user),
        'today': today,
        'summary': alerts.today_summary(request.user),
        'slots': DoseTime.Slot.choices,
        'needs_review': [r for r in rows if r['med'].needs_schedule_review],
    }
    return render(request, 'health/medications.html', context)


def _posted_dose_times(request):
    """
    The slots the patient set by hand on the form, as {slot: (time, qty)}.

    Empty when they left the times alone, which is how the view knows to
    fall back to reading the written schedule instead.
    """
    chosen = {}
    for slot, _label in DoseTime.Slot.choices:
        quantity = _qty(request.POST.get(f'qty_{slot}'))
        if not quantity or quantity <= 0:
            continue
        raw = (request.POST.get(f'time_{slot}') or '').strip()
        try:
            at_time = datetime.time.fromisoformat(raw) if raw else DoseTime.DEFAULT_TIMES[slot]
        except ValueError:
            at_time = DoseTime.DEFAULT_TIMES[slot]
        chosen[slot] = (at_time, quantity)
    return chosen


def _describe_slots(chosen):
    """'Morning 08:00, Night 21:00' -- used as the written schedule when the
    patient set the times by hand instead of typing one."""
    labels = dict(DoseTime.Slot.choices)
    ordered = [s for s, _ in DoseTime.Slot.choices if s in chosen]
    return ', '.join(f'{labels[s]} {chosen[s][0]:%H:%M}' for s in ordered)[:120]


def _save_dose_times(request, med, quiet=False):
    """
    Replace a medication's dose times from the times-of-day form.

    A slot counts as "on" when its quantity is greater than zero, so
    clearing the number is how a patient removes a dose time.
    """
    kept = 0
    for slot, _label in DoseTime.Slot.choices:
        quantity = _qty(request.POST.get(f'qty_{slot}')) or Decimal('0')
        time_raw = (request.POST.get(f'time_{slot}') or '').strip()
        if quantity <= 0:
            DoseTime.objects.filter(medication=med, slot=slot).delete()
            continue
        try:
            at_time = (datetime.time.fromisoformat(time_raw) if time_raw
                       else DoseTime.DEFAULT_TIMES[slot])
        except ValueError:
            at_time = DoseTime.DEFAULT_TIMES[slot]
        DoseTime.objects.update_or_create(
            medication=med, slot=slot,
            defaults={'at_time': at_time, 'quantity': quantity})
        kept += 1

    med.needs_schedule_review = kept == 0
    med.save(update_fields=['needs_schedule_review'])
    med.recompute_refill_date()

    if quiet:
        return
    if kept:
        messages.success(request, f'Reminder times saved for {med.name}.')
    else:
        messages.warning(request,
                         f'{med.name} now has no dose times, so no reminders will be sent.')


# --------------------------------------------------------------------------
# Lifestyle
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def lifestyle(request):
    if request.method == 'POST':
        date_raw = request.POST.get('date', '').strip()
        try:
            log_date = datetime.date.fromisoformat(date_raw) if date_raw else timezone.localdate()
            sleep = _parse_decimal(request.POST.get('sleep_hours'))
            water = _parse_decimal(request.POST.get('water_litres'))
            steps = _parse_int(request.POST.get('steps'))
        except ValueError:
            messages.error(request, 'Please check the values you entered.')
        else:
            LifestyleLog.objects.update_or_create(
                patient=request.user, date=log_date,
                defaults={
                    'sleep_hours': sleep, 'water_litres': water, 'steps': steps,
                    'activity_note': request.POST.get('activity_note', '').strip(),
                },
            )
            analytics.generate_insights(request.user)
            messages.success(request, 'Lifestyle entry saved.')
        return redirect('health_lifestyle')

    logs = LifestyleLog.objects.filter(patient=request.user)[:21]
    sleeps = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    waters = [l.water_litres for l in logs if l.water_litres is not None]
    steps_all = [l.steps for l in logs if l.steps is not None]

    context = {
        'logs': logs,
        'today': timezone.localdate().isoformat(),
        'avg_sleep': round(sum(sleeps) / len(sleeps), 1) if sleeps else None,
        'avg_water': round(sum(waters) / len(waters), 1) if waters else None,
        'avg_steps': int(sum(steps_all) / len(steps_all)) if steps_all else None,
    }
    return render(request, 'health/lifestyle.html', context)


# --------------------------------------------------------------------------
# Mental health -- private, never shareable
# --------------------------------------------------------------------------

# No emoji -- a colour + a soft pastel tint per mood, in the style of a
# calm, card-based mood tracker (think Flo's check-in screen): each mood
# gets a distinct colour identity that shows up as a soft background tint
# on its journal cards and a solid fill on the picker once selected.
MOOD_META = {
    'Good':     {'colour': '#16a34a', 'tint': '#e9f9ef'},
    'Calm':     {'colour': '#0d9488', 'tint': '#e6f7f4'},
    'Stressed': {'colour': '#d97706', 'tint': '#fdf2e3'},
    'Low':      {'colour': '#475569', 'tint': '#eef1f5'},
    'Anxious':  {'colour': '#dc2626', 'tint': '#fdecec'},
}
_DEFAULT_MOOD_META = {'colour': '#7c3aed', 'tint': '#f3effe'}


@role_required(User.Role.PATIENT)
def mental_health(request):
    if request.method == 'POST':
        mood = request.POST.get('mood', '').strip()
        if not mood:
            messages.error(request, 'Pick how you are feeling before saving.')
        else:
            MoodLog.objects.create(
                patient=request.user, date=timezone.localdate(),
                mood=mood, note=request.POST.get('note', '').strip(),
            )
            messages.success(request, 'Saved privately. Only you can see this.')
        return redirect('health_mental_health')

    entries = list(MoodLog.objects.filter(patient=request.user)[:30])
    counts = {}
    for e in entries:
        counts[e.mood] = counts.get(e.mood, 0) + 1
        e.meta = MOOD_META.get(e.mood, _DEFAULT_MOOD_META)

    # Group into a journal layout: one heading per day, entries for that day
    # underneath it, newest day first (entries already come newest-first).
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    days = []
    current_day = None
    for e in entries:
        if current_day is None or current_day['date'] != e.date:
            if e.date == today:
                label = 'Today'
            elif e.date == yesterday:
                label = 'Yesterday'
            else:
                # Formatted in the template (|date:"l, j F"), not with
                # strftime here -- %-d style no-leading-zero flags crash on
                # Windows, which is exactly how a past bug on this project
                # slipped through on a non-Windows dev machine.
                label = None
            current_day = {'date': e.date, 'label': label, 'entries': []}
            days.append(current_day)
        current_day['entries'].append(e)

    mood_options = [dict(key=key, **meta) for key, meta in MOOD_META.items()]
    context = {
        'days': days,
        'mood_options': mood_options,
        'mood_counts': [
            {'mood': mood, 'count': count, 'meta': MOOD_META.get(mood, _DEFAULT_MOOD_META)}
            for mood, count in sorted(counts.items(), key=lambda kv: -kv[1])
        ],
        'total_entries': len(entries),
    }
    context.update(_mood_calendar_context(request))
    return render(request, 'health/mental_health.html', context)


def _mood_calendar_context(request):
    """
    Builds the data for a month-grid calendar with each day tinted by that
    day's mood. `?month=YYYY-MM` navigates; an invalid/missing value falls
    back to the current month rather than erroring.
    """
    today = timezone.localdate()
    month_param = request.GET.get('month', '')
    try:
        year, month = (int(p) for p in month_param.split('-', 1))
        first_of_month = datetime.date(year, month, 1)
    except (ValueError, TypeError):
        first_of_month = today.replace(day=1)

    # Every mood logged in the visible month, last check-in of the day wins
    # if there was more than one that day.
    month_logs = MoodLog.objects.filter(
        patient=request.user,
        date__year=first_of_month.year, date__month=first_of_month.month,
    ).order_by('date', 'id')
    mood_by_date = {}
    for log in month_logs:
        mood_by_date[log.date] = log.mood

    cal = calendar.Calendar(firstweekday=0)  # weeks start Monday
    weeks = []
    for week in cal.monthdatescalendar(first_of_month.year, first_of_month.month):
        row = []
        for day in week:
            mood = mood_by_date.get(day)
            row.append({
                'date': day,
                'in_month': day.month == first_of_month.month,
                'is_today': day == today,
                'mood': mood,
                'meta': MOOD_META.get(mood, _DEFAULT_MOOD_META) if mood else None,
            })
        weeks.append(row)

    # First-of-month math avoids a %-d/%-m style strftime call (Windows-unsafe
    # -- see the day-label comment above); the previous/next month links are
    # built the same plain-arithmetic way.
    prev_month = (first_of_month - datetime.timedelta(days=1)).replace(day=1)
    next_month = (first_of_month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

    return {
        'calendar_weeks': weeks,
        'calendar_weekday_labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'calendar_month_label': first_of_month,  # formatted in the template
        'calendar_prev_month': prev_month.strftime('%Y-%m'),
        'calendar_next_month': next_month.strftime('%Y-%m'),
        'calendar_legend': [dict(key=key, **meta) for key, meta in MOOD_META.items()],
    }


# --------------------------------------------------------------------------
# Record sharing -- the consent engine's user-facing surface
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def share_records(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'grant')

        if action == 'revoke':
            grant = get_object_or_404(ConsentGrant, pk=request.POST.get('grant_id'), patient=request.user)
            grant.revoke()
            AuditLog.record(request.user, 'Revoked a record share',
                            f"{grant.recipient.display_name} -- {grant.scope_label()}",
                            AuditLog.Tag.WARN)
            Notification.send(
                grant.recipient,
                title=f'{request.user.display_name} withdrew access',
                body=f'You can no longer see: {grant.scope_label()}.',
                kind=Notification.Kind.CONSENT,
                level=Notification.Level.WARNING,
            )
            messages.info(request, f'Access revoked for {grant.recipient.display_name}.')
            return redirect('health_share')

        recipient_id = request.POST.get('recipient')
        recipient = User.objects.filter(pk=recipient_id).first()
        if not recipient:
            messages.error(request, 'Choose who you want to share with.')
            return redirect('health_share')

        scopes = request.POST.getlist('scope')
        if not scopes:
            messages.error(request, 'Choose at least one category to share.')
            return redirect('health_share')

        hours = request.POST.get('expires_in', '2')
        expires_at = None
        if hours != 'never':
            try:
                expires_at = timezone.now() + datetime.timedelta(hours=int(hours))
            except ValueError:
                expires_at = timezone.now() + datetime.timedelta(hours=2)

        # Derive the boolean columns from SCOPE_FIELDS so a new category
        # only ever has to be added in one place.
        scope_flags = {field: (scope in scopes) for scope, field in SCOPE_FIELDS.items()}

        grant = ConsentGrant.objects.create(
            patient=request.user, recipient=recipient,
            expires_at=expires_at,
            action_context=request.POST.get('context', 'Manual share'),
            **scope_flags,
        )
        AuditLog.record(request.user, 'Granted a record share',
                        f"{recipient.display_name} -- {grant.scope_label()}", AuditLog.Tag.OK)
        Notification.send(
            recipient,
            title=f'{request.user.display_name} shared records with you',
            body=grant.scope_label(),
            kind=Notification.Kind.CONSENT,
        )
        messages.success(request, f'Share created. Passcode: {grant.passcode}')
        return redirect('health_share')

    grants = ConsentGrant.objects.filter(patient=request.user).select_related('recipient')
    active = [g for g in grants if g.is_active()]
    history = [g for g in grants if not g.is_active()]

    # Who can a patient share with? Verified providers, plus their approved caregivers.
    provider_users = User.objects.filter(
        role=User.Role.PROVIDER,
        provider_profile__verification_status=ProviderProfile.Verification.VERIFIED,
    ).select_related('provider_profile')
    caregiver_users = User.objects.filter(
        patient_links__patient=request.user,
        patient_links__status=CaregiverLink.Status.APPROVED,
    )

    context = {
        'active_shares': active,
        'history': history,
        'recipients': list(provider_users) + list(caregiver_users),
        # Rendered as two checkbox groups so the restricted categories are
        # visibly separate from the everyday ones.
        'standard_scopes': [
            (scope.value, scope.label, scope in (ConsentGrant.Scope.VITALS,
                                                 ConsentGrant.Scope.MEDICATIONS))
            for scope in ConsentGrant.STANDARD_SCOPES
        ],
        'restricted_scopes': [
            (scope.value, scope.label) for scope in ConsentGrant.RESTRICTED_SCOPES
        ],
    }
    return render(request, 'health/share_records.html', context)


# --------------------------------------------------------------------------
# Caregiver views
# --------------------------------------------------------------------------

@role_required(User.Role.CAREGIVER)
def caregiver_dashboard(request):
    """
    The caregiver's single screen, built from the modules the Caregiver
    Module proposal lists: linked patient overview, medication status,
    health status, upcoming appointments, notifications, emergency
    contacts and a "needs attention" card.

    Every module is gated on its own consent scope. A module the patient
    hasn't granted isn't shown greyed out or empty -- it is absent, per
    "Unapproved modules are hidden from the caregiver."
    """
    link = (
        CaregiverLink.objects.filter(caregiver=request.user, status=CaregiverLink.Status.APPROVED)
        .select_related('patient').first()
    )
    pending = CaregiverLink.objects.filter(
        caregiver=request.user, status=CaregiverLink.Status.PENDING).select_related('patient').first()

    notifications = Notification.objects.filter(user=request.user)[:6]

    if not link:
        # No approved link yet -- show the waiting/link state instead of data.
        return render(request, 'health/caregiver_dashboard.html', {
            'link': None, 'pending': pending, 'notifications': notifications,
        })

    # Second gate, after the link itself: is this browser one the patient
    # has approved? An unrecognised device sees the same nothing an
    # unapproved caregiver does.
    if not device_is_trusted(request):
        return render(request, 'health/caregiver_dashboard.html', {
            'link': link, 'pending': None, 'notifications': notifications,
            'device_blocked': True, 'device': current_device(request),
            'patient': link.patient,
        })

    patient = link.patient
    today = timezone.localdate()

    # One query resolves every category rather than one query per module.
    consent = consent_matrix(patient, request.user)
    Scope = ConsentGrant.Scope

    can_vitals = consent[Scope.VITALS]
    can_medications = consent[Scope.MEDICATIONS]
    can_appointments = consent[Scope.APPOINTMENTS]
    can_alerts = consent[Scope.ALERTS]
    can_emergency = consent[Scope.EMERGENCY]
    can_lifestyle = consent[Scope.LIFESTYLE]

    recent_vitals = list(VitalRecord.objects.filter(patient=patient)[:5]) if can_vitals else []
    meds = Medication.objects.filter(patient=patient, active=True) if can_medications else []
    alerts = list(patient.insights.filter(level__in=['WARNING', 'CRITICAL'])[:4]) if can_alerts else []

    appointments = []
    if can_appointments:
        appointments = list(
            Appointment.objects.filter(
                patient=patient, scheduled_for__gte=timezone.now(),
                status__in=[Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED],
            ).select_related('provider', 'provider__user')[:4]
        )

    missed = 0
    doses_due_today = 0
    if can_medications:
        missed = MedicationDose.objects.filter(
            medication__patient=patient, taken=False,
            date__gte=today - datetime.timedelta(days=7), date__lt=today,
        ).count()
        doses_due_today = MedicationDose.objects.filter(
            medication__patient=patient, date=today, taken=False).count()

    lifestyle_today = LifestyleLog.objects.filter(patient=patient, date=today).first() if can_lifestyle else None

    # --- Needs Attention -------------------------------------------------
    # Deliberately assembled from what the caregiver is already allowed to
    # see, so the card can never leak the existence of a hidden category.
    needs_attention = []
    latest_vital = recent_vitals[0] if recent_vitals else None
    if can_vitals and latest_vital and latest_vital.status == VitalRecord.Status.HIGH:
        needs_attention.append({
            'title': 'Latest reading is high',
            'detail': f'{latest_vital.bp_display} on '
                      f'{_friendly_datetime(latest_vital.recorded_at)}',
            'level': 'danger',
        })
    if can_medications and missed:
        needs_attention.append({
            'title': f"{missed} missed dose{'s' if missed != 1 else ''} this week",
            'detail': 'Adherence has slipped in the last seven days.',
            'level': 'warn',
        })
    if can_medications and doses_due_today:
        needs_attention.append({
            'title': f"{doses_due_today} dose{'s' if doses_due_today != 1 else ''} still due today",
            'detail': 'Nothing ticked off yet for these.',
            'level': 'warn',
        })
    if can_vitals and not recent_vitals:
        needs_attention.append({
            'title': 'No vitals logged yet',
            'detail': 'There are no readings to monitor.',
            'level': 'warn',
        })
    for insight in alerts:
        needs_attention.append({
            'title': insight.text,
            'detail': insight.evidence,
            'level': 'danger' if insight.level == 'CRITICAL' else 'warn',
        })

    context = {
        'link': link,
        'pending': None,
        'patient': patient,
        'notifications': notifications,
        'unread_count': sum(1 for n in notifications if n.is_unread),
        # Per-module gates.
        'can_see_vitals': can_vitals,
        'can_see_medications': can_medications,
        'can_see_appointments': can_appointments,
        'can_see_alerts': can_alerts,
        'can_see_emergency': can_emergency,
        'can_see_lifestyle': can_lifestyle,
        # Module data.
        'recent_vitals': recent_vitals,
        'latest_vital': latest_vital,
        'medications': meds,
        'alerts': alerts,
        'appointments': appointments,
        'missed_doses': missed,
        'doses_due_today': doses_due_today,
        'lifestyle_today': lifestyle_today,
        'needs_attention': needs_attention,
        'adherence': analytics.medication_adherence(patient) if can_medications else None,
        # What the patient has chosen NOT to share -- shown as a short,
        # honest list so the caregiver understands the gaps.
        'withheld': [
            ConsentGrant.Scope(scope).label
            for scope in ConsentGrant.STANDARD_SCOPES if not consent[scope]
        ],
    }
    return render(request, 'health/caregiver_dashboard.html', context)


@role_required(User.Role.CAREGIVER)
def caregiver_link_request(request):
    """
    A caregiver who registered without a usable reference can retry here.

    Accepts the same three identifiers as the sign-up form: patient ID,
    patient email, or a single-use invite code.
    """
    if request.method == 'POST':
        patient, invite, error = resolve_patient(request.POST.get('patient_ref', ''))
        if not patient:
            messages.error(request, error)
        elif CaregiverLink.objects.filter(patient=patient, caregiver=request.user).exists():
            messages.info(request, 'You have already requested access to this patient.')
        else:
            create_link_request(
                patient, request.user,
                relationship=request.POST.get('relationship', '').strip(),
                invite=invite,
            )
            messages.success(request, f'Request sent to {patient.display_name}. They need to approve it.')
        return redirect('health_caregiver_dashboard')
    return redirect('health_caregiver_dashboard')


@login_required
def notifications_view(request):
    """Everyone's notification list. Opening the page marks them read."""
    items = list(Notification.objects.filter(user=request.user)[:50])
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return render(request, 'health/notifications.html', {'items': items})


@login_required
def report_problem(request):
    """
    Where any user files a report for an Admin to review.

    Naming someone is optional: a lot of reports are about the platform,
    and requiring a target would push people into blaming whoever is
    nearest. Admins are excluded from the "who is this about" list --
    complaints about an Admin should go through a channel that isn't
    reviewed by their own colleagues, which this deliberately isn't.
    """
    from adminpanel.models import Complaint

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        if not (subject and description):
            messages.error(request, 'Please give your report a subject and describe what happened.')
            return redirect('report_problem')

        against = User.objects.filter(pk=request.POST.get('against_user') or 0).exclude(
            role=User.Role.ADMIN).first()
        complaint = Complaint.objects.create(
            reporter=request.user, against_user=against,
            category=request.POST.get('category', Complaint.Category.OTHER),
            subject=subject, description=description,
        )
        AuditLog.record(request.user, 'Filed a report', complaint.subject, AuditLog.Tag.WARN)
        messages.success(request, 'Report submitted. An administrator will review it.')
        return redirect('report_problem')

    # Only people this user actually deals with, so the dropdown isn't a
    # directory of every account on the platform.
    known = User.objects.filter(
        Q(patient_links__patient=request.user)
        | Q(caregiver_links__caregiver=request.user)
        | Q(provider_profile__appointments__patient=request.user)
    ).exclude(pk=request.user.pk).exclude(role=User.Role.ADMIN).distinct()

    return render(request, 'health/report_problem.html', {
        'categories': Complaint.Category.choices,
        'known_people': known,
        'my_reports': Complaint.objects.filter(reporter=request.user)[:10],
    })


@role_required(User.Role.PATIENT)
def caregiver_requests(request):
    """
    The patient's control panel for caregiver access: pending link
    requests, new-device sign-ins waiting on them, and the invite codes
    they can hand out.
    """
    if request.method == 'POST':
        action = request.POST.get('action', 'link')

        # --- New-device approval -----------------------------------------
        if action == 'device':
            device = get_object_or_404(
                TrustedDevice, pk=request.POST.get('device_id'), patient=request.user)
            if request.POST.get('decision') == 'approve':
                device.approve()
                AuditLog.record(request.user, 'Approved a caregiver device',
                                f'{device.user.display_name} -- {device.label}', AuditLog.Tag.OK)
                Notification.send(
                    device.user,
                    title='Your new device was approved',
                    body=f'{request.user.display_name} approved {device.label}.',
                    kind=Notification.Kind.DEVICE_APPROVAL,
                    action_url_name='health_caregiver_dashboard',
                )
                messages.success(request, f'{device.label} approved.')
            else:
                device.reject()
                AuditLog.record(request.user, 'Rejected a caregiver device',
                                f'{device.user.display_name} -- {device.label}', AuditLog.Tag.WARN)
                messages.info(request, f'{device.label} blocked.')
            return redirect('health_caregiver_requests')

        # --- Invite codes -------------------------------------------------
        if action == 'invite':
            invite = CaregiverInvite.objects.create(
                patient=request.user,
                label=request.POST.get('label', '').strip(),
                expires_at=timezone.now() + datetime.timedelta(days=7),
            )
            AuditLog.record(request.user, 'Generated a caregiver invite code',
                            invite.label or invite.code, AuditLog.Tag.MUTED)
            messages.success(request, f'Invite code {invite.code} created. It expires in 7 days.')
            return redirect('health_caregiver_requests')

        if action == 'revoke_invite':
            invite = get_object_or_404(CaregiverInvite, pk=request.POST.get('invite_id'), patient=request.user)
            invite.expires_at = timezone.now()
            invite.save(update_fields=['expires_at'])
            messages.info(request, f'Invite code {invite.code} cancelled.')
            return redirect('health_caregiver_requests')

        # --- Caregiver link decision --------------------------------------
        link = get_object_or_404(CaregiverLink, pk=request.POST.get('link_id'), patient=request.user)
        decision = request.POST.get('decision')
        if decision == 'approve':
            link.status = CaregiverLink.Status.APPROVED
            link.decided_at = timezone.now()
            link.save(update_fields=['status', 'decided_at'])
            # Approving the link grants the everyday categories only.
            # Records, documents, reports and the AI summary are
            # restricted: the patient has to hand those over deliberately
            # from Share Records.
            ConsentGrant.objects.get_or_create(
                patient=request.user, recipient=link.caregiver, revoked_at__isnull=True,
                defaults={
                    'scope_vitals': True,
                    'scope_medications': True,
                    'scope_appointments': True,
                    'scope_alerts': True,
                    'scope_emergency': True,
                    'scope_lifestyle': True,
                    'action_context': 'Caregiver monitoring',
                },
            )
            AuditLog.record(request.user, 'Approved a caregiver link',
                            link.caregiver.display_name, AuditLog.Tag.OK)
            Notification.send(
                link.caregiver,
                title=f'{request.user.display_name} approved your request',
                body='You can now see their vitals, medicines, appointments and alerts.',
                kind=Notification.Kind.CAREGIVER_DECISION,
                action_url_name='health_caregiver_dashboard',
            )
            messages.success(request, f'{link.caregiver.display_name} can now monitor your vitals.')
        else:
            link.status = CaregiverLink.Status.REJECTED
            link.decided_at = timezone.now()
            link.save(update_fields=['status', 'decided_at'])
            AuditLog.record(request.user, 'Rejected a caregiver link',
                            link.caregiver.display_name, AuditLog.Tag.MUTED)
            Notification.send(
                link.caregiver,
                title=f'{request.user.display_name} declined your request',
                body='They have not shared any data with you.',
                kind=Notification.Kind.CAREGIVER_DECISION,
            )
            messages.info(request, 'Request declined.')
        return redirect('health_caregiver_requests')

    links = CaregiverLink.objects.filter(patient=request.user).select_related('caregiver')
    return render(request, 'health/caregiver_requests.html', {
        'pending': [l for l in links if l.status == CaregiverLink.Status.PENDING],
        'decided': [l for l in links if l.status != CaregiverLink.Status.PENDING],
        'pending_devices': TrustedDevice.objects.filter(
            patient=request.user, status=TrustedDevice.Status.PENDING).select_related('user'),
        'invites': CaregiverInvite.objects.filter(patient=request.user)[:8],
    })


# --------------------------------------------------------------------------
# Document extraction — process and discard
#
# Two tabs, one pipeline. A prescription becomes medicines with reminders;
# a lab report becomes measured values, and any vitals on it are routed
# into the patient's existing vitals tracking. Neither keeps the image.
# --------------------------------------------------------------------------

def _ingest_document(request, source_type, back_to, noun):
    """
    Read one uploaded image, OCR it, discard the bytes, and record the job.

    Shared by the prescription and lab-report uploads. Both make the same
    process-and-discard promise, and duplicating it would mean two places
    where the file could accidentally start being kept.

    Returns `(job, text, None)` on success, or `(None, None, response)` when
    the caller should return that redirect instead.
    """
    uploaded = request.FILES.get('document')
    consented = bool(request.POST.get('consent'))

    if not uploaded:
        messages.error(request, f'Choose a photo of your {noun} first.')
        return None, None, redirect(back_to)

    # Consent gate. Refusals are logged too, so the audit trail shows
    # attempted-but-refused processing, not just what succeeded.
    if not consented:
        AuditLog.record(request.user, 'Refused consent for document extraction',
                        uploaded.name[:100], AuditLog.Tag.WARN)
        messages.error(request,
                       f'We can only read your {noun} if you tick the box to allow it.')
        return None, None, redirect(back_to)

    # Keep the display name before we release the upload object. We store
    # the bare filename only -- never a path, and never the file itself.
    display_name = uploaded.name[:255]

    try:
        extraction.validate_upload(uploaded)
        file_bytes = uploaded.read()          # into memory, never to disk
        text, confidence = extraction.extract_text(file_bytes, display_name)
    except extraction.ExtractionError as exc:
        AuditLog.record(request.user, 'Document extraction failed',
                        str(exc)[:150], AuditLog.Tag.WARN)
        messages.error(request, str(exc))
        return None, None, redirect(back_to)
    finally:
        # Release the bytes as early as possible, whatever happened.
        file_bytes = None
        uploaded = None

    job = ExtractionJob.objects.create(
        patient=request.user,
        source_type=source_type,
        original_filename=display_name,
        raw_text=text,
        ocr_confidence=confidence,
        file_deleted_at=timezone.now(),       # the bytes are already gone
    )

    if not text.strip():
        job.status = ExtractionJob.Status.FAILED
        job.parser_note = 'No readable text found in the image.'
        job.save(update_fields=['status', 'parser_note'])
        messages.error(request,
                       "We couldn't read any text in that image. Try a sharper, "
                       'better-lit photo taken straight on.')
        return None, None, redirect(back_to)

    return job, text, None


@role_required(User.Role.PATIENT)
def prescription_upload(request):
    """
    Read an uploaded prescription, extract the medicines, and discard the file.

    Prescriptions only. Lab reports have their own tab, because what is done
    with the two is completely different -- one becomes medicines with
    reminders, the other becomes measured values and vitals.
    """
    if request.method == 'POST':
        job, text, bounce = _ingest_document(
            request, ExtractionJob.Source.PRESCRIPTION,
            'health_prescription_upload', 'prescription')
        if bounce:
            return bounce

        items, parser_used, note = extraction.parse_medications(text)
        job.parser_used = parser_used
        job.parser_note = note[:200]
        job.save(update_fields=['parser_used', 'parser_note'])

        for item in items:
            ExtractedMedication.objects.create(job=job, **item)

        AuditLog.record(request.user, 'Extracted a document',
                        f'{len(items)} medicine(s) found, parser={parser_used}',
                        AuditLog.Tag.OK)

        if not items:
            messages.warning(request,
                             'We read the image but could not identify any medicines. '
                             'You can add them by hand instead.')
        return redirect('health_extraction_verify', job_id=job.id)

    return render(request, 'health/prescription_upload.html', {
        'llm_in_use': extraction.llm_available(),
        'llm_model': getattr(settings, 'LLM_MODEL', ''),
        'recent': ExtractionJob.objects.filter(
            patient=request.user,
            source_type=ExtractionJob.Source.PRESCRIPTION)[:5],
    })


# --------------------------------------------------------------------------
# Lab reports — their own tab
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def lab_report_upload(request):
    """
    Read an uploaded lab report, extract the measured values, discard the file.

    Same process-and-discard pipeline as a prescription; what differs is
    where the values land afterwards.
    """
    if request.method == 'POST':
        job, text, bounce = _ingest_document(
            request, ExtractionJob.Source.LAB_REPORT,
            'health_lab_upload', 'lab report')
        if bounce:
            return bounce

        items, parser_used, note = labvalues.parse_lab_values(text)
        job.parser_used = parser_used
        job.parser_note = note[:200]
        job.save(update_fields=['parser_used', 'parser_note'])

        for item in items:
            ExtractedLabValue.objects.create(job=job, **item)

        vitals_found = sum(1 for i in items if i['vital_field'])
        AuditLog.record(request.user, 'Extracted a lab report',
                        f'{len(items)} value(s) found, {vitals_found} vital(s), '
                        f'parser={parser_used}', AuditLog.Tag.OK)

        if not items:
            messages.warning(request,
                             'We read the image but could not identify any results. '
                             'You can enter them by hand instead.')
        return redirect('health_lab_verify', job_id=job.id)

    context = {
        'llm_in_use': extraction.llm_available(),
        'llm_model': getattr(settings, 'LLM_MODEL', ''),
        'recent': ExtractionJob.objects.filter(
            patient=request.user, source_type=ExtractionJob.Source.LAB_REPORT)[:5],
    }
    # Upload and history are one page, not two tabs. Splitting them meant a
    # patient had to know in advance whether they wanted to add a report or
    # look at one, which is not how anyone thinks about it.
    context.update(_lab_history(request.user))
    return render(request, 'health/lab_upload.html', context)


def _lab_history(patient):
    """Saved reports, per-analyte trends, and anything out of range."""
    reports = (LabReport.objects.filter(patient=patient)
               .prefetch_related('values').select_related('vitals_record'))

    # A per-analyte trend, so a value read off a report can be compared with
    # the same value on an earlier one rather than sitting in isolation.
    trends = {}
    for report in reports:
        for value in report.values.all():
            trends.setdefault(value.analyte, []).append((report.reported_on, value))
    tracked = sorted(
        ((name, sorted(rows, key=lambda r: r[0], reverse=True))
         for name, rows in trends.items() if len(rows) > 1),
        key=lambda pair: pair[0])

    return {
        'reports': reports,
        'tracked': tracked,
        'abnormal': [v for r in reports for v in r.values.all() if v.is_abnormal][:10],
    }


@role_required(User.Role.PATIENT)
def lab_report_verify(request, job_id):
    """
    The patient checks the values before anything is saved.

    On confirmation the values split two ways, and the split is the whole
    point of this screen: anything tagged with a `vital_field` is written
    to `VitalRecord` so it joins the existing trend charts, and everything
    else is kept as `LabResultValue` rows on a `LabReport`.
    """
    job = get_object_or_404(ExtractionJob, pk=job_id, patient=request.user,
                            source_type=ExtractionJob.Source.LAB_REPORT)

    if request.method == 'POST':
        if request.POST.get('action') == 'discard':
            job.status = ExtractionJob.Status.DISCARDED
            job.save(update_fields=['status'])
            job.clear_text()
            AuditLog.record(request.user, 'Discarded a lab extraction', '', AuditLog.Tag.MUTED)
            messages.info(request, 'Discarded. Nothing was saved.')
            return redirect('health_lab_upload')

        reported_on = _to_date_or_today(request.POST.get('reported_on'))
        vitals = {}
        lab_rows = []
        unusable_bp = []

        for item in job.lab_values.all():
            if not request.POST.get(f'keep_{item.id}'):
                continue
            analyte = request.POST.get(f'analyte_{item.id}', '').strip()
            value = request.POST.get(f'value_{item.id}', '').strip()
            if not (analyte and value):
                continue

            item.analyte = analyte[:120]
            item.value = value[:40]
            item.unit = request.POST.get(f'unit_{item.id}', '').strip()[:30]
            item.reference_range = request.POST.get(f'range_{item.id}', '').strip()[:60]
            # The patient may have corrected the name into (or out of) being
            # a vital, so where it goes is decided from what they confirmed,
            # not from what the parser first guessed.
            item.vital_field = labvalues.vital_field_for(item.analyte)
            item.flag = item.flag or LabResultValue.Flag.UNKNOWN
            item.confirmed = True
            item.save()

            if item.vital_field == 'bp':
                # An unsplit blood pressure. If the patient has typed it as
                # "130/85" we can use it; if they left OCR's mangled version
                # in place we say so rather than guessing where the slash
                # went, or quietly filing it as a lab result.
                pair = labvalues.split_bp(item.value)
                if pair:
                    vitals['bp_systolic'], vitals['bp_diastolic'] = pair
                else:
                    unusable_bp.append(item.value)
            elif item.vital_field:
                vitals[item.vital_field] = item.value
            else:
                lab_rows.append(item)

        vital_record = _vital_from_lab(request.user, vitals, reported_on)

        report = None
        if lab_rows:
            report = LabReport.objects.create(
                patient=request.user, reported_on=reported_on,
                lab_name=request.POST.get('lab_name', '').strip()[:150],
                note=request.POST.get('note', '').strip()[:255],
                vitals_record=vital_record,
            )
            for item in lab_rows:
                LabResultValue.objects.create(
                    report=report, analyte=item.analyte, value=item.value,
                    unit=item.unit, reference_range=item.reference_range,
                    flag=item.flag,
                )

        job.status = ExtractionJob.Status.CONFIRMED
        job.save(update_fields=['status'])
        job.clear_text()        # transcribed text is no longer needed
        AuditLog.record(request.user, 'Confirmed lab report values',
                        f'{len(lab_rows)} result(s), '
                        f'{"vitals updated" if vital_record else "no vitals"}',
                        AuditLog.Tag.OK)

        if vital_record:
            analytics.generate_insights(request.user)
            messages.success(
                request,
                f'{len(vitals)} reading{"s" if len(vitals) != 1 else ""} added to your '
                'vitals tracking.')
        if lab_rows:
            messages.success(
                request,
                f'{len(lab_rows)} lab result{"s" if len(lab_rows) != 1 else ""} saved.')
        if unusable_bp:
            messages.warning(
                request,
                f'We could not read the blood pressure ("{unusable_bp[0]}"), so it was not saved. '
                'Blood pressure needs to be written as two numbers with a slash, like 130/85 — '
                'upload again and correct it, or add it on the Log Vitals page.')
        if not (vital_record or lab_rows):
            messages.info(request, 'Nothing was saved.')

        return redirect('health_lab_upload' if lab_rows else 'health_vitals')

    items = list(job.lab_values.all())
    return render(request, 'health/lab_verify.html', {
        'job': job,
        'vital_items': [i for i in items if i.is_vital],
        'other_items': [i for i in items if not i.is_vital],
        # A blood pressure OCR could not split needs retyping as 130/85.
        'unsplit_bp': [i for i in items
                       if i.vital_field == 'bp' and not labvalues.split_bp(i.value)],
        'today': timezone.localdate(),
        'vital_labels': labvalues.VITAL_LABELS,
    })


@role_required(User.Role.PATIENT)
def lab_results(request):
    """
    Kept so older links and bookmarks still work.

    Uploading and reviewing now live on one page, so this only forwards.
    """
    return redirect('health_lab_upload')


def _to_date_or_today(raw):
    raw = (raw or '').strip()
    if not raw:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return timezone.localdate()


def _vital_from_lab(patient, values, on_date):
    """
    Write the vitals found on a lab report into `VitalRecord`.

    Returns the record, or None when the report carried no vitals at all.
    The reading is tagged `LAB_REPORT` so its provenance stays visible next
    to self-recorded and nurse-recorded readings, and only the fields the
    report actually contained are set -- the rest stay empty rather than
    being invented.
    """
    if not values:
        return None

    def as_int(raw):
        try:
            return int(round(float(str(raw).replace(',', ''))))
        except (TypeError, ValueError):
            return None

    def as_decimal(raw):
        try:
            return Decimal(str(raw).replace(',', ''))
        except (InvalidOperation, ValueError, TypeError):
            return None

    record = VitalRecord(
        patient=patient,
        recorded_at=timezone.make_aware(
            datetime.datetime.combine(on_date, datetime.time(9, 0)),
            timezone.get_current_timezone()),
        source=VitalRecord.Source.LAB_REPORT,
        bp_systolic=as_int(values.get('bp_systolic')),
        bp_diastolic=as_int(values.get('bp_diastolic')),
        blood_sugar=as_decimal(values.get('blood_sugar')),
        weight_kg=as_decimal(values.get('weight_kg')),
        heart_rate=as_int(values.get('heart_rate')),
    )
    # A record where every field failed to parse is not worth keeping.
    if not any([record.bp_systolic, record.bp_diastolic, record.blood_sugar,
                record.weight_kg, record.heart_rate]):
        return None
    record.save()
    return record


@role_required(User.Role.PATIENT)
def extraction_verify(request, job_id):
    """The patient corrects what was extracted before anything is saved."""
    job = get_object_or_404(ExtractionJob, pk=job_id, patient=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'discard':
            job.status = ExtractionJob.Status.DISCARDED
            job.save(update_fields=['status'])
            job.clear_text()
            AuditLog.record(request.user, 'Discarded an extraction', '', AuditLog.Tag.MUTED)
            messages.info(request, 'Discarded. Nothing was added to your medicines.')
            return redirect('health_prescription_upload')

        created = 0
        unreadable = []
        for item in job.medications.all():
            if not request.POST.get(f'keep_{item.id}'):
                continue
            name = request.POST.get(f'name_{item.id}', '').strip()
            if not name:
                continue
            item.name = name[:120]
            item.dose = request.POST.get(f'dose_{item.id}', '').strip()[:60]
            item.frequency = request.POST.get(f'frequency_{item.id}', '').strip()[:120]
            item.duration = request.POST.get(f'duration_{item.id}', item.duration).strip()[:60]
            item.confirmed = True
            item.save(update_fields=['name', 'dose', 'frequency', 'duration', 'confirmed'])

            # The course length and the quantity dispensed are what make a
            # restock warning possible, so they are carried across here
            # rather than being dropped with the rest of the extraction.
            duration_days = schedules.parse_duration_days(item.duration)
            quantity = _qty(request.POST.get(f'quantity_{item.id}'))

            med = Medication.objects.create(
                patient=request.user, name=item.name,
                dose=item.dose or 'As prescribed',
                schedule=item.frequency or 'As prescribed',
                start_date=timezone.localdate(),
                duration_days=duration_days,
                quantity_dispensed=quantity,
                stock_on_hand=quantity,
            )
            parsed = med.set_schedule_from_text()

            # If the patient told us the course length but not how many
            # tablets they were given, we can work it out.
            if quantity is None and duration_days and parsed.daily_quantity > 0:
                supply = parsed.daily_quantity * duration_days
                med.quantity_dispensed = supply
                med.stock_on_hand = supply
                med.save(update_fields=['quantity_dispensed', 'stock_on_hand'])

            med.recompute_refill_date()
            if med.needs_schedule_review:
                unreadable.append(med.name)
            created += 1

        job.status = ExtractionJob.Status.CONFIRMED
        job.save(update_fields=['status'])
        job.clear_text()          # transcribed text is no longer needed
        AuditLog.record(request.user, 'Confirmed extracted medicines',
                        f'{created} added', AuditLog.Tag.OK)

        if created:
            messages.success(request,
                             f'{created} medicine{"s" if created != 1 else ""} added.')
            if unreadable:
                messages.warning(
                    request,
                    'We could not work out reminder times for '
                    f'{", ".join(unreadable)}. Set them on this page so alerts can be sent.')
        else:
            messages.info(request, 'Nothing was added.')
        return redirect('health_medications')

    return render(request, 'health/extraction_verify.html', {
        'job': job,
        'items': job.medications.all(),
    })