import re
import unicodedata

from datetime import date, datetime, timedelta


# ==================================================
# MONTHS
# ==================================================

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,

    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}


MONTH_PATTERN = "|".join(
    sorted(MONTHS.keys(), key=len, reverse=True)
)


# ==================================================
# TEXT NORMALIZATION
# ==================================================

def normalize_text(text):

    text = str(text).lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.replace("’", "'")

    return text


# ==================================================
# REFERENCE DATE
# ==================================================

def get_reference_date(reference_date=None):

    if reference_date is None:
        return date.today()

    if isinstance(reference_date, datetime):
        return reference_date.date()

    if isinstance(reference_date, date):
        return reference_date

    if isinstance(reference_date, str):
        return date.fromisoformat(reference_date[:10])

    raise ValueError("Invalid reference date")


def format_date(value):

    if value is None:
        return None

    return value.isoformat()


# ==================================================
# STATUS DETECTION
# ==================================================

def detect_status(text):

    text = normalize_text(text)

    # --------------------------------------------------
    # UNCERTAIN ANNOUNCEMENTS
    # --------------------------------------------------

    uncertain_words = [
        "might be closed",
        "may be closed",
        "possibly closed",
        "probably closed",
        "could be closed",
        "might close",
        "may close",
        "not sure",
        "maybe closed",
        "perhaps closed",
        "might be open",
        "could be open",
        "possibly open",
        "maybe open",
        "might reopen",
        "may reopen",
    ]

    if any(word in text for word in uncertain_words):
        return "uncertain"

    # --------------------------------------------------
    # CANCELLATION
    # --------------------------------------------------

    cancelled_words = [
        "closure cancelled",
        "closure canceled",
        "cancel the closure",
        "cancelled closure",
        "canceled closure",
        "closure is cancelled",
        "closure is canceled",
        "no longer closed",
        "closure has been cancelled",
        "closure has been canceled",
        "cancelled",
        "canceled",
    ]

    if any(word in text for word in cancelled_words):
        return "cancelled"

    # --------------------------------------------------
    # REOPENING
    # --------------------------------------------------

    reopen_words = [
        "reopen",
        "reopens",
        "reopened",
        "will reopen",
        "opening again",
        "open again",
        "back open",
        "resume operations",
        "resume business",
    ]

    if any(word in text for word in reopen_words):
        return "reopened"

    # --------------------------------------------------
    # CORRECTION
    # --------------------------------------------------

    correction_words = [
        "correction",
        "corrected",
        "instead",
        "change the date",
        "date changed",
        "new date",
        "updated date",
        "not on",
        "the correct date",
        "actually",
    ]

    if any(word in text for word in correction_words):
        return "corrected"

    # --------------------------------------------------
    # OPEN ANNOUNCEMENTS
    # --------------------------------------------------

    open_words = [
        "will be open",
        "is open",
        "will open",
        "remain open",
        "staying open",
        "open as usual",
        "normal opening",
    ]

    if any(word in text for word in open_words):
        return "reopened"

    # --------------------------------------------------
    # CONFIRMED CLOSURE
    # --------------------------------------------------

    closure_words = [
        "closed",
        "closure",
        "closing",
        "will close",
        "shut",
        "shutting",
        "not open",
        "no opening",
        "ferme",
        "fermee",
        "fermeture",
    ]

    if any(word in text for word in closure_words):
        return "confirmed"

    return "not_closure"


# ==================================================
# MONTH-BASED DATE EXTRACTION
# ==================================================

def parse_month_date(text, reference):

    results = []

    patterns = [
        rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\.?(?:\s*,?\s*(20\d{{2}}))?\b",

        rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?(?:\s*(20\d{{2}}))?\b",
    ]

    for pattern_index, pattern in enumerate(patterns):

        for match in re.finditer(pattern, text):

            try:

                if pattern_index == 0:

                    day = int(match.group(1))
                    month = MONTHS[match.group(2)]

                    year = (
                        int(match.group(3))
                        if match.group(3)
                        else None
                    )

                else:

                    month = MONTHS[match.group(1)]
                    day = int(match.group(2))

                    year = (
                        int(match.group(3))
                        if match.group(3)
                        else None
                    )

                if year is None:
                    year = reference.year

                candidate = date(
                    year,
                    month,
                    day
                )

                # If no year was specified and the date
                # has already passed, use next year.
                if candidate < reference and year == reference.year:
                    candidate = date(
                        year + 1,
                        month,
                        day
                    )

                results.append({
                    "date": candidate,
                    "start": match.start(),
                    "end": match.end(),
                    "has_year": match.group(3) is not None,
                })

            except (ValueError, TypeError):
                continue

    return results


# ==================================================
# DATE EXTRACTION
# ==================================================

def extract_date_matches(text, reference_date=None):

    reference = get_reference_date(reference_date)

    normalized = normalize_text(text)

    found = []

    # --------------------------------------------------
    # ISO DATES: 2026-11-13
    # --------------------------------------------------

    for match in re.finditer(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",
        normalized
    ):

        try:

            parsed = date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )

            found.append({
                "date": parsed,
                "start": match.start(),
                "end": match.end(),
                "has_year": True,
            })

        except ValueError:
            continue

    # --------------------------------------------------
    # NUMERIC DATES: 13/11/2026 OR 13-11-2026
    # --------------------------------------------------

    for match in re.finditer(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
        normalized
    ):

        try:

            parsed = date(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1))
            )

            found.append({
                "date": parsed,
                "start": match.start(),
                "end": match.end(),
                "has_year": True,
            })

        except ValueError:
            continue

    # --------------------------------------------------
    # MONTH-BASED DATES
    # --------------------------------------------------

    found.extend(
        parse_month_date(
            normalized,
            reference
        )
    )

    # --------------------------------------------------
    # RELATIVE DATES
    # --------------------------------------------------

    relative_patterns = {
        "the day after tomorrow": 2,
        "day after tomorrow": 2,
        "tomorrow": 1,
        "today": 0,
        "aujourd'hui": 0,
        "demain": 1,
    }

    for phrase, offset in relative_patterns.items():

        for match in re.finditer(
            rf"\b{re.escape(phrase)}\b",
            normalized
        ):

            found.append({
                "date": reference + timedelta(days=offset),
                "start": match.start(),
                "end": match.end(),
                "has_year": False,
            })

    # --------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------

    found.sort(
        key=lambda item: (
            item["start"],
            item["end"]
        )
    )

    unique = []

    seen = set()

    for item in found:

        key = (
            item["date"],
            item["start"],
            item["end"]
        )

        if key not in seen:

            seen.add(key)

            unique.append(item)

    return unique


def extract_dates(text, reference_date=None):

    matches = extract_date_matches(
        text,
        reference_date
    )

    return [
        item["date"]
        for item in matches
    ]


# ==================================================
# COMPACT DATE RANGES
# ==================================================

def extract_compact_range(text, reference_date=None):

    reference = get_reference_date(reference_date)

    normalized = normalize_text(text)

    patterns = [

        # 13-15 November
        rf"\b(\d{{1,2}})\s*(?:-|to|through|until)\s*(\d{{1,2}})\s+({MONTH_PATTERN})(?:\s*,?\s*(20\d{{2}}))?\b",

        # November 13-15
        rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})\s*(?:-|to|through|until)\s*(\d{{1,2}})(?:\s*,?\s*(20\d{{2}}))?\b",
    ]

    for index, pattern in enumerate(patterns):

        match = re.search(
            pattern,
            normalized
        )

        if not match:
            continue

        try:

            if index == 0:

                first_day = int(match.group(1))
                last_day = int(match.group(2))
                month = MONTHS[match.group(3)]

                year_text = match.group(4)

            else:

                month = MONTHS[match.group(1)]
                first_day = int(match.group(2))
                last_day = int(match.group(3))

                year_text = match.group(4)

            year = (
                int(year_text)
                if year_text
                else reference.year
            )

            start = date(
                year,
                month,
                first_day
            )

            end = date(
                year,
                month,
                last_day
            )

            if end < start:
                return None

            if not year_text and start < reference:

                start = date(
                    year + 1,
                    month,
                    first_day
                )

                end = date(
                    year + 1,
                    month,
                    last_day
                )

            return start, end

        except ValueError:
            return None

    return None


# ==================================================
# PERIOD EXTRACTION
# ==================================================

def extract_period(text, reference_date=None):

    reference = get_reference_date(reference_date)
    normalized = normalize_text(text)

    # Compact range: 13-15 November
    compact_range = extract_compact_range(
        normalized,
        reference
    )

    if compact_range:
        return compact_range

    dates = extract_dates(normalized, reference)

    # Explicit range with two dates
    if len(dates) >= 2:
        return dates[0], dates[1]

    # Duration: one week, two weeks, etc.
    duration_match = re.search(
        r"\b(?:for|during)\s+"
        r"(one|two|three|four|1|2|3|4)\s+"
        r"(day|days|week|weeks)\b",
        normalized
    )

    if duration_match:

        amount_words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
        }

        amount_text = duration_match.group(1)

        amount = (
            amount_words[amount_text]
            if amount_text in amount_words
            else int(amount_text)
        )

        unit = duration_match.group(2)

        starting_dates = extract_dates(
            normalized[duration_match.end():],
            reference
        )

        start = (
            starting_dates[0]
            if starting_dates
            else reference
        )

        days = amount * 7 if "week" in unit else amount

        return (
            start,
            start + timedelta(days=days - 1)
        )

    # Single explicit date
    if len(dates) == 1:
        return dates[0], dates[0]

    # Next week
    if "next week" in normalized:

        start = reference + timedelta(
            days=7 - reference.weekday()
        )

        return start, start + timedelta(days=6)

    # This week
    if "this week" in normalized or "for the week" in normalized:

        start = reference - timedelta(
            days=reference.weekday()
        )

        return start, start + timedelta(days=6)

    # Next weekend
    if "next weekend" in normalized:

        days_until_saturday = (
            5 - reference.weekday()
        ) % 7

        if days_until_saturday == 0:
            days_until_saturday = 7

        start = reference + timedelta(
            days=days_until_saturday + 7
        )

        return start, start + timedelta(days=1)

    # This weekend
    if "this weekend" in normalized:

        days_until_saturday = (
            5 - reference.weekday()
        ) % 7

        start = reference + timedelta(
            days=days_until_saturday
        )

        return start, start + timedelta(days=1)

    return None, None

# ==================================================
# TIME CONVERSION
# ==================================================

def convert_time(hour, minute, suffix=None):

    hour = int(hour)

    minute = int(minute)

    if minute < 0 or minute > 59:
        raise ValueError("Invalid minutes")

    if suffix:

        suffix = suffix.lower()

        if hour < 1 or hour > 12:
            raise ValueError("Invalid 12-hour time")

        if suffix == "pm" and hour != 12:
            hour += 12

        elif suffix == "am" and hour == 12:
            hour = 0

    elif hour < 0 or hour > 23:

        raise ValueError("Invalid 24-hour time")

    return f"{hour:02d}:{minute:02d}"


# ==================================================
# TIME EXTRACTION
# ==================================================

def extract_times(text):

    normalized = normalize_text(text)

    pattern = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)?"
        r"\s*(?:to|until|through|[-–])\s*"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)?"
        r"\b",
        re.IGNORECASE
    )

    for match in pattern.finditer(normalized):

        # Do not interpret date ranges as time ranges.
        # A time range must contain a colon or AM/PM.
        has_time_marker = (
            ":" in match.group(0)
            or match.group(3) is not None
            or match.group(6) is not None
        )

        if not has_time_marker:
            continue

        try:

            first_hour = match.group(1)

            first_minute = match.group(2) or "00"

            first_suffix = match.group(3)

            second_hour = match.group(4)

            second_minute = match.group(5) or "00"

            second_suffix = match.group(6)

            # Infer AM/PM when only one side specifies it.
            if first_suffix is None and second_suffix is not None:
                first_suffix = second_suffix

            if second_suffix is None and first_suffix is not None:
                second_suffix = first_suffix

            start_time = convert_time(
                first_hour,
                first_minute,
                first_suffix
            )

            end_time = convert_time(
                second_hour,
                second_minute,
                second_suffix
            )

            if end_time <= start_time:
                continue

            return start_time, end_time

        except ValueError:
            continue

    return None, None


# ==================================================
# CORRECTION DATE EXTRACTION
# ==================================================

def extract_correction_dates(text, reference_date=None):

    normalized = normalize_text(text)

    matches = extract_date_matches(
        normalized,
        reference_date
    )

    if len(matches) < 2:
        return None, None

    # Example:
    # "The closure is on 15 November instead of 13 November."
    # New date comes before "instead of".
    instead_match = re.search(
        r"\binstead of\b",
        normalized
    )

    if instead_match:

        before = [
            item for item in matches
            if item["end"] <= instead_match.start()
        ]

        after = [
            item for item in matches
            if item["start"] >= instead_match.end()
        ]

        if before and after:

            new_date = before[-1]["date"]

            previous_date = after[0]["date"]

            return previous_date, new_date

    # Example:
    # "Change from 13 November to 15 November."
    # First date is old, second date is new.
    from_match = re.search(
        r"\bfrom\b",
        normalized
    )

    to_match = re.search(
        r"\bto\b",
        normalized
    )

    if from_match and to_match:

        previous_candidates = [
            item for item in matches
            if item["start"] >= from_match.end()
            and item["end"] <= to_match.start()
        ]

        new_candidates = [
            item for item in matches
            if item["start"] >= to_match.end()
        ]

        if previous_candidates and new_candidates:

            return (
                previous_candidates[0]["date"],
                new_candidates[0]["date"]
            )

    # Default: first date is old, second is new.
    return (
        matches[0]["date"],
        matches[1]["date"]
    )


# ==================================================
# MAIN MESSAGE PROCESSOR
# ==================================================

def process_message(message, reference_date=None):

    original_message = str(message)

    normalized = normalize_text(
        original_message
    )

    reference = get_reference_date(
        reference_date
    )

    status = detect_status(
        normalized
    )

    result = {
        "original_message": original_message,
        "normalized_message": normalized,
        "closure_status": status,

        "start_date": None,
        "end_date": None,

        "start_time": None,
        "end_time": None,

        "date": None,

        "previous_date": None,
        "previous_start_date": None,

        "validation": "invalid",
    }

    # --------------------------------------------------
    # UNRELATED MESSAGE
    # --------------------------------------------------

    if status == "not_closure":

        result["validation"] = "not_closure"

        return result

    # --------------------------------------------------
    # UNCERTAIN MESSAGE
    # --------------------------------------------------

    if status == "uncertain":

        result["validation"] = "review_required"

        return result

    # --------------------------------------------------
    # CORRECTION
    # --------------------------------------------------

    if status == "corrected":

        previous_date, new_date = extract_correction_dates(
            normalized,
            reference
        )

        if previous_date is None or new_date is None:

            result["validation"] = "review_required"

            return result

        start_date = new_date

        end_date = new_date

        result["previous_date"] = format_date(
            previous_date
        )

        result["previous_start_date"] = format_date(
            previous_date
        )

    else:

        start_date, end_date = extract_period(
            normalized,
            reference
        )

    # --------------------------------------------------
    # REOPENING / CANCELLATION / CLOSURE
    # --------------------------------------------------

    if start_date is None or end_date is None:

        result["validation"] = "review_required"

        return result

    if end_date < start_date:

        result["validation"] = "review_required"

        return result

    # --------------------------------------------------
    # TIME EXTRACTION
    # --------------------------------------------------

    start_time, end_time = extract_times(
        normalized
    )

    # A time range must contain both values.
    if (start_time is None) != (end_time is None):

        result["validation"] = "review_required"

        return result

    # --------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------

    result["start_date"] = format_date(
        start_date
    )

    result["end_date"] = format_date(
        end_date
    )

    result["date"] = format_date(
        start_date
    )

    result["start_time"] = start_time

    result["end_time"] = end_time

    result["validation"] = "valid"

    return result


# ==================================================
# TESTS
# ==================================================

if __name__ == "__main__":

    tests = [

        "The local will be closed tomorrow.",

        "The local will be closed on 13 November 2026.",

        "The local will be closed from 13 November 2026 to 15 November 2026.",

        "The local will be closed from 13-15 November 2026.",

        "The local will be closed for one week starting 7 December 2026.",

        "The local will be closed for two weeks starting 7 December 2026.",

        "The local will be closed next week.",

        "The local will be closed from 8 AM to 2 PM tomorrow.",

        "The local will be closed from 08:00 to 14:00 tomorrow.",

        "The local might be closed soon.",

        "The local will be open tomorrow.",

        "The local will reopen tomorrow.",

        "Correction: the closure is on 15 November 2026 instead of 13 November 2026.",

        "Correction: change the closure from 13 November 2026 to 15 November 2026.",

    ]

    reference = date(2026, 11, 5)

    for test in tests:

        print("\n" + "=" * 60)

        print("MESSAGE:", test)

        print(
            "RESULT:",
            process_message(
                test,
                reference
            )
        )