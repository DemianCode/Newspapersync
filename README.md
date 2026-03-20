# NewspaSync

A self-hosted daily newspaper generator that syncs to your reMarkable.
Runs as a single Docker container with a web UI for managing everything.

---

## Features

- **Web UI** — dashboard, PDF preview, RSS editor at `http://localhost:3050`
- **RSS feeds** — configurable feeds via the web UI or `config/sources.yml`
- **Weather** — current conditions + hourly forecast via Open-Meteo (no API key needed)
- **Wikipedia** — Article of the Day, with graceful error display if unavailable
- **Wikiquote** — Quote of the Day from Wikiquote
- **Word of the Day** — daily word and definition from Merriam-Webster
- **TickTick** — tasks due today and overdue
- **Email** — unread email summary via IMAP
- **Sudoku** — daily puzzle at easy / medium / hard difficulty
- **AI summaries** — optional per-article summaries via any OpenAI-compatible API (or local Ollama)
- **reMarkable sync** — uploads today's PDF, archives previous days, prunes old archives
- **PDF email delivery** — send the newspaper to any inbox after each run (uses the same SMTP credentials)
- **Editions** — multiple named newspaper configurations, each with its own schedule, source selection, delivery target (reMarkable, email, or both), and appearance settings. Change schedules live without restarting.
- **WeasyPrint PDF** — clean newspaper layout, A5 (reMarkable native) or A4
- **Learning Feeds** — sequential lesson delivery from uploaded JSON curricula, with progress tracking
- **Shell Snippets** — run shell commands at build time; output appears in your PDF

---

## Deployment

- [Unraid — Community Applications (recommended)](#unraid--community-applications-recommended)
- [Unraid — SSH / compose (alternative)](#unraid--ssh--compose-alternative)
- [Local (Linux / Mac / WSL2)](#local-linux--mac--wsl2)

---

## Unraid — Community Applications (recommended)

This is the easiest way to install on Unraid. All configuration is done through the Unraid Docker GUI — no SSH or compose files required.

### Step 1 — Add the template repository

In Unraid: **Apps** → **Settings** → scroll to **Template Repositories** → add:

```
https://raw.githubusercontent.com/DemianCode/Newspapersync/main/unraid/
```

Click **Save**.

### Step 2 — Install NewspaSync

Go to **Apps** and search for **NewspaSync**. Click **Install**.

Fill in the fields on the template screen. The most important ones:

| Field | Notes |
|---|---|
| **Timezone** | e.g. `America/New_York`, `Europe/London`, `Australia/Sydney` |
| **Schedule Time** | HH:MM 24h format — when to generate each day |
| **Weather Lat / Lon** | Find your coordinates at [latlong.net](https://www.latlong.net) |
| **SMTP fields** | Only needed if you want PDF email delivery or reMarkable email sync |
| **Secrets** (passwords) | Masked in the UI; stored in Unraid's Docker config |

Everything else can be left at the default and changed later. Click **Apply**.

### Step 3 — Auth reMarkable (one-time, required)

Once the container is running, open an Unraid terminal and run:

```bash
docker exec -it NewspaSync rmapi
```

At the `[/]>` prompt:
1. Visit `https://my.remarkable.com/device/browser/connect`, log in, and copy the one-time code
2. Type `exit` and press Enter — do **not** Ctrl+C

The token is saved to your appdata volume and persists across restarts and updates.

### Step 4 — Auth TickTick (if enabled)

```bash
docker exec -it NewspaSync python -m app.sources.ticktick --auth
```

### Updating

In Unraid Docker tab, click **Check for Updates** on the NewspaSync container, then **Update**. Your config, PDFs, and auth tokens (in `/mnt/user/appdata/NewspaSync/`) are never touched by an update.

### How the image is published

A GitHub Actions workflow (`.github/workflows/docker-publish.yml`) automatically builds and pushes `ghcr.io/demiancode/newspapersync:latest` to the GitHub Container Registry on every push to `main`. No manual intervention needed after the initial setup.

---

## Unraid — SSH / compose (alternative)

If you prefer to manage the container via compose files directly:

### Step 1 — SSH and clone

```bash
mkdir -p /mnt/user/appdata/newspapersync
cd /mnt/user/appdata/newspapersync
git clone https://github.com/DemianCode/Newspapersync.git .
```

### Step 2 — Configure secrets

```bash
cp .env.example .env
nano .env
```

### Step 3 — Configure settings

```bash
nano docker-compose.yml
```

Set your timezone, weather coordinates, and schedule time.

### Step 4 — Build and start

```bash
./redeploy.sh
```

Web UI will be at `http://<unraid-ip>:3050`.

### Step 5 — Auth reMarkable

```bash
./auth-remarkable.sh
```

### Updating

```bash
git pull
./redeploy.sh
```

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
| Dashboard | `/` | View the latest PDF, trigger a manual run, see run history (per-edition in editions mode) |
| RSS Sources | `/sources` | Add, edit, and delete RSS feeds — saves immediately |
| Learning | `/learning` | Upload curricula and track lesson progress per course |
| Shell | `/shell` | Define shell commands whose output appears in the PDF |
| Editions | `/editions` | Create and manage named newspaper configurations with per-edition schedules and delivery |
| Settings | `/settings` | Edit weather, schedule, email, appearance and more — no restart needed |

Changes to RSS sources, settings, schedules, and editions all take effect immediately without restarting the container.

---

## Learning Feeds

The Learning Feed turns your newspaper into a daily lesson delivery system. You upload a curriculum as a JSON file and the app delivers one lesson per day, automatically advancing to the next after the PDF is successfully built.

### How it works

1. Go to **Learning** in the web UI
2. Upload a `curriculum.json` file and give the course a name
3. Each day at build time, the current lesson appears in your newspaper under a **Learning** section
4. The lesson index advances only after the PDF is confirmed built — a reMarkable outage won't cause you to miss a lesson
5. Multiple courses run simultaneously; each tracks its own position independently

### Controls

| Control | What it does |
|---|---|
| Active / Pause | Toggle whether this course appears in the next PDF |
| Lessons per day | How many consecutive lessons to include per build (default: 1) |
| Reset Progress | Restart the course from lesson 1 |
| Delete | Remove the course and its curriculum file |

### Curriculum JSON format

The simplest valid curriculum:

```json
{
  "title": "My Course",
  "lessons": [
    {"title": "Lesson 1 title", "content": "Lesson 1 body text."},
    {"title": "Lesson 2 title", "content": "Lesson 2 body text."}
  ]
}
```

Full format with all optional fields:

```json
{
  "title": "Git Basics",
  "description": "Learn Git from the ground up, one concept per day.",
  "lessons": [
    {
      "title": "What is Version Control?",
      "content": "Version control is a system that records changes to files over time, so you can recall specific versions later. Think of it as an unlimited undo history for your entire project."
    },
    {
      "title": "Installing Git",
      "content": "Download Git from https://git-scm.com. On Mac, run: brew install git. On Ubuntu: sudo apt install git. Verify with: git --version"
    },
    {
      "title": "Your First Repository",
      "content": "Create a new folder, open a terminal there, and run:\n\n  git init\n\nThis creates a hidden .git directory. Your project is now tracked by Git."
    }
  ]
}
```

**Field reference:**

| Field | Required | Description |
|---|---|---|
| `title` | No | Course title (shown in the web UI progress display) |
| `description` | No | Short description (shown below the course name in the UI) |
| `lessons` | **Yes** | Array of lesson objects — must have at least one |
| `lessons[].title` | **Yes** | Lesson heading as it appears in the PDF |
| `lessons[].content` | **Yes** | Lesson body text. Newlines (`\n`) are preserved in the PDF. |

### Generating curricula with AI

The fastest way to build a curriculum is to ask an AI assistant (Claude, ChatGPT, etc.) to generate one. Paste this prompt, filling in your topic and lesson count:

---

> Create a curriculum JSON for a self-study course on **[TOPIC]**.
>
> Requirements:
> - **[N] lessons** total, one delivered per day
> - Each lesson should take roughly **5 minutes to read** on a reMarkable e-ink tablet — plain prose only, no markdown formatting, no bullet points, no headers inside the `content` field
> - Lessons should build on each other progressively, starting from absolute basics
> - The `content` field must be self-contained: no "see the previous lesson" references, no hyperlinks, no code blocks (inline code using backticks is fine)
> - Write in a clear, direct style suited to a morning briefing
>
> Output only valid JSON in this exact format, with no extra explanation:
>
> ```json
> {
>   "title": "Course title",
>   "description": "One sentence description",
>   "lessons": [
>     {"title": "Lesson title", "content": "Lesson body text..."},
>     {"title": "Lesson title", "content": "Lesson body text..."}
>   ]
> }
> ```

---

Replace `[TOPIC]` with what you want to learn (e.g. `Git`, `the Linux command line`, `Docker`, `Python basics`, `touch typing`, `stoicism`) and `[N]` with how many days you want the course to run (e.g. `30`).

**Tips for better results:**

- Ask for **plain prose** — bullet points and headers don't render well in the newspaper layout
- Specify **reading time**, not word count — "5 minutes to read" gives the AI a better signal than "200 words"
- Ask the AI to **avoid forward references** — each lesson should stand alone, since you may reset or skip
- For technical topics, ask the AI to use **inline code** (backticks) for commands rather than code blocks — they survive the PDF layout better
- If a lesson comes out too long, ask the AI to split it; if too short, ask it to expand with a concrete example

---

## Shell Snippets

Shell Snippets let you run any command at newspaper build time and include the output as a monospace block in your PDF. This turns your newspaper into a personal command centre — container status, disk usage, server health checks, or anything else you can express as a shell command.

### How it works

1. Go to **Shell** in the web UI
2. Enter a name and a shell command
3. Click **Test** to run the command immediately and preview the output in the browser
4. If the output looks right, save it — it will appear in the **System Status** section of every PDF

### Test before committing

The Test button runs the command live inside the Docker container and shows you the raw output in the UI. This solves two common problems:

- **Environment mismatches** — a command that works in your host terminal may not work inside Docker if it depends on a binary that isn't in the image. Test catches this immediately before it silently fails in a PDF.
- **Formatting surprises** — ANSI colour codes and control characters are stripped automatically, but the test output shows you exactly what will land on the page.

### Controls

| Control | What it does |
|---|---|
| Active / Pause | Toggle whether this snippet runs at build time |
| Timeout | Max seconds to wait for the command (1–60s, default 10s) |
| Test | Run the command now and show output in the UI |
| Save | Update the name, command, or timeout |
| Delete | Remove the snippet |

### Safety

Commands run as root inside the Docker container with `shell=True` (required for pipes, redirects, and subshells). A blocklist prevents obviously destructive patterns:

| Blocked pattern | Why |
|---|---|
| `rm -rf` | Recursive forced deletion |
| `mkfs` | Filesystem formatting |
| `dd if=` | Raw disk writes |
| `chmod 777` | World-writable permissions |
| Fork bombs | Process exhaustion |

Since the container is isolated on a local self-hosted server, the overall risk is low — but the blocklist guards against accidental pastes.

### Output limits

- ANSI escape codes and non-printable control characters are stripped automatically
- Output is truncated at 3000 characters per snippet
- If a command exceeds its timeout it is killed and the error is shown in the PDF block

### Example commands

| Command | What it shows |
|---|---|
| `uptime` | System load average and uptime |
| `df -h /` | Root filesystem disk usage |
| `free -h` | Memory and swap usage |
| `date +"%A %d %B — %H:%M"` | Formatted current timestamp |
| `curl -s wttr.in/Sydney?format=3` | Weather one-liner |
| `ls -lh /mnt/user/ \| head -20` | Directory listing |
| `docker ps --format "table {{.Names}}\t{{.Status}}"` | Running containers* |

> *The `docker` binary is not installed in the container image by default. To use Docker-related commands, mount the Docker socket and add the Docker CLI to the Dockerfile.

---

## File layout

### On disk

```
.
├── config/
│   ├── sources.yml              # RSS feeds (editable via web UI or directly)
│   ├── settings.yml             # Editable settings saved from the web UI
│   ├── appearance.yml           # PDF theme, font size, paper size, columns
│   ├── editions.yml             # Named edition configurations (auto-created on first edition)
│   ├── learning_feeds.yml       # Learning feed state (auto-created)
│   ├── shell_snippets.yml       # Shell snippet definitions (auto-created)
│   └── curricula/               # Uploaded curriculum JSON files (auto-created)
│       └── <feed-id>.json
├── output/                      # Generated PDFs
│   ├── newspaper-YYYY-MM-DD.pdf              # single-edition naming
│   └── newspaper-morning-YYYY-MM-DD.pdf      # editions naming (includes edition ID)
├── rmapi/                       # rmapi auth state (auto-created, gitignored)
├── .env                         # Your secrets (gitignored, local setup only)
├── docker-compose.yml           # All settings (local/SSH setup)
├── unraid/
│   └── newspapersync.xml        # Unraid Community Applications template
├── .github/workflows/
│   └── docker-publish.yml       # Auto-builds and pushes image to GHCR on push to main
├── redeploy.sh                  # Rebuild and restart the container (local/SSH setup)
└── auth-remarkable.sh           # One-time reMarkable auth helper
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

Non-secret settings can be edited from the **Settings** page in the web UI (saved to `config/settings.yml`), or set as environment variables in `docker-compose.yml` / the Unraid template. Environment variables take precedence over the YAML file.

| Variable | Default | Description |
|---|---|---|
| `WEB_ENABLED` | `true` | Enable the web UI on port 3050 |
| `WEB_PORT` | `3050` | Web UI port |
| `SCHEDULE_TIME` | `06:00` | Daily generation time (HH:MM, container local time). Can be changed live from Settings. |
| `RUN_ON_START` | `false` | Also run immediately when the container starts |
| `TZ` | `UTC` | Container timezone |
| `REMARKABLE_SYNC_METHOD` | `rmapi` | `rmapi` (recommended) or `email` |
| `REMARKABLE_FOLDER` | `Newspaper` | Upload folder on reMarkable |
| `REMARKABLE_ARCHIVE_FOLDER` | `Newspaper/Archive` | Archive folder (blank = delete old files) |
| `REMARKABLE_ARCHIVE_KEEP_DAYS` | `30` | Days to keep archived PDFs (0 = keep forever) |
| `WEATHER_ENABLED` | `false` | Enable weather section |
| `WEATHER_LAT` / `WEATHER_LON` | — | Your coordinates |
| `WEATHER_UNITS` | `celsius` | `celsius` or `fahrenheit` |
| `WIKIPEDIA_ENABLED` | `false` | Show Wikipedia Article of the Day |
| `WIKIQUOTE_DAILY_ENABLED` | `false` | Show Wikiquote Quote of the Day |
| `WOTD_ENABLED` | `false` | Show Merriam-Webster Word of the Day |
| `SUDOKU_ENABLED` | `false` | Include a Sudoku puzzle |
| `SUDOKU_DIFFICULTY` | `medium` | `easy`, `medium`, or `hard` |
| `EMAIL_ENABLED` | `false` | Enable email inbox summary section |
| `TICKTICK_ENABLED` | `false` | Enable TickTick tasks section |
| `RSS_ENABLED` | `true` | Enable RSS news section |
| `RSS_MAX_ARTICLES_PER_FEED` | `5` | Max articles per feed |
| `PDF_EMAIL_ENABLED` | `false` | Send the PDF to an email inbox after each run |
| `PDF_EMAIL_RECIPIENT` | — | Comma-separated recipient address(es) for PDF email delivery |
| `AI_SUMMARY_ENABLED` | `false` | Enable AI article summaries |
| `AI_API_BASE_URL` | OpenAI | Swap for local Ollama: `http://ollama:11434/v1` |
| `AI_MODEL` | `gpt-4o-mini` | Model name |

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
