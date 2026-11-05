import discord
import os

from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from message_processor import process_message

from database import (
    initialize_database,
    is_message_processed,
    save_message
)


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

    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Ignore messages from other channels
    if message.channel.id != CHANNEL_ID:
        return

    # Check if this message was already processed
    if is_message_processed(message.id):
        print("Message already processed. Skipping.")
        return

    print("\nNEW MESSAGE DETECTED")

    # Get the original message date in Algeria timezone
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

    # Save the message in SQLite
    save_message(
        message.id,
        message.channel.id,
        message.author,
        result
    )

    print("Message saved to database!")


# ==================================
# 6. START THE BOT
# ==================================

initialize_database()

client.run(TOKEN)