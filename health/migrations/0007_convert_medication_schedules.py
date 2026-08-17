"""
Convert existing free-text medication schedules into dose times.

Medicines saved before reminders existed carry a schedule like "1-0-1" or
"Twice daily" in a plain text field. This reads each one and creates the
matching `DoseTime` rows so those medicines start producing reminders too.

Anything the parser cannot read with confidence is left with no dose times
and `needs_schedule_review = True`. The medications page then asks the
patient to set the times themselves. Guessing would be worse than asking:
a reminder at the wrong hour trains people to ignore reminders.

Existing `MedicationDose` rows keep `dose_time = NULL`. They stay in the
adherence history rather than being deleted, and the new per-dose-time rows
are created alongside them from today onwards.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    # The real parser is imported rather than copied. It has no model
    # dependencies, so it is safe to use inside a migration.
    from health.schedules import parse_schedule

    Medication = apps.get_model('health', 'Medication')
    DoseTime = apps.get_model('health', 'DoseTime')

    # Kept in step with DoseTime.DEFAULT_TIMES. Written out here because a
    # historical model has fields but not the class attributes.
    import datetime
    default_times = {
        'MORNING': datetime.time(8, 0),
        'AFTERNOON': datetime.time(13, 0),
        'EVENING': datetime.time(18, 0),
        'NIGHT': datetime.time(21, 0),
    }

    for med in Medication.objects.all():
        parsed = parse_schedule(med.schedule)
        if parsed.confident and parsed.slots:
            for slot, quantity in parsed.slots.items():
                DoseTime.objects.get_or_create(
                    medication=med, slot=slot,
                    defaults={'at_time': default_times[slot], 'quantity': quantity},
                )
            med.needs_schedule_review = False
        else:
            med.needs_schedule_review = True
        med.save(update_fields=['needs_schedule_review'])


def backwards(apps, schema_editor):
    DoseTime = apps.get_model('health', 'DoseTime')
    DoseTime.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0006_medication_duration_days_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
