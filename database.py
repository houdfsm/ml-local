import os
import sqlite3

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone


# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FILE = os.path.join(
    BASE_DIR,
    "closure_notifier.db"
)

MAX_OPERATION_ATTEMPTS = 5
MAX_NOTIFICATION_ATTEMPTS = 5


# ==================================================
# DATABASE CONNECTION
# ==================================================

@contextmanager
def get_connection():

    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    try:

        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")

        yield connection

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


# ==================================================
# INITIALIZE DATABASE
# ==================================================

def initialize_database():

    with get_connection() as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                original_message TEXT NOT NULL,
                calendar_event_id TEXT,
                processed_at TEXT,
                start_date TEXT,
                end_date TEXT,
                start_time TEXT,
                end_time TEXT,
                event_type TEXT,
                sync_status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                next_retry_at TEXT
            )
        """)

        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(processed_messages)"
            ).fetchall()
        }

        required_columns = {

            "channel_id": "TEXT DEFAULT ''",
            "author": "TEXT DEFAULT ''",
            "normalized_message": "TEXT",
            "closure_status": "TEXT",
            "closure_date": "TEXT",
            "validation": "TEXT",

            "calendar_event_id": "TEXT",
            "processed_at": "TEXT",

            "start_date": "TEXT",
            "end_date": "TEXT",

            "start_time": "TEXT",
            "end_time": "TEXT",

            "event_type": "TEXT",

            "sync_status": "TEXT DEFAULT 'pending'",
            "retry_count": "INTEGER DEFAULT 0",

            "last_error": "TEXT",
            "next_retry_at": "TEXT"
        }

        for column, definition in required_columns.items():

            if column not in existing_columns:

                connection.execute(
                    f"ALTER TABLE processed_messages "
                    f"ADD COLUMN {column} {definition}"
                )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS notification_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                created_at TEXT,
                UNIQUE(message_id, title)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_retry
            ON processed_messages(sync_status, next_retry_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_notifications_retry
            ON notification_queue(status, next_attempt_at)
        """)

    print("Database initialized successfully.")


# ==================================================
# SAVE MESSAGE
# ==================================================

def save_message(
    message_id,
    original_message,
    start_date=None,
    end_date=None,
    start_time=None,
    end_time=None,
    event_type=None,
    channel_id=None,
    author=None,
    normalized_message=None,
    closure_status=None,
    validation=None
):

    start_date = str(start_date) if start_date else None

    end_date = (
        str(end_date)
        if end_date
        else start_date
    )

    with get_connection() as connection:

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(processed_messages)"
            ).fetchall()
        }

        values = {

            "message_id": str(message_id),

            "original_message": original_message,

            "channel_id": (
                str(channel_id)
                if channel_id is not None
                else ""
            ),

            "author": author or "",

            "normalized_message": (
                normalized_message or original_message
            ),

            "closure_status": (
                closure_status or event_type
            ),

            "closure_date": start_date,

            "validation": validation,

            "start_date": start_date,
            "end_date": end_date,

            "start_time": start_time,
            "end_time": end_time,

            "event_type": event_type
        }

        insert_values = {
            key: value
            for key, value in values.items()
            if key in columns
        }

        column_names = list(insert_values.keys())

        placeholders = ", ".join(
            ["?"] * len(column_names)
        )

        updates = [

            f"{column} = excluded.{column}"

            for column in column_names

            if column not in (
                "message_id",
                "calendar_event_id",
                "sync_status",
                "retry_count",
                "processed_at",
                "last_error",
                "next_retry_at"
            )
        ]

        sql = f"""
            INSERT INTO processed_messages (
                {", ".join(column_names)}
            )

            VALUES ({placeholders})

            ON CONFLICT(message_id) DO UPDATE SET
                {", ".join(updates)}
        """

        connection.execute(
            sql,
            tuple(
                insert_values[column]
                for column in column_names
            )
        )


# ==================================================
# GET MESSAGE
# ==================================================

def get_message(message_id):

    with get_connection() as connection:

        row = connection.execute("""
            SELECT *
            FROM processed_messages
            WHERE message_id = ?
        """, (str(message_id),)).fetchone()

        return dict(row) if row else None


# ==================================================
# CHECK MESSAGE STATUS
# ==================================================

def is_message_processed(message_id):

    message = get_message(message_id)

    return (
        message is not None
        and message["sync_status"] == "completed"
    )


# ==================================================
# BEGIN OPERATION
# ==================================================

def begin_operation(message_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'pending',
                last_error = NULL,
                next_retry_at = NULL

            WHERE message_id = ?
        """, (str(message_id),))


# ==================================================
# UPDATE CALENDAR EVENT ID
# ==================================================

def update_calendar_event(message_id, event_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET calendar_event_id = ?

            WHERE message_id = ?
        """, (
            event_id,
            str(message_id)
        ))


# ==================================================
# MARK MESSAGE COMPLETED
# ==================================================

def mark_message_completed(message_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'completed',
                processed_at = ?,
                retry_count = 0,
                last_error = NULL,
                next_retry_at = NULL

            WHERE message_id = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            str(message_id)
        ))


# ==================================================
# MARK MESSAGE FAILED
# ==================================================

def mark_message_failed(message_id, error):

    now = datetime.now(timezone.utc)

    with get_connection() as connection:

        row = connection.execute("""
            SELECT retry_count

            FROM processed_messages

            WHERE message_id = ?
        """, (str(message_id),)).fetchone()

        if row is None:
            return True

        attempts = row["retry_count"] + 1

        if attempts >= MAX_OPERATION_ATTEMPTS:

            connection.execute("""
                UPDATE processed_messages

                SET sync_status = 'failed',
                    retry_count = ?,
                    last_error = ?,
                    next_retry_at = NULL

                WHERE message_id = ?
            """, (
                attempts,
                str(error),
                str(message_id)
            ))

            return True

        retry_time = now + timedelta(
            minutes=2 * attempts
        )

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'pending',
                retry_count = ?,
                last_error = ?,
                next_retry_at = ?

            WHERE message_id = ?
        """, (
            attempts,
            str(error),
            retry_time.isoformat(),
            str(message_id)
        ))

        return False


# ==================================================
# PERMANENT FAILURE
# ==================================================

def mark_message_permanently_failed(message_id, error):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'failed',
                last_error = ?,
                next_retry_at = NULL

            WHERE message_id = ?
        """, (
            str(error),
            str(message_id)
        ))


# ==================================================
# GET PENDING MESSAGES
# ==================================================

def get_pending_messages():

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:

        rows = connection.execute("""
            SELECT *

            FROM processed_messages

            WHERE sync_status = 'pending'

              AND (
                    next_retry_at IS NULL
                    OR next_retry_at <= ?
              )

            ORDER BY processed_at ASC
        """, (now,)).fetchall()

        return [
            dict(row)
            for row in rows
        ]


# ==================================================
# UPDATE EVENT DATA
# ==================================================

def update_event_data_by_id(
    event_id,
    start_date,
    end_date=None
):

    if isinstance(start_date, dict):

        data = start_date

        start_date = data.get("start_date")
        end_date = data.get("end_date")

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET start_date = ?,
                end_date = ?

            WHERE calendar_event_id = ?
        """, (
            str(start_date) if start_date else None,
            str(end_date) if end_date else None,
            event_id
        ))


# ==================================================
# UPDATE CLOSURE DATE
# ==================================================

def update_closure_date(
    message_id,
    start_date,
    end_date=None
):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET start_date = ?,
                end_date = ?

            WHERE message_id = ?
        """, (
            str(start_date) if start_date else None,
            str(end_date) if end_date else None,
            str(message_id)
        ))


# ==================================================
# GET ALL EVENTS COVERING A DATE
# ==================================================

def get_events_by_date(target_date):

    target_date = str(target_date)

    with get_connection() as connection:

        rows = connection.execute("""
            SELECT *

            FROM processed_messages

            WHERE calendar_event_id IS NOT NULL
              AND sync_status = 'completed'
              AND start_date <= ?
              AND end_date >= ?

            ORDER BY processed_at DESC
        """, (
            target_date,
            target_date
        )).fetchall()

        return [
            dict(row)
            for row in rows
        ]


# ==================================================
# GET ONE EVENT BY DATE
# Backwards-compatible with monitor.py
# ==================================================

def get_event_by_date(target_date):

    events = get_events_by_date(target_date)

    return events[0] if events else None


# ==================================================
# GET EVENTS COVERING A DATE
# ==================================================

def get_events_covering_date(target_date):

    return get_events_by_date(target_date)


# ==================================================
# CLEAR EVENT ID BY MESSAGE
# ==================================================

def clear_event_id(message_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET calendar_event_id = NULL

            WHERE message_id = ?
        """, (str(message_id),))


# ==================================================
# CLEAR ALL REFERENCES TO A CALENDAR EVENT
# ==================================================

def clear_event_id_by_calendar_id(event_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET calendar_event_id = NULL

            WHERE calendar_event_id = ?
        """, (event_id,))


# ==================================================
# DELETE MESSAGE
# ==================================================

def delete_message(message_id):

    with get_connection() as connection:

        connection.execute("""
            DELETE FROM processed_messages

            WHERE message_id = ?
        """, (str(message_id),))


# ==================================================
# ENQUEUE NOTIFICATION
# ==================================================

def enqueue_notification(
    message_id,
    title,
    description
):

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:

        connection.execute("""
            INSERT OR IGNORE INTO notification_queue (

                message_id,
                title,
                description,
                status,
                attempts,
                next_attempt_at,
                created_at

            )

            VALUES (?, ?, ?, 'pending', 0, ?, ?)
        """, (
            str(message_id),
            title,
            description,
            now,
            now
        ))


# ==================================================
# COMPLETE MESSAGE + NOTIFICATION
# ==================================================

def complete_message_with_notification(
    message_id,
    title,
    description
):

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'completed',
                processed_at = ?,
                retry_count = 0,
                last_error = NULL,
                next_retry_at = NULL

            WHERE message_id = ?
        """, (
            now,
            str(message_id)
        ))

        connection.execute("""
            INSERT OR IGNORE INTO notification_queue (

                message_id,
                title,
                description,
                status,
                attempts,
                next_attempt_at,
                created_at

            )

            VALUES (?, ?, ?, 'pending', 0, ?, ?)
        """, (
            str(message_id),
            title,
            description,
            now,
            now
        ))


# ==================================================
# FAILED MESSAGE + NOTIFICATION
# ==================================================

def fail_message_with_notification(
    message_id,
    error,
    title,
    description
):

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:

        connection.execute("""
            UPDATE processed_messages

            SET sync_status = 'failed',
                last_error = ?,
                next_retry_at = NULL

            WHERE message_id = ?
        """, (
            str(error),
            str(message_id)
        ))

        connection.execute("""
            INSERT OR IGNORE INTO notification_queue (

                message_id,
                title,
                description,
                status,
                attempts,
                next_attempt_at,
                created_at

            )

            VALUES (?, ?, ?, 'pending', 0, ?, ?)
        """, (
            str(message_id),
            title,
            description,
            now,
            now
        ))


# ==================================================
# GET PENDING NOTIFICATIONS
# ==================================================

def get_pending_notifications():

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:

        rows = connection.execute("""
            SELECT *

            FROM notification_queue

            WHERE status = 'pending'

              AND (
                    next_attempt_at IS NULL
                    OR next_attempt_at <= ?
              )

            ORDER BY id ASC
        """, (now,)).fetchall()

        return [
            dict(row)
            for row in rows
        ]


# ==================================================
# MARK NOTIFICATION SENT
# ==================================================

def mark_notification_sent(notification_id):

    with get_connection() as connection:

        connection.execute("""
            UPDATE notification_queue

            SET status = 'sent',
                last_error = NULL

            WHERE id = ?
        """, (notification_id,))


# ==================================================
# MARK NOTIFICATION FAILED
# ==================================================

def mark_notification_failed(
    notification_id,
    error
):

    now = datetime.now(timezone.utc)

    with get_connection() as connection:

        row = connection.execute("""
            SELECT attempts

            FROM notification_queue

            WHERE id = ?
        """, (notification_id,)).fetchone()

        if row is None:
            return

        attempts = row["attempts"] + 1

        if attempts >= MAX_NOTIFICATION_ATTEMPTS:

            connection.execute("""
                UPDATE notification_queue

                SET status = 'failed',
                    attempts = ?,
                    last_error = ?,
                    next_attempt_at = NULL

                WHERE id = ?
            """, (
                attempts,
                str(error),
                notification_id
            ))

            return

        retry_time = now + timedelta(
            minutes=5 * attempts
        )

        connection.execute("""
            UPDATE notification_queue

            SET status = 'pending',
                attempts = ?,
                last_error = ?,
                next_attempt_at = ?

            WHERE id = ?
        """, (
            attempts,
            str(error),
            retry_time.isoformat(),
            notification_id
        ))


# ==================================================
# MANUAL DATABASE TEST
# ==================================================

if __name__ == "__main__":

    initialize_database()