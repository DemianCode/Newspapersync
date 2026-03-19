# NewspaSync

A self-hosted daily newspaper generator that syncs to your reMarkable.
Runs as a single Docker container. Includes a web UI for managing feeds and previewing output.

---

## Features

- **Web UI** — dashboard, PDF preview, RSS editor at `http://localhost:3050`
- **RSS feeds** — configurable feeds via the web UI or `config/sources.yml`
- **Weather** — current conditions + hourly forecast via Open-Meteo (no API key needed)
- **TickTick** — tasks due today and overdue
- **Email** — unread email summary via IMAP
- **AI summaries** — optional per-article summaries via any OpenAI-compatible API (or local Ollama)
- **reMarkable sync** — uploads today's PDF, archives previous days, prunes old archives
- **WeasyPrint PDF** — clean newspaper layout, A5 (reMarkable native) or A4

---

## Deployment

- [Local (Linux / Mac / WSL2)](#local-linux--mac--wsl2)
- [Unraid](#unraid)

---

## Local (Linux / Mac / WSL2)

### Step 1 — Clone and configure secrets

```bash
git clone https://github.com/DemianCode/Newspapersync.git
cd Newspapersync
cp .env.example .env
```

Edit `.env` and fill in only the credentials for the sources you plan to use:

| Secret | When needed |
|---|---|
| `EMAIL_USERNAME`, `EMAIL_PASSWORD` | When `EMAIL_ENABLED=true` |
| `TICKTICK_CLIENT_ID/SECRET` | When `TICKTICK_ENABLED=true` |
| `AI_API_KEY` | When `AI_SUMMARY_ENABLED=true` |

Leave unused sections blank — they're ignored.

---

### Step 2 — Configure settings

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

### Step 3 — Build and start

```bash
./redeploy.sh
```

The web UI is available immediately at **http://localhost:3050**.

---

### Step 4 — Auth reMarkable (one-time, required)

```bash
./auth-remarkable.sh
```

The script will:
1. Make sure the container is running
2. Open rmapi inside the container
3. Prompt you to visit `https://my.remarkable.com/device/browser/connect`, log in, and paste the one-time code
4. Automatically verify the auth worked

> **Important:** When you see the `[/]>` prompt, type `exit` and press Enter. Do **not** use Ctrl+C — it can kill rmapi before it saves the token.

Auth state is saved to `./rmapi/` and persists across restarts. You should only ever need to do this once.

---

### Step 5 — Auth TickTick (if enabled)

```bash
docker exec -it newspapersync python -m app.sources.ticktick --auth
```

Follow the OAuth flow. Token is saved to `config/.ticktick_token`.

---

## Unraid

Unraid doesn't have native `docker compose` support in the UI, so the recommended approach is to manage the container via SSH using the compose files directly. Unraid's Docker Compose Manager plugin also works if you have it installed.

### Step 1 — SSH into your Unraid server and clone the repo

Store the project under your appdata share so it survives array changes:

```bash
mkdir -p /mnt/user/appdata/newspapersync
cd /mnt/user/appdata/newspapersync
git clone https://github.com/DemianCode/Newspapersync.git .
```

### Step 2 — Configure secrets

```bash
cp .env.example .env
nano .env   # or vi .env
```

Fill in credentials for the sources you plan to use (see table in local setup above).

---

### Step 3 — Configure settings

```bash
nano docker-compose.yml
```

Set your timezone, weather coordinates, and schedule time (same fields as local setup above).

---

### Step 4 — Build and start

```bash
./redeploy.sh
```

Web UI will be available at `http://<unraid-ip>:3050`.

If you want the container to survive reboots, `restart: unless-stopped` is already set in `docker-compose.yml`. For Unraid, you may also want to add the container to your Unraid Docker autostart list — but since it's compose-managed, the easiest approach is to add `./redeploy.sh` as a User Script (via the User Scripts plugin) set to run at array start.

---

### Step 5 — Auth reMarkable (one-time, required)

Stay in your SSH session and run:

```bash
cd /mnt/user/appdata/newspapersync
./auth-remarkable.sh
```

Follow the same steps as the local auth flow above. The `[/]>` prompt means auth succeeded — type `exit`, don't Ctrl+C.

---

### Step 6 — Auth TickTick (if enabled)

```bash
docker exec -it newspapersync python -m app.sources.ticktick --auth
```

---

### Unraid Docker Compose Manager (alternative)

If you have the **Docker Compose Manager** plugin installed:

1. In the Unraid UI go to **Docker → Compose**.
2. Add a new stack, point it at `/mnt/user/appdata/newspapersync/docker-compose.yml`.
3. Start the stack from the UI.
4. SSH in to run `./auth-remarkable.sh` — this step still requires a terminal.

---

## Web UI

Visit `http://localhost:3050` (local) or `http://<unraid-ip>:3050` (Unraid) after starting the container.

| Page | Path | What it does |
|---|---|---|
| Dashboard | `/` | View the latest PDF, trigger a manual run, see run history |
| RSS Sources | `/sources` | Add, edit, and delete RSS feeds — saves immediately |
| Settings | `/settings` | View all current configuration and common commands |

Changes to RSS sources take effect on the next generation run (no restart needed).
Changes to settings in `docker-compose.yml` require a container restart (`./redeploy.sh`).

---

## File layout

### On disk

```
.
├── config/
│   └── sources.yml        # RSS feeds (editable via web UI or directly)
├── output/                # Generated PDFs
│   └── newspaper-YYYY-MM-DD.pdf
├── rmapi/                 # rmapi auth state (auto-created, gitignored)
├── .env                   # Your secrets (gitignored)
├── docker-compose.yml     # All settings
├── redeploy.sh            # Rebuild and restart the container
└── auth-remarkable.sh     # One-time reMarkable auth helper
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
| `WEB_ENABLED` | `true` | Enable the web UI on port 3050 |
| `WEB_PORT` | `3050` | Web UI port |
| `SCHEDULE_TIME` | `06:00` | Daily generation time (HH:MM, container local time) |
| `RUN_ON_START` | `false` | Also run immediately when the container starts |
| `TZ` | `UTC` | Container timezone |
| `REMARKABLE_SYNC_METHOD` | `rmapi` | `rmapi` only (email delivery not supported on newer devices) |
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
# Rebuild and restart (after any code or config changes)
./redeploy.sh

# Auth reMarkable (first time, or if token expires)
./auth-remarkable.sh

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
./redeploy.sh
```

Your `config/`, `output/`, `rmapi/`, and `.env` are mounted volumes — they are never overwritten by an update.
