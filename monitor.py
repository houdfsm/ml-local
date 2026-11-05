import discord
import os

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from message_processor import process_message

from database import (
    initialize_database,
    is_message_processed,
    save_message,
    update_calendar_event,
    get_event_by_date
)

from calendar_service import create_closure_event


# ==================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==================================

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), ".env"),
    override=True
)

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID")

if TOKEN.startswith("Bot "):
    TOKEN = TOKEN[4:]

if not TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing from .env")

CHANNEL_ID = int(CHANNEL_ID)


# ==================================
# 2. CONFIGURE DISCORD INTENTS
# ==================================

intents = discord.Intents.default()

intents.guilds = True
intents.messages = True
intents.message_content = True


# ==================================
# 3. CREATE DISCORD CLIENT
# ==================================

client = discord.Client(intents=intents)


# ==================================
# 4. BOT CONNECTION EVENT
# ==================================

@client.event
async def on_ready():

    print("\n==============================")
    print("   DISCORD CLOSURE NOTIFIER")
    print("==============================")

    print(f"Connected as: {client.user}")
    print(f"Monitoring channel ID: {CHANNEL_ID}")
    print("Monitoring started...")


# ==================================
# 5. RECEIVE DISCORD MESSAGES
# ==================================

@client.event
async def on_message(message):

    print("\nMESSAGE EVENT RECEIVED")
    print("Author:", message.author)
    print("Channel:", message.channel.name)
    print("Channel ID:", message.channel.id)
    print("Content:", message.content)

    # Ignore messages sent by the bot
    if message.author == client.user:
        return

    # Monitor only the configured channel
    if message.channel.id != CHANNEL_ID:
        return

    # Avoid processing the same Discord message twice
    if is_message_processed(message.id):
        print("Message already processed. Skipping.")
        return

    print("\nNEW MESSAGE DETECTED")

    # Get the message date in Algeria's timezone
    reference_date = message.created_at.astimezone(
        ZoneInfo("Africa/Algiers")
    ).date()

    # Process the message
    result = process_message(
        message.content,
        reference_date
    )

    # Display processing results
    print("\n========== PROCESSING RESULT ==========")
    print("Original message:", result["original_message"])
    print("Normalized message:", result["normalized_message"])
    print("Closure status:", result["closure_status"])
    print("Date:", result["date"])
    print("Validation:", result["validation"])
    print("=======================================")

    # ==================================
    # 6. HANDLE CONFIRMED CLOSURES
    # ==================================

    if (
        result["closure_status"] == "confirmed"
        and result["validation"] == "valid"
    ):

        # Save the Discord message first
        save_message(
            message.id,
            message.channel.id,
            message.author,
            result
        )

        # Check whether an event already exists for this date
        existing_event = get_event_by_date(result["date"])

        if existing_event:

            # Reuse the existing calendar event ID
            update_calendar_event(
                message.id,
                existing_event["calendar_event_id"]
            )

            print("Duplicate closure detected!")
            print("Existing calendar event reused.")

        else:

            try:

                # Create a new Google Calendar event
                event_id = create_closure_event(
                    result["date"],
                    result["original_message"]
                )

                # Link the event ID to the Discord message
                update_calendar_event(
                    message.id,
                    event_id
                )

                print("New calendar event created and saved!")

            except Exception as error:

                print("Error creating calendar event:", error)

    # ==================================
    # 7. HANDLE OTHER MESSAGES
    # ==================================

    else:

        save_message(
            message.id,
            message.channel.id,
            message.author,
            result
        )

        print("Message saved. No calendar event created.")


# ==================================
# 8. INITIALIZE DATABASE AND RUN BOT
# ==================================

initialize_database()

client.run(TOKEN)