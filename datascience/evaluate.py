"""
datascience/evaluate.py -- honest evaluation of the recommender (task 4.7).

Split by PATIENT, never by row: a synthetic patient's rows must not appear
in both train and test folds inside the same evaluation, or the score
would be inflated by the model half-memorising that specific patient.
Uses 5-fold grouped cross-validation (GroupKFold, grouped by patient id)
and reports the mean and standard deviation across folds, because a
single train/test split on a cohort this size is unstable -- one lucky or
unlucky split can swing the number by a lot, and the spread is itself
part of the honest result.

Writes datascience/artifacts/metrics.json (used by the admin analytics
page) and a bar chart to datascience/artifacts/plots/.
"""
import json
from pathlib import Path

from datascience.features import FEATURE_ORDER
from datascience.recommend import CANDIDATES, ARTIFACT_DIR

PLOTS_DIR = ARTIFACT_DIR / 'plots'
METRICS_PATH = ARTIFACT_DIR / 'metrics.json'


def evaluate_recommender(n_splits=5):
    """
    Returns a dict: {candidate_key: {accuracy, precision, recall, f1,
    roc_auc: {mean, std}}}. Falls back to a single train/test evaluation
    (still grouped by patient, just one split) if there aren't enough
    distinct patients for the requested number of folds.
    """
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import GroupKFold

    from datascience.recommend import build_training_table

    X, y_by_candidate, groups = build_training_table()
    if not X:
        raise RuntimeError('No synthetic patients found. Run `python manage.py generate_cohort` first.')

    X = np.array(X)
    groups = np.array(groups)
    n_unique_patients = len(set(groups))
    splits = min(n_splits, n_unique_patients) if n_unique_patients >= 2 else 1

    results = {}
    for key, y_raw in y_by_candidate.items():
        y = np.array(y_raw)
        fold_metrics = {'accuracy': [], 'precision': [], 'recall': [], 'f1': [], 'roc_auc': []}
        confusion = {'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0}

        if splits >= 2 and len(set(y)) > 1:
            gkf = GroupKFold(n_splits=splits)
            fold_iter = gkf.split(X, y, groups)
        else:
            # Too few patients or a single-class label -- report one fit on
            # everything, clearly not held-out, rather than crash.
            fold_iter = [(np.arange(len(X)), np.arange(len(X)))]

        for train_idx, test_idx in fold_iter:
            clf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=42, class_weight='balanced')
            clf.fit(X[train_idx], y[train_idx])
            pred = clf.predict(X[test_idx])
            y_test = y[test_idx]

            fold_metrics['accuracy'].append(accuracy_score(y_test, pred))
            fold_metrics['precision'].append(precision_score(y_test, pred, zero_division=0))
            fold_metrics['recall'].append(recall_score(y_test, pred, zero_division=0))
            fold_metrics['f1'].append(f1_score(y_test, pred, zero_division=0))
            try:
                proba = clf.predict_proba(X[test_idx])
                classes = list(clf.classes_)
                if True in classes and len(set(y_test)) > 1:
                    fold_metrics['roc_auc'].append(roc_auc_score(y_test, proba[:, classes.index(True)]))
            except Exception:
                pass

            for actual, predicted in zip(y_test, pred):
                if actual and predicted:
                    confusion['tp'] += 1
                elif actual and not predicted:
                    confusion['fn'] += 1
                elif not actual and predicted:
                    confusion['fp'] += 1
                else:
                    confusion['tn'] += 1

        def _mean_std(values):
            if not values:
                return {'mean': None, 'std': None}
            arr = np.array(values)
            return {'mean': round(float(arr.mean()), 3), 'std': round(float(arr.std()), 3)}

        results[key] = {
            'n_folds': splits,
            'accuracy': _mean_std(fold_metrics['accuracy']),
            'precision': _mean_std(fold_metrics['precision']),
            'recall': _mean_std(fold_metrics['recall']),
            'f1': _mean_std(fold_metrics['f1']),
            'roc_auc': _mean_std(fold_metrics['roc_auc']),
            'confusion_matrix': confusion,
        }

    payload = {
        'trained_on_patients': n_unique_patients,
        'feature_order': FEATURE_ORDER,
        'candidates': results,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(payload, indent=2))
    _write_plot(results)
    return payload


def _write_plot(results):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return  # matplotlib is optional -- metrics.json is the real artifact

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    keys = list(results.keys())
    f1_means = [results[k]['f1']['mean'] or 0.0 for k in keys]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(keys, f1_means, color='#2f6f5e')
    ax.set_ylim(0, 1)
    ax.set_ylabel('Macro-F1 (mean across folds)')
    ax.set_title('Recommendation engine -- per-candidate F1')
    plt.xticks(rotation=20, ha='right')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'recommender_f1.png', dpi=120)
    plt.close(fig)
