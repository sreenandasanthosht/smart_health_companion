"""
Data migration for the provider-module regrouping.

The finalised provider list dropped the standalone "Doctor" type -- a
doctor practising alone is a small clinic in this model -- and dropped
"Wellness Centre", which the Wellness Programmes group now covers through
fitness centres, dieticians and yoga centres.

Existing rows carrying a retired value would otherwise render as a blank
provider type and fall through to the default dashboard, so they are
remapped here rather than left to rot.
"""
from django.db import migrations

RETIRED = {
    'DOCTOR': 'CLINIC',
    'WELLNESS_CENTRE': 'FITNESS_CENTRE',
}


def forwards(apps, schema_editor):
    ProviderProfile = apps.get_model('providers', 'ProviderProfile')
    for old, new in RETIRED.items():
        ProviderProfile.objects.filter(provider_type=old).update(provider_type=new)


def backwards(apps, schema_editor):
    # Deliberately a no-op: CLINIC rows that were always clinics must not
    # be turned into doctors on the way back down.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0004_appointment_advice_appointment_diagnosis_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
