# AlertHub

Lightweight alert forwarding gateway — receive alerts from Prometheus Alertmanager or custom sources, and broadcast them to **Bark** and **Telegram** concurrently.

## Features

- 🚀 **Multi-channel dispatch** — Bark push + Telegram Bot, sent concurrently via thread pool
- 🔗 **Alertmanager native webhook** — Drop-in compatible with Prometheus Alertmanager
- 📡 **Generic alert API** — Simple JSON endpoint for custom integrations
- ♻️ **Error aggregation** — Collects results from all channels before reporting failures
- ⏱️ **Configurable timeout** — Per-request HTTP timeout with retry and connection pooling
- 🩺 **Health check** — Built-in `/health` endpoint for container orchestration
- 🐳 **Docker ready** — Includes `HEALTHCHECK` probe, `.dockerignore`, and slim image

## Quick Start

### Docker (Recommended)

```bash
docker run -d -p 8000:8000 \
  -e BARK_KEY=your_bark_key \
  -e TELEGRAM_BOT_TOKEN=your_bot_token \
  -e TELEGRAM_CHAT_ID=your_chat_id \
  --name alerthub \
  alerthub:latest
```

### Local Development

```bash
# Install dependencies
uv sync --dev

# Start dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API

### `GET /health`

Health check endpoint.

```json
{"status": "healthy"}
```

### `POST /alert`

Generic alert endpoint.

```bash
curl -X POST http://localhost:8000/alert \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Disk usage > 90%",
    "title": "Disk Alert",
    "level": "critical",
    "url": "https://grafana.example.com/dashboard",
    "group": "infra"
  }'
```

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string | ✅ | Alert message body |
| `title` | string | | Notification title |
| `level` | string | | Severity level (e.g. `critical`, `warning`) |
| `url` | string | | Click-through URL |
| `group` | string | | Alert grouping label |

### `POST /alertmanager-webhook`

Prometheus Alertmanager native webhook. Configure in `alertmanager.yml`:

```yaml
receivers:
  - name: 'alerthub'
    webhook_configs:
      - url: 'http://alerthub:8000/alertmanager-webhook'
```

## Configuration

All configuration is done via environment variables:

| Variable | Description | Required | Default |
|---|---|---|---|
| `BARK_KEY` | Bark push key | At least one channel | — |
| `BARK_URL` | Bark server URL | No | `https://api.day.app` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | At least one channel | — |
| `TELEGRAM_CHAT_ID` | Telegram target chat ID | With bot token | — |
| `SOCKS_PROXY` | SOCKS proxy (e.g. `socks5://host:port`) | No | — |
| `REQUEST_TIMEOUT` | HTTP request timeout in seconds | No | `10` |

## Docker Build

```bash
# Build
docker build -t alerthub .

# Run
docker run -d -p 8000:8000 \
  -e BARK_KEY=your_key \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -e TELEGRAM_CHAT_ID=your_chat_id \
  alerthub
```

## Testing

```bash
# Install dev dependencies
uv sync --dev

# Run all tests
pytest tests/ -v
```

## License

MIT
