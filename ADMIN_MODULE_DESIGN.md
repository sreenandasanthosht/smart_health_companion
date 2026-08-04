# Admin Module Design

Implements `CareNest_Admin_Module_Proposal.docx`.

The proposal's framing: *"Administrators verify providers, manage users, review activities,
and ensure the platform remains secure and trustworthy."* Admin is therefore the only role
whose job is about **other people's** accounts, and every decision here is written to the
audit log for exactly that reason.

## 1. Super Admin is a tier, not a sixth role

**Decision: `User.is_super_admin`, a flag on the existing ADMIN role — not `Role.SUPER_ADMIN`.**

The proposal gives both tiers the same destination ("Admins log in using normal login
credentials and are automatically redirected to the Admin Dashboard") and differs only in
what they may do once there. Modelling Super Admin as its own role would mean every existing
`@role_required(ADMIN)` check had to list two values, and any new check that forgot the
second would silently lock the Super Admin out of a page they outrank. A flag means a Super
Admin simply *is* an Admin, with more permissions.

This is a different shape from the Nurse decision in `NURSING_ROLE_DESIGN.md`, deliberately:
a Nurse has a genuinely different permission set and its own surface, so it earned a role. A
Super Admin has a superset of the same permissions on the same surface.

**Not reused: Django's `is_superuser`.** That grants access to the `/admin/` site, which is a
separate question from who may create CareNest Admin accounts. Keeping the two apart means
either can be granted without the other. `is_platform_super_admin` treats a Django superuser
as a Super Admin so demos and marking aren't blocked, but the flag is what the model means.

Enforcement is `accounts.decorators.super_admin_required`, used on exactly two views.

## 2. How an Admin account comes into existence

Three barriers, so no single mistake creates one:

1. `PUBLIC_ROLE_CHOICES` in `accounts/forms.py` excludes ADMIN, and `ChoiceField` rejects any
   value not in that list — a crafted POST can't grant the role.
2. The user management page can only promote to Nurse.
3. `adminpanel.views.admin_accounts` is the single place in the codebase that sets
   `role=ADMIN`, and it is `super_admin_required`.

The first Super Admin comes from `createsuperuser` plus the seed, matching "The first Super
Admin account is created during system setup."

A Super Admin can't demote or revoke themselves — otherwise the last one could lock everyone
out of admin management permanently. Revoking returns an account to Patient rather than
deleting it, so their audit history stays attributable to a real row.

## 3. Provider verification

The proposal's workflow is *approve or reject*, so both now exist, alongside the pre-existing
"request more information":

| Action | Status | Meaning |
|---|---|---|
| Approve | `VERIFIED` | Listed in the directory, can receive appointments |
| Request info | `NEEDS_INFO` | Review **paused** — the provider resubmits and returns to PENDING |
| Reject | `REJECTED` | Review **ended** — a decision, not a wait |

Request-info and reject both keep the provider out of the directory, but only one of them is
a conclusion. Collapsing them would lose that distinction. Each decision notifies the
provider and writes an audit entry.

## 4. Health camps & wellness events

`providers.HealthEvent`. It lives in `providers`, not `adminpanel`, because it is
provider-owned content that an admin reviews — the same relationship `ProviderProfile`
already has.

There is deliberately **no code path outside `adminpanel.views.events` that can set
`APPROVED`.** The provider's own view creates events at `PENDING` and can only withdraw them.

Public visibility goes through one classmethod, `HealthEvent.public()`, which requires all
three of: approved, still upcoming, and run by a *verified* provider. That last condition
matters — approving an event doesn't override the provider's verification state, so an
approved event from a provider whose verification is later withdrawn disappears again.
`adminpanel/tests.py` covers each of the three conditions separately.

## 5. Reports & complaints

`adminpanel.Complaint`. Any signed-in user can file one from `/health/report/`.

- `against_user` is **optional**. Many reports are about the platform rather than a person,
  and forcing every report to name a target pushes people into blaming whoever is nearest.
- The "who is this about" dropdown lists only people the reporter actually deals with —
  their caregivers, their patients, providers they've had appointments with — rather than a
  directory of every account.
- Admins are excluded from that list. A complaint about an Admin shouldn't be routed to a
  queue reviewed by their own colleagues, and pretending otherwise would be worse than
  leaving it out.
- Statuses are Open → In review → Resolved / Dismissed. The reporter is notified of the
  outcome, because a report that vanishes is barely better than no report at all.

## 6. Announcements

`adminpanel.Announcement`. Publishing **fans out** a stored `Notification` per recipient
rather than being read live from the announcement row. Two reasons: the notification list is
already where users look, and a stored copy means editing an announcement later can't
silently rewrite what people were already told.

Consequences of that choice, both enforced: publishing is idempotent (a second `publish()`
sends nothing), and a published announcement can't be deleted — people have already seen it.
Drafts are private and deletable.

Audience is `ALL` or one role. Admins are excluded from their own announcements.

## 7. Platform analytics

Aggregate counts only. Nothing on this page reads an individual's records — mood check-ins,
for example, are *counted* but never read, consistent with the hard exclusion in
`CONSENT_FRAMEWORK_DESIGN.md`.

## 8. Caregiver management

An Admin can **revoke** a caregiver link but deliberately **cannot approve** one. Approval is
the patient's decision alone; letting an Admin grant access on a patient's behalf would
hollow out the entire consent model in `CAREGIVER_MODULE_DESIGN.md`. Revoking is a safety
valve — for an upheld complaint, say — and it withdraws the associated `ConsentGrant` too,
so revoking the link can't leave live consent behind.

## 9. Settings

`adminpanel.PlatformSettings`, a singleton, Super Admin only. Every field gates real
behaviour; a settings page full of switches that do nothing is worse than no settings page.

| Setting | What it actually does |
|---|---|
| `provider_self_registration_open` | Removes Provider from the sign-up form **and** makes it an invalid submission |
| `caregiver_device_approval_required` | Turns the new-device gate in `accounts/devices.py` on or off |
| `platform_notice` | Renders a banner on every signed-in page |

## 10. Open decisions

- Complaints about an Admin currently have nowhere to go. A separate escalation path to the
  Super Admin would close that gap.
- Announcements can't be scheduled or expired — they publish immediately and stay in the
  notification list forever.
- Analytics are computed live on every page load. Fine at this scale; would need caching or a
  nightly rollup if the platform grew.
- Rejecting a provider is currently terminal in the UI. There's no "reopen" action if an
  admin rejects by mistake — it has to be fixed through `/admin/`.
