# data/

Datasets used by CareNest.

## Current contents

Nothing is required here to run the application. The demo data used for
development and review is generated, not downloaded — create it with:

```
python manage.py seed_demo
```

The synthetic cohort for the data-science models (Phase 5) will also be
generated rather than stored, via `python manage.py generate_cohort`. Its
generation assumptions are written to `reports/synthetic_data_assumptions.md`
at the time it runs, so the dataset is always reproducible from the seed.

## Retired: db_drug_interactions.csv

A 22 MB drug-drug interaction lookup table used to live here. It has been
retired and moved to `_to_delete/`.

Drug-drug interaction checking was removed from the project scope following
review feedback (task 2.1 in the task plan). Automatically flagging
interactions is a clinical decision-support function, and this project makes
no clinical claim. It was replaced by the medication card plus a
"show this to your doctor" prompt, which keeps the patient informed without
the application making a clinical judgement.

The file was a flat CSV read directly at request time, not a Django model,
so retiring it required no migration and left no schema behind.

## Rule for anything added here

No real patient data, ever. Every dataset in this project is either
synthetic or a public reference file, and its origin is recorded in this
file when it is added.
