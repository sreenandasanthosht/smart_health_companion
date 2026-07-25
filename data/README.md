# data/

Drop `db_drug_interactions.csv` here (this exact filename/path is what
`scripts/verify_drug_csv.py` and the Session 5 interaction-checker code
look for).

Expected columns (confirmed against the real file on 2026-07-02):

| Column | Example |
|---|---|
| `Drug 1` | Trioxsalen |
| `Drug 2` | Verteporfin |
| `Interaction Description` | Trioxsalen may increase the photosensitizing activities of Verteporfin. |

Notes:
- No blank rows/values confirmed.
- This is a flat lookup file, not a Django model. It's read directly (via
  `csv`/`pandas`) inside the Session 5 interaction-checking code — there's
  no migration or table for it, since a static reference file doesn't need
  one.
- This file is listed in `.gitignore` if it's large or contains data you
  don't want in the public repo history — check with your teammate before
  committing it. If it's small enough and fine to share, commit it normally
  so Terese's environment also has it (not required for her lane, but
  keeps the repo self-contained for the final submission).
