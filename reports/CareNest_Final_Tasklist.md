# CareNest — Final Tasklist (Two-Person Parallel Plan)

**Audit date:** 18 August 2026
**Audited against:** the live code in `smart_health_companion` (not the task plan)

**Tool key:** **[CD]** Claude Design · **[CW]** Cowork (this session) · **[M]** Manual (run locally)

**Owner key:**
- **[A] Person A — Backend / Data** — models, migrations, auth logic, settings, DS models, tests
- **[B] Person B — Frontend / UX / Docs** — templates, CSS, component kit, accessibility, screenshots, deck
- **[A+B]** — must be done together, or one blocks the other
- **[EITHER]** — genuinely independent, whoever is free

This follows the split already in your task plan (Backend member / Frontend member) and
your two git branches (`sreenanda` / `tereseshc`). Swap the letters if that's backwards.

---

## ⚠️ Rules for working in parallel — read before starting

Your git history already shows **three merge migrations** in `health/migrations`
(`0005_merge`, `0006_merge`, `0009_merge`). That's what happens when two people
create migrations on separate branches. Don't do it a fourth time today.

1. **Only Person A creates migrations.** If B needs a model field, B asks A. No exceptions.
2. **Only Person A touches `config/settings.py`.** It's one file everyone wants to edit.
3. **Only Person B touches CSS and `templates/`.** A touches `.py`; B touches `.html`/`.css`.
4. **`accounts/forms.py` and `accounts/views.py` are A's.
   `accounts/templates/` is B's.** Same feature, different files — no conflict.
5. **Pull before you push.** Every time. You have two active branches.
6. **Nobody edits `reports/` at the same time.** Agree who owns the diary and the report
   file, and the other person sends notes rather than editing directly.

---

## What each tool is actually good for here

| Tool | Use it for | Don't use it for |
|---|---|---|
| **Claude Design** (`claude.ai/design`) | Building a CareNest **component library** — form fields, buttons, cards, consent modal, alert badges, empty states — as one reviewable source of truth, with light/dark and accessibility baked in. | It won't restyle 60 Django templates for you. It produces the kit; applying it is a separate pass. |
| **Cowork** (here) | Reading and editing code, writing forms/validators/tests/migrations, auditing schema, generating docs and the final report. | Running your test suite or dev server — the `venv` is Windows, my sandbox is Linux. Also can't judge how a page *feels*. |
| **Manual** | `manage.py` commands, clicking through all five roles, screen recording, clinical wording, author judgment. | Bulk repetitive edits — hand those to Cowork. |

---

# PHASE 0 — Do this first, together, before splitting up

**Nothing below is trustworthy until these are done. ~20 minutes. [A+B]**

- [ ] **`manage.py migrate`** **[A]** **[M]**
      `db.sqlite3` is dated 4 August; migrations run to `0009` dated 18 August. The
      database on disk is missing ~15 tables — `DoseTime`, `CarePlan`,
      `ProviderAvailability`, `LabReport`, `LabResultValue`, `ExtractedLabValue`,
      `SyntheticPatient`, `ServiceOffering`, `Department`, `MedicineOrder` and more.
      **Every screenshot and demo is invalid until this runs.**
- [ ] **Run the full test suite, record the number** **[A]** **[M]**
      `venv\Scripts\python.exe manage.py test` — the pass/fail count goes in the report.
- [ ] **`generate_cohort` then `train_models`** **[A]** **[M]**
      Current `metrics.json` was trained on **6 patients**; F1 = 0.4 ± 0.49 is noise.
      This unblocks every real number in the report's results chapter. Start it early —
      it runs while you do other things.
- [ ] **Agree the project name: CareNest or Smart Health Companion** **[A+B]**
      Code and design docs say CareNest; decks and the task plan say the other. Decide now,
      in one minute, so neither of you writes the wrong one all day.
- [ ] **Agree who owns `reports/project_diary.md` and the final report file** **[A+B]**

---

# THE PARALLEL SPLIT

From here, A and B work simultaneously. Tracks are independent unless marked.

---

## ═══ TRACK A — Person A (Backend / Data) ═══

### A1. Auth fixes — highest priority, ~2 hours, fully independent of B

All in `accounts/forms.py`, `accounts/views.py`, `accounts/models.py`, `accounts/urls.py`,
`config/settings.py`. **B is not in any of these files.**

- [ ] **Make `email` unique** **[CW]**
      `accounts_user.email` is a plain `varchar(254)`. Registration checks
      `username__iexact`, not `email`. Add `unique=True` + migration + data cleanup.
      *Do this one first — A2 depends on it.*
- [ ] **Delete `_username_for_login`** **[CW]** — depends on the above
      That 20-line helper exists *only* to paper over non-unique emails; it even has a
      `match.count() > 1` branch admitting the case happens. Once email is unique it
      collapses to a single lookup.
- [ ] **Add password reset** **[CW]** — *the biggest functional gap in the project*
      There is no `password_reset` view, URL, or template **anywhere**. A user who forgets
      their password is locked out permanently. Wire up Django's built-in
      `PasswordResetView` family — 5 views, ~15 lines of urls.
      ↪ **Hand off to B:** the 4 reset templates. Tell B as soon as the URLs exist.
- [ ] **Rate limiting / lockout on failed logins** **[CW]**
      Unlimited password guesses today. `django-axes` or a cache-backed counter.
      Gives you a real security paragraph for the report.
- [ ] **Session security settings** **[CW]**
      No `SESSION_COOKIE_AGE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, `SESSION_COOKIE_SECURE`,
      `CSRF_COOKIE_SECURE`, or `SESSION_COOKIE_HTTPONLY` in `settings.py`. Set them explicitly
      for a health app.
- [ ] **`DEBUG` defaults to `True`** — flip to `False` before submission **[CW]**
- [ ] **Move password rules into `RegisterForm.clean()`** **[CW]**
      `password != confirm_password` and `validate_password()` currently sit in the view.
      Move them to the form — Django idiom, reusable, testable.
- [ ] **Move `__init__` below the field declarations** in `RegisterForm` **[CW]**
      It's currently defined mid-class-body, between `role` and `password`.
- [ ] **Add a phone-number `RegexValidator`** **[CW]** — `CharField(max_length=20)` accepts `"aaaaaaa"`.
- [ ] **Build a real `ProviderOnboardingForm`** **[CW]**
      `onboarding_view` writes five credential fields straight from `request.POST.get()`
      onto the model with no validation. `years_experience` uses
      `int(years) if years.isdigit() else None` — silently swallows bad input.
      `profile_view` has the same problem.
- [ ] **Add a terms / privacy consent checkbox to registration** **[CW]**
      Consent is this project's headline claim, and the one place a user legally agrees
      to anything has no checkbox. Log acceptance to `AuditLog`.
      ↪ **Hand off to B:** the checkbox markup and wording.
- [ ] Keep the generic *"Incorrect email or password"* message — it correctly avoids
      leaking which accounts exist. **Note this as deliberate in the report.** **[CW]**

### A2. Schema fixes — independent of B

- [ ] **Add `temperature` and `spo2` to `VitalRecord`** **[CW]**
      Your task plan and design docs both claim "threshold rules for BP/HR/temp/SpO2".
      The table has only `bp_systolic`, `bp_diastolic`, `blood_sugar`, `weight_kg`,
      `heart_rate`. Add the columns or correct every document. **Don't let this
      mismatch reach the report.**
      ↪ **Hand off to B:** two new fields on the vitals form.
- [ ] **Make `bp_systolic` / `bp_diastolic` nullable** **[CW]**
      They're NOT NULL while every other vital is nullable — so a patient logging only
      their weight has to invent a blood pressure.
- [ ] **Bound the numeric vitals fields** **[CW]** — `bp_systolic = 9999` poisons anomaly detection.
- [ ] **Decide the fate of `Medication.schedule`** (free text, still present alongside
      the structured `DoseTime` table that replaced it) **[CW]**
- [ ] **Check what `HealthDocument` actually stores** **[CW]**
      A table called `health_healthdocument` in a system whose central claim is
      process-and-discard reads like a contradiction. If it's metadata only,
      **say so explicitly in the report.**
- [ ] **Add indexes**: `VitalRecord(patient_id, recorded_at)`, `MedicationDose.date`,
      `ConsentGrant(patient_id, recipient_id)`, `AuditLog.created_at` **[CW]**
- [ ] **Squash or document the merged migration tree** **[CW]**
      Two `0004_*`, two `0005_*`, two `0006_*`, plus `0009_merge` in `health/migrations`.
      Either squash, or write a short note explaining the two-developer workflow.
- [ ] **Decide MySQL vs SQLite for the submitted system and state why** **[CW]**
- [ ] **Defend the 10-boolean `ConsentGrant` design in the report** rather than
      refactoring it now — a `ConsentScope` child table would normalise it, but it's
      not worth the churn today. **[CW]**

### A3. Data science — the biggest remaining gap

*Start after `train_models` finishes in Phase 0.*

- [ ] Medication non-adherence model (4.2) **[CW]**
- [ ] Health-risk prediction model (4.3) **[CW]**
- [ ] Vitals anomaly detection model (4.4) **[CW]**
      All three share the existing `datascience/features.py` pipeline, so the marginal
      cost is lower than it looks. Do 4.2 and 4.4 first — the data and thresholds exist.
- [ ] Decide 4.6 (mood/sentiment): build it, or document the exclusion as a deliberate
      privacy decision **[CW]**
- [ ] **CRISP-DM write-up per model (4.8)** — `reports/crispdm/` doesn't exist.
      Explicitly required for MDS grading. **[CW]**
- [ ] Monitoring engine (3.14) — medication alerts done; vitals-anomaly alerts to
      provider/nurse not started **[CW]**
      ↪ **Hand off to B:** the monitoring dashboard (3.30) once the engine emits alerts.

### A4. Tests

- [ ] **Deletion-verification test (5.3)** **[CW]**
      Query `ExtractionJob.raw_text` directly after a completed job to prove it's cleared.
      This is the proof of your headline privacy claim — it deserves a dedicated test.
- [ ] E2E 5-role journey tests (5.6) **[CW]**
- [ ] Consent audit-trail assertions (5.7) **[CW]**
- [ ] Extend `EveryPageRendersTests` to the new lab / care-plan / availability pages **[CW]**

---

## ═══ TRACK B — Person B (Frontend / UX / Docs) ═══

### B1. Cleanup — do this first, it makes everything else tractable

- [ ] **Delete the ~24 stray root-level `.html` mockups** **[CW]**
      `patient_dashboard.html`, `provider_consult.html`, `admin_users.html` etc. sit in the
      project root duplicating the real templates in `*/templates/`. Dead files that will
      confuse anyone reading your submission. Move to `_to_delete/`.
- [ ] **Also clear out** `venv.zip` (18 MB), `_backup_before_build.tar.gz`,
      `db.sqlite3.backup-before-provider-modules` **[CW]**
- [ ] **Consolidate the two stylesheets** — `shc.css` (project root) and the dashboard
      CSS under `static/`. One file. **[CW]**
- [ ] **Rename anything still called `shc`** — the project is CareNest now **[CW]**

### B2. Component library — the Claude Design job

- [ ] **Build the CareNest component kit** **[CD]**
      One set covering: form field (default / focus / error / disabled), button hierarchy,
      card, **consent modal**, alert & severity badges, empty state, table, KPI tile.
      Get it right once, review it as a set, then apply.
- [ ] **Extract `templates/partials/_consent_modal.html`** **[CW]**
      Consent UI is currently inline on 4+ pages with no shared partial. The wording will
      drift between pages — which is exactly the thing your report claims is centrally
      controlled.
- [ ] **Apply the kit's classes across the templates** **[CW]**
- [ ] **Diff the six provider dashboards** (`dash_clinical`, `dash_pharmacy`,
      `dash_diagnostics`, `dash_wellness`, `dash_home_care`, `dash_mental_health`)
      for inconsistent layout and shared blocks **[CW]**
- [ ] **Chart consistency pass** — vitals sparklines and the DS analytics page:
      one palette, one axis treatment, readable at large text sizes **[CD]/[CW]**

### B3. Registration & login UX — the visual half of A1

*Same features as A1, different files. No conflict — but coordinate on timing.*

- [ ] **Verify the conditional field reveal actually works** **[M]**
      Role is a `RadioSelect`; picking Caregiver or Provider should reveal a conditional
      field. Confirm it's wired in JS and doesn't just render everything at once.
- [ ] Password strength meter — currently the user learns their password is too short
      only after a round-trip **[CD]**
- [ ] "Show password" toggle — meaningful for elderly users on mobile **[CD]**
- [ ] ⏳ **Password-reset templates (4 of them)** — *blocked until A ships the URLs* **[CW]**
- [ ] ⏳ **Terms checkbox markup and wording** — *blocked until A adds the form field* **[CW]**
- [ ] ⏳ **Temperature and SpO2 inputs on the vitals form** — *blocked until A's migration* **[CW]**

### B4. Page-by-page field audit

- [ ] **Build the audit sheet first** **[CW]**
      One row per page: URL, template, every input, its model field, validation present,
      required/optional, label text, error message. **24+ pages.** Without the sheet this
      sweep drifts.

| Area | Pages |
|---|---|
| Accounts (5) | register, login, onboarding (caregiver), onboarding (provider), profile |
| Health / patient (14) | dashboard, vitals, medications, lifestyle, mental-health, share, caregiver-dashboard, caregiver-requests, prescription upload, extraction verify, lab upload, lab verify, lab results, notifications |
| Nursing (4) | dashboard, patient detail, log visit, visits |
| Providers (11+6) | directory, appointments, dashboard, services, pending, my-events, public events, previsit snapshot, care plans, availability + 6 role dashboards |
| Admin (13) | dashboard, users, accounts, providers, verification, audit log, caregivers, nursing, complaints, announcements, events, settings, analytics |
| Data science (1) | analytics |

Check on every form:

- [ ] Every field has a `<label>` bound with `for=` (screen readers + elderly users) **[M]**
- [ ] Error messages are plain language, not Django defaults ("Enter a valid value") **[CW]**
- [ ] Every page renders for the roles it should, 403s for the roles it shouldn't **[M]**
- [ ] ↪ **Report to A:** any view doing bare `request.POST.get()` with no Form class

### B5. UX passes — needs your judgment, can't be delegated

- [ ] **Accessibility pass** **[M]** + **[CD]**
      Base font size, 44px minimum tap targets, contrast ≥ 4.5:1, focus-visible outlines,
      no colour-only status indication. Your users are elderly and low-tech — a report
      claiming elderly-friendly design without evidence will get challenged in the viva.
- [ ] **Consent fatigue count** **[M]**
      Task 2.11 explicitly warns about this. Count the modals a patient sees in one
      realistic session: upload a prescription → share with provider → link a caregiver.
      More than three, redesign.
- [ ] **Error recovery walkthrough** **[M]**
      OCR misreads a medicine name. A caregiver's link request is rejected. A provider is
      un-verified mid-session. Walk each unhappy path.
- [ ] **Empty states** — a brand-new patient sees empty vitals, medications, appointments.
      Does each explain what to do next, or show a blank table? **[M]**
- [ ] **Mobile at 375px** — all five dashboards **[M]**

### B6. Documentation & assets

- [ ] **Screenshot every page** into `reports/figures/screens/` (already exists, waiting) **[M]**
      *Do this AFTER Phase 0's migrate, or the screenshots show a stale system.*
- [ ] Update the task tracker xlsx — it says 36/70, reality is ~53/70 **[CW]**
- [ ] Project diary — no entries for 17–18 August (lab reports, medication alerts,
      `core/` refactor, requirements.txt) **[CW]**
- [ ] Demo-2 deck (6.2) **[CW]**
- [ ] Demo recording / screencast (6.4) **[M]** — *needs a working system, do it late*

---

# ═══ CONVERGE — back together at the end ═══

- [ ] **Deployment / demo setup (6.6)** **[A]** with **[B]** verifying
- [ ] **Final project report (6.1)** **[A+B]** **[CW]**
      A writes: architecture, data model, DS chapters, testing.
      B writes: UI/UX, accessibility, user journeys, figures.
      **One person owns the merge** — agree who before you start writing.
- [ ] **Final read-through together** — check the name is consistent, the numbers match
      the metrics you actually generated, and no chapter claims something you cut. **[A+B]**

---

# Timeline — what runs at the same time

| Slot | Person A | Person B |
|---|---|---|
| **0:00–0:30** | *Together:* migrate, run tests, kick off `train_models`, agree the name | ← same |
| **0:30–2:30** | A1 auth fixes (email unique → reset → throttling → settings) | B1 cleanup, then B2 component kit **[CD]** |
| **2:30–4:00** | A2 schema fixes + migrations | B3 registration/login UX + the unblocked templates |
| **4:00–6:00** | A3 data science models (4.2, 4.4) + CRISP-DM | B4 field audit sheet + fixes |
| **6:00–7:00** | A4 tests, especially deletion verification (5.3) | B5 accessibility + consent fatigue, B6 screenshots |
| **7:00+** | *Together:* final report | ← same |

**Three handoff points** where B waits on A — plan around them:

1. A ships password-reset URLs → B builds the 4 templates
2. A adds the terms checkbox field → B writes the markup and wording
3. A's `temperature`/`spo2` migration lands → B adds the vitals inputs

**B should do B1 and B2 during those windows**, since neither depends on A at all.

---

**Realistic note:** the full list is roughly two days of work for two people. If today is
genuinely the last day, run Phase 0, then A does A1 + A3 + CRISP-DM while B does B1 + B6,
and put the UI/UX sweep in the report's *Future Work* chapter rather than half-finishing it.
