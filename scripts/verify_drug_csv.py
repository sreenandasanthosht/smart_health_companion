"""
Session 1 (Lane 1) - sanity-check script for db_drug_interactions.csv

What this does:
    - Confirms the file has exactly the 3 columns the AI pipeline (Session 5)
      will depend on: 'Drug 1', 'Drug 2', 'Interaction Description'.
    - Reports row count, duplicate rows, and any missing values.
    - Does NOT touch the database and does NOT require Django to be running.
      This is pure data prep, per the sprint plan - the real model/table for
      this comes later (Session 3 covers the providers app; the interaction
      data itself is read straight from this CSV in Session 5, not stored as
      its own model, since a flat lookup table doesn't need one).

How to run (from the project root, with your venv activated):
    python scripts/verify_drug_csv.py

Expects the file at: data/db_drug_interactions.csv
(place your CSV there - see data/README.md)
"""
import csv
import sys
from collections import Counter
from pathlib import Path

EXPECTED_COLUMNS = ["Drug 1", "Drug 2", "Interaction Description"]
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "db_drug_interactions.csv"


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: could not find {CSV_PATH}")
        print("Save your CSV there first (see data/README.md), then re-run this script.")
        sys.exit(1)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)

    print(f"File: {CSV_PATH}")
    print(f"Columns found: {columns}")

    if columns != EXPECTED_COLUMNS:
        print("WARNING: columns do not match exactly what Session 5's lookup code will expect.")
        print(f"  Expected: {EXPECTED_COLUMNS}")
        print(f"  Found:    {columns}")
        print("  Fix the header row, or update the column names in the Session 5 lookup code to match.")
    else:
        print("Columns OK - match what the interaction-checker will expect.")

    print(f"Row count: {len(rows)}")

    # Missing values
    missing = 0
    for i, row in enumerate(rows, start=2):  # +2: header is line 1, data starts at line 2
        for col in EXPECTED_COLUMNS:
            if col in row and not row[col].strip():
                missing += 1
                if missing <= 10:
                    print(f"  Missing '{col}' at row {i}")
    if missing:
        print(f"WARNING: {missing} missing value(s) found (showing first 10 above).")
    else:
        print("No missing values in Drug 1 / Drug 2 / Interaction Description.")

    # Duplicate (Drug 1, Drug 2) pairs - not necessarily an error (a drug pair can have
    # more than one interaction note in some DrugBank-style exports), just worth knowing.
    pair_counts = Counter((r.get("Drug 1", "").strip().lower(), r.get("Drug 2", "").strip().lower()) for r in rows)
    dupes = {pair: count for pair, count in pair_counts.items() if count > 1}
    print(f"Duplicate (Drug 1, Drug 2) pairs: {len(dupes)}")

    # Unique drug count - useful context for how big the seed/demo medication list should be
    drugs = set()
    for r in rows:
        drugs.add(r.get("Drug 1", "").strip())
        drugs.add(r.get("Drug 2", "").strip())
    drugs.discard("")
    print(f"Unique drug names across both columns: {len(drugs)}")

    print("\nDone. If columns/rows look right, this file is ready to be used as-is in")
    print("Session 5 (load with pandas or csv.DictReader and do a simple name lookup -")
    print("no database model needed for this dataset).")


if __name__ == "__main__":
    main()
