"""One shot: primary Google Calendar -> a scrolling AWTRIX pushed app."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from awtrix import Awtrix
from google_calendar import calendar_service, event_payload, fetch_events, load_credentials, select_events
import meeting_mode


APP_NAME = "google_calendar"


def utcnow():
    return datetime.now(timezone.utc)


def ongoing(event, now):
    return event.start <= now.astimezone(timezone.utc) < event.end


def awtrix_call(method, *args):
    """AWTRIX errors can echo display text; keep provider bodies out of logs."""
    try:
        return method(*args)
    except (OSError, ValueError) as exc:
        raise ValueError("AWTRIX request failed; check AWTRIX_HOST, network connectivity, "
                         "and the clock's app settings, then retry") from exc


def run(authorize=False):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)

    def configured_path(name, default):
        path = Path(os.environ.get(name) or default).expanduser()
        return path if path.is_absolute() else root / path

    credentials_path = configured_path("GOOGLE_CALENDAR_CREDENTIALS_PATH", ".google-calendar/credentials.json")
    token_path = configured_path("GOOGLE_CALENDAR_TOKEN_PATH", ".google-calendar/token.json")
    try:
        display_zone = ZoneInfo(os.environ.get("GOOGLE_CALENDAR_TIMEZONE") or "America/New_York")
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("GOOGLE_CALENDAR_TIMEZONE must be an IANA timezone such as America/New_York") from exc
    if authorize:
        print("Opening Google Calendar sign-in in your browser; finish within three minutes.", flush=True)
    credentials = load_credentials(credentials_path, token_path, authorize=authorize)
    if authorize:
        print("Google Calendar authorized; token saved with owner-only permissions.")
        return
    service = calendar_service(credentials)
    try:
        events = fetch_events(service, utcnow())
    finally:
        service.close()

    client = Awtrix(os.environ.get("AWTRIX_HOST", "http://192.168.4.94"))
    _, apps = awtrix_call(client.list_apps)
    # A pushed app that removed itself leaves an origin-null tombstone, which is
    # not an app we could replace; only refuse a present foreign one.
    if any(app.get("name") == APP_NAME and app.get("present") is True
           and app.get("origin") not in (None, "pushed") for app in apps):
        raise ValueError("AWTRIX has a non-pushed google_calendar app; refusing to replace or delete it")
    # Select again after the API and preflight requests: an event may have ended.
    now = utcnow()
    selected = select_events(events, now)
    print("Calendar label evaluation: timezone=%s local_date=%s" %
          (display_zone.key, now.astimezone(display_zone).date().isoformat()))
    # The wave is poll-driven: this once-a-minute run decides whether it holds the display.
    brightness, wave_state, idle_state = meeting_mode.config()
    if any(ongoing(event, now) for event in selected):
        # A meeting gets the display to itself; the text page would be disabled anyway.
        meeting_mode.enter(client, wave_state, idle_state, brightness)
        print("Verified meeting wave is showing for the event in progress")
        return
    # Release before any other branch: an emptied calendar must not strand the wave.
    if meeting_mode.active(wave_state):
        meeting_mode.exit_mode(client, wave_state)
    if not selected:
        if any(app.get("name") == APP_NAME and app.get("present") is True for app in apps):
            awtrix_call(client.delete_app, APP_NAME)
            _, apps = awtrix_call(client.list_apps)
            if any(app.get("name") == APP_NAME and app.get("present") is True for app in apps):
                raise ValueError("google_calendar is still present after removal; check AWTRIX")
        print("google_calendar hidden: no eligible events within 24 hours.")
        return
    payload = event_payload(selected, now, display_zone)
    awtrix_call(client.push_app, APP_NAME, payload)
    _, apps = awtrix_call(client.list_apps)
    if not any(app.get("name") == APP_NAME and app.get("origin") == "pushed"
               and all(app.get(key) is True for key in ("present", "enabled", "inLoop")) for app in apps):
        raise ValueError("google_calendar was not verified present, pushed, enabled and inLoop; "
                         "check the clock's app settings")
    print("Verified google_calendar: present, pushed, enabled, inLoop | lifetime %dms" % payload["lifetimeMs"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize", action="store_true", help="sign in once in a browser on your Mac")
    args = parser.parse_args()
    try:
        run(authorize=args.authorize)
    except (OSError, ValueError) as exc:
        print("deskmate calendar: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
