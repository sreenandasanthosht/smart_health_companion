# CareNest — Module List

**Task 2.9** · Revised from the original 13-module list. Status is as of
2026-08-03 and reflects what is in the code, not what was planned.

| # | Module | Django app | Responsibility | Status |
|---|---|---|---|---|
| M1 | Identity & Roles | `accounts` | One `User` covering five roles; CareNest ID generation; profile with progressive completion | Implemented |
| M2 | Authentication | `accounts` | Registration, login, logout, session handling. Nurse and Admin are not self-registerable | Implemented |
| M3 | Access Control | `accounts` | `@role_required` gating on every protected view; suspended-account blocking | Implemented |
| M4 | Vitals | `health` | Recording BP, sugar, weight and heart rate; automatic Normal / Watch / High flagging; provenance tagging | Implemented |
| M5 | Medication | `health` | Prescriptions, per-day dose tracking, refill dates, adherence percentage | Implemented |
| M6 | Lifestyle | `health` | Daily sleep, water, steps and activity; one entry per day | Implemented |
| M7 | Mental Health | `health` | Private mood journal. Structurally excluded from all sharing | Implemented |
| M8 | Consent Engine | `health` | `ConsentGrant` with per-category scope, expiry and revocation; `has_consent()` enforcement | Implemented |
| M9 | Caregiver Linking | `accounts` + `health` | Request by CareNest ID, patient-side approval, consent granted on approval | Implemented |
| M10 | Analytics | `health` | Health score, trend series, rule-based insights with stored evidence | Implemented |
| M11 | Provider Verification | `providers` | Document checklist, three-state verification, admin approve / request-info | Implemented |
| M12 | Provider Directory | `providers` | Searchable listing of verified providers only | Implemented |
| M13 | Appointments | `providers` | Request → accept / decline → annotate → complete | Implemented |
| M14 | Nursing | `nursing` | Assignments, visit logging, nurse-recorded vitals, escalation with severity | Implemented |
| M15 | Platform Administration | `adminpanel` | Live KPIs, user management, suspension, nurse assignment | Implemented |
| M16 | Audit Trail | `adminpanel` | Append-only log of consequential actions, surviving user deletion | Implemented |
| M17 | Document Extraction | `health` | OCR + parsing of prescriptions, process-and-discard, verify-before-save | Planned — Phase 2 |
| M18 | Pre-visit Snapshot | `providers` | Consented, read-only patient summary for an upcoming appointment | Planned — Phase 3 |
| M19 | Care Plans | `providers` | Provider-set measurable targets shown on the patient dashboard | Planned — Phase 3 |
| M20 | Availability | `providers` | Weekly availability pattern constraining booking | Planned — Phase 3 |
| M21 | Monitoring & Alerts | `monitoring` | Rule-driven alerts routed to the assigned nurse and consented providers | Planned — Phase 4 |
| M22 | Data Science | `datascience` | Non-adherence, health risk, anomaly detection, recommendations, mood analysis | Planned — Phase 5 |

## Modules removed from the original list

| Original module | Why it was removed |
|---|---|
| Drug Interaction Checker | Automatic interaction flagging is clinical decision support, and this project makes no clinical claim. Removed after review feedback (task 2.1) and replaced by the medication card plus a "show this to your doctor" prompt. The 22 MB dataset was retired in Phase 0. |
| Document / Media Store | Superseded by the process-and-discard design. Documents are read in memory and deleted; only structured fields persist. There is nothing to store, so there is no store. |

## Numbering note

This list renumbers from the original 13-module set. When cross-referencing
older documents, note that the old numbering does not map one-to-one —
several original modules were split (identity from authentication from access
control) because they turned out to have genuinely different responsibilities
once built.
