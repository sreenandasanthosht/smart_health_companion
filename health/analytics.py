"""
health/analytics.py -- the analysis layer behind the dashboard.

This is the "Modeling" step of the CRISP-DM write-up (task 4.8), kept
deliberately rule-based and explainable rather than a trained black-box
model. Every insight carries the evidence that produced it, so a reviewer
can always ask "why did it say that?" and get a concrete answer.

Three things live here:
  * health_score()      -- a single 0-100 number for the dashboard
  * vital_series()      -- recent readings shaped for the trend charts
  * generate_insights() -- the rules that produce HealthInsight rows
"""
import datetime
from decimal import Decimal

from django.utils import timezone

from health.models import HealthInsight, LifestyleLog, MedicationDose, VitalRecord

# --- Reference ranges used across the analytics (adult, at-rest) ---
BP_SYS_NORMAL_MAX = 129
BP_DIA_NORMAL_MAX = 84
HR_NORMAL_MAX = 99
SUGAR_FASTING_NORMAL_MAX = Decimal('125.0')
SLEEP_TARGET_HOURS = Decimal('7.0')
WATER_TARGET_LITRES = Decimal('2.0')
STEPS_TARGET = 8000


def _recent_vitals(patient, days=30, limit=30):
    since = timezone.now() - datetime.timedelta(days=days)
    return list(VitalRecord.objects.filter(patient=patient, recorded_at__gte=since)[:limit])


def health_score(patient):
    """
    A 0-100 wellbeing score, starting at 100 and deducting for things that
    are measurably off-target. Returns (score, band) where band is one of
    'Excellent', 'Good', 'Fair', 'Needs attention'.

    Deductions are small and additive so the number moves smoothly rather
    than swinging on a single reading.
    """
    score = 100
    vitals = _recent_vitals(patient, days=30, limit=10)

    if vitals:
        high = sum(1 for v in vitals if v.status == VitalRecord.Status.HIGH)
        watch = sum(1 for v in vitals if v.status == VitalRecord.Status.WATCH)
        score -= min(35, high * 9 + watch * 4)

        sugars = [v.blood_sugar for v in vitals if v.blood_sugar is not None]
        if sugars and (sum(sugars) / len(sugars)) > SUGAR_FASTING_NORMAL_MAX:
            score -= 8
    else:
        # No data logged at all -- we can't say anything positive.
        score -= 20

    # Medication adherence over the last 14 days.
    since = timezone.localdate() - datetime.timedelta(days=14)
    doses = MedicationDose.objects.filter(medication__patient=patient, date__gte=since)
    total = doses.count()
    if total:
        missed = doses.filter(taken=False).count()
        score -= min(20, int(round(missed / total * 20)))

    # Lifestyle over the last 7 days.
    logs = LifestyleLog.objects.filter(patient=patient, date__gte=timezone.localdate() - datetime.timedelta(days=7))
    sleeps = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    if sleeps and (sum(sleeps) / len(sleeps)) < SLEEP_TARGET_HOURS:
        score -= 6

    score = max(0, min(100, score))
    if score >= 85:
        band = 'Excellent'
    elif score >= 70:
        band = 'Good'
    elif score >= 50:
        band = 'Fair'
    else:
        band = 'Needs attention'
    return score, band


def vital_series(patient, limit=8):
    """
    Recent readings, oldest-first, shaped for the dashboard trend cards.
    Returns a dict of metric -> {'points': [...], 'labels': [...],
    'latest': value, 'status': 'Normal'|'Elevated'|'High'}.
    """
    records = list(VitalRecord.objects.filter(patient=patient)[:limit])
    records.reverse()  # model ordering is newest-first; charts read left-to-right

    labels = [r.recorded_at.strftime('%d %b') for r in records]

    def build(values, normal_max, high_max=None):
        clean = [v for v in values if v is not None]
        latest = clean[-1] if clean else None
        if latest is None:
            status = 'No data'
        elif high_max is not None and latest > high_max:
            status = 'High'
        elif latest > normal_max:
            status = 'Elevated'
        else:
            status = 'Normal'
        return {'points': [float(v) if v is not None else None for v in values],
                'labels': labels, 'latest': latest, 'status': status}

    systolic = [r.bp_systolic for r in records]
    diastolic = [r.bp_diastolic for r in records]
    bp = build(systolic, BP_SYS_NORMAL_MAX, 139)
    bp['latest'] = f"{records[-1].bp_systolic}/{records[-1].bp_diastolic}" if records else None
    bp['diastolic'] = diastolic

    return {
        'bp': bp,
        'heart_rate': build([r.heart_rate for r in records], HR_NORMAL_MAX, 109),
        'blood_sugar': build([r.blood_sugar for r in records], SUGAR_FASTING_NORMAL_MAX, Decimal('180.0')),
        'weight': build([r.weight_kg for r in records], Decimal('999.9')),
    }


def sparkline_path(points, width=240, height=56):
    """
    Turn a list of numbers into an SVG polyline `points` string, so the
    dashboard trend cards draw real data instead of a fixed decorative
    curve. Returns '' when there isn't enough data to draw a line.
    """
    clean = [float(p) for p in points if p is not None]
    if len(clean) < 2:
        return ''
    lo, hi = min(clean), max(clean)
    span = (hi - lo) or 1.0
    step = width / (len(clean) - 1)
    pad = 6
    usable = height - (pad * 2)
    coords = []
    for i, value in enumerate(clean):
        x = i * step
        # invert y: SVG origin is top-left, charts read bottom-up
        y = pad + (usable - ((value - lo) / span) * usable)
        coords.append(f"{x:.1f},{y:.1f}")
    return ' '.join(coords)


def generate_insights(patient, persist=True):
    """
    Run every rule against the patient's recent data and return a list of
    HealthInsight objects (saved when `persist` is True, replacing the
    previous set so the dashboard never shows stale advice).

    Each rule appends both a message and the evidence behind it.
    """
    found = []

    def add(level, text, evidence=''):
        found.append(HealthInsight(patient=patient, level=level, text=text, evidence=evidence))

    vitals = _recent_vitals(patient, days=30, limit=10)

    # Rule 1 -- consecutive out-of-range blood pressure.
    if len(vitals) >= 2:
        newest_two = vitals[:2]
        if all(v.status == VitalRecord.Status.HIGH for v in newest_two):
            readings = ', '.join(f"{v.bp_systolic}/{v.bp_diastolic}" for v in newest_two)
            add(HealthInsight.Level.CRITICAL,
                'Blood pressure has been high on your last two readings.',
                f"Readings: {readings} (>= 140/90 is the high threshold)")
        elif all(v.status != VitalRecord.Status.NORMAL for v in newest_two):
            readings = ', '.join(f"{v.bp_systolic}/{v.bp_diastolic}" for v in newest_two)
            add(HealthInsight.Level.WARNING,
                'Blood pressure has been trending above your normal range.',
                f"Readings: {readings}")

    # Rule 2 -- sustained high resting heart rate.
    hrs = [v.heart_rate for v in vitals[:3] if v.heart_rate is not None]
    if len(hrs) >= 2 and all(h >= 100 for h in hrs):
        add(HealthInsight.Level.WARNING,
            'Resting heart rate has stayed above 100 bpm across recent readings.',
            f"Readings: {', '.join(str(h) for h in hrs)} bpm")

    # Rule 3 -- average fasting sugar above range.
    sugars = [v.blood_sugar for v in vitals if v.blood_sugar is not None]
    if len(sugars) >= 3:
        avg = sum(sugars) / len(sugars)
        if avg > SUGAR_FASTING_NORMAL_MAX:
            add(HealthInsight.Level.WARNING,
                f'Average fasting blood sugar is {avg:.0f} mg/dL, above the usual range.',
                f"Mean of last {len(sugars)} readings (normal fasting is under {SUGAR_FASTING_NORMAL_MAX:.0f})")

    # Rule 4 -- weight moving steadily in one direction.
    weights = [v.weight_kg for v in vitals if v.weight_kg is not None]
    if len(weights) >= 3:
        change = weights[0] - weights[-1]  # newest minus oldest
        if abs(change) >= Decimal('2.0'):
            direction = 'up' if change > 0 else 'down'
            add(HealthInsight.Level.INFO,
                f'Weight has moved {direction} by {abs(change):.1f} kg across your recent entries.',
                f"From {weights[-1]} kg to {weights[0]} kg")

    # Rule 5 -- missed medication doses.
    since = timezone.localdate() - datetime.timedelta(days=7)
    missed = MedicationDose.objects.filter(medication__patient=patient, date__gte=since, taken=False).count()
    if missed >= 3:
        add(HealthInsight.Level.WARNING,
            f'{missed} medicine doses were missed in the last 7 days.',
            'Counted from your medication tracker')
    elif missed:
        add(HealthInsight.Level.INFO,
            f'{missed} medicine dose{"s" if missed > 1 else ""} missed this week.',
            'Counted from your medication tracker')

    # Rule 6 -- short sleep.
    logs = list(LifestyleLog.objects.filter(patient=patient, date__gte=since))
    sleeps = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    if len(sleeps) >= 3:
        avg_sleep = sum(sleeps) / len(sleeps)
        if avg_sleep < SLEEP_TARGET_HOURS:
            add(HealthInsight.Level.INFO,
                f'Average sleep is {avg_sleep:.1f} hours, below the {SLEEP_TARGET_HOURS:.0f}-hour target.',
                f"Mean of {len(sleeps)} nights logged this week")

    # Rule 7 -- nothing wrong, and there IS data to say so.
    if not found and vitals:
        add(HealthInsight.Level.INFO,
            'Your recent readings are all within their normal ranges.',
            f"Based on {len(vitals)} reading(s) in the last 30 days")

    # Rule 8 -- no data at all.
    if not vitals:
        add(HealthInsight.Level.INFO,
            'Log your first set of vitals to start seeing trends and alerts.',
            'No readings recorded yet')

    if persist:
        HealthInsight.objects.filter(patient=patient).delete()
        HealthInsight.objects.bulk_create(found)
        return list(HealthInsight.objects.filter(patient=patient))
    return found


def medication_adherence(patient, days=14):
    """Percentage of scheduled doses actually taken in the window."""
    since = timezone.localdate() - datetime.timedelta(days=days)
    doses = MedicationDose.objects.filter(medication__patient=patient, date__gte=since)
    total = doses.count()
    if not total:
        return None
    return int(round(doses.filter(taken=True).count() / total * 100))
