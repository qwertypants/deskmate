"""Reversible exclusive control of the AWTRIX app loop, shared by controllers."""

import json
from pathlib import Path


def direct(method, *args, **kwargs):
    return method(*args, **kwargs)


def guarded(method, *args, **kwargs):
    """AWTRIX errors can echo display text; keep provider bodies out of logs."""
    try:
        return method(*args, **kwargs)
    except OSError as exc:
        raise ValueError("AWTRIX request failed; check AWTRIX_HOST and the network") from exc


def caller(call):
    return call or direct


def load(path):
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, ValueError) as exc:
        raise ValueError("AWTRIX takeover state is unreadable; check the device state and remove the file") from exc


def save(path, state):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(state) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def snapshot(apps, settings, owner_names, current_app=None):
    order = [app["name"] for app in apps
             if app.get("enabled") is True and app.get("inLoop") is True
             and app["name"] not in owner_names]
    return {"active": True,
            "brightness": settings.get("brightness", 120),
            "autoBrightness": settings.get("autoBrightness", False),
            # Only apps that can actually run belong in the saved loop. Older
            # snapshots could include disabled apps here when AWTRIX reported
            # inLoop=True for them; enabled apps outside the loop stay omitted.
            "order": order,
            "disabled": [app["name"] for app in apps
                         if (not app.get("enabled") or
                             (app.get("origin") == "script" and app.get("inLoop") is not True))
                         and app["name"] not in owner_names],
            # Presence is not the same as the app currently on the display.
            # Save only a current app that will be restored to the loop.
            "activeApp": current_app if isinstance(current_app, str) and current_app in order else None}


def claim(client, state_path, owner, owner_names, brightness, other_state_path, call=direct):
    """Take the loop exclusively. Returns the snapshot, or None to defer."""
    call = caller(call)
    other = load(other_state_path) if other_state_path else None
    if other and other.get("active"):
        return None
    _, apps = call(client.list_apps)
    existing = next((app for app in apps if app.get("name") == owner), None)
    if existing and existing.get("origin") != "script":
        raise ValueError("AWTRIX has a non-script app named " + owner + "; refusing to replace it")
    _, settings = call(client.get_settings)
    _, device = call(client.get_device)
    state = load(state_path)
    # Snapshot once per takeover: a repeated run must not capture the reshaped loop.
    if not state or not state.get("active"):
        save(state_path, snapshot(apps, settings, owner_names, device.get("currentApp")))
    client.set_app_order([owner], [app["name"] for app in apps if app.get("name") != owner])
    call(client.patch_settings, {"autoBrightness": False, "brightness": brightness})
    call(client.activate_app, owner)
    return load(state_path)


def release(client, state_path, owner, owner_names, call=direct):
    call = caller(call)
    state = load(state_path)
    _, apps = call(client.list_apps)
    if any(app.get("name") == owner and app.get("origin") != "script" for app in apps):
        raise ValueError("AWTRIX has a non-script app named " + owner + "; refusing to remove it")
    disabled = [name for name in (state.get("disabled", []) if state else
                                  [app["name"] for app in apps if not app.get("enabled")]) if name not in owner_names]
    # Exclude disabled apps even when restoring older snapshots whose order
    # included an app AWTRIX reported as both inLoop and disabled.
    disabled_set = set(disabled)
    order = [name for name in (state.get("order", []) if state else
                               [app["name"] for app in apps if app.get("enabled") is True
                                and app.get("inLoop") is True])
             if name not in owner_names and name not in disabled_set]
    # Keep the owner's script installed for its next run, but out of the loop.
    disabled.append(owner)
    client.set_app_order(order, disabled)
    if state and state.get("active"):
        call(client.patch_settings, {"autoBrightness": bool(state.get("autoBrightness", False)),
                                     "brightness": int(state.get("brightness", 120))})
        active_app = state.get("activeApp")
        if active_app and active_app in order:
            call(client.activate_app, active_app, fast=True)
    state_path.unlink(missing_ok=True)
