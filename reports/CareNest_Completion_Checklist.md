# CareNest / Smart Health Companion — Completion Checklist
**Status audit date:** 18 August 2026
**Audited against:** `D:\msds\project\integrated smart health tracker\smart_health_companion` (actual code, not the task tracker)
**Goal:** wrap up and produce the Final Project Report (task 6.1)

---

## 0. Read this first — the tracker is stale

`Smart_Health_Companion_Task_Plan.xlsx` was last verified against code on **2026-08-03**.
Since then a large amount of work has landed (extraction pipeline, lab reports,
medication alerts, provider modules, the whole `datascience` app). The tracker
says **36/70 done**; the real figure is closer to **53/70**.

Two other drift items to fix before the report is written:

- [ ] The project has been renamed **CareNest** in the code/design docs, but the
      decks, the task plan and older reports still say *Smart Health Companion*.
      Pick one name and make it consistent everywhere.
- [ ] The project diary has no entries for **17–18 August** (lab reports,
      medication alerts, `core/` refactor, requirements.txt). Add them — the
      diary is a graded deliverable.

---

## 1. Already done (verified in code today — no action needed)

These are marked "Not started" or "In progress" in the xlsx but exist and work:

- [x] 2.11 Consent pop-up UX — `docs/consent_ux.md`; consent UI live on prescription,
      lab-report, caregiver and mental-health pages
- [x] 2.12 Navigation / information architecture — `docs/information_architecture.md`
      + rendered diagram in `reports/figures/`
- [x] 3.6 Prescription/lab extraction pipeline — `health/extraction.py` (499 lines),
      in-memory only, local Tesseract OCR, `parser_used` recorded, `ExtractionTests` present
- [x] 3.11 Provider marketplace incl. availability — `providers/availability` view + template
- [x] 3.12 / 3.28 Pre-visit snapshot — `previsit_snapshot` view, template, consent share flow
- [x] 3.13 / 3.29 Care plan / targets — `CarePlan` model + `care_plans` view + template
- [x] 3.22 Prescription upload UI + verify screen — `prescription_upload.html`, `extraction_verify.html`
- [x] 3.23 Consent components wired to extract/share actions
- [x] 4.1 Synthetic dataset — `generate_cohort` management command + `synthetic_data_assumptions.md`
- [x] 4.5 Recommendation engine — `datascience/recommend.py`, rule+RandomForest hybrid
- [x] 4.9 DS analytics page — `/datascience/analytics/` (admin-only)
- [x] 5.1 / 5.2 Backend + RBAC/consent tests — **132 tests** across accounts, adminpanel, core
- [x] Bonus (not in the plan at all): lab reports module, medication reminder /
      missed-dose / restock alert engine (`health/alerts.py`), structured `DoseTime` schedules

**Action:** update the xlsx statuses to match, so the report's progress numbers are honest.

---

## 2. Genuinely pending — build work

### Data science (the biggest gap, and the highest-weighted section for MDS)

- [ ] **4.7a Re-run the metrics with a real cohort.** `datascience/artifacts/metrics.json`
      was produced from a **6-patient** cohort — F1 values of 0.4 with std 0.49 are noise,
      not results. Run:
      ```
      python manage.py generate_cohort        # 100 patients
      python manage.py train_models
      ```
      Do this *before* writing the report — these numbers go in the results section.
- [ ] 4.2 Medication non-adherence detection model (BP1)
- [ ] 4.3 Health-risk prediction model (BP2)
- [ ] 4.4 Vital-sign anomaly detection model — rule thresholds exist in
      `health/analytics.py`; a trained model does not
- [ ] 4.6 Private mood / sentiment check-in — `MoodLog` exists but is deliberately
      excluded from the DS pipeline; decide whether to build this or document the exclusion
      as a privacy design decision
- [ ] **4.8 CRISP-DM write-up per model** — `reports/crispdm/` does not exist.
      Required for grading. Even for the one finished model (recommender) this is missing.

### Backend / frontend

- [ ] 3.14 Remote monitoring + alerts engine — *partially* done. Medication alerts
      work; vitals-anomaly alerts to provider/nurse do not. No `MonitoringAlert` model.
- [ ] 3.30 Remote monitoring dashboard + alert display — no template exists

---

## 3. Genuinely pending — testing & verification

- [ ] 5.3 Verify true deletion (no residual files, no LLM retention) — this is the
      headline privacy claim of the project; it needs a demonstrable test
- [ ] 5.4 Frontend / UI testing across all five roles, responsive
- [ ] 5.5 Accessibility check (large text, simple flows — target users are elderly/low-tech)
- [ ] 5.6 End-to-end 5-role journey tests (per-flow tests exist; full journeys don't)
- [ ] 5.7 Dedicated consent audit-trail assertions
- [ ] **Run the full suite and record the result.** I could not run it from here —
      the `venv` is Windows and my sandbox is Linux. Run locally:
      ```
      venv\Scripts\python.exe manage.py test
      ```
      The pass/fail count belongs in the report's testing chapter.

---

## 4. Deliverables

- [ ] **6.1 Final project report** ← today's target. Depends on §2 and §3 above for
      its results and testing chapters. See §5 for the decision needed.
- [ ] 6.2 Final Demo-2 deck
- [ ] 6.3 Project diary — add 17–18 Aug entries, then consolidate
- [ ] 6.4 Demo recording / screencast
- [ ] 6.5 Code cleanup — README rewritten already; docstring pass outstanding;
      also clean up the stray root-level `*.html` mockups, `venv.zip`,
      `_backup_before_build.tar.gz` and `db.sqlite3.backup-*` before submission
- [ ] 6.6 Deployment / demo setup

---

## 5. Decision needed before the report is written

The report cannot be finished until you decide how to frame the four unbuilt
DS models (4.2, 4.3, 4.4, 4.6) and the monitoring engine (3.14/3.30):

- **Option A — build first.** Push 4.2/4.3/4.4 out today (they share the existing
  feature pipeline in `datascience/features.py`, so the marginal cost is lower than
  it looks), then write a report describing a complete system.
- **Option B — honest split.** Write the report now, documenting what's implemented
  and putting the rest in a clearly labelled *Future Work / Planned Modules* chapter.
- **Option C — design-complete framing.** Present them as fully designed with
  implementation pending.

For an MDS submission, a report with only one working model is a weak results
chapter. **Option A for 4.2 and 4.4 specifically** is probably the best use of
today: adherence and anomaly detection both already have the data and the
thresholds; they mainly need a model wrapper and an evaluation run.

---

## Suggested order for today

1. Re-run `generate_cohort` + `train_models` (unblocks all real metrics)
2. Run the test suite, record the count
3. Build 4.2 + 4.4 if going with Option A
4. Write CRISP-DM docs (4.8) for whatever models exist
5. Update the xlsx tracker + diary
6. Write the final report (6.1)
