import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User
from datascience.recommend import METADATA_PATH, MODEL_PATH


@login_required
@role_required(User.Role.ADMIN)
def analytics(request):
    """
    Admin-only model performance page (task 4.9). Reads whatever
    `python manage.py train_models` last wrote -- this view never trains
    anything itself, so opening the page has no side effects.
    """
    from datascience.evaluate import METRICS_PATH

    metrics = None
    if METRICS_PATH.exists():
        metrics = json.loads(METRICS_PATH.read_text())

    return render(request, 'datascience/analytics.html', {
        'metrics': metrics,
        'model_trained': MODEL_PATH.exists(),
        'metadata': json.loads(METADATA_PATH.read_text()) if METADATA_PATH.exists() else None,
    })
