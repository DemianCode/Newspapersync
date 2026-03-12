# NewspaSync

A self-hosted daily newspaper generator that syncs to your reMarkable.
Runs as a single Docker container. Includes a web UI for managing feeds and previewing output.

---

## Features

- **Web UI** — dashboard, PDF preview, RSS editor at `http://localhost:8080`
- **RSS feeds** — configurable feeds via the web UI or `config/sources.yml`
- **Weather** — current conditions + hourly forecast via Open-Meteo (no API key needed)
- **TickTick** — tasks due today and overdue
- **Email** — unread email summary via IMAP
- **AI summaries** — optional per-article summaries via any OpenAI-compatible API (or local Ollama)
- **reMarkable sync** — uploads today's PDF, archives previous days, prunes old archives
- **WeasyPrint PDF** — clean newspaper layout, A5 (reMarkable native) or A4

---

## Quick start

### Step 1 — Copy the secrets file

```bash
cp .env.example .env
```

Edit `.env` and fill in only the credentials for sources you plan to use:

| Secret | When needed |
|---|---|
| `SMTP_*`, `REMARKABLE_DEVICE_EMAIL` | When using email sync to reMarkable |
| `EMAIL_USERNAME`, `EMAIL_PASSWORD` | When `EMAIL_ENABLED=true` (inbox summary) |
| `TICKTICK_CLIENT_ID/SECRET` | When `TICKTICK_ENABLED=true` |
| `AI_API_KEY` | When `AI_SUMMARY_ENABLED=true` |

Leave unused sections blank — they're ignored.

---

### Step 2 — Configure in docker-compose.yml

Open `docker-compose.yml` and set at minimum:

```yaml
TZ: "Australia/Sydney"          # your timezone
WEATHER_LAT: "-33.8688"         # your latitude
WEATHER_LON: "151.2093"         # your longitude
WEATHER_LOCATION_NAME: "Sydney" # displayed on the newspaper
SCHEDULE_TIME: "06:00"          # when to generate each day
```

Enable or disable sources with the `*_ENABLED` flags (weather is on by default, everything else is off).

---

### Step 3 — Auth reMarkable (one-time)

Skip this step if you plan to use email sync only.

```bash
docker compose run --rm newspapersync rmapi
```

This opens the rmapi interactive setup. It prints a URL — go to
**my.remarkable.com → Settings → one-time code**, paste the code back.
Auth state is saved to `./rmapi/` and persists across container restarts.

**Sync methods** — set `REMARKABLE_SYNC_METHOD` in `docker-compose.yml`:

| Method | How it works | Requires |
|---|---|---|
| `rmapi` | Uploads via rmapi CLI, supports archiving | rmapi auth (step above) |
| `email` | Sends PDF to your device email address | SMTP + device email in `.env` |
| `rmapi_with_email_fallback` | Tries rmapi first, falls back to email | Both of the above |

Find your device email at: **my.remarkable.com → Settings → Email & storage**.

---

### Step 4 — Build and start

```bash
docker compose up -d --build
```

The web UI is available immediately at **http://localhost:8080**.
The newspaper generates at your scheduled time, or click **Generate Now** in the dashboard.

---

### Step 5 — Auth TickTick (if enabled)

```bash
docker exec -it newspapersync python -m app.sources.ticktick --auth
```

Follow the OAuth flow. Token is saved to `config/.ticktick_token`.

---

## Web UI

Visit **http://localhost:8080** after starting the container.

| Page | Path | What it does |
|---|---|---|
| Dashboard | `/` | View the latest PDF, trigger a manual run, see run history |
| RSS Sources | `/sources` | Add, edit, and delete RSS feeds — saves immediately |
| Settings | `/settings` | View all current configuration and common commands |

Changes to RSS sources take effect on the next generation run (no restart needed).
Changes to settings in `docker-compose.yml` require a container restart.

---

## File layout

### On disk

```
.
├── config/
│   └── sources.yml        # RSS feeds (editable via web UI or directly)
├── output/                # Generated PDFs
│   └── newspaper-YYYY-MM-DD.pdf
├── rmapi/                 # rmapi auth state (auto-created)
├── .env                   # Your secrets (gitignored)
└── docker-compose.yml     # All settings
```

### On your reMarkable

```
Newspaper/
  newspaper-2025-01-15.pdf      ← today's issue
  Archive/
    newspaper-2025-01-14.pdf
    newspaper-2025-01-13.pdf
    ...                          ← kept for REMARKABLE_ARCHIVE_KEEP_DAYS days
```

---

## Configuration reference

All non-secret settings live in `docker-compose.yml`. Full inline comments are there.

| Variable | Default | Description |
|---|---|---|
| `WEB_ENABLED` | `true` | Enable the web UI on port 8080 |
| `WEB_PORT` | `8080` | Web UI port |
| `SCHEDULE_TIME` | `06:00` | Daily generation time (HH:MM, container local time) |
| `RUN_ON_START` | `false` | Also run immediately when the container starts |
| `TZ` | `UTC` | Container timezone |
| `REMARKABLE_SYNC_METHOD` | `rmapi_with_email_fallback` | See sync methods above |
| `REMARKABLE_FOLDER` | `Newspaper` | Upload folder on reMarkable |
| `REMARKABLE_ARCHIVE_FOLDER` | `Newspaper/Archive` | Archive folder (blank = delete old files) |
| `REMARKABLE_ARCHIVE_KEEP_DAYS` | `30` | Days to keep archived PDFs (0 = keep forever) |
| `WEATHER_ENABLED` | `true` | Enable weather section |
| `WEATHER_LAT` / `WEATHER_LON` | — | Your coordinates |
| `WEATHER_UNITS` | `celsius` | `celsius` or `fahrenheit` |
| `EMAIL_ENABLED` | `false` | Enable email inbox summary section |
| `TICKTICK_ENABLED` | `false` | Enable TickTick tasks section |
| `RSS_ENABLED` | `true` | Enable RSS news section |
| `RSS_MAX_ARTICLES_PER_FEED` | `5` | Max articles per feed |
| `AI_SUMMARY_ENABLED` | `false` | Enable AI article summaries |
| `AI_API_BASE_URL` | OpenAI | Swap for local Ollama: `http://ollama:11434/v1` |
| `AI_MODEL` | `gpt-4o-mini` | Model name |
| `PDF_THEME` | `light` | `light` or `dark` |
| `PDF_PAPER_SIZE` | `A5` | `A5` (reMarkable native) or `A4` |
| `PDF_COLUMNS` | `1` | News columns: `1` or `2` |

---

## Common commands

```bash
# Start (or restart after config changes)
docker compose up -d --build

# View logs
docker compose logs -f

# Trigger generation now (via CLI)
docker compose exec newspapersync python -m app.main --now

# Stop
docker compose down
```

---

## Updating

```bash
git pull
docker compose up -d --build
```

Your `config/`, `output/`, `rmapi/`, and `.env` are mounted volumes — they are never overwritten by an update.
