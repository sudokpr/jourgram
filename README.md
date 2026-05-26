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

## Setup

### 1. Prerequisites

- Python 3.12+
- Node.js 20+ (for grammY bot)
- Telegram account with a private supergroup named "LifeOS"

### 2. Telegram Setup

1. Create a private supergroup named "LifeOS"
2. Enable Topics in the group
3. Create topics: Journal, Learning, Ideas, Expenses, Links, Quick Dump
4. Get your API credentials from https://my.telegram.org

### 3. Installation

```bash
# Clone the repository
cd /home/kp/workspace/projects/jourgram

# Install Python dependencies
uv sync

# Install bot dependencies
cd bot && npm install && cd ..

# Copy environment file
cp .env.example .env

# Edit .env with your credentials
```

### 4. Configuration

Edit `config.yaml` or `.env` with your settings:

```yaml
telegram:
  api_id: 12345
  api_hash: your_api_hash
  phone: "+1234567890"
  session_name: life-data-lake

storage:
  data_dir: "./data"
  media_dir: "./data/media"
  raw_json_dir: "./data/raw-json"

gemini:
  api_key: your_api_key
  model_daily: "gemini-2.5-flash"
  model_deep: "gemini-2.5-pro"
```

### 5. Initialize Database

```bash
python -m app.main healthcheck
```

## Usage

### CLI Commands

```bash
# Start ingestion service
python -m app.main ingest

# Generate daily summary
python -m app.main summarize

# Generate summary for specific date
python -m app.main summarize --date 2024-01-15

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

# For daily summarization
sudo cp systemd/life-data-lake-summarize.timer /etc/systemd/system/
sudo systemctl enable life-data-lake-summarize.timer
```

## Project Structure

```
life-data-lake/
├── app/
│   ├── api/            # Query handlers
│   ├── config/         # Settings and configuration
│   ├── ingestion/       # Telethon ingestion service
│   ├── knowledge_base/  # Link processing
│   ├── llm/            # LLM provider abstraction
│   ├── models/         # Pydantic models
│   ├── scheduler/      # Automated tasks
│   ├── search/         # FTS5 search engine
│   ├── storage/        # Database and file storage
│   ├── summarizer/     # Daily/weekly summarization
│   ├── telegram/       # Telegram client management
│   ├── workers/        # Async processing workers
│   └── main.py         # CLI entry point
├── bot/                # grammY bot (TypeScript)
├── data/               # Data storage
│   ├── media/
│   ├── raw-json/
│   ├── exports/
│   └── summaries/
├── scripts/            # Utility scripts
├── systemd/            # Systemd service files
└── tests/              # Tests
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

## License

MIT