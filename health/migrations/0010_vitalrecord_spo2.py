# Add SpO2 (blood oxygen saturation) to VitalRecord.
#
# The design docs and task plan both describe "threshold rules for
# BP/HR/temp/SpO2", but the table only ever had BP, blood sugar, weight
# and heart rate. Temperature was deliberately left out (product decision,
# 2026-08-19) -- this project is aimed at chronic-condition monitoring for
# elderly/caregiver users, and temperature is an acute-illness signal that
# would need its own "how are you feeling today" flow to mean anything, not
# a single self-reported number sitting alongside blood pressure. SpO2, by
# contrast, plugs directly into the same self-reported vitals routine and
# has a well-understood pass/watch/high threshold, so it was added.
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0009_merge_20260818_1154'),
    ]

    operations = [
        migrations.AddField(
            model_name='vitalrecord',
            name='spo2',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Blood oxygen saturation (%)',
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
    ]
