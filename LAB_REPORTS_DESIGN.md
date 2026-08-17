# CareNest — Lab Reports

Why lab reports got their own tab, how a report is read, and how one report
ends up in two different places.

---

## 1. Why a separate tab

Prescriptions and lab reports were sharing one upload page with a "what is
this?" dropdown. They shouldn't, because what happens *after* extraction has
nothing in common:

| | Prescription | Lab report |
|---|---|---|
| Becomes | medicines | measured values |
| Then | dose times, reminders, stock countdown | vitals tracking, or saved results |
| Checked against | the pharmacy | earlier reports |

Sharing one page meant the verify screen had to be generic enough for both,
which made it worse at each. Now:

```
/health/prescription/   Upload Prescription   -> medicines + reminders
/health/lab-report/     Lab Reports           -> upload + saved results
```

**One lab tab, not two.** Uploading and reviewing started out as separate
pages, which meant a patient had to decide in advance whether they wanted
to add a report or look at one — not how anyone thinks about it. They are
now one page: the upload form, then the saved history below it.
`/health/lab-results/` still resolves, and redirects, so older links keep
working.

Each tab links to the other, so uploading the wrong thing on the wrong tab
is one click to fix.

---

## 2. One report, two destinations

This is the heart of it. Every extracted value is asked one question:
**is this a vital sign?**

| Answer | Goes to | Why |
|---|---|---|
| Yes — blood pressure, blood sugar, weight, pulse | `VitalRecord` | joins the trend charts and health score the patient already has |
| No — haemoglobin, cholesterol, creatinine, … | `LabResultValue` on a `LabReport` | nothing existing to join; kept for comparison over time |

Splitting on that one question is why a blood sugar read off a report and a
blood sugar the patient typed in never end up in two parallel histories of
the same measurement.

The mapping lives in `labvalues.VITAL_PATTERNS`, matched against the
analyte name. Two deliberate decisions there:

- **`146/94` is split into two rows** — "Blood pressure (systolic)" and
  "Blood pressure (diastolic)" — because no single column can hold a pair.
  A bare "blood pressure" that was never split is *not* treated as a vital.
- **HbA1c is not a vital**, even though it is a sugar test. It is a
  three-month average, not a reading taken at a moment, so plotting it on
  the same axis as a finger-prick glucose would be wrong.

Vitals written this way are tagged `source = LAB_REPORT`, so their
provenance stays visible next to self-recorded and nurse-recorded readings,
and they run through the same `compute_status()` flagging as any other
reading.

### Blood pressure became optional

`VitalRecord.bp_systolic` and `bp_diastolic` are now nullable. A lab report
frequently carries a blood sugar or a weight and no blood pressure at all —
a reading holding only the fields the report actually contained is honest,
where inventing `0/0` would not be. `bp_display` returns an em dash for
those, and the analytics rules skip records with no BP rather than charting
a gap as a zero. `compute_status()` also now flags on blood sugar
(≥126 watch, ≥180 high), which it could not do before because a
sugar-only reading was impossible.

---

## 3. Reading the values

`health/labvalues.py`. Same two-parser shape as the prescription pipeline:
Gemini when a key is configured, falling back to explicit rules.

The rule parser reads a results table line by line:

```
Haemoglobin            10.2       g/dL        12.0 - 15.5
   analyte             value      unit        reference range
```

It also handles `B.P. 146/94` (anchored to the start of the line, so a date
like `10/08/2026` is never mistaken for one), strips page furniture
(headers, patient details, footers), and picks up a printed `High` / `Low`
marker where there is one.

**Flags are computed, not guessed.** A value is compared against the
printed reference range — `12.0 - 15.5`, `< 200`, `> 40` — and marked
NORMAL, LOW or HIGH. With no range to compare against the flag is
`UNKNOWN`, not "normal". Deciding a number is abnormal without a range
would be a clinical claim this project does not make, and `UNKNOWN` is
excluded from the "results outside normal range" count for the same reason.

**Implausible numbers are rejected as vitals.** `VITAL_RANGES` sanity-checks
each value before it is offered — a "weight" of 400 kg is an OCR error, not
a measurement, and stays out of the trend chart.

---

## 4. The report itself is never kept

Identical promise to prescriptions, and now enforced by one shared function
(`_ingest_document`) rather than two copies that could drift:

1. The upload is validated and read into memory. Django's in-memory upload
   handler is forced, so a large file cannot spill to a temp file.
2. Tesseract reads it; the bytes are released in a `finally` block.
3. `file_deleted_at` is stamped **before the response is returned** — the
   verify page can therefore tell the patient the photo is already gone,
   and be telling the truth.
4. `raw_text` holds the transcription only while the patient checks it, and
   is cleared the moment they confirm or discard.

Consent is a gate, not a checkbox: refusing is recorded in the audit log
too, so the trail shows attempted-but-refused processing rather than only
what succeeded.

---

## 5. What the patient sees

**Lab Reports** — upload, with a plain statement of where results will go.

**Check what we found** — two tables, clearly separated: *Vitals* ("these go
into your vitals tracking") and *Lab results* ("these are saved under My Lab
Results"). Every field is editable, and correcting an analyte's name
re-decides where it goes, because the destination is derived from what the
patient confirmed rather than from what the parser first guessed.

**My Lab Results** — reports newest first, plus a per-analyte strip for any
test taken more than once, so a value can be read as a direction rather than
a number in isolation.

---

## 6. Getting a clean extraction

Four things determine how good the result is, in order of how much they
matter.

### 1. Upload the PDF, not a photo of it

By far the biggest factor. A PDF from a lab already contains its text —
`pdfplumber` reads it exactly, and `ocr_confidence` is recorded as 100
because nothing was guessed. Photographing a PDF on screen throws away
perfect text in order to guess at it again.

Requires `python -m pip install pdfplumber`. A scanned PDF (a photo in a
PDF wrapper) has no text layer and is reported as such rather than
silently returning nothing.

### 2. Set `LLM_API_KEY`

The rule parser reads a tidy column-aligned table well. It struggles when
OCR wraps or merges columns. Gemini handles that far better, and returns
the values already structured. This is the difference between "Medium"
confidence and "High" across the board.

### 3. Image preparation (automatic)

Before recognition an image is greyscaled, upscaled to ~2000px wide, and
contrast-stretched. Tesseract also runs in `--psm 6` ("a single uniform
block of text") rather than the default full page-layout analysis, which
on a results table hunts for columns and routinely splits or merges them
in the wrong place. This is what turns `13419` back into `134.19`.

### 4. What the parser was taught about real reports

Observed on an actual kidney function report and handled explicitly:

| Feature | Example |
|---|---|
| Abnormality marker before the value | `SERUM UREA  L  17  mg/dl  19 - 45` |
| Compound units | `ml/min/1.73m^2`, `10^3/uL`, `mmol/L` |
| Rows with no unit or range | `UREA / CREATININE RATIO  24.64` |
| Method annotations | `Method: Calculated` — excluded |
| Footers and watermarks | `Powered by Labsmart`, `NOT VALID FOR MEDICO LEGAL PURPOSE` — excluded |
| OCR junk glued to a test name | `Serum Uric Acid 55 Mo` → `Serum Uric Acid` |
| Names that are mostly digits | rejected as misread columns |
| Bullet points, and OCR's version of them | `• Heart rate` read as `e Heart rate` → `Heart Rate` |
| Comma used as a decimal point | `6,2%` → `6.2` (but `1,200` stays twelve hundred) |

Bullets deserve a note: a summary-style report is a bulleted list, and OCR
reads `•` as `e`, `o`, `©` or `*`. Left in place that letter becomes part of
the test name — `E Heart Rate` — which then fails to match anything and
silently drops the row. Stripping bullets first recovered three of five rows
on a real annual-summary report.

### Blood pressure that lost its slash

`130/85` is frequently recognised as `13035`. There is no honest way to work
out where the slash belonged, so nothing is guessed. The value is kept as a
vital named "Blood pressure", shown in the vitals section of the verify page
with a warning, and the patient retypes it. `split_bp()` splits it at
confirmation time — the correction takes effect exactly where corrections
belong. A blood pressure left unreadable is reported as not saved, rather
than being quietly filed as a lab result.

---

## 7. Known limits

- **Column-aligned tables read best.** A report whose columns wrap badly
  will still parse poorly from a photo. Upload the PDF, or set the LLM key.
- **Scanned PDFs are not read.** They contain no text layer; upload them as
  an image instead so OCR runs.
- **No interpretation.** CareNest records what the report said and flags it
  against the printed range. It does not tell the patient what a value
  means, and the results page says so.
