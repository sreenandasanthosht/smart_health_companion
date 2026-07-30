# Nursing Role Design (Task 2.4)

## The core decision: own role, not a Provider subtype

**Decision: Nurse becomes its own value in `User.Role`, alongside Patient, Caregiver,
Provider and Admin -- not a subtype of Provider.**

Reasoning:

- A Nurse's job (task 3.10: assignment, visit logging, escalation, data-entry-on-behalf)
  is a fundamentally different permission set from a Provider's (verification, listings,
  care plans, availability). Modelling Nurse as a Provider subtype would mean constantly
  branching Provider logic by sub-type, which adds complexity for no real benefit.
- The `User` model already uses a single-table + `role` discriminator design (see
  `accounts/models.py`), not per-role subtype tables. Adding `NURSE` as a fifth choice
  keeps that same simple pattern instead of introducing a new inheritance shape just for
  this one role.
- Practical effect: `accounts/models.py`'s `User.Role` will next need
  `NURSE = 'NURSE', 'Nurse'` added (the same way `ADMIN` was just added), with its own
  migration, when this design is implemented.

## 1. Placement

A Nurse sits between Caregiver and Provider: linked to a specific patient like a Caregiver
is, but professionally credentialed like a Provider is. That means nursing needs **both**:

- A **patient assignment** (who they're currently caring for), similar in shape to the
  Caregiver-patient link.
- A **lightweight verification** step, so an unverified account can't start logging visits.
  This can reuse the same verification queue/pattern already built for Providers
  (`adminpanel/verification.html`) rather than inventing a second one -- an Admin approves
  a Nurse's credentials the same way they approve a Provider's.

## 2. Assignment

How a Nurse gets connected to a patient:

- A patient (or their Caregiver, on their behalf) requests a Nurse, or an agency/Admin
  assigns one directly.
- Each assignment is its own record, not just a foreign key on the Nurse or the patient,
  because assignments start and end (a Nurse's engagement with a given patient is
  time-bounded, unlike the ongoing accounts.User relationship itself). Minimum fields:
  `nurse`, `patient`, `start_date`, `end_date` (null while ongoing), `assigned_by`.

## 3. Visit logging

What a Nurse records per visit:

- Date/time of the visit.
- Vitals taken during the visit -- these should be written into the **same** Vitals model
  the patient uses for self-entry (task 3.4), not a separate table, but tagged with who
  entered it (see the open question in Section 5) so a BP reading a Nurse took during a
  home visit is clearly distinguishable from one the patient logged themselves.
- Free-text notes.
- Medications administered during the visit.
- An escalation flag, if something during the visit needs to be raised (see Section 4).

## 4. Escalation

When a Nurse flags something urgent during or after a visit:

- **Target:** the patient's assigned Provider, and/or a linked Caregiver -- whichever is
  appropriate to the situation. This slots into the same alerting path already planned for
  task 3.14 (Remote monitoring + alerts engine), which already routes anomaly and
  missed-dose alerts to "provider/nurse" -- escalation is that same pipe, run in reverse
  (nurse-originated instead of system-originated).
- **Severity:** at minimum a simple level (e.g. routine note vs. urgent), so downstream
  alerting can decide whether to notify immediately or just log it.
- **Boundary, per the task plan's own note:** nursing is "logging/coordination only, not
  clinical orders." A Nurse can raise an escalation and record what they observed, but
  cannot prescribe medication or edit a Care Plan (task 3.13) -- those stay
  Provider-only actions. An escalation is a request for a Provider's attention, not a
  clinical decision in itself.

## 5. Data model implications (feeds the ERD update, task 2.6)

Two new entities, matching the plan's own note ("add Consent, NursingVisit, CarePlan,
ProviderService"):

- **`NursingVisit`**: nurse, patient, timestamp, vitals recorded (or a link to the Vitals
  rows created during that visit), notes, escalation flag/severity.
- **`NurseAssignment`**: nurse, patient, start_date, end_date, assigned_by.

## 6. Open decisions to confirm before the ERD (2.6)

- Does the existing/planned Vitals model need an `entered_by` or `source` field
  (self / nurse / caregiver) so nurse-entered readings are provenance-tagged rather than
  indistinguishable from the patient's own entries?
- Who is allowed to end or reassign a `NurseAssignment` -- the patient, an Admin, or both?
  (Relevant to the Admin "Users" and "Providers" management pages already built.)
- Confirm with the Frontend partner that task 3.26 ("Nurse dashboard: assignments,
  visit-logging forms, escalation UI") is scoped to match this design once it's final.
