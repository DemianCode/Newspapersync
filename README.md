# NewspaSync

A self-hosted daily newspaper generator that syncs to your reMarkable Paper Pro.
Runs as a Docker container on Unraid (or any Docker host).

## Features

- **RSS feeds** — configurable list of feeds (see `config/sources.yml`)
- **Weather** — current conditions + hourly forecast via Open-Meteo (no API key needed)
- **TickTick** — tasks due today and overdue
- **Email** — unread email summary via IMAP
- **AI summaries** — optional per-article summaries via any OpenAI-compatible API
- **reMarkable sync** — uploads today's PDF, archives previous days, prunes old archives
- **WeasyPrint PDF** — clean newspaper layout, A5 (reMarkable native) or A4

## Quick Start

### 1. Configure

Edit `docker-compose.yml`:
- Set `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_LOCATION_NAME`
- Set `TZ` to your timezone
- Enable/disable sources (`WEATHER_ENABLED`, `EMAIL_ENABLED`, `TICKTICK_ENABLED`, etc.)
- Set credentials for any enabled sources

Edit `config/sources.yml` to add/remove RSS feeds.

### 2. Set up rmapi (reMarkable auth)

```bash
docker compose run --rm newspapersync rmapi
```

Follow the prompts — you'll be given a one-time code to enter at my.remarkable.com.
The auth state is saved to `./rmapi/` and persists between restarts.

### 3. Set up TickTick (if enabled)

```bash
docker exec -it newspapersync python -m app.sources.ticktick --auth
```

Follow the OAuth flow. Token is saved to `config/.ticktick_token`.

### 4. Run

```bash
docker compose up -d
```

The container will wait until your scheduled time (`SCHEDULE_TIME`) and run daily.

### Manual trigger

```bash
docker exec -it newspapersync python -m app.main --now
```

## File layout on reMarkable

```
Newspaper/
  newspaper-2025-01-15.pdf    ← today
Archive/
  newspaper-2025-01-14.pdf
  newspaper-2025-01-13.pdf
  ...                         ← kept for REMARKABLE_ARCHIVE_KEEP_DAYS days
```

## Configuration reference

All settings live in `docker-compose.yml` as environment variables.
See inline comments there for full documentation.

| Variable | Default | Description |
|---|---|---|
| `SCHEDULE_TIME` | `06:00` | Daily generation time (HH:MM, container local) |
| `RUN_ON_START` | `false` | Run immediately when container starts |
| `REMARKABLE_FOLDER` | `Newspaper` | Upload folder on reMarkable |
| `REMARKABLE_ARCHIVE_FOLDER` | `Newspaper/Archive` | Archive folder (blank = delete) |
| `REMARKABLE_ARCHIVE_KEEP_DAYS` | `30` | Days to keep archived PDFs |
| `WEATHER_ENABLED` | `true` | Enable weather section |
| `WEATHER_LAT` / `WEATHER_LON` | — | Your coordinates |
| `WEATHER_UNITS` | `celsius` | `celsius` or `fahrenheit` |
| `EMAIL_ENABLED` | `false` | Enable email section |
| `TICKTICK_ENABLED` | `false` | Enable TickTick tasks section |
| `AI_SUMMARY_ENABLED` | `false` | Enable AI article summaries |
| `PDF_THEME` | `light` | `light` or `dark` |
| `PDF_PAPER_SIZE` | `A5` | `A5` (reMarkable) or `A4` |
| `PDF_COLUMNS` | `1` | News columns: `1` or `2` |
| `TZ` | `UTC` | Container timezone |
