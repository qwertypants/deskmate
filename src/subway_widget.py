"""One shot: MTA subway predictions -> subway_trains and subway_eta AWTRIX apps."""
import argparse
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

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


def window_active(now):
    local = datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
    return local.weekday() < 4 and (8, 45) <= (local.hour, local.minute) < (10, 0)


def owned_apps(apps):
    present = [app for app in apps if app.get("name") in APP_NAMES and app.get("present") is True]
    if any(app.get("origin") != "pushed" for app in present):
        raise ValueError("AWTRIX has a non-pushed subway app; refusing to replace or delete it")
    return {app["name"] for app in present}


def cleanup(client, before):
    present = owned_apps(before)
    if takeover_active():
        return None
    for name in APP_NAMES:
        if name in present:
            client.delete_app(name)
    _, after = client.list_apps()
    for name in APP_NAMES:
        if any(app.get("name") == name and app.get("present") is True for app in after):
            raise ValueError(name + " was not verified absent after cleanup")
    print("Verified subway_trains and subway_eta absent: outside Mon-Thu 08:45-10:00 America/New_York")
    return None


def run(dry_run=False):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)
    if takeover_active():
        return None
    if not window_active(time.time()):
        if dry_run:
            result = {"action": "cleanup", "apps": list(APP_NAMES),
                      "policy": "delete present pushed apps only; refuse foreign ownership; verify both absent"}
            print(json.dumps(result, indent=2))
            return result
        client = Awtrix(os.environ.get("AWTRIX_HOST", "http://192.168.4.94"))
        _, before = client.list_apps()
        return cleanup(client, before)
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
    host = os.environ.get("AWTRIX_HOST", "http://192.168.4.94")
    try:
        ipaddress.ip_address(urlsplit(host).hostname or "")
    except ValueError as exc:
        raise ValueError("Subway publication requires AWTRIX_HOST with a literal IP address "
                         "(for example http://192.0.2.1); DNS resolution is not bounded by "
                         "the socket timeout. Set the clock's IP in .env or the shell.") from exc
    client = Awtrix(host)
    _, before = client.list_apps()
    owned_apps(before)
    if takeover_active():
        return None
    # Re-evaluate the window and catchability after fetches and ownership preflight.
    now = time.time()
    if not window_active(now):
        return cleanup(client, before)
    result = {}
    for name in APP_NAMES:
        if takeover_active():
            return None
        now = time.time()
        local = datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
        cutoff = local.replace(hour=10, minute=0, second=0, microsecond=0).timestamp()
        # TTL starts on the device. Reserve connect and response socket phases,
        # plus 250ms for local processing; DNS hosts are refused above.
        reserve = 2 * client.timeout + 0.25
        lifetime_ms = int((cutoff - now - reserve) * 1000)
        if not window_active(now) or lifetime_ms < 1:
            _, current = client.list_apps()
            return cleanup(client, current)
        result[name] = payloads(feed, scheduled, transfer, now)[name]
        result[name]["lifetimeMs"] = min(result[name]["lifetimeMs"], lifetime_ms)
        result[name]["lifetimeExpiry"] = "remove"
        try:
            client.push_app(name, result[name])
        except (OSError, ValueError):
            # A failed response leaves the write outcome unknown. Reconcile, never retry.
            if not window_active(time.time()):
                _, current = client.list_apps()
                cleanup(client, current)
            raise
        if not window_active(time.time()):
            _, current = client.list_apps()
            return cleanup(client, current)
    _, after = client.list_apps()
    if not window_active(time.time()):
        return cleanup(client, after)
    for name in APP_NAMES:
        if not any(app.get("name") == name and app.get("origin") == "pushed"
                   and all(app.get(key) is True for key in ("present", "enabled", "inLoop")) for app in after):
            raise ValueError(name + " was not verified present, pushed, enabled and inLoop")
    print("Verified subway_trains and subway_eta | realtime=%s | schedule=%s" %
          (feed.warning or "parsed", schedule_warning or "current"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print in-window public-data payloads or out-of-window cleanup policy without contacting AWTRIX")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print("deskmate subway: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
