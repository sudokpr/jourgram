# Life Data Lake

A local-first personal data management system with Telegram as the primary ingestion interface.

## Features

- **Telegram Integration**: Uses Telethon MTProto for real-time message ingestion
- **Topic-Based Organization**: Journal, Learning, Ideas, Expenses, Links, Quick Dump
- **Local Storage**: Raw JSON storage on filesystem, SQLite for metadata
- **AI Summarization**: Gemini-powered daily and weekly summaries
- **Search**: Full-text search using SQLite FTS5
- **Link Knowledge Base**: Automatic link content extraction
- **grammY Bot**: Telegram bot interface for queries

## Architecture

```
Telegram Supergroup (LifeOS with Topics)
    ↓
Telethon ingestion service
    ↓
Append-only raw event store
    ↓
Async processing workers
├── normalization
├── media downloader
├── link extractor
└── summarization queue
    ↓
Gemini summarizer
    ↓
Telegram summary channels / grammY bot
```

## Prerequisites

- Python 3.12+
- Node.js 20+ (for grammY bot)
- Telegram account

## Setup

### 1. Telegram Setup

1. Create a private supergroup named "LifeOS"
2. Enable Topics in the group (Admin > Topics > Enable)
3. Create these topics:
   - Journal
   - Learning
   - Ideas
   - Expenses
   - Links
   - Quick Dump
4. Get your API credentials from https://my.telegram.org

### 2. Find Your Chat ID

Forward any message from your LifeOS group to [@userinfobot](https://t.me/userinfobot). It will show you:
- Your personal chat ID
- The group chat ID (starts with -100)

### 3. Find Topic IDs

Topic IDs are the numbers in the topic links. When viewing a topic in Telegram:
- Look at the URL: `https://t.me/c/1234567890/1` where `1` is the topic ID
- Or right-click a topic name to copy the invite link

For example, if your group link is `https://t.me/c/9876543210/1`:
- `9876543210` is your chat_id (you'll enter it as `-1009876543210`)
- `1` is the journal topic ID

### 4. Installation

```bash
# Install Python dependencies
uv sync --extra prod

# Install bot dependencies
cd bot && npm install && cd ..

# Copy environment file
cp .env.example .env
```

### 5. Configuration

Edit `.env` with your credentials:

```bash
# Telegram credentials from my.telegram.org
TELEGRAM__API_ID=12345
TELEGRAM__API_HASH=your_api_hash_here
TELEGRAM__PHONE=+1234567890

# Chat ID of your LifeOS supergroup (starts with -100)
TELEGRAM__CHAT_ID=-1009876543210

# Topic IDs - the numbers after the slash in topic links
TELEGRAM__TOPICS__JOURNAL=1
TELEGRAM__TOPICS__LEARNING=2
TELEGRAM__TOPICS__IDEAS=3
TELEGRAM__TOPICS__EXPENSES=4
TELEGRAM__TOPICS__LINKS=5
TELEGRAM__TOPICS__QUICK_DUMP=6

# Gemini API key
GEMINI__API_KEY=your_gemini_key_here
```

### 6. Initialize

```bash
# Verify configuration
python -m app.main healthcheck

# Start ingestion service
python -m app.main ingest
```

## Configuration Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM__API_ID` | From my.telegram.org | `12345` |
| `TELEGRAM__API_HASH` | From my.telegram.org | `abc123...` |
| `TELEGRAM__PHONE` | Your phone number | `+1234567890` |
| `TELEGRAM__CHAT_ID` | LifeOS group ID | `-1009876543210` |
| `TELEGRAM__TOPICS__JOURNAL` | Topic ID for Journal | `1` |
| `TELEGRAM__TOPICS__LEARNING` | Topic ID for Learning | `2` |
| `GEMINI__API_KEY` | Google AI API key | `AIza...` |

## Usage

### CLI Commands

```bash
# Start ingestion service
python -m app.main ingest

# Generate daily summary
python -m app.main summarize

# Generate summary for specific date
python -m app.main summarize --date 2024-01-15

# Generate summaries for date range
python -m app.main summarize-range 2024-01-01 2024-01-31

# Backfill historical messages
python -m app.main backfill 30

# Search messages
python -m app.main search "keyword"

# Export data
python -m app.main export --format json

# Health check
python -m app.main healthcheck

# Rebuild search index
python -m app.main rebuild-index

# Process pending links
python -m app.main fetch-links
```

### Docker

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

### Systemd

```bash
# Install service
sudo cp systemd/life-data-lake.service /etc/systemd/system/
sudo systemctl enable life-data-lake
sudo systemctl start life-data-lake

# For daily summarization timer
sudo cp systemd/life-data-lake-summarize.timer /etc/systemd/system/
sudo cp systemd/life-data-lake-summarize.service /etc/systemd/system/
sudo systemctl enable life-data-lake-summarize.timer
sudo systemctl start life-data-lake-summarize.timer
```

## Project Structure

```
.
├── app/
│   ├── api/              # Query handlers
│   ├── bot/              # Bot placeholder (grammY is TypeScript)
│   ├── config/           # Settings (Pydantic)
│   ├── ingestion/        # Telethon ingestion service
│   ├── knowledge_base/    # Link processing
│   ├── llm/              # LLM provider abstraction
│   ├── models/           # Pydantic models
│   ├── scheduler/        # Automated tasks
│   ├── search/           # FTS5 search engine
│   ├── storage/          # Database and file storage
│   ├── summarizer/       # Daily/weekly summarization
│   ├── telegram/         # Telegram client management
│   ├── workers/          # Async processing workers
│   └── main.py           # CLI entry point
├── bot/                  # grammY bot (TypeScript)
├── data/                  # Data storage
│   ├── media/
│   ├── raw-json/
│   ├── exports/
│   └── summaries/
├── scripts/              # Utility scripts
├── systemd/              # Systemd service files
└── tests/                # Tests
```

## Supported Message Types

- Text messages
- Photos
- Documents
- Links/URLs
- Edited messages
- Replies
- Forwarded messages

## Future Sources

The architecture is designed to support future ingestion sources:
- WhatsApp
- MQTT/home automation
- Location history
- Browser history
- Kindle highlights
- Email

## Troubleshooting

### "Chat not found" error
- Ensure `TELEGRAM__CHAT_ID` is correct (must start with `-100`)
- Make sure your bot/user account is a member of the group

### Topic ID confusion
- Topic IDs are **not** the topic names - they are numeric IDs from the topic links
- Look at topic links: `t.me/c/CHAT_ID/TOPIC_ID`

### Authentication issues
- Delete the `.session` file and re-run to re-authenticate
- Ensure phone number includes country code

## License

MIT