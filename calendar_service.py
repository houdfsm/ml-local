import os
import hashlib

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENTIALS_FILE = os.path.join(
    BASE_DIR,
    "credentials.json"
)

TOKEN_FILE = os.path.join(
    BASE_DIR,
    "token.json"
)

TIMEZONE_NAME = "Africa/Algiers"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

CALENDAR_ID = "primary"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


# ==================================================
# GOOGLE CALENDAR AUTHENTICATION
# ==================================================

def get_calendar_service():

    credentials = None

    if os.path.exists(TOKEN_FILE):

        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if (
        credentials
        and credentials.expired
        and credentials.refresh_token
    ):

        credentials.refresh(Request())

    elif not credentials or not credentials.valid:

        if not os.path.exists(CREDENTIALS_FILE):

            raise FileNotFoundError(
                "credentials.json was not found."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE,
            SCOPES
        )

        credentials = flow.run_local_server(
            port=0
        )

    with open(
        TOKEN_FILE,
        "w",
        encoding="utf-8"
    ) as token_file:

        token_file.write(
            credentials.to_json()
        )

    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False
    )


# ==================================================
# DATE AND TIME HELPERS
# ==================================================

def parse_date(value):

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    return date.fromisoformat(
        str(value)[:10]
    )


def parse_time(value):

    if isinstance(value, time):
        return value

    return time.fromisoformat(
        str(value)
    )


def deterministic_event_id(source_message_id):

    """
    Generate a stable Google Calendar event ID
    using the original Discord message ID.
    """

    if source_message_id is None:
        return None

    return hashlib.sha256(
        str(source_message_id).encode("utf-8")
    ).hexdigest()


# ==================================================
# BUILD CALENDAR EVENT
# ==================================================

def build_event(
    result,
    original_message,
    source_url=None
):

    start_date = parse_date(
        result["start_date"]
    )

    end_date = parse_date(
        result.get("end_date") or result["start_date"]
    )

    if end_date < start_date:

        raise ValueError(
            "The closure end date cannot be before its start date."
        )

    start_time = result.get("start_time")
    end_time = result.get("end_time")

    description = (
        "Local closure announcement.\n\n"
        "Original announcement:\n"
        f"{original_message}"
    )

    if source_url:

        description += (
            "\n\nDiscord announcement:\n"
            f"{source_url}"
        )

    event = {
        "summary": "Local Closed",
        "description": description,
        "transparency": "opaque",
    }

    # ALL-DAY EVENT

    if not start_time and not end_time:

        event["start"] = {
            "date": start_date.isoformat()
        }

        # Google Calendar uses an exclusive end date.
        event["end"] = {
            "date": (
                end_date + timedelta(days=1)
            ).isoformat()
        }

    # TIMED EVENT

    else:

        if not start_time or not end_time:

            raise ValueError(
                "Both start_time and end_time are required."
            )

        parsed_start_time = parse_time(start_time)
        parsed_end_time = parse_time(end_time)

        start_datetime = datetime.combine(
            start_date,
            parsed_start_time
        ).replace(
            tzinfo=TIMEZONE
        )

        end_datetime = datetime.combine(
            end_date,
            parsed_end_time
        ).replace(
            tzinfo=TIMEZONE
        )

        if end_datetime <= start_datetime:

            raise ValueError(
                "The closure end time must be after its start time."
            )

        event["start"] = {
            "dateTime": start_datetime.isoformat(),
            "timeZone": TIMEZONE_NAME
        }

        event["end"] = {
            "dateTime": end_datetime.isoformat(),
            "timeZone": TIMEZONE_NAME
        }

    return event


# ==================================================
# CREATE EVENT
# ==================================================

def create_closure_event(
    result,
    original_message,
    source_message_id=None,
    source_url=None
):

    service = get_calendar_service()

    event = build_event(
        result,
        original_message,
        source_url
    )

    event_id = deterministic_event_id(
        source_message_id
    )

    if event_id:
        event["id"] = event_id

    try:

        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event
        ).execute()

        print(
            "Calendar event created:",
            created_event["id"]
        )

        return created_event["id"]

    except HttpError as error:

        # If the event already exists, reuse it.
        if error.resp.status == 409 and event_id:

            updated_event = service.events().patch(
                calendarId=CALENDAR_ID,
                eventId=event_id,
                body=event
            ).execute()

            print(
                "Existing Calendar event reused:",
                event_id
            )

            return updated_event["id"]

        raise


# ==================================================
# UPDATE EVENT
# ==================================================

def update_closure_event(
    event_id,
    result,
    original_message,
    source_url=None
):

    if not event_id:

        raise ValueError(
            "Missing Calendar event ID."
        )

    service = get_calendar_service()

    event = build_event(
        result,
        original_message,
        source_url
    )

    updated_event = service.events().patch(
        calendarId=CALENDAR_ID,
        eventId=event_id,
        body=event
    ).execute()

    print(
        "Calendar event updated:",
        event_id
    )

    return updated_event["id"]


# ==================================================
# DELETE EVENT
# ==================================================

def delete_closure_event(event_id):

    if not event_id:

        raise ValueError(
            "Missing Calendar event ID."
        )

    service = get_calendar_service()

    try:

        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()

        print(
            "Calendar event deleted:",
            event_id
        )

        return True

    except HttpError as error:

        if error.resp.status in (404, 410):

            print(
                "Calendar event was already deleted."
            )

            return True

        raise


# ==================================================
# REOPEN EVENT
# ==================================================

def reopen_closure_event(
    event_id,
    reopen_date
):

    if not event_id:

        raise ValueError(
            "Missing Calendar event ID."
        )

    reopen_date = parse_date(reopen_date)

    service = get_calendar_service()

    event = service.events().get(
        calendarId=CALENDAR_ID,
        eventId=event_id
    ).execute()

    start = event.get("start", {})
    end = event.get("end", {})

    # ALL-DAY EVENT

    if "date" in start and "date" in end:

        original_start = parse_date(start["date"])
        original_end = parse_date(end["date"])

        # The closure already ended.

        if original_end <= reopen_date:

            return {
                "status": "already_ended",
                "event_id": event_id
            }

        # Reopening on or before the closure start.

        if reopen_date <= original_start:

            delete_closure_event(event_id)

            return {
                "status": "deleted",
                "event_id": event_id
            }

        # Shorten the event.
        # Google Calendar end date is exclusive.

        updated_event = service.events().patch(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body={
                "end": {
                    "date": reopen_date.isoformat()
                }
            }
        ).execute()

        return {
            "status": "shortened",
            "event_id": updated_event["id"],
            "end_date": (
                reopen_date - timedelta(days=1)
            ).isoformat()
        }

    # TIMED EVENT

    elif "dateTime" in start and "dateTime" in end:

        original_start = datetime.fromisoformat(
            start["dateTime"].replace("Z", "+00:00")
        )

        original_end = datetime.fromisoformat(
            end["dateTime"].replace("Z", "+00:00")
        )

        reopen_datetime = datetime.combine(
            reopen_date,
            time.min
        ).replace(
            tzinfo=TIMEZONE
        )

        # The closure already ended.

        if original_end <= reopen_datetime:

            return {
                "status": "already_ended",
                "event_id": event_id
            }

        # Reopening before or on closure start.

        if reopen_datetime <= original_start:

            delete_closure_event(event_id)

            return {
                "status": "deleted",
                "event_id": event_id
            }

        updated_event = service.events().patch(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body={
                "end": {
                    "dateTime": reopen_datetime.isoformat(),
                    "timeZone": TIMEZONE_NAME
                }
            }
        ).execute()

        return {
            "status": "shortened",
            "event_id": updated_event["id"],
            "end_date": (
                reopen_date - timedelta(days=1)
            ).isoformat()
        }

    else:

        raise ValueError(
            "Unsupported Google Calendar event format."
        )


# ==================================================
# MANUAL CONNECTION TEST
# ==================================================

if __name__ == "__main__":

    service = get_calendar_service()

    calendar = service.calendars().get(
        calendarId=CALENDAR_ID
    ).execute()

    print(
        "Google Calendar connected successfully."
    )

    print(
        "Calendar:",
        calendar.get("summary")
    )

    print(
        "Timezone:",
        TIMEZONE_NAME
    )