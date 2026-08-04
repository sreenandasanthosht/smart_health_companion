# CareNest — Consent Pop-up UX

**Task 2.11** · Design for the consent interaction, written for an audience of
chronic and elderly patients, many of them low-technology users.

---

## The problem this design is solving

Consent interfaces usually fail in one of two ways. Either they ask so often
that people click through without reading — consent fatigue, which produces
technically-valid consent that is ethically worthless — or they ask once in
dense language that nobody understands.

Our target users make this harder. Someone managing hypertension at seventy is
not going to read a paragraph of policy on a phone screen, and a caregiver
standing next to them adds social pressure to just say yes.

So the design goal is not "obtain consent". It is: **the patient understands
what is about to be shared, with whom, and for how long — and saying no is as
easy as saying yes.**

---

## Six rules

**1. One decision per screen.** Never combine "share your data" with "and also
accept these terms". A screen that asks two things gets one answer.

**2. Plain language, no system vocabulary.** Not "grant scoped access to the
vitals entity". Instead: *"Dr Nair will be able to see your blood pressure
readings for the next 24 hours."* Name the person, name the data, name the
duration, in one sentence a person can read aloud.

**3. Both buttons look like buttons.** The decline option is never a small
grey link beside a large coloured button. Equal visual weight, because
unequal weight is a way of pressuring someone while appearing to offer a
choice.

**4. Large targets, large text.** Minimum 16 px body text in the dialog, and
touch targets of at least 44 px. This is an accessibility requirement, not a
preference.

**5. Say what happens afterwards.** Every consent screen states how to undo
it: *"You can stop this at any time from Share Records."* Consent that feels
permanent is consent people are afraid to give.

**6. Ask as few times as possible.** Batch related permissions into one
decision. Prefer an ongoing caregiver grant, made once with a clear
withdrawal path, over asking on every view.

---

## Where consent is requested

| Trigger | Type | Default expiry | Why here |
|---|---|---|---|
| Approving a caregiver | One-off, ongoing grant | None (ongoing) | Establishes a standing relationship; asking repeatedly would be fatigue |
| Creating a record share | Explicit, patient-initiated | Patient chooses: 2 h / 24 h / 7 days / ongoing | The patient is already deliberately sharing |
| Pre-visit snapshot (Phase 3) | One tap from the appointment | 24 h after the appointment | Bounded to the reason it was given |
| Prescription extraction (Phase 2) | Per-upload tick, cannot be skipped | Single use | The document leaves the patient's control momentarily |

Mental health appears in none of these. It is not a consent option that
defaults to off — there is no code path that shares it at all.

---

## Dialog layout

```
┌────────────────────────────────────────────────┐
│  Share your health records?                    │   24 px, bold
│                                                │
│  Dr Anjali Nair will be able to see:           │   16 px
│                                                │
│     ✓  Your blood pressure and other vitals    │   plain words,
│     ✓  Your current medicines                  │   not field names
│                                                │
│  They will NOT see:                            │
│     ✗  Your mental health journal              │   always shown,
│        (this is never shared with anyone)      │   builds trust
│                                                │
│  This access lasts 24 hours, then stops        │   16 px, bold
│  by itself.                                    │
│                                                │
│  You can stop it sooner from Share Records.    │   14 px, muted
│                                                │
│  ┌──────────────────┐  ┌──────────────────┐    │
│  │   No, not now    │  │   Yes, share     │    │   equal weight
│  └──────────────────┘  └──────────────────┘    │   both ≥ 44 px tall
└────────────────────────────────────────────────┘
```

Showing what will *not* be shared is deliberate. It is the fastest way to
communicate that the system has limits, and it makes the mental-health
exclusion visible rather than something the patient has to take on faith.

---

## Implementation notes

Build it as one reusable Django template partial,
`templates/partials/_consent_modal.html`, taking: recipient name, a list of
plain-language scope descriptions, an expiry description, and the form action.
One component, used at every consent point, so the wording and behaviour
cannot drift apart across screens.

Accessibility requirements: `role="dialog"` with `aria-modal="true"`,
focus moved into the dialog on open and returned to the trigger on close,
Escape closes it as a decline, focus trapped inside while open, and a visible
focus ring on both buttons. It must be fully operable by keyboard.

The modal must never be the only path. Every consent it can grant is also
reachable from Share Records, because a dialog that a user dismisses by
accident should not lock them out of a feature.

---

## What to validate in Phase 6

Give an untrained tester this task: *"Let your daughter see your blood
pressure readings, but not your medicines."* Then ask them afterwards, without
showing the screen again, who can now see what and for how long. If they
cannot say, the wording has failed, regardless of how correct the underlying
consent record is.
