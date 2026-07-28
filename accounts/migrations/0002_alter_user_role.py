# Generated manually to add the ADMIN role choice.
# Safe to run: this only updates Django's internal "choices" metadata for
# the `role` column -- it does not change the column type or add any new
# database column, so it applies instantly even on existing data.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('PATIENT', 'Patient'),
                    ('CAREGIVER', 'Caregiver'),
                    ('PROVIDER', 'Provider'),
                    ('ADMIN', 'Admin'),
                ],
                default='PATIENT',
                max_length=20,
            ),
        ),
    ]
