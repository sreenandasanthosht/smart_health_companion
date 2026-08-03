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

