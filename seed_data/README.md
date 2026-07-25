# seed_data/

Session 1 deliverable: planning-stage seed data, not yet loaded into any
database table (the models these will feed into don't exist until Session
2 - `health` app - and Session 3 - `providers` app).

## Files

- **providers.json** - 21 dummy providers (mix of specialties, 18 already
  `approved` and 3 left `pending` on purpose, so Terese's Session 3
  provider-verification/admin-approval flow has something real to approve
  or reject instead of an empty queue).
- **caregiver_patient_links.json** - 3 caregiver-patient pairs, matching
  the "simple version" scope decision in the sprint plan (caregiver enters
  the patient's unique ID to link - no request/approve workflow).

## What happens to these next

In **Session 3** (once `ProviderProfile`, `Appointment`, `ProviderNote`
models exist and are migrated), write a Django management command, e.g.:

```
python manage.py load_seed_data
```

that reads these JSON files and creates the real `ProviderProfile` rows
(and, once `accounts.User` supports it, creates caregiver/patient user
pairs and link records). Keeping the seed data in plain JSON now means
that command is a thin loader, not a place where you're inventing data
on the fly later.

## Admin account

Not a file - just run this once your venv is active, from the project
root:

```
python manage.py createsuperuser
```

Use a real email/password you'll remember; this is the account Terese's
Session 3 provider-approval review will use to log into `/admin/`.
