import sqlite3
import os

# Store the database in the same folder as this file
DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "closure_notifier.db"
)


# Connect to the database
def connect_database():
    connection = sqlite3.connect(DATABASE_PATH)
    return connection


# Create the database table if it doesn't exist
def initialize_database():
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            author TEXT,
            original_message TEXT NOT NULL,
            normalized_message TEXT,
            closure_status TEXT,
            closure_date TEXT,
            validation TEXT,
            calendar_event_id TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


# Check whether a message has already been processed
def is_message_processed(message_id):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT message_id
        FROM processed_messages
        WHERE message_id = ?
    """, (str(message_id),))

    result = cursor.fetchone()

    connection.close()

    return result is not None


# Save a processed Discord message
def save_message(message_id, channel_id, author, result):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO processed_messages (
            message_id,
            channel_id,
            author,
            original_message,
            normalized_message,
            closure_status,
            closure_date,
            validation
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(message_id),
        str(channel_id),
        str(author),
        result["original_message"],
        result["normalized_message"],
        result["closure_status"],
        result["date"],
        result["validation"]
    ))

    connection.commit()
    connection.close()


# Retrieve a message using its Discord ID
def get_message(message_id):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM processed_messages
        WHERE message_id = ?
    """, (str(message_id),))

    result = cursor.fetchone()

    connection.close()

    if result is None:
        return None

    return dict(result)


# Update the Google Calendar event ID for a message
def update_calendar_event(message_id, event_id):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE processed_messages
        SET calendar_event_id = ?
        WHERE message_id = ?
    """, (event_id, str(message_id)))

    connection.commit()
    connection.close()


# Delete a message from the database
def delete_message(message_id):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM processed_messages
        WHERE message_id = ?
    """, (str(message_id),))

    connection.commit()
    connection.close()


# Display all stored messages
def get_all_messages():
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM processed_messages
        ORDER BY processed_at DESC
    """)

    results = cursor.fetchall()

    connection.close()

    return [dict(row) for row in results]

def get_event_by_date(closure_date):
    connection = connect_database()
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM processed_messages
        WHERE closure_date = ?
        AND calendar_event_id IS NOT NULL
        LIMIT 1
    """, (closure_date,))

    result = cursor.fetchone()
    connection.close()

    if result is None:
        return None

    return dict(result)

# Test the database independently
if __name__ == "__main__":

    initialize_database()
    print("Database initialized successfully!")

    test_result = {
        "original_message": "The local will be closed on 12 November.",
        "normalized_message": "the local will be closed on 12 november",
        "closure_status": "confirmed",
        "date": "2026-11-12",
        "validation": "valid"
    }

    test_id = "123456789"

    save_message(
        test_id,
        "987654321",
        "TestUser",
        test_result
    )

    print("Message saved!")
    print("Already processed:", is_message_processed(test_id))
    print("Retrieved message:", get_message(test_id))
    print("All messages:", get_all_messages())

