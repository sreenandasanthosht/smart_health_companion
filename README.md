# CareNest

Where Care Continues — MDS482-4 Project-I.
Built with **Django** (Python) using the **MVT** architecture, on **SQLite** by default
(MySQL is supported by flipping one setting).

## What works

Every page is backed by the database. There is no placeholder data left in the
running application.

Patients register themselves and land straight on a dashboard that fills in as
they use it: they log vitals (each reading auto-flagged Normal / Watch / High),
track medicines and tick off doses, record sleep, water, steps and activity, and
keep a private mental-health journal. The dashboard computes a health score,
draws real trend lines from their own readings, and lists generated observations
alongside the evidence for each one.

Caregivers request access using a patient's CareNest ID and see nothing at all
until that patient approves them — and then only the categories the patient
consented to. Providers register, submit verification documents, and appear in
the searchable directory only once an administrator approves them; patients book
appointments with them, and providers accept, decline, annotate and complete
those requests. Nurses are assigned to patients by an administrator, log home
visits with vitals that are provenance-tagged as nurse-recorded, and can raise
escalations for a provider's attention. Administrators work a live verification
queue, manage and suspend accounts, assign nurses, and read an append-only audit
log of every consequential action.

## Roles

| Role | How the account is created | Main surface |
|---|---|---|
| Patient | Self-registers | `/health/dashboard/` |
| Caregiver | Self-registers, then patient approves the link | `/health/caregiver-dashboard/` |
| Provider | Self-registers, then admin verifies | `/providers/dashboard/` |
| Nurse | Assigned by an administrator | `/nursing/dashboard/` |
| Admin | Created with `createsuperuser` or by an admin | `/admin-panel/dashboard/` |

Nurse and Admin are deliberately **not** self-registerable — the registration
form rejects those values outright.

## Project layout

```
smart_health_companion/
├── manage.py
├── config/          # settings + top-level URLs
├── accounts/        # users, roles, CareNest ID, auth, profile, caregiver links
├── health/          # vitals, medications, lifestyle, mental health, consent
│   └── analytics.py # health score, trend series, insight rules
├── providers/       # provider profiles, verification, appointments
├── nursing/         # nurse assignments and visit logging
├── adminpanel/      # platform admin dashboard + audit log
├── core/            # home page, seed_demo command, end-to-end tests
├── templates/       # shared layouts and sidebars
└── static/          # CSS
```

Six apps: `accounts`, `health`, `providers`, `nursing`, `adminpanel`, `core`.
In Django an "app" is a feature-module, not a whole separate site.

## Quick start

```bash
# 1. create & activate a virtual environment
python -m venv venv
venv\Scripts\activate           # macOS/Linux: source venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. set up local config (already done if .env exists)
copy .env.example .env          # macOS/Linux: cp .env.example .env
#    USE_SQLITE=1 is the default and needs no database server

# 4. create the database tables
python manage.py migrate

# 5. fill it with realistic demo data (optional but recommended)
python manage.py seed_demo

# 6. run it
python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

After `seed_demo`, every account uses the password `CareNest#2026`:

| Role | Email |
|---|---|
| Patient | `latha@example.com` (has history, a caregiver and a nurse) |
| Patient | `ramesh@example.com` |
| Caregiver | `meera@example.com` |
| Provider | `dr.nair@example.com` (verified) |
| Provider | `prakashlab@example.com` (awaiting verification) |
| Nurse | `nurse.priya@example.com` |
| Admin | `admin@example.com` (also a Django superuser) |

Re-running `seed_demo` is safe; `python manage.py seed_demo --reset` wipes the
demo accounts and rebuilds them.

There are two different admin surfaces, and they are not the same thing:

* `/admin/` — Django's built-in developer admin, for inspecting raw tables.
* `/admin-panel/dashboard/` — CareNest's own Admin role dashboard, a real app feature.

## Tests

```bash
python manage.py test
```

39 end-to-end tests cover registration and login for every role, saving vitals
and medicines, the consent rules (including that mental-health data can never be
shared), provider verification and booking, nurse visit logging, role-based
access control, and that every page returns HTTP 200.

## Design decisions

Two design documents drove the data model and are worth reading alongside the code:

* `CONSENT_FRAMEWORK_DESIGN.md` — implemented by `health.models.ConsentGrant` and
  the `has_consent()` check. Mental-health data is a hard exclusion: there is no
  scope value that can grant access to it.
* `NURSING_ROLE_DESIGN.md` — implemented by the `nursing` app. Nurse-recorded
  vitals go into the same `VitalRecord` table as self-recorded ones but carry a
  `source` and `entered_by`, which answers the open question that document raised.

The status flags and dashboard insights are rule-based rather than a trained
model, and every insight stores the evidence that produced it. That keeps the
system explainable and gives the CRISP-DM write-up an interpretable baseline to
compare any later model against.
