# Prescription Extraction — Privacy Statement

**Task 3.6 / 5.3** · Written 2026-08-03. This is the text the report's privacy
section should be built from, and the claims here are the ones that must be
defensible in a viva.

---

## What actually happens to an uploaded prescription

1. The patient selects a photo and must tick an explicit consent box. Without
   the tick, nothing is read — the request is rejected and the refusal is
   written to the audit log.
2. The image is read into memory. It is **never written to disk**.
3. Tesseract runs **on the machine running CareNest** and converts the image
   to text. The image does not leave the computer at any point.
4. The text is structured into medicine name / dose / frequency / duration.
   This step has two possible paths — see below.
5. The image bytes are released. `ExtractionJob.file_deleted_at` records when.
6. The patient reviews and corrects the result. Only what they confirm becomes
   a `Medication` row.
7. On confirm or discard, the transcribed text is cleared from the database
   too. Only the structured medicines and a short audit record remain.

## The one thing that leaves the machine

**With an LLM key configured** (the current setup, using Google Gemini), the
**OCR text** of the prescription is sent to Google's Generative Language API
to be structured. This text contains medicine names, doses, and whatever else
the prescription carried — potentially including the patient's name if it
appeared on the paper.

**The image is never sent.** Only the transcribed text.

**With no key configured**, the local rule-based parser runs instead and
nothing is transmitted anywhere at all. The system is fully functional in this
mode; it is simply less accurate on unusual formats.

Which path ran is recorded on every job (`parser_used`), so it is always
possible to say afterwards, for any given upload, whether anything was sent.

### What the report must state

Do not write "no data ever leaves your device" — that is false in the current
configuration. The accurate claim is:

> The prescription image is processed entirely on the local machine and is
> never stored or transmitted. The text extracted from it is sent to Google
> Gemini for structuring, under Google's API data-use terms. The system also
> supports a fully local mode in which no data is transmitted at all.

Before submission, cite Google's stated retention policy for the Gemini API
(paid vs free tier differ — the free tier is used for product improvement,
which matters here and should be stated plainly rather than glossed over).

## How the no-storage claim is enforced, not just asserted

Two mechanisms, both testable:

**Django's upload handling is constrained.** By default Django streams any
upload over 2.5 MB to a temporary *file on disk*. Prescription photos from a
phone routinely exceed that, so the default would have quietly broken the
claim. `settings.FILE_UPLOAD_HANDLERS` is therefore restricted to
`MemoryFileUploadHandler` only, and uploads above 15 MB are rejected rather
than spilled to disk.

**A test walks the filesystem.** `ExtractionTests.test_uploaded_file_is_never_written_to_disk`
snapshots every file under the project root before an upload and again after,
and fails if a single new file appears. There is also a test asserting the
upload-handler setting itself, so that if someone changes it later the suite
tells them what they have broken.

## Accuracy, honestly

Extraction is not reliable enough to be trusted without review, and the design
assumes this rather than hiding it. The verify screen is mandatory: nothing is
saved until the patient confirms it, and low-confidence rows are flagged.

A real example from testing a clean, printed, computer-generated prescription
at 93% OCR confidence: Tesseract read `10ml` as `10m!`. The rule-based parser
consequently failed to extract that dose and reported medium confidence rather
than inventing a value. Three of four medicines were extracted perfectly; the
fourth needed correction.

That is the *best* case. Handwritten prescriptions are substantially worse.
Report printed and handwritten accuracy separately, and do not quote a single
combined figure — it would be misleading.

## Limitations to state in the report

- No PDF support; images only.
- Extraction quality on handwriting is poor, which is a property of OCR, not a
  defect in this implementation.
- The LLM path depends on an external service; when it fails the system falls
  back to rules rather than erroring, and records that it did so.
- The system extracts medicines only. It makes no clinical judgement about
  them, checks no interactions, and gives no advice.
