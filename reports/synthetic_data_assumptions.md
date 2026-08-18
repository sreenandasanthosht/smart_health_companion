# Synthetic cohort assumptions (generate_cohort)

Regenerated automatically every time `python manage.py generate_cohort` runs.
This file always reflects the actual last run, not a plan.

- Patients: 6 (no real patient data; every row is tagged via
  `datascience.SyntheticPatient` and uses an `@carenest.synthetic` email)
- History per patient: 15 days, ending today
- Random seed: 5 (reproducible -- the same seed and patient count
  always produces the same cohort)
- Hypertensive (base rate ~40%): 2 of 6
- Diabetic (base rate ~25%): 2 of 6
- Both conditions: 2 of 6
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
