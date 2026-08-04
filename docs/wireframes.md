# CareNest — Screen Layouts

**Task 2.10** · Layouts for all five role dashboards.

These are not speculative wireframes. The screens exist and are running, so
this document records the **as-built** layout, with captured screenshots as
the evidence. Files live in `reports/figures/screens/`.

---

## Shared shell

Every signed-in screen uses one layout, defined in
`templates/base_dashboard.html`:

```
┌──────────────┬────────────────────────────────────────────────────┐
│              │  ☰   [ search ]              🔔   [avatar] Name    │  topbar, 74 px
│   sidebar    ├────────────────────────────────────────────────────┤
│   240 px     │                                                    │
│              │   page-head:  role chip                            │
│  brand       │               H1 title                             │
│  nav items   │               one-line description                 │
│  ...         │                                                    │
│  ─────────   │   [ callouts — messages, warnings, consent notes ]  │
│  Emergency   │                                                    │
│  Log out     │   [ content: stat cards / panels / tables / forms ] │
│              │                                                    │
│  context box │                                                    │
└──────────────┴────────────────────────────────────────────────────┘
```

The sidebar swaps per role (five partials in `templates/partials/`); the
topbar and content frame are identical everywhere. One shell means a user who
learns one screen has learned the shape of all of them — which matters for
the low-technology audience.

---

## Patient dashboard — `patient_dashboard.png`

The densest screen in the system, in four bands:

```
band 1   Greeting + CareNest ID  |  Health Summary card (generated insights)
band 2   4 stat cards:  Medicines Due · Next Appointment · Next Refill · Health Score
band 3   Health Analytics: 4 trend cards (BP, heart rate, sugar, weight)
         — sparklines drawn from the patient's own readings, not decoration
band 4   3 panels: Recent Activity · Today's Goals · Today's Medicines
band 5   "Why we're saying that" — every insight with the evidence behind it
```

Two deliberate choices. The CareNest ID sits in the greeting *and* the
sidebar, because linking a caregiver means reading it aloud over the phone.
And the evidence table at the bottom exists so that no number on the screen
is unexplained — a patient, or an examiner, can always ask why and get an
answer.

Severity is never carried by colour alone: a critical insight gets an alert
icon as well as a red bullet.

## Vitals — `patient_vitals.png`

Two columns, 8 : 4. Left holds the trend cards and the full reading history
with a status column. Right holds the entry form. The form is on the right so
that on a narrow screen it stacks *below* the data, letting the patient see
their history before adding to it.

## Medications — `patient_medications.png`

Left: active medicines, each with a Mark taken / Undo control and a refill
countdown. Right: the add-medicine form. An adherence callout sits above
both, coloured by whether adherence is at or above 80 percent.

## Share Records — `patient_share_records.png`

7 : 5 split. Left: active shares, each with the recipient, scope, expiry,
passcode and a Revoke button; below it, share history including revoked and
expired grants. Right: the create-a-share form.

The mental-health checkbox is rendered **visible but permanently disabled**,
labelled "never shareable". Hiding it would have been cleaner visually and
worse ethically — the patient should be able to see that the boundary exists.

## Mental Health — `patient_mental_health.png`

Purple "Private" chip instead of the usual teal role chip, so the screen
looks different from every other one. Mood buttons, optional note, entry
history, and a frequency breakdown. A muted callout states that this is a
structural exclusion, not a setting.

## Caregiver dashboard — `caregiver_dashboard.png`

Two distinct states. Before approval: a waiting panel and a form to request
access by CareNest ID — no patient data of any kind. After approval: latest
vitals, recent readings, medicines and alerts, each section shown only if the
patient consented to that category. An unconsented section renders an
explicit "not shared" panel rather than silently vanishing, so the caregiver
understands the boundary rather than assuming a bug.

## Provider dashboard — `provider_dashboard.png`

Three stat cards (pending requests, confirmed upcoming, patients seen) over a
two-column body: appointment requests with Accept / Decline on the left,
confirmed appointments with an inline note field and Mark completed on the
right.

## Provider verification — `provider_verification_status.png`

7 : 5 split. Left: a large status badge, plain-language explanation, and the
document checklist with Received / Missing pills. Right: the editable details
form for resubmission. The screenshot shows the *pending* state, which is the
one a provider sees first.

## Nurse dashboard — `nurse_dashboard.png`

Three stat cards (assigned patients, visits this week, escalations raised)
over a card grid, one per assigned patient, each showing the latest reading
with its status flag and the date of the last visit. The sidebar carries a
"Scope of practice" box stating what a nurse may and may not do — the
logging-not-prescribing boundary made visible in the interface.

## Admin dashboard — `admin_dashboard.png`

Four KPI cards over a 7 : 5 split: "Needs attention" on the left as an
actionable queue, "Today at a glance" and role counts on the right, with the
latest audit entries beneath. Every number is a live query.

## Admin verification queue — `admin_verification_queue.png`

A table with a document-status column showing which of the four required
documents each provider has supplied, plus inline Approve and Request info
controls with an optional reason field.

## Admin audit log — `admin_audit_log.png`

Filterable table: date, time, actor, action (as a coloured pill by severity)
and target. Append-only — there is no edit or delete control anywhere on the
page, by design.

---

## Responsive behaviour

The grid classes (`g-2`, `g-3`, `g-7-5`, `g-8-4`, `stats`) collapse to a
single column below the tablet breakpoint, and the sidebar becomes toggleable
via the hamburger. Phase 6 covers verification at 200 percent zoom and at
phone width, which is where the ten-item patient sidebar is most at risk.
