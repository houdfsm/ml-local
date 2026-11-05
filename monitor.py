import os
import asyncio
import logging

import discord

from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from message_processor import process_message

from database import (
    initialize_database,
    save_message,
    get_message,
    get_event_by_date,
    get_events_covering_date,
    update_event_data_by_id,
    update_calendar_event,
    clear_event_id,
    begin_operation,
    mark_message_completed,
    mark_message_failed,
    mark_message_permanently_failed,
    get_pending_messages,
    enqueue_notification,
    complete_message_with_notification,
    fail_message_with_notification,
    get_pending_notifications,
    mark_notification_sent,
    mark_notification_failed,
)

from calendar_service import (
    create_closure_event,
    update_closure_event,
    delete_closure_event,
    reopen_closure_event,
)


# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(
    os.path.join(BASE_DIR, ".env"),
    override=True
)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()

NOTIFICATION_CHANNEL_ID = os.getenv(
    "NOTIFICATION_CHANNEL_ID", ""
).strip()

TIMEZONE_NAME = "Africa/Algiers"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

MAX_CALENDAR_ATTEMPTS = 3
RETRY_DELAYS = [2, 5, 10]

NOTIFICATION_CHECK_INTERVAL = 30
RECOVERY_CHECK_INTERVAL = 60


# ==================================================
# LOGGING
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("closure_notifier")


# ==================================================
# VALIDATE CONFIGURATION
# ==================================================

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from .env")

if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing from .env")

if not NOTIFICATION_CHANNEL_ID:
    raise ValueError(
        "NOTIFICATION_CHANNEL_ID is missing from .env"
    )

try:
    CHANNEL_ID = int(CHANNEL_ID)
    NOTIFICATION_CHANNEL_ID = int(
        NOTIFICATION_CHANNEL_ID
    )

except ValueError:
    raise ValueError(
        "Discord channel IDs must be numbers."
    )


# ==================================================
# DISCORD CLIENT
# ==================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

client = discord.Client(intents=intents)

background_tasks_started = False

# Prevent simultaneous processing of the same message.
message_locks = {}


# ==================================================
# DATABASE CLAIM HELPER
# ==================================================

def claim_message(message_id):

    claimed = begin_operation(message_id)

    if not claimed:

        logger.info(
            "Message %s is already being processed.",
            message_id
        )

        return False

    return True


# ==================================================
# CALENDAR RETRY SYSTEM
# ==================================================

async def retry_calendar_operation(function, *args):

    for attempt in range(MAX_CALENDAR_ATTEMPTS):

        try:

            return await asyncio.to_thread(
                function,
                *args
            )

        except HttpError as error:

            status = getattr(
                error.resp,
                "status",
                None
            )

            if status not in (
                429, 500, 502, 503, 504
            ):
                raise

            if attempt == MAX_CALENDAR_ATTEMPTS - 1:
                raise

            delay = RETRY_DELAYS[attempt]

            logger.warning(
                "Calendar API temporary error %s. "
                "Retrying in %s seconds.",
                status,
                delay
            )

        except (TimeoutError, ConnectionError):

            if attempt == MAX_CALENDAR_ATTEMPTS - 1:
                raise

            delay = RETRY_DELAYS[attempt]

            logger.warning(
                "Calendar connection problem. "
                "Retrying in %s seconds.",
                delay
            )

        except Exception as error:

            if attempt == MAX_CALENDAR_ATTEMPTS - 1:
                raise

            error_name = type(error).__name__.lower()

            temporary_error = (
                "timeout" in error_name
                or "connection" in error_name
            )

            if not temporary_error:
                raise

            delay = RETRY_DELAYS[attempt]

            logger.warning(
                "Temporary error. Retrying in %s seconds.",
                delay
            )

        await asyncio.sleep(delay)


# ==================================================
# NOTIFICATION HELPERS
# ==================================================

def queue_notification(
    message_id,
    title,
    description
):

    enqueue_notification(
        message_id,
        title,
        description
    )


def complete_with_notification(
    message_id,
    title,
    description
):

    complete_message_with_notification(
        message_id,
        title,
        description
    )


def notify_review_required(message_id, reason):

    complete_with_notification(
        message_id,
        "Announcement requires review",
        (
            "I detected a possible closure announcement, "
            "but I could not safely confirm its details.\n\n"
            f"Reason: {reason}\n\n"
            "No Google Calendar event was created."
        )
    )


# ==================================================
# DATE HELPERS
# ==================================================

def message_reference_date(message):

    timestamp = message.created_at.astimezone(
        TIMEZONE
    )

    return timestamp.date()


def find_existing_event(start_date):

    if not start_date:
        return None

    return get_event_by_date(start_date)


def find_closure_records(target_date):

    if not target_date:
        return []

    records = get_events_covering_date(
        target_date
    )

    unique_records = {}

    for record in records:

        event_id = record.get(
            "calendar_event_id"
        )

        if event_id:
            unique_records[event_id] = record

    return list(unique_records.values())


# ==================================================
# PROCESS DISCORD MESSAGE
# ==================================================

async def _handle_message(
    message,
    edited=False,
    recovery=False
):

    if message.author.bot:
        return

    if message.channel.id != CHANNEL_ID:
        return

    message_id = str(message.id)

    original_message = message.content.strip()

    if not original_message:
        return

    logger.info(
        "Processing message %s",
        message_id
    )

    previous_record = get_message(message_id)

    if (
        previous_record
        and previous_record.get("sync_status") == "completed"
        and (not edited or recovery)
    ):

        logger.info(
            "Message already processed: %s",
            message_id
        )

        return

    save_message(
        message_id,
        original_message,
        channel_id=message.channel.id,
        author=str(message.author)
    )

    reference_date = message_reference_date(
        message
    )

    try:

        result = process_message(
            original_message,
            reference_date
        )

    except Exception as error:

        logger.exception(
            "Message processing failed."
        )

        permanent = mark_message_failed(
            message_id,
            error
        )

        if permanent:

            fail_message_with_notification(
                message_id,
                error,
                "Message processing failed",
                (
                    "The announcement could not be processed. "
                    "Please check the application logs."
                )
            )

        return

    status = result["closure_status"]
    validation = result["validation"]

    start_date = result.get("start_date")
    end_date = result.get("end_date")

    logger.info(
        "Message status: %s | Validation: %s",
        status,
        validation
    )

    save_message(
        message_id,
        original_message,
        start_date,
        end_date,
        result.get("start_time"),
        result.get("end_time"),
        status,
        channel_id=message.channel.id,
        author=str(message.author),
        normalized_message=result.get("normalized_message"),
        closure_status=status,
        validation=validation
    )

    # ==================================================
    # NOT A CLOSURE
    # ==================================================

    if status == "not_closure":

        if edited and previous_record:

            old_event_id = previous_record.get(
                "calendar_event_id"
            )

            if old_event_id:

                if not claim_message(message_id):
                    return

                try:

                    await retry_calendar_operation(
                        delete_closure_event,
                        old_event_id
                    )

                    clear_event_id(message_id)

                    complete_with_notification(
                        message_id,
                        "Closure announcement removed",
                        (
                            "An edited Discord announcement is "
                            "no longer a closure announcement. "
                            "Its Calendar event was deleted."
                        )
                    )

                except Exception as error:

                    permanent = mark_message_failed(
                        message_id,
                        error
                    )

                    if permanent:

                        fail_message_with_notification(
                            message_id,
                            error,
                            "Calendar deletion failed",
                            (
                                "The old Calendar event could not "
                                "be removed. Please check the "
                                "application logs."
                            )
                        )

                    logger.exception(
                        "Could not remove old Calendar event."
                    )

                return

        mark_message_completed(message_id)

        logger.info(
            "Unrelated message ignored."
        )

        return

    # ==================================================
    # INVALID OR UNCERTAIN ANNOUNCEMENT
    # ==================================================

    if validation != "valid":

        notify_review_required(
            message_id,
            (
                "The announcement is ambiguous or its "
                "date/time could not be safely determined."
            )
        )

        logger.warning(
            "Review required for message %s",
            message_id
        )

        return

    # ==================================================
    # CANCELLATION
    # ==================================================

    if status == "cancelled":

        existing_event = None
        old_record = None

        if previous_record:

            existing_event = previous_record.get(
                "calendar_event_id"
            )

        if not existing_event:

            old_record = find_existing_event(
                start_date
            )

            if old_record:

                existing_event = old_record.get(
                    "calendar_event_id"
                )

        if not existing_event:

            notify_review_required(
                message_id,
                "The closure to cancel could not be identified."
            )

            return

        if not claim_message(message_id):
            return

        update_calendar_event(
            message_id,
            existing_event
        )

        try:

            await retry_calendar_operation(
                delete_closure_event,
                existing_event
            )

            if old_record:

                clear_event_id(
                    old_record["message_id"]
                )

            clear_event_id(message_id)

            complete_with_notification(
                message_id,
                "Closure cancelled",
                (
                    "The closure was successfully cancelled.\n"
                    "The corresponding Google Calendar event "
                    "was deleted."
                )
            )

            logger.info(
                "Closure cancellation completed."
            )

        except Exception as error:

            permanent = mark_message_failed(
                message_id,
                error
            )

            if permanent:

                fail_message_with_notification(
                    message_id,
                    error,
                    "Calendar cancellation failed",
                    (
                        "The closure could not be cancelled "
                        "after several attempts. "
                        "Please check the application logs."
                    )
                )

            logger.exception(
                "Cancellation failed."
            )

        return

    # ==================================================
    # CORRECTION
    # ==================================================

    if status == "corrected":

        previous_date = (
            result.get("previous_start_date")
            or result.get("previous_date")
        )

        if not previous_date:

            notify_review_required(
                message_id,
                "The previous closure date was not identified."
            )

            return

        old_record = find_existing_event(
            previous_date
        )

        if not old_record:

            notify_review_required(
                message_id,
                (
                    "No existing Calendar event was found "
                    "for the date being corrected."
                )
            )

            return

        event_id = old_record.get(
            "calendar_event_id"
        )

        if not event_id:

            notify_review_required(
                message_id,
                "The existing Calendar event has no saved ID."
            )

            return

        if not claim_message(message_id):
            return

        update_calendar_event(
            message_id,
            event_id
        )

        try:

            await retry_calendar_operation(
                update_closure_event,
                event_id,
                result,
                original_message
            )

            update_event_data_by_id(
                event_id,
                start_date,
                end_date
            )

            complete_with_notification(
                message_id,
                "Closure corrected",
                (
                    "The existing Google Calendar event "
                    "was updated with the corrected date."
                )
            )

            logger.info(
                "Closure correction completed."
            )

        except Exception as error:

            permanent = mark_message_failed(
                message_id,
                error
            )

            if permanent:

                fail_message_with_notification(
                    message_id,
                    error,
                    "Calendar correction failed",
                    (
                        "The corrected closure could not be "
                        "synchronized. Please check the "
                        "application logs."
                    )
                )

            logger.exception(
                "Correction failed."
            )

        return

    # ==================================================
    # REOPENING
    # ==================================================

    if status == "reopened":

        reopen_date = datetime.fromisoformat(
            start_date
        ).date()

        previous_day = (
            reopen_date - timedelta(days=1)
        ).isoformat()

        matching_records = find_closure_records(
            previous_day
        )

        if not matching_records:

            matching_records = find_closure_records(
                start_date
            )

        existing_event = None
        old_record = None

        if previous_record:

            existing_event = previous_record.get(
                "calendar_event_id"
            )

        if not existing_event:

            if len(matching_records) == 1:

                old_record = matching_records[0]

                existing_event = old_record.get(
                    "calendar_event_id"
                )

            elif len(matching_records) > 1:

                notify_review_required(
                    message_id,
                    (
                        "Multiple closure events were found "
                        "around the reopening date. "
                        "Manual identification is required."
                    )
                )

                return

        if not existing_event:

            notify_review_required(
                message_id,
                "No existing closure event was found to reopen."
            )

            return

        original_start = None

        if old_record:

            original_start = old_record.get(
                "start_date"
            )

        if not original_start and previous_record:

            original_start = previous_record.get(
                "start_date"
            )

        if not original_start:

            notify_review_required(
                message_id,
                "The original closure start date is missing."
            )

            return

        if not claim_message(message_id):
            return

        try:

            reopen_result = await retry_calendar_operation(
                reopen_closure_event,
                existing_event,
                start_date
            )

            reopen_status = reopen_result["status"]

            if reopen_status == "deleted":

                if old_record:

                    clear_event_id(
                        old_record["message_id"]
                    )

                clear_event_id(message_id)

                description = (
                    "The closure was completely removed "
                    "because the local reopened before "
                    "or on its original closure date."
                )

            elif reopen_status == "shortened":

                update_event_data_by_id(
                    existing_event,
                    original_start,
                    reopen_result["end_date"]
                )

                description = (
                    "The closure was shortened.\n"
                    f"Last closed day: {reopen_result['end_date']}\n"
                    f"Reopening date: {start_date}"
                )

            else:

                description = (
                    "The closure had already ended before "
                    f"the reopening date ({start_date}). "
                    "No Calendar changes were necessary."
                )

            complete_with_notification(
                message_id,
                "Local reopening processed",
                description
            )

            logger.info(
                "Reopening completed: %s",
                reopen_status
            )

        except Exception as error:

            permanent = mark_message_failed(
                message_id,
                error
            )

            if permanent:

                fail_message_with_notification(
                    message_id,
                    error,
                    "Reopening synchronization failed",
                    (
                        "The reopening could not be synchronized. "
                        "Please check the application logs."
                    )
                )

            logger.exception(
                "Reopening failed."
            )

        return

    # ==================================================
    # CONFIRMED CLOSURE
    # ==================================================

    if status == "confirmed":

        if not claim_message(message_id):
            return

        try:

            existing_record = None
            event_id = None

            if previous_record:

                event_id = previous_record.get(
                    "calendar_event_id"
                )

            if not event_id:

                existing_record = find_existing_event(
                    start_date
                )

                if existing_record:

                    event_id = existing_record.get(
                        "calendar_event_id"
                    )

            if event_id:

                update_calendar_event(
                    message_id,
                    event_id
                )

                await retry_calendar_operation(
                    update_closure_event,
                    event_id,
                    result,
                    original_message
                )

                update_event_data_by_id(
                    event_id,
                    start_date,
                    end_date
                )

                logger.info(
                    "Existing closure event updated."
                )

            else:

                event_id = await retry_calendar_operation(
                    create_closure_event,
                    result,
                    original_message,
                    message_id
                )

                update_calendar_event(
                    message_id,
                    event_id
                )

                logger.info(
                    "New closure event created."
                )

            complete_with_notification(
                message_id,
                "Closure synchronized",
                (
                    "A confirmed closure announcement was "
                    "successfully synchronized with Google Calendar.\n\n"
                    f"Start: {start_date}\n"
                    f"End: {end_date}"
                )
            )

        except Exception as error:

            permanent = mark_message_failed(
                message_id,
                error
            )

            if permanent:

                fail_message_with_notification(
                    message_id,
                    error,
                    "Calendar synchronization failed",
                    (
                        "The closure could not be synchronized "
                        "after several attempts. "
                        "Please check the application logs."
                    )
                )

            logger.exception(
                "Closure synchronization failed."
            )

        return

    # ==================================================
    # UNKNOWN STATUS
    # ==================================================

    notify_review_required(
        message_id,
        "The announcement type was not recognized."
    )


# ==================================================
# MESSAGE LOCK WRAPPER
# ==================================================

async def handle_message(
    message,
    edited=False,
    recovery=False
):

    message_id = str(message.id)

    if message_id not in message_locks:

        message_locks[message_id] = asyncio.Lock()

    lock = message_locks[message_id]

    async with lock:

        await _handle_message(
            message,
            edited=edited,
            recovery=recovery
        )


# ==================================================
# DISCORD MESSAGE EVENTS
# ==================================================

@client.event
async def on_message(message):

    await handle_message(message)


@client.event
async def on_message_edit(before, after):

    if before.content == after.content:
        return

    logger.info(
        "Message edited: %s",
        after.id
    )

    await handle_message(
        after,
        edited=True
    )


# ==================================================
# NOTIFICATION WORKER
# ==================================================

async def notification_worker():

    await client.wait_until_ready()

    logger.info(
        "Notification worker started."
    )

    while not client.is_closed():

        try:

            notifications = get_pending_notifications()

            channel = client.get_channel(
                NOTIFICATION_CHANNEL_ID
            )

            if channel is None:

                channel = await client.fetch_channel(
                    NOTIFICATION_CHANNEL_ID
                )

            for notification in notifications:

                try:

                    embed = discord.Embed(
                        title=notification["title"],
                        description=notification["description"],
                        color=discord.Color.blue(),
                        timestamp=datetime.now(timezone.utc)
                    )

                    await channel.send(
                        embed=embed
                    )

                    mark_notification_sent(
                        notification["id"]
                    )

                    logger.info(
                        "Notification sent: %s",
                        notification["id"]
                    )

                except Exception as error:

                    mark_notification_failed(
                        notification["id"],
                        error
                    )

                    logger.exception(
                        "Notification sending failed."
                    )

        except Exception:

            logger.exception(
                "Notification worker encountered an error."
            )

        await asyncio.sleep(
            NOTIFICATION_CHECK_INTERVAL
        )


# ==================================================
# RECOVERY WORKER
# ==================================================

async def recovery_worker():

    await client.wait_until_ready()

    logger.info(
        "Recovery worker started."
    )

    while not client.is_closed():

        try:

            pending_messages = get_pending_messages()

            if pending_messages:

                logger.info(
                    "Pending messages: %s",
                    len(pending_messages)
                )

            channel = client.get_channel(
                CHANNEL_ID
            )

            if channel is None:

                channel = await client.fetch_channel(
                    CHANNEL_ID
                )

            for record in pending_messages:

                message_id = int(
                    record["message_id"]
                )

                try:

                    message = await channel.fetch_message(
                        message_id
                    )

                    await handle_message(
                        message,
                        edited=True,
                        recovery=True
                    )

                except discord.NotFound:

                    logger.error(
                        "Pending Discord message %s no longer exists.",
                        message_id
                    )

                    mark_message_permanently_failed(
                        message_id,
                        "Original Discord message no longer exists."
                    )

                    fail_message_with_notification(
                        message_id,
                        "Original Discord message no longer exists.",
                        "Recovery failed",
                        (
                            "A pending announcement could not be "
                            "recovered because its original Discord "
                            "message no longer exists."
                        )
                    )

                except discord.Forbidden:

                    logger.error(
                        "Bot cannot access pending message %s.",
                        message_id
                    )

                except Exception:

                    logger.exception(
                        "Recovery failed for message %s.",
                        message_id
                    )

        except Exception:

            logger.exception(
                "Recovery worker encountered an error."
            )

        await asyncio.sleep(
            RECOVERY_CHECK_INTERVAL
        )


# ==================================================
# BOT READY
# ==================================================

@client.event
async def on_ready():

    global background_tasks_started

    logger.info(
        "Logged in as: %s",
        client.user
    )

    logger.info(
        "Monitoring channel: %s",
        CHANNEL_ID
    )

    logger.info(
        "Notification channel: %s",
        NOTIFICATION_CHANNEL_ID
    )

    logger.info(
        "Timezone: %s",
        TIMEZONE_NAME
    )

    logger.info("Retry system: enabled")
    logger.info("Notification queue: enabled")
    logger.info("Restart recovery: enabled")

    if not background_tasks_started:

        background_tasks_started = True

        asyncio.create_task(
            notification_worker()
        )

        asyncio.create_task(
            recovery_worker()
        )

    logger.info(
        "Bot is ready!"
    )


# ==================================================
# START APPLICATION
# ==================================================

def main():

    initialize_database()

    logger.info(
        "Starting Discord Closure Notifier..."
    )

    client.run(
        DISCORD_TOKEN
    )


if __name__ == "__main__":

    main()