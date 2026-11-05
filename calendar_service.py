import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta

# Allow the application to create and manage calendar events
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_calendar_service():

    credentials = None

    # Check whether we already have an authorization token
    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE, SCOPES
        )

    # Authenticate if necessary
    if not credentials or not credentials.valid:

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )

            credentials = flow.run_local_server(port=0)

        # Save the authorization token
        with open(TOKEN_FILE, "w") as token:
            token.write(credentials.to_json())

    # Connect to Google Calendar API
    service = build("calendar", "v3", credentials=credentials)

    return service

def create_closure_event(closure_date, original_message):

    service = get_calendar_service()

    # Calculate the day after the closure
    end_date = (
        datetime.strptime(closure_date, "%Y-%m-%d")
        + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    event = {
        "summary": "Local Closed",
        "description": original_message,

        "start": {
            "date": closure_date
        },

        "end": {
            "date": end_date
        }
    }

    created_event = service.events().insert(
        calendarId="primary",
        body=event
    ).execute()

    print("Closure event created!")
    print("Event ID:", created_event["id"])

    return created_event["id"]

def create_closure_event(closure_date, original_message):

    service = get_calendar_service()

    event = {
        "summary": "Local Closed",
        "description": original_message,
        "start": {
            "date": closure_date
        },
       "end": {
    "date": (
        datetime.strptime(closure_date, "%Y-%m-%d")
        + timedelta(days=1)
    ).strftime("%Y-%m-%d")
}
    }

    created_event = service.events().insert(
        calendarId="primary",
        body=event
    ).execute()

    print("Closure event created!")
    print("Event ID:", created_event["id"])

    return created_event["id"]


if __name__ == "__main__":

    event_id = create_closure_event(
        "2026-11-12",
        "The local will be closed on 12 November."
    )

    print("Saved event ID:", event_id)
        