# CareNest — Service Provider Modules

How nine kinds of service provider are grouped into six modules, what each
module's dashboard does, and which fields each one records.

---

## 1. The grouping rule

Providers are grouped by **what a patient does with them**, not by what they
are called. Four different names for "book a slot with a person" is one flow,
not four modules; and a gym, a dietician and a yoga centre run the same system
with different content in the plan.

| Module | Provider types | Core flow |
|---|---|---|
| **Clinical Care** | Small clinic, Small hospital | Book slot → consult → record → follow-up |
| **Mental Health** | Psychologist / Counsellor | Book session → session notes → next session |
| **Diagnostics** | Diagnostic lab | Book test → collect sample → enter values → release report |
| **Pharmacy** | Pharmacy | Prescription → order → price & availability → fulfil |
| **Wellness Programmes** | Fitness centre / gym, Dietician / nutritionist, Yoga centre | Enrol → assign plan → log sessions → track progress |
| **Home Care** | Home nurse provider | Request → assign nurse → ongoing care → complete |

The grouping lives in exactly one place — `ProviderProfile.GROUP_OF_TYPE` in
`providers/models.py`. Dashboard routing, the directory filter, the sidebar and
the registration dropdown all read from it, so adding a provider type is a
one-line change.

### Why some lines were drawn where they were

**Gym + dietician + yoga share one dashboard.** All three enrol a client,
assign a plan, run sessions over weeks and track progress. Only the *content*
of the plan differs, which is what `WellnessProgramme.kind` is for. Three
separate modules would have been three copies of the same code.

**Mental Health is separate from Clinical Care** even though both are "book a
person for a slot". The difference is confidentiality, not workflow: a
counsellor's notes are more sensitive than a clinic's visit note, and the
patient's mood journal is structurally excluded from ordinary sharing. Keeping
mental health in its own model confines that exception to one file instead of
scattering `if provider_type == PSYCHOLOGIST` through the clinical views.

**Small hospital ≈ small clinic, plus departments.** The only structural
difference modelled is `Department`. Beds, admissions and inpatient billing are
deliberately out of scope — they are a system of their own and add nothing to
the outpatient flow CareNest models.

**Home Care reuses the `nursing` app.** A home nurse provider is an
organisation that *employs* nurses; `NurseAssignment` and `NursingVisit`
already model what a nurse does at a patient's home. This module only changes
who allocates them — the agency instead of a platform administrator.

---

## 2. Routing

One URL, six dashboards:

```
/providers/dashboard/  →  providers.views.dashboard  (dispatcher)
                            └─ providers/dashboards.py → the group's function
```

`provider_dashboard` stays a single URL name, so the login redirect, the role
decorators and every existing template link keep working untouched. Which
dashboard a provider sees is decided entirely by the service they chose at
registration.

Registration shows the nine types under six `<optgroup>` headings — the
provider sees which module they are joining before they submit.

---

## 3. Fields recorded per module

### Shared by every group

`ServiceOffering` — the service / price list every provider keeps, shown on
their directory profile.

| Field | Notes |
|---|---|
| name, description | |
| price | optional |
| duration_minutes | optional |
| is_active | hidden vs listed |

### Clinical Care

`Department` (small hospitals only) — name, head_name, description,
consulting_hours, is_active.

`Appointment` gained four optional fields, so every appointment booked before
this change stays valid:

| Field | Purpose |
|---|---|
| department | which department the visit is under (hospitals) |
| service | which listed service was booked |
| diagnosis | impression recorded at the consultation |
| advice | what the patient was told |
| follow_up_on | drives the "follow-ups due" counter |

### Mental Health

`CounsellingSession` — provider, patient, scheduled_for, duration_minutes,
mode (in person / video / phone), session_number, concern, status.

Two note fields, deliberately distinct:

| Field | Who can read it |
|---|---|
| private_notes | the counsellor only — never rendered on any patient or caregiver page |
| shared_summary | the client |

Plus `follow_up_on` for the next session.

### Diagnostics

`LabTest` — name, category, sample_type, preparation, price, report_hours,
home_collection, is_active.

`TestBooking` — patient, test, scheduled_for, home_collection,
collection_address, status (requested → confirmed → collected → report ready),
collected_at, reported_at, summary.

`TestResultValue` — analyte, value, unit, reference_range, flag
(normal / low / high).

**Design note:** results are stored as *structured values*, not uploaded
files. This keeps diagnostics inside the project's process-and-discard rule —
there is no document to store — and lets a released value flow into the
patient's existing trend charts instead of sitting in a PDF they have to open.
A report cannot be released until at least one value has been entered.

### Pharmacy

`MedicineOrder` — patient, pharmacy, status, fulfilment (pickup / delivery),
delivery_address, prescription_reference, patient_note, pharmacy_note.

`OrderItem` — medicine_name, strength, quantity, unit_price, is_available,
substitute_note.

Status moves along a fixed path (`PHARMACY_NEXT_STATUS` in
`providers/dashboards.py`), so an invalid jump is never offered:

```
PLACED → ACCEPTED → PREPARING → READY → DISPATCHED → DELIVERED
   └──→ REJECTED
```

This is where the prescription-extraction module pays off: the medicines a
patient confirms after OCR become the lines of an order, so nothing is typed
twice.

### Wellness Programmes

`WellnessProgramme` — name, kind (fitness / diet / yoga / general), level,
description, duration_weeks, sessions_per_week, fee, capacity, is_active.
Exposes `active_enrolments` and `seats_left`.

`ProgrammeEnrolment` — programme, patient, status, goal, started_on, ends_on,
plan_notes (the diet chart / workout / asana routine). Exposes `sessions_done`
and `progress_percent`, computed against `duration_weeks × sessions_per_week`.

`ProgrammeSession` — on_date, duration_minutes, activity, attended,
trainer_note, weight_kg.

Accepting an enrolment sets `started_on` to today and `ends_on` to
`duration_weeks` later automatically.

### Home Care

`HomeCareStaff` — provider, nurse, designation, qualification,
years_experience, is_available.

`HomeCareRequest` — patient, provider, care_type (elderly / post-op / chronic /
palliative / mother & baby / other), shift (day / night / full / visit),
starts_on, days_required, address, requirements, status, assigned_staff,
provider_note.

Care cannot be started until a nurse is assigned. The nurse pool offered
excludes anyone already on the agency's team.

---

## 4. Migration of existing data

Two provider types were retired when the list was finalised:

| Retired | Remapped to | Why |
|---|---|---|
| `DOCTOR` | `CLINIC` | A doctor practising alone is a small clinic in this model |
| `WELLNESS_CENTRE` | `FITNESS_CENTRE` | Covered by the Wellness Programmes group |

Handled by `providers/migrations/0005_remap_doctor_to_clinic.py`. The reverse
operation is deliberately a no-op — clinics that were always clinics must not
become doctors on the way back down.

---

## 5. Integration with existing patient data

Each provider module is designed to write into a data stream the patient
dashboard already reads, rather than being a silo:

| Module | Feeds |
|---|---|
| Diagnostics | released `TestResultValue`s → patient vitals and trend charts |
| Wellness | logged `ProgrammeSession`s → lifestyle activity log |
| Pharmacy | fulfilled orders → medication records and adherence tracking |
| Home Care | assigned nurses → existing `NursingVisit` logging |
| Clinical | consultation records → health insights |

Wiring these connections is the next phase; the models are shaped for it.
