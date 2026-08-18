# CareNest — Project Diary

MDS482-4 Project-I · Sreenanda T, Terese Mathew · Guide: Dr Apash Roy

Add an entry per working session. Record what changed and *why*, not just
what was done — the reasoning is what the report and the viva need, and it
is the part nobody remembers three weeks later.

---

## Entry format

```
## YYYY-MM-DD — <short title>
**Who:** <names>
**Phase:** <phase from the completion plan>
**Done:** what actually changed
**Why:** the reasoning behind any decision made
**Blocked / open:** anything unresolved
**Next:** the immediate next step
```

---

## 2026-07-28 — Admin role, admin panel, and design documents
**Who:** Sreenanda, Terese
**Phase:** pre-plan (task-plan phase 2)

**Done:** Registered the custom `User` model in Django's admin. Added `ADMIN`
and later `NURSE` to `User.Role`. Built a separate in-app `adminpanel`
application at `/admin-panel/` with dashboard, verification queue, users,
providers and audit-log pages. Wrote `CONSENT_FRAMEWORK_DESIGN.md` (task 2.3)
and `NURSING_ROLE_DESIGN.md` (task 2.4).

**Why:** Django's built-in `/admin/` is a developer tool for inspecting
tables; the Admin *role* in our system is a product feature with its own
workflows (verification, suspension, audit). Conflating them would have
meant either exposing raw tables to a non-technical administrator or
rebuilding Django admin badly. They are deliberately two different surfaces.

Nursing was made its own `User.Role` rather than a Provider subtype, because
a nurse's permission set (assignment, visit logging, escalation) differs
fundamentally from a provider's (verification, listings, care plans), and the
codebase already uses a single-table role discriminator.

---

## 2026-07-31 — Project renamed to CareNest
**Who:** Sreenanda, Terese
**Phase:** pre-plan

**Done:** Renamed the product from "Smart Health Companion" to "CareNest",
tagline "Where Care Continues", across all live templates, views, README and
config comments.

**Why:** The new name reflects the continuity-of-care positioning agreed in
the scope redefinition. Internal technical identifiers (the Python package
name `smart_health_companion`, module import paths, the MySQL `DB_NAME`
default) were deliberately **not** renamed — renaming those would break
imports and migrations for no user-visible benefit.

**Open:** Two SRS documents and the review decks were submitted under the old
name. The final report needs a dated rename note in its front matter so an
examiner does not read these as two separate projects.

---

## 2026-07-31 — Application wired to the database end to end
**Who:** Sreenanda, Terese
**Phase:** pre-plan (task-plan phase 3)

**Done:** Replaced every placeholder page with real database-backed
functionality:

- Real authentication for all five roles; `role_required` decorator enforcing
  role-based access on every protected view.
- `VitalRecord` with automatic Normal/Watch/High flagging, `Medication` with
  per-day `MedicationDose` tracking, `LifestyleLog`, private `MoodLog`.
- `ConsentGrant` implementing the consent framework: per-category scope,
  expiry, revocation, and a `has_consent()` enforcement check.
- `CaregiverLink` with patient-side approval gating all caregiver access.
- `ProviderProfile` with document checklist and three-state verification;
  `Appointment` with the full request → accept → complete loop.
- `nursing` app: `NurseAssignment`, `NursingVisit`, escalation with severity.
- `AuditLog` (append-only) written on every consequential action.
- `health/analytics.py`: health score, trend series, and rule-based insights
  that each store the evidence that produced them.
- `seed_demo` management command and 39 end-to-end tests.

**Why:** Rule-based analytics rather than a trained model at this stage,
because the system has no real data yet and an interpretable baseline is what
the CRISP-DM write-up will compare any later model against. Storing the
evidence alongside each insight keeps the system explainable in a viva.

Mental-health data was implemented as a *hard exclusion* — there is no
`ConsentGrant` scope that can grant access to it — rather than as a default-off
setting, so it cannot be shared by misconfiguration.

---

## 2026-08-03 — Local verification and completion plan
**Who:** Sreenanda
**Phase:** 0

**Done:** Ran `migrate`, `seed_demo` and the full test suite on the local
Windows machine. All 39 tests pass. Wrote the phase-wise completion plan
covering the remaining work in eight phases.

**Why:** The task tracker had drifted badly out of date — many rows marked
"Not started" were in fact complete, which made the progress percentage
meaningless. The completion plan starts by reconciling the tracker against
reality before any new work is added.

**Next:** Reconcile the task tracker. Then Phase 1 (design artifacts) and
Phase 2 (prescription extraction) can run in parallel, one per person.

---

## 2026-08-03 — Phase 0 cleanup: drug-interaction dependency retired
**Who:** Sreenanda
**Phase:** 0

**Done:** Moved `data/db_drug_interactions.csv` (22 MB) and
`scripts/verify_drug_csv.py` to `_to_delete/`. Rewrote `data/README.md` to
document the retirement and the no-real-patient-data rule. Added
`.gitattributes` and extended `.gitignore`.

**Why:** Drug-drug interaction checking was removed from scope after review
feedback (task 2.1) because automatic interaction flagging is clinical
decision support, and this project makes no clinical claim. It was replaced
by the medication card plus a "show this to your doctor" prompt. Keeping a
22 MB dataset for a removed feature was dead weight in the repository and an
invitation to scope creep back into it.

**Blocked / open:** The files are in `_to_delete/` rather than deleted,
because the tooling used could not remove files on this drive. Delete that
folder manually.

**Next:** Task tracker reconciliation, then Phase 1.

---

## 2026-08-03 — Phase 1: design artifacts regenerated from the code
**Who:** Sreenanda, Terese (working jointly from here — the two-person task
split in the tracker no longer applies)
**Phase:** 1

**Done:** Produced the full set of design documents in `docs/`, generated from
the running system rather than from the pre-build intent:

- `erd.md` — every entity, field and relationship, dumped from the Django
  models via introspection.
- `architecture.md` — layered architecture plus a sequence diagram of a
  consent-gated read.
- `use_cases.md` — five actors, 28 implemented use cases each mapped to a real
  URL, and 8 planned ones mapped to phases.
- `modules.md` — 22 modules with implemented/planned status, and a record of
  the two modules removed from the original list.
- `information_architecture.md` — per-role navigation derived from the sidebar
  partials and URL configuration.
- `wireframes.md` — as-built layout of every screen.
- `consent_ux.md` — consent pop-up design for elderly, low-technology users.

All diagrams rendered to PNG and SVG in `reports/figures/`, and twelve
full-page screenshots captured from the running app with seeded data in
`reports/figures/screens/`.

**Why:** The earlier design artifacts predated the implementation, so they
described a system that no longer exists — six entities were missing and two
removed ones were still present. Generating them from model introspection
rather than from memory means the ERD cannot silently disagree with the
schema. Where the code and an ideal design differ, the documents note it
rather than drawing the ideal.

**Also fixed:** the patient dashboard was showing critical health warnings
with a green tick, which read as "all good" for what is a red alert. Severity
now drives both the icon and its colour, so status is never carried by colour
alone — an accessibility requirement as well as a correctness one.

**Blocked / open:** `_to_delete/` (25 MB) still needs deleting by hand. The
`admin` account still has role PATIENT.

**Next:** Phase 2 — prescription extraction. Decision taken: Tesseract for OCR
locally, with an LLM API for parsing the extracted text. This means
prescription *text* leaves the machine, which must be disclosed in the consent
wording and in the report's privacy section.

---

## 2026-08-03 — Login fixed for createsuperuser accounts
**Phase:** 1 (follow-up)

**Done:** `login_view` now resolves the typed email to a username before
authenticating, instead of assuming the two are identical.

**Why:** Registration always sets username = email, so the old code worked for
every registered account. `createsuperuser` asks for them separately, so the
project's original `admin` account (username `admin`, email
`admin.shc@email.com`) could never sign in to the app at all — typing the
username failed email validation, typing the email matched no username. Two
tests now cover it, including the exact failing case.

---

## 2026-08-03 — Phase 2: prescription extraction (process-and-discard)
**Phase:** 2

**Done:**
- `ExtractionJob` and `ExtractedMedication` models. The job records OCR
  confidence, which parser ran, and when the image bytes were released.
- `health/extraction.py`: local Tesseract OCR, a Gemini-backed parser, and a
  rule-based parser as an automatic fallback.
- Upload page with a mandatory consent tick, and a verify screen where the
  patient corrects the result before anything is saved.
- 16 tests, including one that walks the whole project tree before and after
  an upload and fails if any file appears.

**Why the rule-based parser exists alongside the LLM:** the app must work with
no API key, must survive the API being down mid-demo, and gives the report a
baseline to compare LLM extraction against on the same documents. The parser
that ran is recorded per job, so the comparison uses real data.

**Privacy consequence — must be in the report.** With a Gemini key configured,
the OCR *text* leaves the machine. The image never does. The claim is no longer
"nothing leaves your device"; the accurate wording is in
`docs/extraction_privacy.md` and must be used verbatim in the privacy section.

**A trap worth recording:** Django streams uploads over 2.5 MB to a temporary
file on disk by default. Phone photos exceed that routinely, so the default
would have silently made the process-and-discard claim false. Settings now
restrict uploads to the in-memory handler and reject anything over 15 MB. A
test asserts the setting, so a future change cannot break it unnoticed.

**Measured on a clean printed prescription:** 93.3% OCR confidence, 4 of 4
medicines found, 3 of 4 perfectly. Tesseract read `10ml` as `10m!`, so that
dose was dropped and confidence correctly reduced rather than guessed.

**Next:** Phase 2 is code-complete but not validated on real documents. Install
Tesseract, add a Gemini key to `.env`, and run 8-10 real prescriptions through
it — including handwritten ones — recording printed vs handwritten accuracy
separately in `reports/extraction_accuracy.md`.

---

## 2026-08-04 — Caregiver security (Terese's branch merged in)
**Who:** Terese
**Phase:** unplanned, alongside Phase 2/3

**Done:** `CaregiverInvite`, `Notification` and `TrustedDevice` models;
invite-code-or-email-or-CareNest-ID resolution for linking a caregiver to a
patient (`accounts/linking.py`); new-device sign-in approval for caregivers,
gated on `PlatformSettings.caregiver_device_approval_required`
(`accounts/devices.py`); a `Super Admin` distinction on top of `Admin`.

**Why:** Not part of the original phase plan — this was built independently
and arrived via `git pull`. Landed cleanly: migrations apply in sequence
(`accounts.0006`–`0008`), all tests pass, no conflicts with Phase 2/3 work.

**Blocked / open:** These features are not yet reflected in `docs/erd.md`,
`docs/use_cases.md` or the task tracker, which still describe the system as
of Phase 1. Needs a documentation catch-up pass before the report is written.

---

## 2026-08-05 — MySQL, a shared live instance, and Phase 3: Provider Care Loop
**Who:** Sreenanda
**Phase:** 3

**Done, infrastructure:**
- Fixed a Windows-only crash: `%-d` / `%-I` strftime flags (used to drop a
  leading zero) work on Linux/macOS but raise `ValueError` on Windows, which
  is exactly the kind of bug that survives testing on the developer's own
  machine and only shows up after a `git pull` onto a different one. Replaced
  with a `_friendly_datetime()` helper built from plain arithmetic.
- Switched the running app from SQLite to the MySQL database the project was
  designed around (`USE_SQLITE=0`); resolved a driver install and a root
  password mismatch along the way. All 105 tests passed against MySQL.
- Added `CSRF_TRUSTED_ORIGINS`, read from `.env`, which the project had never
  needed before because it had never been reached from any host other than
  `localhost`.
- App made temporarily reachable to both project members at once via a
  Cloudflare quick tunnel (`cloudflared`) pointed at the MySQL-backed local
  server — same running app, same database, both members see each other's
  changes live. No separate deployment, no second database to keep in sync.

**Done, Phase 3 — Provider Care Loop:**
- `ProviderAvailability` (weekly recurring hours) and `CarePlan` (one metric,
  one target, a review date, a note) models.
- Pre-visit snapshot (`previsit_snapshot`): shows a provider a patient's
  recent vitals, medication adherence, active care plans and nursing
  escalations from the last 30 days — but only for scopes the patient has
  actually granted, never because an appointment merely exists. A scope not
  granted renders an explicit "not shared" panel. Every view (and every
  refusal) is written to the audit log.
- One-click "share a pre-visit snapshot" action for patients: grants vitals +
  medications only, expiring 24 hours after the appointment.
- Care plan creation restricted to patients a provider has actually had an
  appointment with; progress is computed from the patient's own real data
  (`CarePlan.progress()`), returning `None` rather than a guessed value when
  there isn't enough data yet. Shown on the patient dashboard as a goal bar.
- Booking now validated against a provider's `ProviderAvailability`, if any
  is set; providers with no configured hours remain bookable any time.
- 10 new tests (`CareLoopTests`), covering consent-gated visibility, the
  mental-health exclusion holding under this new view, cross-provider
  appointment isolation, audit logging, and both availability outcomes.

**Why:** The pre-visit snapshot is the clearest answer to "why does a patient
need this app when they already have a doctor" — the provider sees three
months of trend data instead of one recalled number, and only what the
patient chose to share.

**Next:** Phase 4 — Monitoring, Alerts & Ephemeral Sharing.

---

## 2026-08-10 — Recommendation engine (Phase 5, task 4.5, started ahead of Phase 4)
**Who:** Sreenanda
**Phase:** 5 (data science) — the recommendation engine specifically, done
out of order at request; the other four Phase 5 models and Phase 4 (alerts)
are still pending.

**Done:**
- New `datascience` app. `SyntheticPatient` model marks every fake patient
  used for training/evaluation (`@carenest.synthetic` email), so real users
  are never touched by any of this.
- `generate_cohort` management command: synthetic patients (100 by default),
  each with 60-120 days of fake vitals, medication doses, lifestyle logs and
  a few mood check-ins, shaped by five hidden per-patient "tendency" floats
  (sleep, adherence, activity, hydration, engagement). Fixed-seed
  reproducible; assumptions written to `reports/synthetic_data_assumptions.md`
  on every run.
- `datascience/features.py`: turns a patient's last-14-days logs into a
  feature vector — the same computation for a synthetic training patient and
  a real one at prediction time.
- `datascience/recommend.py`: the engine itself, a RULE-PLUS-MODEL hybrid.
  A rule decides whether a suggestion is even eligible (backed by the
  patient's own numbers, matching the thresholds already in
  `health/analytics.py`); a `RandomForestClassifier` per suggestion type
  (trained on the synthetic cohort) ranks the eligible ones. Falls back to a
  plain rule-based score if no model has been trained yet, so a fresh
  checkout never breaks. Returns at most 3 suggestions, each with the
  concrete numbers behind it. Lifestyle/adherence nudges only — no clinical
  instructions, and MoodLog is never read.
- `datascience/evaluate.py` + `train_models` command: 5-fold **grouped**
  cross-validation, split by patient (never by row), metrics written to
  `datascience/artifacts/metrics.json` and a bar chart to
  `datascience/artifacts/plots/`.
- Admin-only model performance page at `/datascience/analytics/`.
- Patient dashboard shows a "Suggestions for you" panel — patient-facing
  only, confirmed by test to never reach a provider's pre-visit snapshot.
- 8 new tests (`DataScienceTests`): cohort generation count and
  reproducibility, no patient spans a fold's train/test split, model
  trains and predicts without error, graceful fallback with no trained
  model, no mood data anywhere in the engine, suggestions never leak to a
  provider view.

**Why this order:** requested directly, ahead of the plan's own sequencing
(Phase 4 first). The recommendation engine only depends on Phase 0 data
models, not on the alert engine, so nothing here was blocked by skipping
ahead — Phase 4 and the other four Phase 5 models are still open.

**Open follow-up:** run `python manage.py generate_cohort` then
`python manage.py train_models` locally to get real metrics (the ones
produced during development used a 6-8 patient cohort for test speed and
are not meaningful). Read `datascience/artifacts/metrics.json` critically —
anything above ~0.95 on a small synthetic cohort is more likely a leak than
genuine skill. The CRISP-DM write-up for this model (task 4.8) is still
needed in `reports/crispdm/`.

**Next:** Phase 4 — Monitoring, Alerts & Ephemeral Sharing (still pending),
or the remaining four Phase 5 models, whichever the team picks up next.

---

