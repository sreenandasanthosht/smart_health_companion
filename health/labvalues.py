"""
Reading measured values off a lab report, and deciding where each one goes.

A lab report is a table: an analyte, a number, a unit, and usually a
reference range. This module turns the OCR text of that table into
structured values, then answers the question that actually matters --
is this a vital sign, or is it not?

  * Vitals (blood pressure, blood sugar, weight, pulse) are written to
    `VitalRecord`, so they join the trend charts the patient already has.
  * Everything else is kept as `LabResultValue` rows on a `LabReport`.

Splitting on that one question is why the same reading never ends up in
two parallel histories.

Nothing here stores the report itself. As with prescriptions, the image is
read in memory and discarded; only confirmed values persist.
"""
import re
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------------------
# Which analytes are vitals, and which VitalRecord column they belong in
# --------------------------------------------------------------------------

# Matched against a lowercased analyte name. Order matters: the first
# pattern that matches wins, so the more specific ones come first.
VITAL_PATTERNS = [
    # The split halves come first. Once a value has been separated into
    # systolic and diastolic it names its own column, and must not fall
    # through to the generic pattern below -- which would send a perfectly
    # usable blood pressure to the lab-results table instead of vitals.
    (r'systolic', 'bp_systolic'),
    (r'diastolic', 'bp_diastolic'),
    # A bare "blood pressure" is the unsplit "146/94" form, which no single
    # column can hold. Handled by BP_LINE at parse time; anywhere else it
    # is unusable as a vital.
    (r'blood\s*pressure|^bp\b|\bbp\b', 'bp'),
    (r'h(?:a)?emoglobin\s*a1c|hba1c|glycated', None),      # a lab value, not a vital
    (r'blood\s*sugar|glucose|\bfbs\b|\brbs\b|\bppbs\b|sugar\s*\(?(?:f|pp)', 'blood_sugar'),
    (r'\bweight\b|body\s*weight', 'weight_kg'),
    (r'heart\s*rate|pulse\s*rate|^pulse\b|\bpulse\b', 'heart_rate'),
]

# What each vital column expects, used to sanity-check a parsed number
# before it is offered as a vital. A "weight" of 400 kg is an OCR error,
# not a measurement, and should stay out of the trend chart.
VITAL_RANGES = {
    'bp_systolic': (50, 260),
    'bp_diastolic': (30, 180),
    'blood_sugar': (20, 800),
    'weight_kg': (2, 300),
    'heart_rate': (25, 250),
}

VITAL_LABELS = {
    'bp': 'Blood pressure',
    'bp_systolic': 'Blood pressure (systolic)',
    'bp_diastolic': 'Blood pressure (diastolic)',
    'blood_sugar': 'Blood sugar',
    'weight_kg': 'Weight',
    'heart_rate': 'Heart rate',
}


def vital_field_for(analyte):
    """
    Which `VitalRecord` field this analyte belongs to, or '' if none.

    HbA1c is deliberately *not* a vital even though it is a sugar test:
    it is a three-month average, not a reading taken at a moment, so
    plotting it on the same axis as finger-prick glucose would be wrong.
    """
    name = (analyte or '').strip().lower()
    if not name:
        return ''
    for pattern, field in VITAL_PATTERNS:
        if re.search(pattern, name):
            return field or ''
    return ''


# --------------------------------------------------------------------------
# Parsing the text
# --------------------------------------------------------------------------

# Lines that are page furniture rather than results. Real reports carry a
# lot of it: letterheads, footers, marketing, interpretation notes and
# per-test method annotations, all of which look enough like a result line
# to be picked up if they are not excluded first.
NOISE = re.compile(
    r'^\s*(?:dr\.?|mr\.?|mrs\.?|ms\.?|lab|laborator|clinic|hospital|address|'
    r'phone|mob|tel|email|www|http|reg(?:d)?\.?\b|regn|'
    r'patient|name|age|sex|gender|date|sample|specimen|collected|received|'
    r'registered|reported|ref(?:erred)?\s*by|referred|'
    r'page|report|result|test\s*name|units?|reference|normal\s*range|biochemistry|'
    r'h(?:a)?ematology|department|profile|panel|'
    r'method|note|signature|verified|checked|authorised|authorized|'
    r'end\s*of|interpretation|comments?|correlate|clinically|'
    r'powered\s*by|not\s*valid|work\s*timings?|causes?\s*of|'
    r'increased|decreased|pregnan|therapy|disease)\b', re.I)

# Marketing and footers that carry no leading keyword -- a watermark or a
# company name with a stray number beside it reads exactly like a result.
NOISE_ANYWHERE = re.compile(
    r'(?:software|solutions|technolog|pvt\.?\s*ltd|private\s*limited|'
    r'letterhead|sample\s*report|©|all\s*rights)', re.I)

# Bullet points, and what OCR turns them into. A "•" is routinely read as
# "e", "o", "©" or "*", and left in place it becomes part of the test name
# -- which is how "Heart rate" arrives as "E Heart Rate". Stripped from the
# front of every line before anything else is attempted.
BULLET = re.compile(r'^\s*(?:[•●▪◦·*+\-–—>»]+\s*)?(?:[eEoOcC©¢°]\s+(?=[A-Za-z]{3}))?')

# "12.4", "1,200", "0.85", and "6,2" -- OCR and non-English reports both
# produce a comma where a decimal point belongs. A comma followed by
# exactly three digits is a thousands separator; anything else is a point.
NUMBER = r'\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?'

# A unit as printed on a report. Deliberately generous about slashes,
# carets and digits: real units include "ml/min/1.73m^2" and "10^3/uL".
UNIT = (
    # Units with no slash, listed explicitly because a bare word next to a
    # number is otherwise indistinguishable from the start of a range.
    r'(?:%|kg|lbs?|bpm|mmHg|fl|pg|sec|ratio|mm/hr'
    # Anything of the shape "<prefix>/<something>" -- mg/dL, ng/dL, µIU/mL,
    # 10^6/uL, ml/min/1.73m^2, cells/cumm. Listing these one by one was the
    # bug that made "Free T4  0.9  ng/dL" parse as value 0.8: an unlisted
    # unit forced the regex to backtrack and swallow it into the test name.
    r'|(?:\d+\^?\d*|[A-Za-zµ]{1,6})/[A-Za-zµ0-9.^]{1,12}(?:/[A-Za-z0-9.^]{1,10})?'
    r'|/cumm)')

# "12.0 - 15.5", "12.0-15.5", "(70 - 100)", "< 200", "up to 5.0"
RANGE = (rf'(?:\(?\s*(?:{NUMBER})\s*(?:-|–|to)\s*(?:{NUMBER})\s*\)?'
         rf'|[<>]\s*=?\s*(?:{NUMBER})'
         rf'|up\s*to\s*(?:{NUMBER}))')

# A single-letter abnormality marker printed between the test name and the
# value, as in "SERUM UREA    L    17    mg/dl    19 - 45". Without this the
# L is absorbed into the test name and the row parses as a different test.
LEADING_FLAG = r'(?:(?P<lead_flag>[HL])\s+)?'

# The main line pattern: NAME [FLAG] VALUE [UNIT] [RANGE]
RESULT_LINE = re.compile(
    rf'^(?P<name>[A-Za-z][A-Za-z0-9 ()\-./%\']{{2,60}}?)'
    rf'\s*[:\-]?\s+'
    rf'{LEADING_FLAG}'
    rf'(?P<value>{NUMBER})\s*'
    rf'(?P<unit>{UNIT})?\s*'
    rf'(?P<range>{RANGE})?\s*$', re.I)

# Trailing junk that OCR leaves glued to a test name: a stray number from
# the value column, or a mangled unit fragment.
#
# Note what is NOT here: a general "strip any trailing one- or two-letter
# word" rule. It looked tidy and it turned "Vitamin D" into "Vitamin" and
# would have done the same to "Free T3" and "Vitamin B12". Only fragments
# that are actually junk are listed.
NAME_TAIL_JUNK = re.compile(
    r'\s+(?:\d+(?:\.\d+)?|mo|mott|fomatt|rnin|nin|mgd|mgdl|gdl|mgl|dl|ul|mi|ml)$', re.I)


def _strip_name_junk(name):
    """Peel trailing junk off a test name, since OCR often leaves several."""
    for _ in range(3):
        cleaned = NAME_TAIL_JUNK.sub('', name).strip(' :-.')
        if cleaned == name:
            break
        name = cleaned
    return name

# Blood pressure is written as one token, so it gets its own pattern.
# Anchored to the start of the line, because "146/94" appearing anywhere
# else on a report is far more likely to be a date or a ratio. The gap is
# generous because report tables pad heavily between column and value.
BP_LINE = re.compile(
    r'^\s*(?P<name>b\.?\s?p\.?|blood\s*pressure)[^0-9]{0,40}'
    r'(?P<sys>\d{2,3})\s*/\s*(?P<dia>\d{2,3})', re.I)

# An explicit High/Low marker printed beside the value.
FLAG_WORDS = re.compile(r'\b(high|low|h|l|abnormal|normal)\b\s*$', re.I)


def _clean_number(raw):
    """
    A printed number as a Decimal.

    "1,200" is twelve hundred; "6,2" is six point two. Distinguished by
    what follows the comma, because a thousands separator is always three
    digits and a decimal comma never is.
    """
    text = str(raw).strip()
    if re.fullmatch(r'\d+,\d{1,2}', text):
        text = text.replace(',', '.')
    else:
        text = text.replace(',', '')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalise_number(raw):
    """The same fix, applied to the text stored for display."""
    text = str(raw).strip()
    return text.replace(',', '.') if re.fullmatch(r'\d+,\d{1,2}', text) else text


def _flag_from_range(value, reference_range):
    """
    Compare the value against the printed reference range.

    Returns 'NORMAL', 'LOW', 'HIGH' or 'UNKNOWN'. Unknown when there is no
    range to compare against -- guessing whether a number is abnormal
    without a range would be a clinical claim this project does not make.
    """
    number = _clean_number(value)
    if number is None or not reference_range:
        return 'UNKNOWN'

    text = reference_range.strip().strip('()')

    match = re.match(rf'^\s*({NUMBER})\s*[-–]|\s*to\s*', text)
    pair = re.match(rf'^\s*({NUMBER})\s*(?:[-–]|to)\s*({NUMBER})\s*$', text)
    if pair:
        low, high = _clean_number(pair.group(1)), _clean_number(pair.group(2))
        if low is None or high is None:
            return 'UNKNOWN'
        if number < low:
            return 'LOW'
        if number > high:
            return 'HIGH'
        return 'NORMAL'

    upper = re.match(rf'^\s*(?:<|up\s*to)\s*({NUMBER})\s*$', text, re.I)
    if upper:
        limit = _clean_number(upper.group(1))
        return 'UNKNOWN' if limit is None else ('HIGH' if number > limit else 'NORMAL')

    lower = re.match(rf'^\s*>\s*({NUMBER})\s*$', text)
    if lower:
        limit = _clean_number(lower.group(1))
        return 'UNKNOWN' if limit is None else ('LOW' if number < limit else 'NORMAL')

    return 'UNKNOWN'


def split_bp(value):
    """
    Turn "130/85" into (130, 85), or return None.

    Used at confirmation time. A blood pressure whose slash OCR lost comes
    through as one unusable number; the patient retypes it on the verify
    page and it is split here, which is the right place for a correction to
    take effect.
    """
    match = re.match(r'^\s*(\d{2,3})\s*[/\\|]\s*(\d{2,3})\s*$', str(value or ''))
    if not match:
        return None
    systolic, diastolic = match.group(1), match.group(2)
    if not (_plausible_as_vital('bp_systolic', systolic)
            and _plausible_as_vital('bp_diastolic', diastolic)):
        return None
    return int(systolic), int(diastolic)


def _plausible_as_vital(field, value):
    """Keep an OCR misread out of the vitals chart."""
    number = _clean_number(value)
    if number is None:
        return False
    low, high = VITAL_RANGES.get(field, (None, None))
    if low is None:
        return True
    return low <= float(number) <= high


def parse_lab_values_rules(text):
    """
    Extract values from OCR text using explicit rules.

    Returns a list of dicts: analyte, value, unit, reference_range, flag,
    vital_field, confidence. Confidence is a completeness score -- how many
    of the parts a rule actually matched -- not a probability.
    """
    results = []

    for raw_line in (text or '').splitlines():
        line = BULLET.sub('', raw_line.strip()).strip()
        if len(line) < 4:
            continue

        # Blood pressure first: it is the one result written as a pair.
        bp = BP_LINE.search(line)
        if bp:
            systolic, diastolic = bp.group('sys'), bp.group('dia')
            if (_plausible_as_vital('bp_systolic', systolic)
                    and _plausible_as_vital('bp_diastolic', diastolic)):
                results.append({
                    'analyte': 'Blood pressure (systolic)', 'value': systolic,
                    'unit': 'mmHg', 'reference_range': '90 - 120', 'flag': 'UNKNOWN',
                    'vital_field': 'bp_systolic', 'confidence': 0.85,
                })
                results.append({
                    'analyte': 'Blood pressure (diastolic)', 'value': diastolic,
                    'unit': 'mmHg', 'reference_range': '60 - 80', 'flag': 'UNKNOWN',
                    'vital_field': 'bp_diastolic', 'confidence': 0.85,
                })
                continue

        if NOISE.match(line) or NOISE_ANYWHERE.search(line):
            continue

        # Strip a trailing High/Low marker before matching, and remember it.
        printed_flag = ''
        flag_match = FLAG_WORDS.search(line)
        if flag_match:
            word = flag_match.group(1).upper()
            printed_flag = {'H': 'HIGH', 'L': 'LOW', 'HIGH': 'HIGH',
                            'LOW': 'LOW', 'NORMAL': 'NORMAL'}.get(word, '')
            if printed_flag:
                line = line[:flag_match.start()].strip()

        match = RESULT_LINE.match(line)
        if not match:
            continue

        # A marker printed before the value ("SERUM UREA  L  17") beats a
        # range comparison, because it is what the lab itself concluded.
        lead = (match.group('lead_flag') or '').upper()
        if lead:
            printed_flag = {'H': 'HIGH', 'L': 'LOW'}.get(lead, printed_flag)

        analyte = re.sub(r'\s{2,}', ' ', match.group('name')).strip(' :-.')
        analyte = _strip_name_junk(analyte)
        if len(analyte) < 3 or analyte.isdigit():
            continue
        # A "test name" that is mostly digits is a misread column, not a test.
        letters = sum(c.isalpha() for c in analyte)
        if letters < 3 or letters < len(analyte.replace(' ', '')) / 2:
            continue

        value = normalise_number(match.group('value'))
        unit = (match.group('unit') or '').strip()
        ref = (match.group('range') or '').strip().strip('()')

        flag = printed_flag or _flag_from_range(value, ref)
        field = vital_field_for(analyte)
        # A blood-pressure line that reached here did not contain a usable
        # "120/80" -- OCR mangles the slash often ("130/85" as "13035").
        # It is kept as a vital with field 'bp' so the verify page shows it
        # in the vitals section for the patient to retype, rather than
        # guessing at where the slash belonged.
        if field and field != 'bp' and not _plausible_as_vital(field, value):
            field = ''

        confidence = 0.4 + (0.2 if unit else 0.0) + (0.2 if ref else 0.0) \
            + (0.15 if flag != 'UNKNOWN' else 0.0)

        results.append({
            'analyte': analyte.title()[:120],
            'value': str(value)[:40],
            'unit': unit[:30],
            'reference_range': ref[:60],
            'flag': flag,
            'vital_field': field,
            'confidence': round(min(confidence, 0.95), 2),
        })

    # De-duplicate by analyte, keeping the most complete match.
    best = {}
    for item in results:
        key = item['analyte'].lower()
        if key not in best or item['confidence'] > best[key]['confidence']:
            best[key] = item
    return list(best.values())


# --------------------------------------------------------------------------
# LLM path -- sends TEXT ONLY, never the image
# --------------------------------------------------------------------------

LLM_PROMPT = """You are extracting structured results from the OCR text of a medical lab report.
The OCR is imperfect and may contain misread characters.

Return ONLY the measured results you can actually identify. Do not invent a
test that is not there, and do not correct a value into a different number.
Ignore headers, patient details, addresses and footers.

For each result give:
  analyte          the name of the test, e.g. "Haemoglobin"
  value            the measured number as printed, e.g. "12.4"
  unit             e.g. "g/dL", or "" if not printed
  reference_range  e.g. "12.0 - 15.5", or "" if not printed
  flag             one of NORMAL, LOW, HIGH, UNKNOWN. Use UNKNOWN unless the
                   report prints a marker or a range you can compare against.

If blood pressure appears as "120/80", return it as two separate results named
"Blood pressure (systolic)" and "Blood pressure (diastolic)".

Set "confidence" between 0 and 1 to reflect how sure you are. Be honest: use a
low value when the OCR text is garbled.

OCR TEXT:
---
{text}
---
"""

GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "analyte": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "reference_range": {"type": "string"},
                    "flag": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["analyte", "value", "unit", "reference_range",
                             "flag", "confidence"],
            },
        }
    },
    "required": ["results"],
}


def parse_lab_values_llm(text):
    """
    Ask the configured LLM to structure the OCR text of a lab report.

    Raises ExtractionError on any failure, so the caller falls back to the
    rule-based parser rather than showing the patient an error.
    """
    from health import extraction

    body = extraction.call_gemini(LLM_PROMPT.format(text=text[:8000]), GEMINI_SCHEMA)
    try:
        items = body['results']
    except (KeyError, TypeError) as exc:
        raise extraction.ExtractionError(
            'LLM response was not in the expected format.') from exc

    valid_flags = {'NORMAL', 'LOW', 'HIGH', 'UNKNOWN'}
    cleaned = []
    for item in items:
        analyte = str(item.get('analyte', '')).strip()
        value = str(item.get('value', '')).strip()
        if not analyte or not value:
            continue
        try:
            confidence = float(item.get('confidence', 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        flag = str(item.get('flag', 'UNKNOWN')).strip().upper()
        if flag not in valid_flags:
            flag = 'UNKNOWN'

        value = normalise_number(value)
        field = vital_field_for(analyte)
        if field and field != 'bp' and not _plausible_as_vital(field, value):
            field = ''

        cleaned.append({
            'analyte': analyte[:120],
            'value': value[:40],
            'unit': str(item.get('unit', '')).strip()[:30],
            'reference_range': str(item.get('reference_range', '')).strip()[:60],
            'flag': flag,
            'vital_field': field,
            'confidence': round(max(0.0, min(confidence, 1.0)), 2),
        })
    return cleaned


def parse_lab_values(text):
    """
    Structure lab-report text, preferring the LLM and falling back to rules.

    Returns (values, parser_used, note) -- the same shape as
    `extraction.parse_medications`, so the caller records which path
    produced a given result either way.
    """
    import logging

    from django.conf import settings

    from health import extraction

    logger = logging.getLogger(__name__)

    if extraction.llm_available():
        try:
            items = parse_lab_values_llm(text)
            return items, 'LLM', f'Parsed by {settings.LLM_MODEL}'
        except extraction.ExtractionError as exc:
            logger.warning('LLM lab parse failed, falling back to rules: %s', exc)
            items = parse_lab_values_rules(text)
            return items, 'RULES', f'LLM unavailable ({exc}); used rule-based parser'
    items = parse_lab_values_rules(text)
    return items, 'RULES', 'No LLM key configured; used local rule-based parser'
