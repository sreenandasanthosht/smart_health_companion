# Generated manually to add the NURSE role choice (per NURSING_ROLE_DESIGN.md:
# nursing is its own role, not a Provider subtype).
# Safe to run: this only updates Django's internal "choices" metadata for
# the `role` column -- it does not change the column type or add any new
# database column, so it applies instantly even on existing data.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_role'),
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
                    ('NURSE', 'Nurse'),
                ],
                default='PATIENT',
                max_length=20,
            ),
        ),
    ]
