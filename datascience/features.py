"""
datascience/features.py -- turns one patient's raw logs into a feature
vector, the same way for a synthetic training patient and a real patient
at prediction time. This is what keeps the model honest: every feature
here is something the app can actually compute today, on demand, from
data it already has. Nothing here looks at the future and nothing here
looks at a label.

FEATURE_ORDER is the fixed column order every consumer (training,
evaluation, prediction) must use, so a saved model and a fresh feature
vector always line up.
"""
import datetime
from decimal import Decimal

from django.utils import timezone

from health.models import LifestyleLog, MedicationDose, VitalRecord

FEATURE_ORDER = [
    'avg_sleep_hours',
    'avg_water_litres',
    'avg_steps',
    'missed_dose_rate',
    'vitals_logged_14d',
    'avg_bp_systolic',
    'high_bp_ratio',
    'lifestyle_days_logged',
    'age',
]


def _age(patient):
    dob = getattr(patient, 'date_of_birth', None)
    if not dob:
        return 45  # a neutral default when a real patient hasn't filled this in yet
    today = timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def patient_features(patient, window_days=14):
    """
    Compute the feature dict for `patient` from their last `window_days` of
    logs. Returns a plain dict keyed by FEATURE_ORDER, so callers can do
    [features[k] for k in FEATURE_ORDER] to get a model-ready vector.

    Every value has a sensible "no data yet" default (0 or None-safe) so a
    brand-new patient still gets a valid, if uninformative, feature row --
    the calling code (recommend.py) is responsible for deciding whether
    there's *enough* data to act on, not this function.
    """
    since_date = timezone.localdate() - datetime.timedelta(days=window_days)
    since_dt = timezone.now() - datetime.timedelta(days=window_days)

    logs = list(LifestyleLog.objects.filter(patient=patient, date__gte=since_date))
    sleeps = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    waters = [l.water_litres for l in logs if l.water_litres is not None]
    steps = [l.steps for l in logs if l.steps is not None]

    doses = MedicationDose.objects.filter(medication__patient=patient, date__gte=since_date)
    total_doses = doses.count()
    missed_doses = doses.filter(taken=False).count()

    vitals = list(VitalRecord.objects.filter(patient=patient, recorded_at__gte=since_dt))
    systolics = [v.bp_systolic for v in vitals]
    high_count = sum(1 for v in vitals if v.status == VitalRecord.Status.HIGH)

    return {
        'avg_sleep_hours': float(sum(sleeps) / len(sleeps)) if sleeps else 7.0,
        'avg_water_litres': float(sum(waters) / len(waters)) if waters else 2.0,
        'avg_steps': float(sum(steps) / len(steps)) if steps else 8000.0,
        'missed_dose_rate': (missed_doses / total_doses) if total_doses else 0.0,
        'vitals_logged_14d': float(len(vitals)),
        'avg_bp_systolic': float(sum(systolics) / len(systolics)) if systolics else 118.0,
        'high_bp_ratio': (high_count / len(vitals)) if vitals else 0.0,
        'lifestyle_days_logged': float(len(logs)),
        'age': float(_age(patient)),
    }


def feature_vector(patient, window_days=14):
    """The same features as patient_features(), ordered for a model."""
    feats = patient_features(patient, window_days=window_days)
    return [feats[k] for k in FEATURE_ORDER]
