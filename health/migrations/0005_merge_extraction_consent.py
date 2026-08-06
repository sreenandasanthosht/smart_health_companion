from django.db import migrations


class Migration(migrations.Migration):
    """Merges the two parallel 0004 migrations (consent scope + extraction jobs)."""

    dependencies = [
        ("health", "0004_consentgrant_scope_ai_summary_and_more"),
        ("health", "0004_extractionjob_extractedmedication"),
    ]

    operations = []
