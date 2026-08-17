# CareNest — Medication Reminders & Restock Alerts

Why free-text schedules could not drive an alert, what replaced them, and
how the three alert rules work.

---

## 1. The problem

Before this change a medication stored its schedule as a sentence:

```
Medication.schedule = "1-0-1"
Medication.dose     = "500 mg"
```

and adherence was one `MedicationDose` row **per day**.

Neither an intake reminder nor a restock warning is possible from that:

- **No clock time.** "1-0-1" is not a time. Nothing to fire an alert at.
- **No quantity.** `next_refill_date` was a date somebody typed, not a
  number counted down. Nothing to predict a run-out from.
- **One tick per day.** A medicine taken three times a day could only be
  ticked once, so a missed evening dose was invisible and the adherence
  percentage was wrong for anything other than a once-a-day medicine.

---

## 2. What was added

### `DoseTime` — the schedule, structured

One row per time of day this medicine is taken.

| Field | Example |
|---|---|
| slot | MORNING / AFTERNOON / EVENING / NIGHT |
| at_time | 08:00 — patient can change it |
| quantity | 1, 0.5, 2 |

`"1-0-1"` becomes two rows: Morning 08:00 ×1, Night 21:00 ×1. This is what
a reminder fires against.

### `Medication` — course length and stock

| Field | Purpose |
|---|---|
| duration_days | how long the course runs; stops dose rows being generated after it ends |
| quantity_dispensed | how many were handed over |
| stock_on_hand | how many are left, counted down as doses are ticked |
| restock_threshold_days | warn this many days before running out (default 3) |
| needs_schedule_review | set when the written schedule could not be read |
| restock_alerted_at | stops the low-stock warning repeating |

Derived, never stored: `daily_quantity`, `days_of_stock_left`,
`projected_runout_date`, `is_low_stock`. `next_refill_date` is now
**computed** from stock and consumption rather than typed, so it cannot
drift out of step with what was actually taken.

### `MedicationDose` — one row per dose, not per day

`unique_together` is now `(medication, date, dose_time)`. `dose_time` is
nullable so rows recorded under the old scheme survive rather than being
deleted. Two timestamps — `reminded_at` and `missed_alerted_at` — make the
alert rules idempotent.

`mark_taken()` also draws the dose quantity out of stock; `mark_not_taken()`
puts it back. That single link is what makes the restock warning possible.

---

## 3. Reading the written schedule

`health/schedules.py` converts prescription notation into slots.

| Input | Result |
|---|---|
| `1-0-1`, `1-1-1`, `0.5-0-0.5`, `1-0-1-1` | dash notation, 3 or 4 parts |
| `1 Morning, 1 Night`, `2 tablets at night` | counted slot words |
| `BD`, `TDS`, `OD`, `HS`, `QID` | Latin abbreviations |
| `twice daily`, `3 times a day` | plain English counts |
| `morning and night`, `at bedtime` | named slots, quantity assumed 1 |
| `SOS`, `as needed`, `alternate day` | recognised and deliberately not scheduled |

**Two weaker signals are reconciled rather than raced.** "Once daily, at
night" states a count (1) and names a slot (night) — the named slot wins,
because it is more specific. "BD after dinner" states a count of 2 but
names only one slot, so the count wins: a named slot cannot be the complete
list when it accounts for fewer doses than the count does.

**Nothing is guessed.** A schedule the parser cannot read with confidence
produces *no* dose times and sets `needs_schedule_review`. The medications
page then asks the patient to set the times. A reminder at the wrong hour
teaches people to ignore reminders, which is worse than no reminder.

### The parser is optional

Uploading a prescription is never required. The **Add a medicine** form on
the medications page has a times-of-day table — Morning / Afternoon /
Evening / Night, each with an editable time and a quantity — so a patient
can set reminders entirely by hand.

Both routes are accepted on the same form, and **the manual times win**. A
patient who ticked the times themselves has said exactly what they want;
there is no reason to run their words through a parser as well. When only
the times are given, the written `schedule` field is filled in from them
(`"Morning 06:30, Night 22:15"`) so the medication still reads sensibly
everywhere else. Submitting neither is refused rather than creating a
medicine that can never remind anyone.

---

## 4. The three alert rules

All in `health/alerts.py`. All idempotent.

| Rule | Fires when | Level |
|---|---|---|
| **Reminder** | the scheduled time has arrived and the dose isn't ticked, within a 2-hour grace window | ACTION |
| **Missed** | the grace period has passed and it still isn't ticked | WARNING |
| **Restock** | `days_of_stock_left` ≤ `restock_threshold_days` | WARNING |

Missed doses look back to yesterday, so a dose missed late at night is
still reported the next morning instead of vanishing at midnight. The
restock warning has a 20-hour quiet period so it is raised once a day, not
on every page load.

Alerts land in the existing `accounts.Notification` model, so they appear
in the bell menu and the notifications page with no new delivery plumbing.

---

## 5. What actually triggers them

Django only runs when a request arrives — nothing wakes up at 8 AM on its
own. Two triggers, deliberately:

**1. A scheduled command — the real trigger.**

```
python manage.py send_medication_alerts
```

Run every 15 minutes by Windows Task Scheduler. This fires on time even
when nobody is logged in, which is the whole point of a reminder.

**2. A catch-up on page load.**

`health_dashboard` and `health_medications` also call
`run_medication_alerts()` for the signed-in patient. This means the feature
still demonstrates correctly on a laptop where the scheduler was never set
up, and nothing is silently missed. Because every rule is idempotent, the
two triggers cannot produce duplicate notifications.

### Setting up Task Scheduler on Windows

1. Open **Task Scheduler** → *Create Task*
2. **General:** name it `CareNest medication alerts`, tick *Run whether user
   is logged on or not*
3. **Triggers:** New → Daily → *Repeat task every 15 minutes* for *1 day*
4. **Actions:** New → Start a program
   - Program: `C:\Program Files\Python314\python.exe`
   - Arguments: `manage.py send_medication_alerts --quiet`
   - Start in: `C:\sem 4 DS\PROJECT\project\smart_health_companion`
5. Save

`--quiet` keeps it silent unless something was actually sent.

---

## 6. Existing data

`health/migrations/0007_convert_medication_schedules.py` reads every saved
medication's free-text schedule and creates the matching dose times.
Anything it cannot read is flagged for the patient rather than guessed at.

Old `MedicationDose` rows keep `dose_time = NULL`. They stay in the
adherence history; new per-dose-time rows are created alongside them from
the day of migration onwards.

---

## 7. Known limits

- **Weekly and alternate-day schedules are not supported.** They are
  recognised and excluded rather than mis-scheduled.
- **Stock is only as good as what the patient enters.** If they never say
  how many tablets they have, no restock warning can be raised — the page
  says so rather than pretending.
- **Notifications are in-app only.** SMS or push would need an external
  service; the `Notification` model is the seam where that would attach.
- **The rule-based extractor still produces messy schedules.** Setting
  `LLM_API_KEY` materially improves this, because the LLM can be asked to
  return the schedule already structured rather than as a sentence that has
  to be re-parsed.
