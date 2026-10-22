# Subway arrival estimates

The two independent pushed apps answer what trains are coming and when leaving
now would get you to 34 St-Hudson Yards. They do not take an arrival deadline,
recommend a departure time, judge lateness, or sort routes by fastest arrival.

- `subway_trains` shows the next two downtown arrivals within an hour at 135 St,
  with 3 first and 2 second. `135 3 12:08p,12:16p | 2 12:10p` is an example.
- `subway_eta` shows the next catchable departure for each route, in the same
  order, and its approximate final arrival. `HY 3@12:08p ~12:33p | 2@12:10p
  ~12:35p` means boarding the 3 at 12:08 would reach Hudson Yards around 12:33.
  A route with insufficient data or no catchable train says `no estimate`.

Catchability assumes leaving the apartment at the current evaluation time and
walking six minutes to the platform. That is an initial assumption for a quick
walker, to refine from observations. It is `WALK_SECONDS` in `src/subway.py`.
The trip uses downtown platforms `224S` at 135 St and `127S` at Times Sq-42 St,
then westbound 7/7X from `725S` to `726S` at Hudson Yards. The latter S suffix is
MTA's direction identifier, despite the geographic westbound trip.

The transfer takes the minimum from MTA `transfers.txt`, currently 180 seconds
from station 127 to 725. When the static schedule is unavailable, the same
verified three-minute minimum is the initial transfer assumption. The estimate
uses the first available 7 departure after that transfer.
Arrival means arrival at the final platform. Exit walking is not included.
A held train can arrive before its departure; the trains app shows arrival,
and catchability uses departure. `+1d` marks an arrival after local midnight.

## Run

Use the repository's Python 3.10+ environment and requirements:

```sh
python -m pip install -r requirements.txt
python src/subway_widget.py --dry-run
```

Dry run downloads public MTA data, updates the local schedule cache, and prints
the exact two JSON payloads. It never contacts AWTRIX. Normal mode pushes both
apps to `AWTRIX_HOST` from the project `.env` or shell environment:

```sh
python src/subway_widget.py
```

No API key or MTA login is required for these feeds. No credentials, account
registration, or agreement acceptance is automated. MTA publishes the feeds
subject to its [terms](https://www.mta.info/developers/terms-and-conditions).
Use remains subject to those terms.

There is no central launcher or app registry in this repository. Like Calendar,
this is a separate one-shot command. It reuses `Awtrix`, refuses to overwrite
present non-pushed apps with either name, and verifies both apps are pushed,
present, enabled, and in the loop. Both names must be enabled in AWTRIX's app
controls. It does not change brightness, app order, or unrelated apps. An active
meeting or idle takeover state defers the update before any network requests;
custom `MEETING_STATE_PATH` and `IDLE_STATE_PATH` are honored.

Optional scheduling, after a manual run and device verification, is one poll
per minute. Replace the example paths and install it yourself with `crontab -e`:

```cron
* * * * * /usr/bin/flock -n /home/your-user/deskmate/.subway.lock /home/your-user/deskmate/.venv/bin/python /home/your-user/deskmate/src/subway_widget.py >> /home/your-user/deskmate/subway.log 2>&1 # deskmate-subway
```

This does not replace existing cron lines. Each invocation reads the project
`.env`, even from another working directory. Takeover transitions and this poll
should not be run concurrently; the dedicated lock prevents overlapping subway
polls, while the active-state check preserves existing takeovers. It is not a
cross-controller lock. No schedule is installed by this feature.

## Data and reliability

[MTA developer resources](https://www.mta.info/developers) links to the current
[realtime feed catalog](https://api.mta.info/). Its published combined URL is
`https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs` for
1/2/3/4/5/6/7/S. Anonymous HTTP 200 protobuf access, actual 2/3/7 trip updates,
and the required directed platform predictions were verified on 2026-10-22.
A guessed `gtfs-7` URL returned HTTP 200 XML `NoSuchKey`, so it is not used.
HTTP success alone is insufficient; the parser requires an initialized protobuf,
a full-dataset header, and a usable timestamp.

The [MTA reference](https://api.mta.info/GTFS.pdf) explains the NYCT extension
fields, terminal times, and prediction limitations. The old PDF predates the 7
in the combined feed. `nyct_subway.py` registers the relevant fields from the
[MTA-linked protobuf](https://raw.githubusercontent.com/OneBusAway/onebusaway-gtfs-realtime-api/master/src/main/proto/com/google/transit/realtime/gtfs-realtime-NYCT.proto).
Standard messages use the official MobilityData `gtfs-realtime-bindings`.

There is no MTA end-to-end apartment-to-destination ETA API in this integration.
It joins predictions on each individual trip, adds the walking and transfer
assumptions, then selects a connecting 7. It never joins two unrelated trains'
stop times. Missing, skipped, reversed, or unusable destination predictions do
not produce an invented ride duration.

Source signals determine whether a usable prediction needs a warning:

- MTA describes vehicle timestamps as last detected movement and suggests a
  90-second stalled threshold. A trip with older movement warns `train stalled`.
  Missing movement or assignment information warns instead of assuming health.
- Unassigned trains, changed scheduled/actual tracks, a trip delay alert,
  positive time uncertainty, or old trip-update timestamps also warn. Normal
  origin/destination terminal track differences alone do not warn. Trip alerts
  are read from the combined train feed. The
  separate general service-alert feed is not integrated.
- Project freshness policy accepts feed data up to 90 seconds old normally,
  then warns `old feed` through 300 seconds. Beyond 300 seconds, or more than
  30 seconds in the future, the feed is unusable. These age limits are project
  policy, not an MTA accuracy guarantee.

The [supplemented static schedule](https://rrgtfsfeeds.s3.amazonaws.com/gtfs_supplemented.zip)
is downloaded at most hourly and compacted to the relevant routes/platforms in
ignored `.subway/schedule.zip`. The verified download was about 21 MB; the local
subset was about 173 KB. Downloads have a 20-second socket timeout and size
limits. No ZIP paths are extracted. Service weekdays, date exceptions, feed
validity dates, prohibited transfers, pickup/drop-off restrictions, overnight
GTFS times, and New York DST service epochs are checked.

Realtime data replaces static first-leg departures whenever the feed is usable,
even if the live set is empty. Scheduled 7 connections are permitted only beyond
both live prediction coverage and the larger of the advertised replacement
window and a conservative 30-minute floor. A known matching realtime trip,
including a cancelled or skipped trip, is not reintroduced from static data.
MTA warns that static/realtime trip identifiers cannot always be matched. This
is not a general journey planner and cannot guarantee detection of every service
change. A schedule-derived connection warns `7 schedule`. When the realtime
feed fails, current scheduled first and second legs can supply a rough estimate
with `schedule only` and the feed failure reason. A failed hourly refresh can
reuse a cache up to 24 hours old with `old schedule`; otherwise unavailable
schedule data cannot invent departures. No meaningful full trip means
`no estimate`.

Only unreliable or missing data adds `icon: attentionwarning` and brief reason
text. Ordinary walking assumptions and the approximate `~` marker do not trigger
a warning. Ensure that icon ID already exists on the device; this command does
not install icons. No warning means the selected source signals passed these
checks, not that the arrival is guaranteed.

Payloads expire after at most 60 seconds, sooner when a shown train departs,
the selected train stops being catchable, or the feed crosses a freshness limit.
Absolute local clock times avoid a frozen minute countdown. The next poll
recomputes from the new leave-now time. Failed AWTRIX writes or readback return
nonzero; the two separate pushes are not atomic and are never blindly retried.
A successfully published rough/no-estimate state returns zero and logs its source
status. No data error is converted to a reassuring empty screen.

## Verification boundary

Run `python -m unittest discover -s tests -v` as in the README. Subway tests use
synthetic protobuf/ZIP fixtures and mocked network/device boundaries. Syntax and
whitespace checks are `python -m compileall -q src tests` and `git diff --check`.
A live `--dry-run` verifies current MTA access and parsing without installing or
activating device apps. Neither tests nor a dry run establish physical display
legibility, icon availability, actual walking time, transfer comfort, or Pi cron
execution. Those require a separately authorized device/commute check.
