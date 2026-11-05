# ML-Local – Discord Closure Notifier

## 1. Project Description

ML-Local is a Python application that monitors a specific Discord channel for announcements about local closures.

When a confirmed closure announcement is detected, the bot extracts the relevant dates and automatically creates or updates an event in Google Calendar.

The bot can also detect cancellations, corrections, and reopening announcements.

If an announcement is unclear or incomplete, the bot sends a notification requesting manual review instead of creating an incorrect event.

## 2. Main Features

- Monitor a configured Discord channel.
- Detect confirmed closure announcements.
- Extract single dates and date ranges.
- Support relative dates such as tomorrow and next week.
- Validate extracted dates.
- Create Google Calendar events.
- Update events when closure dates change.
- Delete events when closures are cancelled.
- Handle reopening announcements.
- Prevent duplicate calendar events.
- Store processed messages using SQLite.
- Send Discord notifications.
- Retry failed operations.
- Recover pending operations after restarting.

## 3. Technologies Used

- Python
- Discord.py
- Google Calendar API
- SQLite
- Google OAuth 2.0
- Python-dotenv

## 4. Project Structure

```text
ml-local/
│
├── monitor.py
├── message_processor.py
├── calendar_service.py
├── database.py
├── .env
├── .gitignore
├── credentials.json
├── token.json
├── closure_notifier.db
└── README.md
```

### Main Files

- `monitor.py`: Connects to Discord and manages message monitoring.
- `message_processor.py`: Detects closure announcements and extracts dates.
- `calendar_service.py`: Handles Google Calendar operations.
- `database.py`: Stores messages, event mappings, and notification information.

## 5. Installation

Clone the repository:

```bash
git clone YOUR_REPOSITORY_URL
cd ml-local
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install discord.py python-dotenv tzdata
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## 6. Configuration

Create a `.env` file containing:

```env
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN
CHANNEL_ID=YOUR_MONITORED_CHANNEL_ID
NOTIFICATION_CHANNEL_ID=YOUR_NOTIFICATION_CHANNEL_ID
```

You also need a Google OAuth Desktop application credentials file named `credentials.json`.

The application generates `token.json` after authentication.

Never upload credentials or secret tokens to GitHub.

## 7. Running the Application

Start the application:

```bash
python monitor.py
```

The bot connects to Discord, initializes the database, and starts monitoring the configured channel.

## 8. Supported Announcement Examples

**Closure:**

```text
The local will be closed tomorrow.
```

**Date range:**

```text
The local will be closed from 13 November 2026 to 15 November 2026.
```

**Correction:**

```text
Correction: The closure is on 15 November instead of 13 November.
```

**Cancellation:**

```text
The closure on 13 November 2026 has been cancelled.
```

**Reopening:**

```text
The local will reopen on 15 November 2026.
```

Unclear announcements or announcements with missing dates require manual review.

## 9. Database and Reliability

SQLite stores processed Discord messages and their associated Google Calendar events.

The application includes:

- Duplicate prevention.
- Processing status tracking.
- Retry mechanisms.
- Notification queue.
- Recovery of pending operations after restart.

## 10. Project Objective

The objective of ML-Local is to automate the management of local closure announcements by connecting Discord with Google Calendar, reducing manual work and keeping users informed about closure dates.