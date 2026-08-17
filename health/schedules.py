"""
Turning a written schedule into times of day.

A prescription says "1-0-1", "1 Morning, 1 Night", "BD" or "twice daily".
None of those can drive a reminder: an alert needs a clock time and a
quantity. This module converts the words into structured slots, and is
honest about when it could not.

When `confident` comes back False the medication is flagged for the
patient to fix by hand. Nothing here guesses -- a schedule we cannot read
produces no dose times at all, because a reminder at the wrong hour is
worse than no reminder.
"""
import re
from decimal import Decimal, InvalidOperation

MORNING = 'MORNING'
AFTERNOON = 'AFTERNOON'
EVENING = 'EVENING'
NIGHT = 'NIGHT'

SLOT_ORDER = [MORNING, AFTERNOON, EVENING, NIGHT]

# The words a prescription might use for each slot.
SLOT_WORDS = {
    MORNING: ('morning', 'morn', 'breakfast', 'am', 'sunrise', 'om'),
    AFTERNOON: ('afternoon', 'noon', 'lunch', 'midday', 'mid-day'),
    EVENING: ('evening', 'eve', 'tea'),
    NIGHT: ('night', 'bedtime', 'bed time', 'dinner', 'supper', 'hs', 'on', 'pm'),
}

# Latin abbreviations still in everyday use on Indian prescriptions.
ABBREVIATIONS = {
    'od': [MORNING],
    'qd': [MORNING],
    'om': [MORNING],
    'bd': [MORNING, NIGHT],
    'bid': [MORNING, NIGHT],
    'tds': [MORNING, AFTERNOON, NIGHT],
    'tid': [MORNING, AFTERNOON, NIGHT],
    'qid': [MORNING, AFTERNOON, EVENING, NIGHT],
    'qds': [MORNING, AFTERNOON, EVENING, NIGHT],
    'hs': [NIGHT],
    'nocte': [NIGHT],
}

# Plain-English counts.
COUNT_WORDS = {
    'once': 1, 'one': 1, 'single': 1,
    'twice': 2, 'two': 2, 'bd': 2,
    'thrice': 3, 'three': 3,
    'four': 4, 'fourth': 4,
}

# How many doses map onto which slots, when all we know is "N times a day".
BY_COUNT = {
    1: [MORNING],
    2: [MORNING, NIGHT],
    3: [MORNING, AFTERNOON, NIGHT],
    4: [MORNING, AFTERNOON, EVENING, NIGHT],
}

# Phrases that describe a schedule we deliberately do not automate.
UNSCHEDULABLE = ('sos', 'as needed', 'if required', 'prn', 'when necessary',
                 'alternate day', 'weekly', 'once a week', 'every other day')


class ParsedSchedule:
    """
    The result of reading a schedule string.

    `slots` maps a slot name to the quantity taken then, e.g.
    {'MORNING': Decimal('1'), 'NIGHT': Decimal('1')}.
    """

    def __init__(self, slots=None, confident=False, note=''):
        self.slots = slots or {}
        self.confident = confident
        self.note = note

    @property
    def daily_quantity(self):
        return sum(self.slots.values(), Decimal('0'))

    @property
    def doses_per_day(self):
        return len(self.slots)

    def __repr__(self):                                     # pragma: no cover
        return f"<ParsedSchedule {self.slots} confident={self.confident}>"


def _to_qty(raw, default=Decimal('1')):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return default
    # A schedule of 0 means "not at this time", and nobody takes 20 tablets
    # in one go -- treat anything wilder than that as a misread.
    if value <= 0 or value > 20:
        return Decimal('0') if value <= 0 else default
    return value


def parse_schedule(text):
    """
    Read a written schedule and return a `ParsedSchedule`.

    Recognised, roughly in the order tried:
      1-0-1 / 1-1-1 / 0.5-0-0.5      dash notation (3 or 4 parts)
      1 Morning, 1 Night             counted slot words
      Morning and night              slot words with no count (assumes 1)
      BD / TDS / OD / HS             Latin abbreviations
      twice daily / 3 times a day    plain English counts
    """
    raw = (text or '').strip()
    if not raw:
        return ParsedSchedule(note='No schedule given.')

    low = raw.lower()

    for phrase in UNSCHEDULABLE:
        if phrase in low:
            return ParsedSchedule(
                note='This is taken as needed rather than at fixed times, '
                     'so no reminders were set.')

    # Most explicit first: dash notation, then numbers attached to slot words.
    for parser in (_parse_dash, _parse_counted_words):
        result = parser(low)
        if result is not None:
            return result

    # Otherwise reconcile two weaker signals. "Once daily, at night" states a
    # count (1) and names a slot (night); the named slot is the better answer.
    # "BD after dinner" states a count of 2 but names only one slot, so the
    # count wins -- a named slot cannot be trusted to be the complete list
    # when it accounts for fewer doses than the count does.
    named = _named_slots(low)
    counted = _count_based(low)

    if counted and named:
        chosen = named if len(named) == len(counted) else counted
        return ParsedSchedule({slot: Decimal('1') for slot in chosen}, confident=True)
    if counted:
        return ParsedSchedule({slot: Decimal('1') for slot in counted}, confident=True)
    if named:
        return ParsedSchedule({slot: Decimal('1') for slot in named}, confident=True)

    return ParsedSchedule(
        note="We could not work out the times from this. Please set them yourself.")


def _parse_dash(low):
    """1-0-1, 1-1-1, 0.5-0-0.5, 1-0-1-1."""
    match = re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*[-–]\s*'
                      r'(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?', low)
    if not match:
        return None

    parts = [p for p in match.groups() if p is not None]
    if len(parts) == 3:
        order = [MORNING, AFTERNOON, NIGHT]
    else:
        order = [MORNING, AFTERNOON, EVENING, NIGHT]

    slots = {}
    for slot, part in zip(order, parts):
        qty = _to_qty(part)
        if qty > 0:
            slots[slot] = qty
    if not slots:
        return ParsedSchedule(note='That schedule reads as no doses at all.')
    return ParsedSchedule(slots, confident=True)


def _parse_counted_words(low):
    """1 Morning, 1 Night  /  2 tablets at night  /  1 tab morning & evening."""
    slots = {}
    for slot, words in SLOT_WORDS.items():
        for word in words:
            # Skip the two-letter ones here -- "on" and "am" match far too
            # much ordinary text. They are handled as abbreviations instead.
            if len(word) <= 2:
                continue
            pattern = rf'(\d+(?:\.\d+)?)\s*(?:tabs?|tablets?|caps?|capsules?|ml|drops?|units?)?\s*(?:at|in|the|every)?\s*{word}'
            match = re.search(pattern, low)
            if match:
                qty = _to_qty(match.group(1))
                if qty > 0:
                    slots[slot] = qty
                break
    if not slots:
        return None

    # "1 tab morning & evening" puts a number in front of one slot only.
    # Any other slot named in the same line gets the same treatment rather
    # than being dropped -- assume one unit where no number was given.
    for slot in _named_slots(low):
        slots.setdefault(slot, Decimal('1'))
    return ParsedSchedule(slots, confident=True)


def _count_based(low):
    """
    The slots implied by a dose count, or None.

    Covers Latin abbreviations (BD, TDS, OD, HS) and plain English
    ("twice daily", "3 times a day"). It says nothing about *which* times of
    day were named -- that is `_named_slots`' job.
    """
    for abbr, order in ABBREVIATIONS.items():
        if re.search(rf'\b{abbr}\b', low):
            return list(order)

    # "daily" is d-a-i-l-y, so matching a bare "day" would miss it.
    match = re.search(r'(\d+|once|twice|thrice|one|two|three|four)\s*'
                      r'(?:times?|x)?\s*(?:a|per|every)?\s*(?:daily|day)\b', low)
    if not match:
        return None
    token = match.group(1)
    count = int(token) if token.isdigit() else COUNT_WORDS.get(token)
    if not count or count not in BY_COUNT:
        return None
    return list(BY_COUNT[count])


def _named_slots(low):
    """The times of day actually named in the text, in daily order."""
    found = []
    for slot in SLOT_ORDER:
        for word in SLOT_WORDS[slot]:
            # Two-letter words like "on", "am" and "pm" match far too much
            # ordinary text to be trusted here.
            if len(word) <= 2:
                continue
            if re.search(rf'\b{re.escape(word)}\b', low):
                found.append(slot)
                break
    return found


# --------------------------------------------------------------------------
# Duration -- how long the course runs, which is what stock is counted against
# --------------------------------------------------------------------------

def parse_duration_days(text):
    """
    Read '5 days', 'for 2 weeks', '1 month', '10/7' and return whole days.

    Returns None when there is nothing to read, rather than guessing a
    course length that would produce a wrong restock date.
    """
    low = (text or '').strip().lower()
    if not low:
        return None

    # '10/7' is prescription shorthand for 10 days.
    match = re.search(r'\b(\d{1,3})\s*/\s*7\b', low)
    if match:
        return int(match.group(1))

    match = re.search(r'(\d+(?:\.\d+)?)\s*(day|week|month)', low)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        multiplier = {'day': 1, 'week': 7, 'month': 30}[unit]
        days = int(round(value * multiplier))
        return days if 0 < days <= 730 else None

    if 'continuous' in low or 'long term' in low or 'lifelong' in low:
        return None
    return None
