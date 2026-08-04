"""
Prescription and lab-report extraction — the process-and-discard pipeline.

The design promise is not "we store your documents securely". It is "we do
not store them at all". Everything here is written to make that literally
true and demonstrable:

  * the uploaded bytes are held in a BytesIO and never written to disk
    (settings forces MemoryFileUploadHandler so Django cannot spill large
    uploads to a temp file either);
  * OCR runs locally via Tesseract, so the IMAGE never leaves the machine;
  * only the structured result is persisted, and the transcribed text is
    cleared as soon as the patient has confirmed or discarded it.

PRIVACY NOTE — read before changing anything here. When an LLM key is
configured, the OCR *text* is sent to that provider to be structured. The
image is not. With no key configured the local rule-based parser is used and
nothing leaves the machine at all. Whichever path runs is recorded on the
job (`parser_used`) so the report can state honestly what happened, and so
the two approaches can be compared on the same documents.
"""
import io
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'}


class ExtractionError(Exception):
    """Raised for anything the patient should be told about in plain words."""


# ---------------------------------------------------------------------------
# Step 1 — OCR (always local)
# ---------------------------------------------------------------------------

def extract_text(file_bytes, filename=''):
    """
    Run Tesseract over the image bytes and return (text, mean_confidence).

    The bytes stay in memory throughout. Nothing is written to disk.
    """
    try:
        import pytesseract
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:                                  # pragma: no cover
        raise ExtractionError(
            'The OCR libraries are not installed. Run: pip install pytesseract Pillow'
        ) from exc

    if getattr(settings, 'TESSERACT_CMD', ''):
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()
    except UnidentifiedImageError as exc:
        raise ExtractionError(
            "That file doesn't look like an image we can read. "
            'Please upload a JPG or PNG photo of the prescription.'
        ) from exc

    # Greyscale helps Tesseract on phone photos of printed text.
    if image.mode not in ('L', 'RGB'):
        image = image.convert('RGB')

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        raise ExtractionError(
            'Could not read the image. Check that Tesseract is installed and that '
            'TESSERACT_CMD in your .env points at it.'
        ) from exc

    words, confidences = [], []
    for word, conf in zip(data.get('text', []), data.get('conf', [])):
        word = (word or '').strip()
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        if word and conf >= 0:
            words.append(word)
            confidences.append(conf)

    # Rebuild line structure — dosage notation like "1-0-1" only makes sense
    # per line, so a flat bag of words would lose it.
    lines, current, last_line_id = [], [], None
    for i, word in enumerate(data.get('text', [])):
        word = (word or '').strip()
        line_id = (data.get('block_num', [0])[i], data.get('par_num', [0])[i], data.get('line_num', [0])[i])
        if line_id != last_line_id and current:
            lines.append(' '.join(current))
            current = []
        last_line_id = line_id
        if word:
            current.append(word)
    if current:
        lines.append(' '.join(current))

    text = '\n'.join(ln for ln in lines if ln.strip())
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    return text, mean_conf


# ---------------------------------------------------------------------------
# Step 2a — rule-based parser (local, always available, fully explainable)
# ---------------------------------------------------------------------------

# Dosage notations seen on Indian prescriptions, mapped to plain English.
# Every entry here is something a viva examiner can be walked through.
DOSAGE_NOTATION = {
    '1-0-1': 'Morning and night',
    '1-1-1': 'Morning, afternoon and night',
    '1-0-0': 'Morning only',
    '0-0-1': 'Night only',
    '0-1-0': 'Afternoon only',
    '1-1-0': 'Morning and afternoon',
    '0-1-1': 'Afternoon and night',
    'OD': 'Once daily',
    'BD': 'Twice daily',
    'BID': 'Twice daily',
    'TDS': 'Three times daily',
    'TID': 'Three times daily',
    'QID': 'Four times daily',
    'HS': 'At bedtime',
    'SOS': 'When required',
    'STAT': 'Immediately, once',
}

# A leading numbered-list marker before the medicine, e.g. "1)", "2.", "(3]".
# Printed prescriptions routinely number their medicine list; without
# stripping this first, FORM_PREFIX (anchored to the start of the line)
# never matches and the whole line is silently skipped.
LIST_PREFIX = r'^\s*[\(\[]?\d{1,2}[\.\)\]]?\s*'

# Prefixes that mark the start of a medicine line.
FORM_PREFIX = r'(?:Tab|Tablet|Cap|Capsule|Syp|Syrup|Inj|Injection|Susp|Oint|Drop|Drops)\.?'
# A dose such as "500mg", "5 mg", "10ml", "2.5 mcg".
DOSE_PATTERN = r'(\d+(?:\.\d+)?\s?(?:mcg|mg|ml|IU|units?|g)\b)'
# A duration such as "x 30 days", "for 10 days", "* 2 weeks", or a bare
# "8 days" with no leading marker. "bays" is included as an alias because
# Tesseract commonly confuses "d" and "b" in this exact word.
DURATION_PATTERN = r'(?:(?:x|for|\*)\s*)?\b(\d+\s*(?:days?|bays?|weeks?|months?))\b'
# Either a coded frequency (OD/BD/1-0-1/...) or the plain-English style seen
# on many Indian prescriptions: "1 Morning", "4 Morning, 1 Night".
FREQ_PATTERN = (
    r'(\d-\d-\d|\bOD\b|\bBD\b|\bBID\b|\bTDS\b|\bTID\b|\bQID\b|\bHS\b|\bSOS\b|\bSTAT\b|'
    r'\d+\s*(?:Morning|Afternoon|Evening|Night|Noon)'
    r'(?:\s*,?\s*\d+\s*(?:Morning|Afternoon|Evening|Night|Noon))*)'
)

# Lines that are never a medicine.
NOISE_PATTERN = re.compile(
    r'^\s*(?:dr\.?|clinic|hospital|address|phone|mob|reg|date|patient|age|sex|'
    r'diagnosis|advice|follow|signature|rx)\b', re.I)


def parse_medications_rules(text):
    """
    Extract medicines using explicit regex rules.

    Returns a list of dicts: name, dose, frequency, duration, confidence.
    Confidence reflects how many of the four fields a rule actually matched —
    it is a completeness score, not a probability, and is never invented.
    """
    results = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 4 or NOISE_PATTERN.match(line):
            continue
        # Strip a leading list number ("1)", "2.") before anything else, so
        # it doesn't block the form-prefix check below.
        line = re.sub(LIST_PREFIX, '', line)
        if len(line) < 4:
            continue

        has_prefix = re.match(FORM_PREFIX, line, re.I) is not None
        dose_match = re.search(DOSE_PATTERN, line, re.I)
        freq_match = re.search(FREQ_PATTERN, line, re.I)
        dur_match = re.search(DURATION_PATTERN, line, re.I)

        # A line is a medicine if it names a form, or carries a dose plus a
        # recognisable frequency. Requiring both avoids matching stray numbers.
        if not (has_prefix or (dose_match and freq_match)):
            continue

        name = line
        if has_prefix:
            name = re.sub(FORM_PREFIX, '', name, count=1, flags=re.I)
        for pattern in (DOSE_PATTERN, FREQ_PATTERN, DURATION_PATTERN):
            name = re.sub(pattern, '', name, flags=re.I)
        # A bare duration unit with no count attached (OCR often drops the
        # number, e.g. "'Days" left over from a line that should have read
        # "N Days") is leftover noise, not part of the medicine name.
        name = re.sub(r'\b(?:Days?|Weeks?|Months?)\b', '', name, flags=re.I)
        name = re.sub(r'[^A-Za-z0-9 \-+/]', ' ', name)
        name = re.sub(r'\s{2,}', ' ', name).strip(' -')

        if not name or len(name) < 3:
            continue

        freq_raw = freq_match.group(1) if freq_match else ''
        # Coded notations (OD, BD, 1-0-1, ...) are looked up case-insensitively
        # and expanded to plain English. Word-based frequencies ("1 Morning,
        # 1 Night") are already plain English, so they're kept as typed
        # rather than forced through the lookup table.
        frequency = DOSAGE_NOTATION.get(freq_raw.upper(), freq_raw)

        # Completeness score: prefix 0.4, dose 0.3, frequency 0.2, duration 0.1
        confidence = (0.4 if has_prefix else 0.0) + (0.3 if dose_match else 0.0) \
            + (0.2 if freq_match else 0.0) + (0.1 if dur_match else 0.0)

        results.append({
            'name': name.title()[:120],
            'dose': (dose_match.group(1) if dose_match else '')[:60],
            'frequency': frequency[:120],
            'duration': (dur_match.group(1) if dur_match else '')[:60],
            'confidence': round(min(confidence, 0.95), 2),
        })

    # De-duplicate by name, keeping the most complete match.
    best = {}
    for item in results:
        key = item['name'].lower()
        if key not in best or item['confidence'] > best[key]['confidence']:
            best[key] = item
    return list(best.values())


# ---------------------------------------------------------------------------
# Step 2b — LLM parser (optional; sends TEXT ONLY, never the image)
# ---------------------------------------------------------------------------

LLM_PROMPT = """You are extracting structured medicine data from the OCR text of a prescription.
The OCR is imperfect and may contain misread characters.

Return ONLY the medicines you can actually identify. Do not guess a medicine
that is not there, and do not correct a drug name into a different drug.
If a field is not present, return an empty string for it.

Set "confidence" between 0 and 1 to reflect how sure you are that this line
really is that medicine with that dose. Be honest: use a low value when the
OCR text is garbled.

Expand dosage notation into plain English: 1-0-1 means "Morning and night",
OD "Once daily", BD "Twice daily", TDS "Three times daily", HS "At bedtime",
SOS "When required".

OCR TEXT:
---
{text}
---
"""

GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "medications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dose": {"type": "string"},
                    "frequency": {"type": "string"},
                    "duration": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "dose", "frequency", "duration", "confidence"],
            },
        }
    },
    "required": ["medications"],
}


def llm_available():
    return bool(getattr(settings, 'LLM_API_KEY', ''))


def parse_medications_llm(text):
    """
    Ask the configured LLM to structure the OCR text.

    Raises ExtractionError on any failure so the caller can fall back to the
    rule-based parser rather than showing the patient an error.
    """
    if not llm_available():
        raise ExtractionError('No LLM API key configured.')

    provider = getattr(settings, 'LLM_PROVIDER', 'gemini').lower()
    if provider != 'gemini':
        raise ExtractionError(f'Unsupported LLM provider: {provider}')

    model = getattr(settings, 'LLM_MODEL', 'gemini-2.0-flash')
    url = (f'https://generativelanguage.googleapis.com/v1beta/models/'
           f'{model}:generateContent?key={settings.LLM_API_KEY}')
    payload = {
        'contents': [{'parts': [{'text': LLM_PROMPT.format(text=text[:8000])}]}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': GEMINI_SCHEMA,
            'temperature': 0.0,
        },
    }
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')

    try:
        timeout = getattr(settings, 'LLM_TIMEOUT_SECONDS', 20)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise ExtractionError(f'LLM returned HTTP {exc.code}') from exc
    except Exception as exc:
        raise ExtractionError(f'LLM request failed: {exc}') from exc

    try:
        raw = body['candidates'][0]['content']['parts'][0]['text']
        items = json.loads(raw)['medications']
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ExtractionError('LLM response was not in the expected format.') from exc

    cleaned = []
    for item in items:
        name = str(item.get('name', '')).strip()
        if not name:
            continue
        try:
            confidence = float(item.get('confidence', 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        cleaned.append({
            'name': name[:120],
            'dose': str(item.get('dose', '')).strip()[:60],
            'frequency': str(item.get('frequency', '')).strip()[:120],
            'duration': str(item.get('duration', '')).strip()[:60],
            'confidence': round(max(0.0, min(confidence, 1.0)), 2),
        })
    return cleaned


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def parse_medications(text):
    """
    Structure OCR text, preferring the LLM and falling back to rules.

    Returns (medications, parser_used, note). The caller records all three,
    so it is always visible which path produced a given result.
    """
    if llm_available():
        try:
            items = parse_medications_llm(text)
            return items, 'LLM', f'Parsed by {settings.LLM_MODEL}'
        except ExtractionError as exc:
            logger.warning('LLM parse failed, falling back to rules: %s', exc)
            items = parse_medications_rules(text)
            return items, 'RULES', f'LLM unavailable ({exc}); used rule-based parser'
    items = parse_medications_rules(text)
    return items, 'RULES', 'No LLM key configured; used local rule-based parser'


def validate_upload(uploaded):
    """Reject anything we should not try to process, with a readable reason."""
    max_bytes = getattr(settings, 'MAX_UPLOAD_BYTES', 15 * 1024 * 1024)
    if uploaded.size == 0:
        raise ExtractionError('That file is empty.')
    if uploaded.size > max_bytes:
        raise ExtractionError(
            f'That image is {uploaded.size // (1024 * 1024)} MB. '
            f'Please upload one smaller than {max_bytes // (1024 * 1024)} MB.')
    content_type = (uploaded.content_type or '').lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ExtractionError(
            'Please upload a photo or scan as a JPG or PNG. '
            'PDFs are not supported yet.')
