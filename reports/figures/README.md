# Report figures

Generated 2026-08-03 from the running system. Every figure here is real
output — none is illustrative or hand-drawn.

## Diagrams

Rendered from Mermaid source (`.mmd` in this folder) using mermaid-cli.
Both PNG (for Word) and SVG (scales without blurring, for print) are
provided. To regenerate after editing a `.mmd` file:

```
mmdc -i erd.mmd -o erd.png -b white -w 4800
```

| File | Figure | Task | Source |
|---|---|---|---|
| `erd.png` / `.svg` | Entity relationship diagram | 2.6 | `docs/erd.md` |
| `architecture_1.png` / `.svg` | Layered system architecture | 2.7 | `docs/architecture.md` |
| `architecture_2.png` / `.svg` | Sequence: consent-gated read | 2.7 | `docs/architecture.md` |
| `use_cases.png` / `.svg` | Actor / use-case diagram | 2.5, 2.8 | `docs/use_cases.md` |
| `information_architecture.png` / `.svg` | Role-based navigation map | 2.12 | `docs/information_architecture.md` |

`erd.png` is 4784 px wide. Place it on a landscape page, or crop it into two
halves (patient health domain / care coordination) if the report template
cannot take a landscape figure.

## Screenshots

In `screens/`. Captured at 1440×900 viewport, 2× device scale (so they are
print-sharp), full page, logged in as the seeded demo accounts with real
seeded data.

| File | Screen | Account |
|---|---|---|
| `patient_dashboard.png` | Patient dashboard | latha@example.com |
| `patient_vitals.png` | Vitals with trends and history | latha@example.com |
| `patient_medications.png` | Medicines with dose tracking | latha@example.com |
| `patient_share_records.png` | Consent and record sharing | latha@example.com |
| `patient_mental_health.png` | Private mood journal | latha@example.com |
| `caregiver_dashboard.png` | Caregiver monitoring view | meera@example.com |
| `provider_dashboard.png` | Provider appointments | dr.nair@example.com |
| `provider_verification_status.png` | Verification pending state | prakashlab@example.com |
| `nurse_dashboard.png` | Nurse assigned patients | nurse.priya@example.com |
| `admin_dashboard.png` | Platform KPIs | admin@example.com |
| `admin_verification_queue.png` | Provider verification queue | admin@example.com |
| `admin_audit_log.png` | Append-only audit log | admin@example.com |

To regenerate them, run the app with seeded data and re-capture. The numbers
in the screenshots depend on `seed_demo`'s fixed random seed, so they are
reproducible.

## A caution for the report

These screenshots contain seeded demo data only. No real patient data exists
anywhere in this project. State that in the figure caption the first time a
screenshot appears, so a reader never has to wonder.
