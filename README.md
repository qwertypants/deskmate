# Desk Mate

One command queries real Codex usage and sends one `codex` pushed app to the TC001.
AWTRIX owns displaying it and rotating it alongside your other apps.

An independent [Google Calendar widget](docs/google-calendar.md) shows up to
three events' local times and titles on one scrolling line with the
`calendardots` icon, and replaces the display with the Great Wave animation
while a meeting is underway. It runs on the Pi every minute and hides when the
next 24 hours are clear.

The independent [subway apps](docs/subway.md) show downtown 3/2 arrivals at
135 St and the estimated Hudson Yards arrival if you leave now, walk six minutes,
and transfer to the 7 at Times Square. Preview with
`python src/subway_widget.py --dry-run`; normal mode pushes `subway_trains` and
`subway_eta`. Unreliable data adds the `attentionwarning` icon and a brief reason.

The selected 32×8 layout shows everything at once:

- A pale terminal prompt icon on the left.
- Blue five-hour percentage **remaining**, with its own bottom-row bar.
- Purple seven-day percentage **remaining**, with its own bottom-row bar.
- Gold available reset count on the right.

For example: terminal icon → **33% · 42% · 3**. The two usage regions are each
11 pixels wide; bars round to the nearest pixel. All text uses compact 3×5 glyphs,
with a condensed `100%` at the upper limit. A missing value is `?`; missing usage
has no bar. Reset counts of ten or more show `+`; the console prints the exact
count. There is no reset bar because Codex provides no total reset allowance.

## Setup and run

Run directly on a computer with an authenticated Codex CLI; a Raspberry Pi is
optional. Installing the full requirements now requires Python **3.10+**;
**3.11+** is recommended for ongoing Google library support. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python src/main.py
```

The Codex command uses `python-dotenv` and the Python standard library for HTTP,
parsing, and SSH orchestration. Calendar authentication and fetching use Google's
Python client libraries. On Raspberry Pi OS, install `python3-venv` with
`sudo apt install python3-venv` if virtual-environment creation requires it.

The machine being queried needs a current Codex CLI with `app-server --stdio`
support, an existing ChatGPT-backed Codex login, and internet access. Check
`codex login status`. API-key-only authentication does not provide these account
limits. In Pi-over-SSH mode, these requirements apply to the Mac, not the Pi.

## Configuration

Edit `.env`. Existing shell environment variables take precedence. The file is
loaded relative to the project, even when you run the script from another directory.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AWTRIX_HOST` | Built-in fallback | Set this to your AWTRIX NG base URL |
| `CODEX_MAX_AGE_SECONDS` | `3600` | Maximum age of returned metrics and display lifetime, in seconds |
| `CODEX_SSH_HOST` | empty | Query locally, or use `user@mac` / an SSH config alias |
| `CODEX_HOME` | `~/.codex` | Codex data directory; in SSH mode this is on the Mac |
| `MEETING_BRIGHTNESS` | `120` | Display brightness while a calendar meeting is underway |

Leave `CODEX_HOME` blank for the normal location. The reader also honors the remote
Mac's existing `CODEX_HOME` environment variable when no explicit path is supplied.
Use an absolute path if your Mac stores Codex data elsewhere.

## Privacy and security

This project is designed for a private, trusted display. The Google Calendar
integration requests only read-only access to the primary calendar and sends the
selected event title and time to the AWTRIX display. The title may be visible to
anyone who can see the display; that is expected for a desk display and is not
written to the application logs. The integration never creates, edits, or deletes
calendar events.

OAuth client files, refresh tokens, and `.env` are local secrets. They are ignored
by Git and should never be committed, pasted into issues, or included in a public
archive. The token directory is created with mode `700` and token files with mode
`600`.

The AWTRIX HTTP API is a privileged local control plane: Desk Mate can change
settings, app order, and scripts. Keep the clock on a trusted LAN or otherwise
protect its API; do not expose `AWTRIX_HOST` to the public internet. HTTP is
acceptable only when the network is trusted. Use the device's authentication and
HTTPS options when the network is shared or untrusted.

The repository contains synthetic test titles and token-shaped placeholder values,
not real calendar data or credentials. Before publishing a fork, check local
`.env`, `.google-calendar/`, logs, and custom credential paths even though the
standard paths are Git-ignored.

### Running on the Pi using your Mac's data

The Pi needs LAN access to AWTRIX and SSH key access to the Mac. Enable **Remote
Login** on macOS, establish SSH key authentication, and verify the Mac's host key
interactively before running the widget. On the Pi:

```sh
ssh your-user@your-mac.local 'python3 --version'
ssh -o BatchMode=yes your-user@your-mac.local 'python3 --version'
```

Set `CODEX_SSH_HOST=your-user@your-mac.local` in the Pi's `.env`, then run
`python src/main.py` there. The Mac needs Python 3.9+ and an authenticated Codex CLI;
it does not need Desk Mate or `python-dotenv` installed for SSH reads. The Pi sends
the same reader code through SSH stdin to `python3 -`; only selected usage JSON
comes back. SSH connects within five seconds and the entire read has a 30-second
timeout. It never asks for passwords or copies credentials/transcripts. The Mac
must be awake and reachable. The reader searches `PATH`, then `~/.local/bin/codex`;
make Codex available there in the Mac's noninteractive SSH environment.
Pi-over-SSH execution has been verified with Raspberry Pi OS and macOS.

## Where usage comes from

Each run starts a short-lived `codex app-server --stdio` subprocess, initializes
its documented JSONL protocol, and calls `account/rateLimits/read`. The server
uses the existing Codex login on that machine; Desk Mate never reads or copies
the credential files. No model turn is started, and no reset is consumed.

The official [Codex app-server API](https://learn.chatgpt.com/docs/app-server)
provides percentage **used**, window length, reset timestamps, and
`rateLimitResetCredits.availableCount`. The count is authoritative; the credit
detail list may be incomplete. A missing reset count or weekly window is displayed as `?`, never zero.
Unknown usage has no bar.

Your account reports a **seven-day** secondary window, not five days. The reader
checks the window lengths rather than relabeling a different window as weekly.
The display converts the API’s percentage used to percentage remaining
(`100 - used_percent`). Blue means five-hour allowance left; purple means
seven-day allowance left. Text and bars use the same rounded remaining value
(halves rounded up), so a full bar means the allowance is entirely available. Resets are an available count;
there is no total from which to compute a meaningful percentage.

V1 used local session snapshots, which omitted reset credits. This version uses
the official live query for all three metrics, with no session-file fallback.
The subprocess has a 20-second total query timeout and is stopped afterward.
The CLI/app-server interface is experimental and requires a compatible Codex
version. Authentication, connection, malformed data, and timeout failures exit
nonzero before any push. Future-dated, expired, or stale metrics are also rejected.

## AWTRIX behavior and verification

The client follows the official AWTRIX NG
[HTTP API](https://ang.blueforcer.de/reference/http/) and
[payload reference](https://ang.blueforcer.de/reference/payload/).
The single screen uses `PUT /api/v1/apps/pushed/codex` with a `draw` command:

```text
{"draw":[["bitmap",0,0,32,8,"<base64 RGB888 pixels>"]],"lifetimeMs":3600000,"lifetimeExpiry":"remove"}
```

The icon, numbers, and two independent bars are encoded in one small bitmap
(768 RGB bytes before base64), using AWTRIX's normal drawing API. No downloaded
icon, extra rendering dependency, device script, or scrolling is needed. AWTRIX
still handles the app loop. Other apps and rotation settings are preserved.

Lifetime is the smaller of the remaining age allowance and time until either
known usage window resets. Rerunning updates the same `codex` app. A preflight
refuses to replace a non-pushed app named `codex`. A push requires a successful
HTTP status and `{"ok":true}`; `GET /api/v1/apps` must confirm the replacement is
present, pushed, enabled, and in the loop.

Only after this verification, the old `codex_week` and `codex_resets` pushed pages
are deleted if present. Scripts with those names are left alone. Cleanup is
verified afterward. If a push or cleanup fails, the console reports it and exits
nonzero; old pages remain until removed or their existing lifetime expires.
Disabled `codex` must be enabled using AWTRIX's own controls.

Each invocation queries fresh data. The optional Pi cron job below runs every
10 minutes from 6:00am through 8:00pm Eastern time.
The app disappears when its lifetime runs out or AWTRIX reboots; the next
successful run recreates it. There is no persistent Python daemon, database,
Docker, UI, Berry application, or firmware modification.

On the **physical TC001**, confirm the small numbers and terminal icon are readable,
the blue and purple bars match their values, and `codex` rotates normally alongside
your other apps. HTTP success and a screen-pixel API readback cannot establish
physical brightness or legibility.

## Scheduled updates on the Pi

This is optional. After verifying a manual run, replace every example path with
your checkout path and install these entries with `crontab -e` as the Pi user:

```cron
CRON_TZ=America/New_York
*/10 6-19 * * * /usr/bin/flock -n /home/your-user/deskmate/.widget.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/main.py >> /home/your-user/deskmate/widget.log 2>&1 # deskmate-codex
0 20 * * * /usr/bin/flock -n /home/your-user/deskmate/.widget.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/main.py >> /home/your-user/deskmate/widget.log 2>&1 # deskmate-codex
```

It runs every 10 minutes from 6:00am through 7:50pm, plus once at 8:00pm,
using Eastern time (including daylight saving time), and resumes after reboot.
The virtual environment and project `.env` are used without shell activation.
`flock` prevents overlapping runs. Check `crontab -l` and
`tail -n 20 /home/your-user/deskmate/widget.log` on the Pi. Remove both entries
with `crontab -e` to stop scheduled updates.

The Mac must have Remote Login enabled and accept the Pi's SSH key without a
password. Sleeping/offline Mac or network failures are logged; cron tries again
at the next scheduled fetch. The display may disappear between refreshes when
the one-hour freshness lifetime expires or a usage window resets. Failed queries
never push invented values or extend the previous reading's lifetime.

## Tests and manual updates

```sh
source .venv/bin/activate
python -m unittest discover -s tests -v
```

## Overnight Pixel Fireplace mode

The controller uses the existing AWTRIX `Pixel-Fireplace` script, keeping its
procedural fire animation intact. The script must already be installed on the
clock; idle mode refuses to substitute another animation. It keeps the current
brightness and app loop in a private state file, dims the display to 10/255 by
default, and restores both at 6:00am.

The schedule uses New York time and can be adjusted with `IDLE_TIMEZONE`,
`IDLE_BRIGHTNESS`, and `IDLE_STATE_PATH`. Add these entries to the Pi user's
crontab, replacing the checkout path:

```cron
CRON_TZ=America/New_York
0 20 * * * /usr/bin/flock -n /home/your-user/deskmate/.idle-mode.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/idle_mode.py enter >> /home/your-user/deskmate/idle-mode.log 2>&1
0 6 * * * /usr/bin/flock -n /home/your-user/deskmate/.idle-mode.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/idle_mode.py exit >> /home/your-user/deskmate/idle-mode.log 2>&1
@reboot /usr/bin/flock -n /home/your-user/deskmate/.idle-mode.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/idle_mode.py sync >> /home/your-user/deskmate/idle-mode.log 2>&1
```

The controller refuses to replace a non-script app named `pixel-fireplace`,
and verifies the script is present, enabled, and in the loop after entry.

Idle mode stands down while a calendar meeting is showing the Great Wave
animation, and the dimmed fireplace resumes when that meeting ends.

After changing code, rerun the tests and `python src/main.py`. For another checkout
on the Pi, commit/push the intended changes from your development machine, then:

```sh
cd /path/to/deskmate
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements.txt
python src/main.py
```

Keep each machine's `.env` local. There is no background service to restart.
