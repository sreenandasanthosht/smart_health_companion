"""
python manage.py generate_cohort [--patients N] [--days N] [--seed N] [--reset]

Generates a SYNTHETIC training/evaluation cohort for the datascience app --
no real patient data anywhere in this file. Every patient created here is
tagged with a datascience.SyntheticPatient row and an @carenest.synthetic
email address, so they are trivially distinguishable from real signups and
never appear in any real-user-facing list or search.

Design (documented again in reports/synthetic_data_assumptions.md, written
by this command as it runs, so the numbers below always match reality):
  - 100 patients by default. About 40% are flagged hypertensive and 25%
    diabetic (independently, so some patients are both), which sets the
    baseline distribution their fake vitals are drawn from.
  - Each patient gets 90 days of history by default (the plan's 60-120
    day range).
  - Five hidden "tendency" floats per patient (0=poor, 1=excellent) drive
    how their logs look: sleep, medication adherence, activity, hydration
    and general logging engagement. These are the ground truth the
    recommendation model is trained to predict FROM the noisy logs -- see
    datascience/recommend.py for why they are never used as a feature.
  - Logging is deliberately incomplete: a real patient doesn't record
    vitals or lifestyle every single day, and how often they DO is itself
    driven by their engagement tendency.
"""
import datetime
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from datascience.models import SyntheticPatient
from health.models import LifestyleLog, Medication, MedicationDose, MoodLog, VitalRecord

MOODS = ['Calm', 'Content', 'Anxious', 'Low', 'Stressed', 'Good']
CONDITION_MEDS = {
    'hypertension': ('Amlodipine', '5mg', 'Once daily, morning'),
    'diabetes': ('Metformin', '500mg', 'Twice daily, with meals'),
    'general': ('Multivitamin', '1 tablet', 'Once daily'),
}


def _vital_status(systolic, diastolic, heart_rate):
    """Mirrors VitalRecord.compute_status() -- duplicated here on purpose
    because bulk_create() skips model.save(), and this keeps the two
    definitions next to their own docstrings instead of one importing
    private behaviour from the other."""
    if systolic >= 140 or diastolic >= 90 or (heart_rate and heart_rate >= 110):
        return VitalRecord.Status.HIGH
    if systolic >= 130 or diastolic >= 85 or (heart_rate and heart_rate >= 100):
        return VitalRecord.Status.WATCH
    return VitalRecord.Status.NORMAL


def _clip(value, lo, hi):
    return max(lo, min(hi, value))


class Command(BaseCommand):
    help = 'Generate a synthetic patient cohort for the datascience models (no real data).'

    def add_arguments(self, parser):
        parser.add_argument('--patients', type=int, default=100)
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--reset', action='store_true',
                             help='Delete any existing synthetic cohort first and regenerate.')

    def handle(self, *args, **options):
        User = get_user_model()
        n_patients = options['patients']
        n_days = options['days']
        base_seed = options['seed']

        existing = SyntheticPatient.objects.count()
        if existing and not options['reset']:
            self.stdout.write(self.style.WARNING(
                f'{existing} synthetic patients already exist. Pass --reset to regenerate.'))
            return

        if existing:
            User.objects.filter(synthetic_profile__isnull=False).delete()  # cascades to their health data
            self.stdout.write(f'Deleted {existing} existing synthetic patients.')

        today = timezone.localdate()
        n_hypertensive = n_diabetic = n_both = 0

        for i in range(n_patients):
            rng = random.Random(base_seed * 100_000 + i)
            age = rng.randint(30, 80)
            sex = rng.choice(['M', 'F'])
            hypertensive = rng.random() < 0.40
            diabetic = rng.random() < 0.25
            if hypertensive:
                n_hypertensive += 1
            if diabetic:
                n_diabetic += 1
            if hypertensive and diabetic:
                n_both += 1

            sleep_tendency = rng.random()
            adherence_tendency = rng.random()
            activity_tendency = rng.random()
            hydration_tendency = rng.random()
            engagement_tendency = rng.random()

            email = f'synth-patient-{base_seed}-{i + 1:04d}@carenest.synthetic'
            user = User.objects.create_user(
                username=email, email=email, password=None,
                first_name='Synthetic', last_name=f'Patient {i + 1}',
                role=User.Role.PATIENT,
                date_of_birth=today.replace(year=today.year - age),
                sex=sex,
            )
            user.set_unusable_password()
            user.save(update_fields=['password'])

            SyntheticPatient.objects.create(
                user=user, age=age, sex=sex,
                chronic_hypertension=hypertensive, chronic_diabetes=diabetic,
                sleep_tendency=sleep_tendency, adherence_tendency=adherence_tendency,
                activity_tendency=activity_tendency, hydration_tendency=hydration_tendency,
                engagement_tendency=engagement_tendency, seed=base_seed * 100_000 + i,
            )

            # -- Medications, one per relevant chronic condition + a baseline one.
            meds = []
            if hypertensive:
                name, dose, schedule = CONDITION_MEDS['hypertension']
                meds.append(Medication.objects.create(
                    patient=user, name=name, dose=dose, schedule=schedule,
                    start_date=today - datetime.timedelta(days=n_days)))
            if diabetic:
                name, dose, schedule = CONDITION_MEDS['diabetes']
                meds.append(Medication.objects.create(
                    patient=user, name=name, dose=dose, schedule=schedule,
                    start_date=today - datetime.timedelta(days=n_days)))
            if not meds:
                name, dose, schedule = CONDITION_MEDS['general']
                meds.append(Medication.objects.create(
                    patient=user, name=name, dose=dose, schedule=schedule,
                    start_date=today - datetime.timedelta(days=n_days)))

            vitals_batch, lifestyle_batch, dose_batch, mood_batch = [], [], [], []

            base_weight = rng.uniform(55, 95)
            for offset in range(n_days, 0, -1):
                day = today - datetime.timedelta(days=offset)
                log_prob = 0.35 + 0.5 * engagement_tendency  # 0.35 - 0.85

                # Vitals -- not every day.
                if rng.random() < log_prob * 0.6:
                    sys_mean = 145 if hypertensive else 118
                    systolic = int(_clip(rng.gauss(sys_mean, 10), 90, 190))
                    diastolic = int(_clip(rng.gauss(sys_mean - 45, 7), 55, 120))
                    hr = int(_clip(rng.gauss(75, 10), 50, 130))
                    sugar_mean = 165 if diabetic else 100
                    sugar = round(_clip(rng.gauss(sugar_mean, 22), 70, 320), 1)
                    weight = round(_clip(base_weight + rng.gauss(0, 0.4), 40, 150), 1)
                    rec = VitalRecord(
                        patient=user,
                        recorded_at=timezone.make_aware(datetime.datetime.combine(day, datetime.time(8, 0))),
                        bp_systolic=systolic, bp_diastolic=diastolic, heart_rate=hr,
                        blood_sugar=sugar, weight_kg=weight,
                        status=_vital_status(systolic, diastolic, hr), source=VitalRecord.Source.SELF,
                    )
                    vitals_batch.append(rec)

                # Lifestyle -- not every day either.
                if rng.random() < log_prob:
                    sleep_hours = round(_clip(rng.gauss(5.0 + sleep_tendency * 3.5, 0.7), 3.0, 10.0), 1)
                    water = round(_clip(rng.gauss(0.8 + hydration_tendency * 1.8, 0.3), 0.2, 4.0), 1)
                    steps = int(_clip(rng.gauss(2000 + activity_tendency * 9000, 1500), 0, 20000))
                    lifestyle_batch.append(LifestyleLog(
                        patient=user, date=day, sleep_hours=sleep_hours,
                        water_litres=water, steps=steps,
                    ))

                # Medication doses -- one tick per medication per day.
                for med in meds:
                    taken = rng.random() < _clip(0.3 + adherence_tendency * 0.65, 0.05, 0.98)
                    dose_batch.append(MedicationDose(
                        medication=med, date=day, taken=taken,
                        taken_at=timezone.make_aware(datetime.datetime.combine(day, datetime.time(9, 0))) if taken else None,
                    ))

                # A handful of mood check-ins, sparse and unrelated to the label logic.
                if rng.random() < 0.08:
                    mood_batch.append(MoodLog(patient=user, date=day, mood=rng.choice(MOODS), note=''))

            VitalRecord.objects.bulk_create(vitals_batch)
            LifestyleLog.objects.bulk_create(lifestyle_batch)
            MedicationDose.objects.bulk_create(dose_batch)
            MoodLog.objects.bulk_create(mood_batch)

        self._write_assumptions(n_patients, n_days, base_seed, n_hypertensive, n_diabetic, n_both)
        self.stdout.write(self.style.SUCCESS(
            f'Generated {n_patients} synthetic patients ({n_days} days each, seed={base_seed}).'))

    def _write_assumptions(self, n_patients, n_days, seed, n_hyp, n_dia, n_both):
        path = settings.BASE_DIR / 'reports' / 'synthetic_data_assumptions.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f"""# Synthetic cohort assumptions (generate_cohort)

Regenerated automatically every time `python manage.py generate_cohort` runs.
This file always reflects the actual last run, not a plan.

- Patients: {n_patients} (no real patient data; every row is tagged via
  `datascience.SyntheticPatient` and uses an `@carenest.synthetic` email)
- History per patient: {n_days} days, ending today
- Random seed: {seed} (reproducible -- the same seed and patient count
  always produces the same cohort)
- Hypertensive (base rate ~40%): {n_hyp} of {n_patients}
- Diabetic (base rate ~25%): {n_dia} of {n_patients}
- Both conditions: {n_both} of {n_patients}
- Vitals: hypertensive patients drawn from a higher systolic baseline
  (mean 145 vs 118 mmHg); diabetic patients from a higher fasting-sugar
  baseline (mean 165 vs 100 mg/dL). Logged on a subset of days, not daily.
- Lifestyle (sleep/water/steps) and medication adherence are each driven
  by a hidden per-patient "tendency" float (0-1), used only to generate
  the fake logs and to label training data -- never given to a model as
  an input feature.
- Overall logging frequency (how many days have ANY record at all) is
  itself driven by a hidden "engagement tendency", so sparser patients
  look the way a real disengaged patient's data would.
- Mood check-ins are sparse (~8% of days) and not used to generate or
  label any recommendation -- MoodLog is a hard exclusion throughout the
  app (see CONSENT_FRAMEWORK_DESIGN.md).

Limitation: this is a small, synthetic cohort with hand-chosen base rates
and distributions, not real epidemiological data. It is fit for
demonstrating and evaluating the modelling pipeline, not for any clinical
claim.
"""
        path.write_text(text)
