"""
Add a spread of providers across different cities.

    python manage.py seed_providers --dry-run     # show what would be created
    python manage.py seed_providers               # create them

Why this exists separately from `seed_demo`: seed_demo builds the one
end-to-end demo story (Latha, her caregiver, her nurse, her two doctors) and
everything in it is wired to that story. This command does one narrow job --
populate the provider directory with enough real-looking providers, in enough
different cities, to exercise the directory's search, its service-group
filter and its location filter. Keeping them apart means running this one
cannot disturb the demo story, and re-running seed_demo cannot disturb these.

Safe to run more than once. Accounts are looked up by email and skipped if
they already exist; nothing here updates or deletes an existing provider.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from adminpanel.models import AuditLog
from providers.models import ProviderProfile

User = get_user_model()

PASSWORD = 'CareNest#2026'

P = ProviderProfile.ProviderType

# (email, first, last, phone, type, specialty, clinic, address, reg_no, years, verified)
#
# Addresses are written the way a provider actually would -- "Area, City
# PINCODE" -- because that single free-text line is what the directory's
# location filter searches. Spreading them across cities is the point: it is
# what makes "show me providers in Kochi" a meaningful query.
PROVIDERS = [
    ('bloomclinic@example.com', 'Anjali', 'Menon', '+91 98470 11201',
     P.CLINIC, 'General Physician', 'Bloom Family Clinic',
     'Panampilly Nagar, Kochi 682036', 'KMC-2015-30112', 11, True),

    ('sreedhar.hospital@example.com', 'Sreedhar', 'Pillai', '+91 94470 22303',
     P.HOSPITAL, 'Multi-speciality', 'Sreedhar Memorial Hospital',
     'Pattom, Thiruvananthapuram 695004', 'KMC-2009-11876', 19, True),

    ('mindspace.calicut@example.com', 'Fathima', 'Rasheed', '+91 96450 33404',
     P.PSYCHOLOGIST, 'Clinical Psychologist', 'MindSpace Counselling',
     'Mavoor Road, Kozhikode 673004', 'RCI-A-2018-4471', 8, True),

    ('citylabs.blr@example.com', 'Vinod', 'Rao', '+91 98860 44505',
     P.DIAGNOSTIC_LAB, 'Pathology & Imaging', 'CityLabs Diagnostics',
     'Jayanagar 4th Block, Bengaluru 560011', 'NABL-2017-0918', None, True),

    ('nammapharmacy@example.com', 'Lakshmi', 'Iyer', '+91 90030 55606',
     P.PHARMACY, 'Retail & Home Delivery', 'Namma Pharmacy',
     'T. Nagar, Chennai 600017', 'TNDC-2016-55231', None, True),

    ('pulsefitness.hyd@example.com', 'Arjun', 'Reddy', '+91 99490 66707',
     P.FITNESS_CENTRE, 'Strength & Cardio Training', 'Pulse Fitness Studio',
     'Madhapur, Hyderabad 500081', 'TSGYM-2019-2210', 6, True),

    ('nourish.mumbai@example.com', 'Priya', 'Deshpande', '+91 98200 77808',
     P.DIETICIAN, 'Clinical Nutrition', 'Nourish Diet Clinic',
     'Bandra West, Mumbai 400050', 'IDA-2014-7789', 12, True),

    ('shantiyoga.pune@example.com', 'Kabir', 'Joshi', '+91 90280 88909',
     P.YOGA_CENTRE, 'Hatha & Therapeutic Yoga', 'Shanti Yoga Kendra',
     'Kothrud, Pune 411038', 'YCB-2020-3345', 9, True),

    ('carewell.delhi@example.com', 'Neha', 'Sharma', '+91 98110 99001',
     P.HOME_NURSE, 'Elderly & Post-operative Care', 'CareWell Home Nursing',
     'Lajpat Nagar, New Delhi 110024', 'DNC-2018-6602', 7, True),

    ('greenleaf.thrissur@example.com', 'Thomas', 'Varghese', '+91 94950 10102',
     P.CLINIC, 'Diabetology', 'Greenleaf Care Centre',
     'Poothole, Thrissur 680004', 'KMC-2013-22908', 14, True),

    # Two left unverified on purpose, so the Admin verification queue has
    # something in it and the directory can be seen correctly excluding them.
    ('coastal.kollam@example.com', 'Rekha', 'Nair', '+91 94460 20203',
     P.DIAGNOSTIC_LAB, 'Clinical Biochemistry', 'Coastal Diagnostics',
     'Chinnakada, Kollam 691001', 'NABL-2021-0455', None, False),

    ('sunrise.coimbatore@example.com', 'Bala', 'Subramanian', '+91 99420 30304',
     P.HOSPITAL, 'General Medicine', 'Sunrise Community Hospital',
     'R.S. Puram, Coimbatore 641002', 'TNMC-2012-88014', 16, False),
]


class Command(BaseCommand):
    help = 'Add a spread of providers across different cities to the directory.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be created without writing anything.')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = skipped = 0

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'DRY RUN -- nothing will be written.\n'))

        for (email, first, last, phone, ptype, specialty, clinic,
             address, reg_no, years, verified) in PROVIDERS:

            if User.objects.filter(email__iexact=email).exists():
                self.stdout.write(f'  skip    {clinic:<30} (already exists)')
                skipped += 1
                continue

            label = 'verified' if verified else 'pending '
            self.stdout.write(f'  create  {clinic:<30} {label}  {address}')
            created += 1
            if dry_run:
                continue

            user = User.objects.create_user(
                username=email, email=email, password=PASSWORD,
                first_name=first, last_name=last,
                role=User.Role.PROVIDER, phone_number=phone,
                address=address,
            )
            profile = ProviderProfile.objects.create(
                user=user, provider_type=ptype, specialty=specialty,
                clinic_name=clinic, address=address,
                registration_number=reg_no, years_experience=years,
                doc_registration_certificate=True, doc_government_id=True,
                doc_organization_info=True, doc_address_proof=verified,
            )
            if verified:
                # Same path an Admin approval takes, so verified_at is set and
                # the provider appears in the directory exactly as a really
                # approved one would.
                profile.approve()
                AuditLog.record(None, 'Approved provider',
                                profile.display_name(), AuditLog.Tag.OK)

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would create {created}, skip {skipped}. '
                'Re-run without --dry-run to apply.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'{created} provider(s) created, {skipped} already present.'))
        if created:
            self.stdout.write(f'Password for every new account: {PASSWORD}')
            self.stdout.write(
                'Cities now searchable from Find a Provider: '
                'Kochi, Thiruvananthapuram, Kozhikode, Bengaluru, Chennai, '
                'Hyderabad, Mumbai, Pune, New Delhi, Thrissur.')
