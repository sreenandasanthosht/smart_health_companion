"""
Export everything in your database to one JSON file that can be committed.

    python manage.py export_data

Writes seed_data/shared_data.json. Commit that file, push, and your teammate
runs:

    python manage.py loaddata seed_data/shared_data.json

...to end up with an identical database.

WHEN TO USE THIS vs seed_demo
-----------------------------
`seed_demo` is the normal way we share data: it builds the demo accounts and
history from code, it is idempotent, and it never conflicts. Prefer adding to
`seed_demo.py` when the data is something the project should always have.

Use `export_data` for the other case -- when you have clicked a lot of things
into the app by hand and want to hand that exact state over rather than
re-typing it.

IMPORTANT: treat the exported file as a SNAPSHOT, not a merge. `loaddata`
matches rows by primary key and overwrites them, so if you both created
different records that happen to share an ID, loading one file on top of a
populated database silently replaces rows. The safe procedure is:

    1. Only one person exports (whoever has the state worth keeping).
    2. The other person loads it into a database with no conflicting data --
       either freshly migrated, or after `python manage.py flush`.

Django's own tables (permissions, content types, sessions, admin log) are
excluded on purpose: `migrate` recreates them, and including them causes
integrity errors on the receiving side.
"""
import io
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

# Django-internal tables that must NOT travel between databases.
EXCLUDED = [
    'contenttypes',
    'auth.permission',
    'sessions',
    'admin.logentry',
]

DEFAULT_OUTPUT = 'seed_data/shared_data.json'


class Command(BaseCommand):
    help = 'Dump the project data to a committable JSON file for your teammate.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-o', '--output', default=DEFAULT_OUTPUT,
            help=f'Where to write the file (default: {DEFAULT_OUTPUT})',
        )

    def handle(self, *args, **options):
        out_path = Path(options['output'])
        if not out_path.is_absolute():
            out_path = Path(settings.BASE_DIR) / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        exclude_args = []
        for label in EXCLUDED:
            exclude_args += ['--exclude', label]

        # dumpdata's own `output=` argument opens the file itself with the
        # platform's default encoding -- on Windows that is cp1252, not
        # UTF-8, so any curly quote or dash typed into a title/body field
        # (e.g. a medication alert message) corrupts the file and breaks
        # `loaddata` with a UnicodeDecodeError on the receiving laptop.
        # Capture dumpdata's output as text ourselves and write it out
        # with an explicit utf-8 encoding instead.
        buffer = io.StringIO()
        call_command(
            'dumpdata',
            *exclude_args,
            natural_foreign=True,
            indent=2,
            stdout=buffer,
        )
        out_path.write_text(buffer.getvalue(), encoding='utf-8', newline='\n')

        size_kb = out_path.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(
            f'Wrote {out_path} ({size_kb:.0f} KB).'
        ))
        self.stdout.write(
            'Next: commit and push it. Your teammate runs\n'
            f'    python manage.py loaddata {options["output"]}\n'
            'into a freshly migrated (or flushed) database -- see the module\n'
            'docstring for why that matters.'
        )
