"""Show the Great Wave Berry animation while a calendar meeting is underway."""

import argparse
import os
from pathlib import Path
import sys

from awtrix import Awtrix
import awtrix_takeover
from awtrix_takeover import claim, guarded, release

# AWTRIX app names must match [A-Za-z0-9_-]{1,32}, so the shipped "Great Wave"
# display name from the @name header cannot also be the app name.
APP_NAME = "deskmate-wave"
DEFAULT_BRIGHTNESS = 120
DEFAULT_STATE = ".meeting-mode-state.json"
DEFAULT_IDLE_STATE = ".idle-mode-state.json"


def source_path():
    return Path(__file__).resolve().parent.parent / "packs/transitions/great-wave.be"


def wave_source():
    path = source_path()
    source = path.read_text() if path.exists() else ""
    if not source.strip():
        raise ValueError("Great Wave source is missing from packs/transitions; update this checkout first")
    return source


def config():
    try:
        brightness = int(os.environ.get("MEETING_BRIGHTNESS", str(DEFAULT_BRIGHTNESS)))
    except ValueError as exc:
        raise ValueError("MEETING_BRIGHTNESS must be an integer from 0 to 255") from exc
    if not 0 <= brightness <= 255:
        raise ValueError("MEETING_BRIGHTNESS must be an integer from 0 to 255")
    return brightness, resolve("MEETING_STATE_PATH", DEFAULT_STATE), \
        resolve("IDLE_STATE_PATH", DEFAULT_IDLE_STATE)


def resolve(name, default):
    path = Path(os.environ.get(name) or default).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[1] / path


def verified(apps):
    wave_is_ready = any(app.get("name") == APP_NAME and app.get("origin") == "script"
                        and app.get("error") is None
                        and all(app.get(key) is True for key in ("present", "enabled", "inLoop"))
                        for app in apps)
    loop_members = [app for app in apps
                    if app.get("enabled") is True and app.get("inLoop") is True]
    return wave_is_ready and len(loop_members) == 1 and loop_members[0].get("name") == APP_NAME


def extra_loop_apps(apps):
    return [app.get("name") for app in apps
            if app.get("name") != APP_NAME and app.get("enabled") is True
            and app.get("inLoop") is True]


def enter(client, state_path, idle_state_path, brightness):
    _, apps = client.list_apps()
    existing = next((app for app in apps if app.get("name") == APP_NAME), None)
    if existing and existing.get("origin") != "script":
        raise ValueError("AWTRIX has a non-script " + APP_NAME + " app; refusing to replace it")
    if not existing or existing.get("error") is not None:
        client.install_script(APP_NAME, wave_source())
    # A meeting outranks overnight idle mode. Passing no other state path means the
    # wave never defers; idle_mode.enter is the side that stands down instead.
    state = claim(client, state_path, APP_NAME, {APP_NAME}, brightness, None, call=guarded)
    _, apps = client.list_apps()
    if not verified(apps):
        if extra_loop_apps(apps):
            disabled = [app["name"] for app in apps if app.get("name") != APP_NAME]
            client.set_app_order([APP_NAME], disabled)
            client.activate_app(APP_NAME)
            _, apps = client.list_apps()
        if not verified(apps):
            extras = extra_loop_apps(apps)
            detail = "; extra active loop apps: " + ", ".join(
                str(name) for name in extras) if extras else ""
            raise ValueError(APP_NAME + " was not verified as the sole active loop app"
                             " (present, script, enabled, inLoop and error-free)" + detail)
    return state


def exit_mode(client, state_path):
    release(client, state_path, APP_NAME, {APP_NAME}, call=guarded)


def active(state_path):
    """True only while a meeting takeover is open, so idle runs cost nothing."""
    state = awtrix_takeover.load(state_path)
    return bool(state and state.get("active"))


def run(command):
    brightness, state_path, idle_state_path = config()
    client = Awtrix(os.environ.get("AWTRIX_HOST", "http://192.168.4.94"))
    if command == "enter":
        enter(client, state_path, idle_state_path, brightness)
        print("Verified meeting wave: only enabled app in loop", flush=True)
    else:
        exit_mode(client, state_path)
        print("Verified normal AWTRIX mode restored after meeting", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("enter", "exit"))
    args = parser.parse_args()
    try:
        run(args.command)
    except (OSError, ValueError) as exc:
        print("deskmate meeting mode: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
