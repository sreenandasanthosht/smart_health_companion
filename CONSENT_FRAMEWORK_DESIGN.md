# Consent Framework Design (Task 2.3)

## Why this exists

Smart Health Companion handles sensitive health data -- vitals, medications, prescriptions,
mental health entries -- and that data sometimes needs to cross a boundary: from the
patient to a caregiver, a nurse, a provider, or (briefly) an OCR/LLM extraction pipeline.
Every one of those crossings needs the patient's explicit, revocable consent. This document
designs that framework so it can be modelled in the ERD update (task 2.6) and built as the
consent engine (task 3.7).

## 1. Consent events -- when does a consent check fire?

A consent check must fire at every point where data leaves the patient's own view:

- **Prescription/lab extraction.** The OCR+LLM pipeline (task 3.6) reads an uploaded
  document. Consent here covers *processing* the document, even though the file itself is
  discarded immediately after (the process-and-discard design from task 2.2).
- **Provider pre-visit snapshot.** Sharing vitals/medications with a Provider ahead of an
  appointment (task 3.12).
- **Caregiver monitoring.** A Caregiver viewing a linked patient's vitals and alerts
  (already previewed in `health/caregiver_dashboard.html`).
- **Nurse visit access.** A Nurse viewing or entering data during a visit (task 3.10).
- **Ephemeral secure sharing.** One-off share codes with an expiry, already stubbed in
  `health/share_records.html` (e.g. a share that "expires in 2 hours").
- **Admin/support access.** An Admin viewing user data while handling verification or a
  support ticket (the `adminpanel` app) -- see the "break-glass" question in Section 6.

## 2. Granularity -- what can be consented to separately?

Consent is not all-or-nothing. Three axes:

- **By category.** Vitals, Medications, Lab/prescription records, Lifestyle logs can each
  be granted independently. **Mental health entries are the one exception: they are never
  shareable at all**, per the existing design ("Private Mental Health Log... never visible
  to caregivers or providers" -- `core/views.py`). This isn't a consent option the patient
  turns on/off; it's a hard exclusion enforced regardless of what else is granted.
- **By time.** A grant can be open-ended (e.g. an ongoing Caregiver link) or time-boxed
  (e.g. "for the next 2 hours" for a one-off provider share).
- **By recipient.** A grant is always scoped to one specific person or role instance (a
  named Caregiver, a named Provider, a named Nurse) -- never a blanket "share with anyone."

## 3. Consent log -- the audit trail

Every grant becomes one row in a consent log, which will become the `Consent` entity in the
ERD (task 2.6). Minimum fields:

| Field | Purpose |
|---|---|
| `patient` | whose data this is |
| `recipient` | who was granted access (caregiver / nurse / provider / admin) |
| `scope` | which category(ies) were granted |
| `granted_at` | when the grant was made |
| `expires_at` | null for ongoing, or a timestamp for time-boxed grants |
| `revoked_at` | null unless the patient withdrew it early |
| `action_context` | what action used this consent (e.g. "pre-visit snapshot", "OCR extraction") |

This table is also what feeds the Admin **Audit Log** page already built (the "Sharing"
entries you'll see there, e.g. "Revoked a record share").

## 4. Withdrawal

A patient can revoke a grant at any time -- already demoed in `health/share_records.html`'s
"history" section (status: "Revoked"). Two rules:

1. Withdrawal takes effect immediately: it doesn't just stop *future* shares, it cuts off
   any *in-progress* access the moment it's recorded.
2. The withdrawal itself is logged (sets `revoked_at`) so the audit trail shows both the
   grant and the revocation, not just a disappearing row.

## 5. Enforcement pattern (how task 3.7 will use this)

The consent engine (task 3.7) is a decorator/middleware that, before letting a view return
data, checks: *does a `Consent` row exist for (patient, recipient, scope) where
`revoked_at` is null and (`expires_at` is null or in the future)?* If not, the request is
denied and the denial itself is logged the same way a grant would be, so the audit log
also shows attempted-but-refused access.

## 6. Open decisions to confirm before the ERD (2.6)

- Final list of consentable scopes -- is it exactly {Vitals, Medications, Lab/prescription
  records, Lifestyle}, or should Appointments/notes also be a separate scope?
- Default expiry if a patient doesn't set one when granting to a Provider for a single
  appointment (e.g. auto-expire 24h after the appointment time?).
- Whether Admin/support needs a "break-glass" path to view data without a standing
  consent grant (e.g. to resolve an account-recovery ticket) -- and if so, that access
  must still write an exceptional, clearly-flagged entry to the same consent log so it's
  never invisible in the audit trail.
