"""
datascience/recommend.py -- the recommendation engine (task 4.5).

This is a RULE-PLUS-MODEL HYBRID, on purpose, not a pure model:

  * A RULE decides ELIGIBILITY -- whether a suggestion even applies to this
    patient right now (e.g. "average sleep below 7 hours") and whether
    there's enough data to say so responsibly. This keeps the engine
    honest and explainable: it can never suggest something that isn't
    backed by the patient's own numbers, and the rule threshold is the
    same one written in health/analytics.py, not a second, disagreeing
    definition of "low sleep".

  * A trained MODEL decides RANKING -- among the suggestions that are
    eligible, which ones matter most for THIS patient, learned from the
    synthetic cohort. Two patients can both be "eligible" for a sleep
    suggestion and a hydration suggestion, but a model that has seen
    (feature pattern -> true underlying tendency) pairs across 100
    synthetic patients can judge which one is more likely to actually be
    the bigger problem for this specific combination of numbers, rather
    than always breaking ties in the same fixed order.

At most 3 suggestions are returned, each carrying the concrete numbers
that produced it. Nothing here reads MoodLog and nothing here produces a
clinical instruction -- only lifestyle and medication-adherence nudges.

If no trained model exists yet (train_models hasn't been run), the engine
still works: it falls back to a plain rule-based score (how far off target
the patient is, normalised 0-1) so the feature is never simply broken for
a fresh checkout of the project.
"""
import datetime
import json
from pathlib import Path

from django.utils import timezone

from datascience.features import FEATURE_ORDER, patient_features

ARTIFACT_DIR = Path(__file__).resolve().parent / 'artifacts'
MODEL_PATH = ARTIFACT_DIR / 'recommender.joblib'
METADATA_PATH = ARTIFACT_DIR / 'recommender_metadata.json'


def _sleep_eligible(f):
    return f['avg_sleep_hours'] < 7.0


def _sleep_reason(f):
    return (f"Average sleep over the last 14 days is {f['avg_sleep_hours']:.1f} hours, "
            f"below the 7-hour target.")


def _adherence_eligible(f):
    return f['missed_dose_rate'] >= 0.15


def _adherence_reason(f):
    pct = round(f['missed_dose_rate'] * 100)
    return f"{pct}% of scheduled doses were missed in the last 14 days."


def _activity_eligible(f):
    return f['avg_steps'] < 6000


def _activity_reason(f):
    return f"Average daily steps over the last 14 days is {f['avg_steps']:.0f}, below the 8,000-step target."


def _hydration_eligible(f):
    return f['avg_water_litres'] < 1.5


def _hydration_reason(f):
    return f"Average water intake over the last 14 days is {f['avg_water_litres']:.1f} L, below the 2 L target."


def _vitals_logging_eligible(f):
    return f['vitals_logged_14d'] < 3


def _vitals_logging_reason(f):
    n = int(f['vitals_logged_14d'])
    return f"Only {n} vital reading(s) logged in the last 14 days, too few to see a trend."


# One entry per recommendation candidate. `min_data` guards against acting
# on too little information; `eligible` is the actual trigger; `label` is
# the ground-truth column read off SyntheticPatient during training (never
# available for a real patient, which is exactly why the model has to
# learn it from the observable features instead).
CANDIDATES = {
    'SLEEP': {
        'title': 'Work on a more consistent sleep routine',
        'min_data': lambda f: f['lifestyle_days_logged'] >= 3,
        'eligible': _sleep_eligible,
        'reason': _sleep_reason,
        'label_field': 'sleep_tendency',
    },
    'ADHERENCE': {
        'title': 'Set a reminder for your medication doses',
        'min_data': lambda f: True,  # missed_dose_rate defaults to 0.0 with no doses, which is never eligible anyway
        'eligible': _adherence_eligible,
        'reason': _adherence_reason,
        'label_field': 'adherence_tendency',
    },
    'ACTIVITY': {
        'title': 'Add a short walk to your day',
        'min_data': lambda f: f['lifestyle_days_logged'] >= 3,
        'eligible': _activity_eligible,
        'reason': _activity_reason,
        'label_field': 'activity_tendency',
    },
    'HYDRATION': {
        'title': 'Drink more water through the day',
        'min_data': lambda f: f['lifestyle_days_logged'] >= 3,
        'eligible': _hydration_eligible,
        'reason': _hydration_reason,
        'label_field': 'hydration_tendency',
    },
    'VITALS_LOGGING': {
        'title': 'Log your vitals more often',
        'min_data': lambda f: True,
        'eligible': _vitals_logging_eligible,
        'reason': _vitals_logging_reason,
        'label_field': 'engagement_tendency',
    },
}

# Rule-only fallback score when no trained model is available -- how far
# off target the patient is, squashed into 0-1 so it ranks the same way a
# model's predict_proba would.
_FALLBACK = {
    'SLEEP': lambda f: max(0.0, min(1.0, (7.0 - f['avg_sleep_hours']) / 7.0)),
    'ADHERENCE': lambda f: max(0.0, min(1.0, f['missed_dose_rate'])),
    'ACTIVITY': lambda f: max(0.0, min(1.0, (6000 - f['avg_steps']) / 6000)),
    'HYDRATION': lambda f: max(0.0, min(1.0, (1.5 - f['avg_water_litres']) / 1.5)),
    'VITALS_LOGGING': lambda f: max(0.0, min(1.0, (3 - f['vitals_logged_14d']) / 3)),
}


def build_training_table():
    """
    Feature matrix, one row per synthetic patient, plus a binary label per
    candidate (their true underlying tendency, thresholded at 0.5 -- a
    LOW tendency means they genuinely need that nudge). Also returns the
    patient id for each row so evaluation can group-split by patient.
    """
    from datascience.models import SyntheticPatient  # local import: only needed for training

    rows, labels, groups = [], {key: [] for key in CANDIDATES}, []
    for sp in SyntheticPatient.objects.select_related('user').all():
        feats = patient_features(sp.user)
        rows.append([feats[k] for k in FEATURE_ORDER])
        groups.append(sp.user_id)
        for key, cfg in CANDIDATES.items():
            tendency = getattr(sp, cfg['label_field'])
            labels[key].append(tendency < 0.5)
    return rows, labels, groups


def train_recommender():
    """
    Train one small classifier per candidate on the synthetic cohort and
    persist all of them together. Returns the fitted models dict.
    """
    from sklearn.ensemble import RandomForestClassifier

    X, y_by_candidate, _groups = build_training_table()
    if not X:
        raise RuntimeError('No synthetic patients found. Run `python manage.py generate_cohort` first.')

    models = {}
    for key, y in y_by_candidate.items():
        clf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=42, class_weight='balanced')
        clf.fit(X, y)
        models[key] = clf

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump(models, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps({
        'feature_order': FEATURE_ORDER,
        'candidates': list(CANDIDATES.keys()),
        'trained_on_patients': len(X),
    }, indent=2))
    return models


def _load_models():
    if not MODEL_PATH.exists():
        return None
    import joblib
    try:
        return joblib.load(MODEL_PATH)
    except Exception:
        return None


def _model_score(models, key, vector):
    clf = models[key]
    proba = clf.predict_proba([vector])[0]
    classes = list(clf.classes_)
    if True in classes:
        return float(proba[classes.index(True)])
    if len(classes) == 1:
        # every training patient had the same label for this candidate
        return 1.0 if classes[0] else 0.0
    return 0.5


def recommend_for_patient(patient, top_n=3):
    """
    The public entry point. Returns at most `top_n` dicts, each with
    key/title/reason/score, ranked highest-score first. Never touches
    MoodLog. Safe to call even if no model has been trained yet.
    """
    feats = patient_features(patient)
    vector = [feats[k] for k in FEATURE_ORDER]
    models = _load_models()

    scored = []
    for key, cfg in CANDIDATES.items():
        if not cfg['min_data'](feats):
            continue
        if not cfg['eligible'](feats):
            continue
        if models is not None:
            try:
                score = _model_score(models, key, vector)
            except Exception:
                score = _FALLBACK[key](feats)
        else:
            score = _FALLBACK[key](feats)
        scored.append({
            'key': key,
            'title': cfg['title'],
            'reason': cfg['reason'](feats),
            'score': round(score, 3),
        })

    scored.sort(key=lambda c: c['score'], reverse=True)
    return scored[:top_n]
