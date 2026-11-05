import re
from datetime import datetime, timedelta


def normalize_text(text):

    text = text.lower()

    text = re.sub(r'[^\w\s]', '', text)

    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def detect_closure(text):

    uncertain_words = [
        "maybe",
        "might",
        "possibly",
        "perhaps",
        "could"
    ]

    for word in uncertain_words:
        if word in text.split():
            return "uncertain"

    confirmed_phrases = [
        "will be closed",
        "is closed",
        "will remain closed",
        "closure confirmed",
        "the local closes"
    ]

    for phrase in confirmed_phrases:

        if phrase in text:
            return "confirmed"

    return "not_closure"
def extract_date(text, reference_date=None):

    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12
    }

    if reference_date is None:
        reference_date = datetime.now().date()

    # TODAY
    if "today" in text:
        return reference_date.strftime("%Y-%m-%d")

    # TOMORROW
    if "tomorrow" in text:
        tomorrow = reference_date + timedelta(days=1)

        return tomorrow.strftime("%Y-%m-%d")

    # Format: 12 November or 12 November 2026
    pattern1 = r'\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\b'

    # Format: November 12 or November 12 2026
    pattern2 = r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:\s+(\d{4}))?\b'

    match = re.search(pattern1, text)

    if match:

        day = int(match.group(1))
        month = months[match.group(2)]

        year = int(match.group(3)) if match.group(3) else reference_date.year

    else:

        match = re.search(pattern2, text)

        if not match:
            return None

        month = months[match.group(1)]
        day = int(match.group(2))

        year = int(match.group(3)) if match.group(3) else reference_date.year

    try:

        date = datetime(year, month, day)

        # Don't silently interpret a past date without an explicit year
        if match.group(3) is None and date.date() < reference_date:
            return None

        return date.strftime("%Y-%m-%d")

    except ValueError:

        return None
    
def process_message(message, reference_date=None):

    normalized = normalize_text(message)

    closure_status = detect_closure(normalized)

    date = extract_date(normalized, reference_date)

    result = {
        "original_message": message,
        "normalized_message": normalized,
        "closure_status": closure_status,
        "date": date
    }

    validation = validate_result(result)

    result["validation"] = validation

    return result

    # Check 3: Date validity
    try:

        datetime.strptime(result["date"], "%Y-%m-%d")

    except ValueError:

        return "invalid_date"

    # All checks passed
    return "valid"
# 4. Validate result
def validate_result(result):

    if result["closure_status"] == "not_closure":
        return "not_closure"

    if result["closure_status"] == "uncertain":
        return "review_required"

    if result["date"] is None:
        return "review_required"

    try:
        datetime.strptime(result["date"], "%Y-%m-%d")

    except ValueError:
        return "invalid_date"

    return "valid"
