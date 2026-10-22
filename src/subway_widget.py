"""One shot: MTA subway predictions -> subway_trains and subway_eta AWTRIX apps."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

from awtrix import Awtrix
from awtrix_takeover import load
from meeting_mode import resolve
from subway import Feed, parse_feed, payloads
from subway_schedule import REALTIME_URL, download, load_schedule

APP_NAMES = ("subway_trains", "subway_eta")


def takeover_active():
    for name, default in (("MEETING_STATE_PATH", ".meeting-mode-state.json"),
                          ("IDLE_STATE_PATH", ".idle-mode-state.json")):
        state = load(resolve(name, default))
        if state is not None and not isinstance(state, dict):
            raise ValueError("AWTRIX takeover state must be an object")
        if state and state.get("active"):
            print("Subway update deferred: AWTRIX takeover active")
            return True
    return False


def run(dry_run=False):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)
    if not dry_run and takeover_active():
        return None
    scheduled, transfer, schedule_warning = load_schedule(root / ".subway/schedule.zip", time.time())
    try:
        data = download(REALTIME_URL, 5_000_000)
    except (OSError, ValueError):
        feed = Feed(int(time.time()), warning="feed offline")
    else:
        try:
            feed = parse_feed(data, time.time())
        except ValueError:
            feed = Feed(int(time.time()), warning="feed invalid/stale")
    if dry_run:
        result = payloads(feed, scheduled, transfer, time.time())
        print(json.dumps(result, indent=2))
        return result
    client = Awtrix(os.environ.get("AWTRIX_HOST", "http://192.168.4.94"))
    _, before = client.list_apps()
    if any(app.get("name") in APP_NAMES and app.get("present") is True
           and app.get("origin") != "pushed" for app in before):
        raise ValueError("AWTRIX has a non-pushed subway app; refusing to replace it")
    if takeover_active():
        return None
    # Re-evaluate catchability after fetches and ownership preflight.
    result = payloads(feed, scheduled, transfer, time.time())
    for name in APP_NAMES:
        client.push_app(name, result[name])
    _, after = client.list_apps()
    for name in APP_NAMES:
        if not any(app.get("name") == name and app.get("origin") == "pushed"
                   and all(app.get(key) is True for key in ("present", "enabled", "inLoop")) for app in after):
            raise ValueError(name + " was not verified present, pushed, enabled and inLoop")
    print("Verified subway_trains and subway_eta | realtime=%s | schedule=%s" %
          (feed.warning or "parsed", schedule_warning or "current"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="fetch public data and print payloads without contacting AWTRIX")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print("deskmate subway: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
