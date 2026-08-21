# Enforce a unique email at the database level.
#
# Registration and login both treat "email" as the account identity
# (username == email everywhere a user is created), but AbstractUser's
# email field is only blank=True -- never unique -- so nothing stopped two
# rows sharing one email, and accounts/views.py grew a 20-line helper
# (`_username_for_login`) purely to cope with that possibility.
#
# Safe to run on this project's data: `select lower(email), count(*) ...
# having count(*) > 1` returns no rows as of 2026-08-19. The RunPython step
# below is a defensive normalise-then-check so this migration also behaves
# correctly if it is ever run against a database that does have duplicates
# (it fails loudly with a clear message instead of a bare IntegrityError).
from django.db import migrations, models


def normalise_and_check_emails(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    seen = {}
    duplicates = []
    for user in User.objects.all().order_by('id'):
        normalised = (user.email or '').strip().lower()
        if normalised != user.email:
            user.email = normalised
            user.save(update_fields=['email'])
        if normalised in seen:
            duplicates.append((seen[normalised], user.id, normalised))
        else:
            seen[normalised] = user.id

    if duplicates:
        details = ', '.join(
            f'user #{a} and #{b} both use "{email}"' for a, b, email in duplicates)
        raise RuntimeError(
            'Cannot add a unique constraint on accounts_user.email -- '
            f'duplicate emails exist: {details}. Resolve these manually '
            '(merge or rename the accounts) and re-run this migration.')


def noop_reverse(apps, schema_editor):
    # Nothing to undo: lower-casing emails is not something we want to
    # reverse, and the AlterField reversal below drops the constraint on
    # its own.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_alter_user_managers'),
    ]

    operations = [
        migrations.RunPython(normalise_and_check_emails, noop_reverse),
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(max_length=254, unique=True, verbose_name='email address'),
        ),
    ]
