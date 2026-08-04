# Caregiver Module Design

Implements `CareNest_Caregiver_Module_Proposal.docx` and the caregiver half of
`CareNest_User_Registration_and_Onboarding_Flow.docx`.

The organising principle from the proposal: *"Patient privacy is the highest priority, so no
caregiver can access patient information without patient approval."* Everything below is a
consequence of that sentence.

## 1. Three gates, not one

A caregiver's request for data passes three independent checks. Each is enforced in a
different place, so failing to add one can't silently open the others:

| Gate | Question | Where |
|---|---|---|
| Link | Has the patient approved this person at all? | `CaregiverLink.status == APPROVED` |
| Device | Has the patient approved this *browser*? | `accounts/devices.device_is_trusted()` |
| Consent | Has the patient shared this *category*? | `health.models.consent_matrix()` |

`health.views.caregiver_dashboard` applies them in that order and returns a different page
for each failure, so the caregiver always knows which one they're waiting on.

## 2. Registration and linking

Sign-up asks for full name, email, phone number, password and one reference to the patient.
Per the onboarding spec that reference may be **any** of three things, and the caregiver
isn't asked to say which:

- the patient's CareNest ID (`User.unique_id`, shown at the top of their dashboard),
- the email address the patient registered with,
- a single-use invite code (`CaregiverInvite`).

`accounts/linking.resolve_patient()` disambiguates: a `CN-` prefix means invite code, an `@`
means email, anything else is an ID. Both entry points -- the registration form and the retry
form on the caregiver dashboard -- call it, so they can't drift apart.

**Why invite codes exist.** Handing out a CareNest ID is permanent: it works forever, for
anyone who learns it. An invite is consumed on first use and expires after seven days, so a
patient who wants to add one specific person can do that without creating a standing
credential. The code is only consumed once a link is actually created, so a failed
registration doesn't burn it.

## 3. Approval, and what it grants

The patient decides on `/health/caregiver-requests/`. Approving:

1. flips the link to `APPROVED`,
2. creates a `ConsentGrant` covering the **standard** tier only -- vitals, medications,
   appointments, alerts, emergency contacts, lifestyle,
3. writes an `AuditLog` entry,
4. notifies the caregiver.

Records, health documents, medical reports and the AI summary are the **restricted** tier
and are deliberately *not* included. The proposal names them as items that "remain hidden
unless permission is granted", so granting them stays a separate, deliberate act on the
Share Records page. See `CONSENT_FRAMEWORK_DESIGN.md` section 2 for the full table.

Mental-health entries are outside both tiers and can never be shared.

## 4. New-device login approval

From the proposal's "Secure Login": a caregiver on a device the patient hasn't seen is held
until the patient confirms it.

- A device is a random opaque token in an `httponly` cookie (`TrustedDevice.COOKIE_NAME`) --
  not a browser fingerprint, which would be both less reliable and more invasive.
- The **first** device a caregiver ever uses is trusted implicitly. There is no earlier
  device for it to look suspicious against, and an unlinked caregiver can't see anything
  regardless.
- Every subsequent unrecognised device is created `PENDING` and the patient is notified.
- A *missing* device row is treated as trusted, not blocked. Cookies get cleared; locking a
  caregiver out of an account they legitimately hold is a worse failure than the one this
  guards against. Any *known* device that is pending or rejected is blocked.
- The gate is on reading patient data, not on signing in: the caregiver can still reach
  their own account and see what they're waiting for.

## 5. Dashboard modules

The seven modules the proposal lists, each hidden entirely when its scope isn't granted
("Unapproved modules are hidden from the caregiver" -- not greyed out, absent):

| Module | Scope required |
|---|---|
| Linked patient overview | the link itself |
| Health status / recent readings | `VITALS` |
| Medication status | `MEDICATIONS` |
| Upcoming appointments | `APPOINTMENTS` |
| Needs attention | derived -- see below |
| Notifications | none (the caregiver's own) |
| Emergency contacts | `EMERGENCY` |

**Needs Attention** is assembled only from data the caregiver is already permitted to see.
That's a deliberate constraint: a card that said "3 items need attention" while hiding what
they were would leak the existence of a category the patient chose to withhold.

The dashboard also lists, plainly, which standard categories the patient has *not* shared.
Being honest about the gaps is better than a caregiver assuming they're seeing everything.

## 6. Revocation

`ConsentGrant.revoke()` sets `revoked_at` rather than deleting the row, so the audit trail
shows both the grant and the withdrawal. The caregiver is notified when access is withdrawn.
Revoking consent does not break the link, and rejecting a device does not revoke consent --
the three gates are independent in both directions.

## 7. Data model summary

New in `accounts`:

- **`CaregiverInvite`** -- patient, code, label, expires_at, used_at, used_by.
- **`Notification`** -- user, kind, level, title, body, action_url_name, read_at.
- **`TrustedDevice`** -- user, patient, token, label, status, first/last seen, decided_at.

New in `health`:

- **`HealthDocument`** -- patient, title, kind, note, issued_on. Behind the restricted tier.
- **`ConsentGrant`** gains `scope_appointments`, `scope_alerts`, `scope_emergency`,
  `scope_documents`, `scope_reports`, `scope_ai_summary`.

`User` gains `allergies`, `medical_conditions`, `emergency_contact_name` and
`emergency_contact_relation`, all optional and all counted toward
`profile_completion()` -- the onboarding spec's "progressive profile completion".

## 8. Open decisions

- Should a rejected device notify the caregiver, or fail silently? Currently silent, on the
  theory that an attacker shouldn't learn they were spotted -- but that also means a
  legitimate caregiver whose patient mis-clicked gets no explanation.
- Invite codes expire after a fixed seven days. Worth letting the patient choose?
- Notifications are in-app only. Email or SMS delivery would make the approval request
  meaningfully more likely to be seen by an elderly patient who doesn't open the app daily.
