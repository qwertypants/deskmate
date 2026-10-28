"""One shot: live Codex limits -> one 32x8 AWTRIX pushed app."""

import base64
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from awtrix import Awtrix
from codex import freshness, read_usage


FONT = {
    "0": "111 101 101 101 111", "1": "010 110 010 010 111",
    "2": "111 001 111 100 111", "3": "111 001 111 001 111",
    "4": "101 101 111 001 001", "5": "111 100 111 001 111",
    "6": "111 100 111 101 111", "7": "111 001 010 010 010",
    "8": "111 101 111 101 111", "9": "111 101 111 001 111",
    "%": "101 001 010 100 101", "?": "111 001 010 000 010",
    "+": "000 010 111 010 000", ":": "0 1 0 1 0",
}

EASTERN = ZoneInfo("America/New_York")


def rounded_remaining(value):
    return None if value is None else int(math.floor(100 - value["used_percent"] + 0.5))


def primary_reset_clock(primary):
    """Return the primary reset as Eastern wall-clock h:mm text."""
    try:
        reset = primary["resets_at"]
        if (isinstance(reset, bool) or not isinstance(reset, (int, float))
                or not math.isfinite(reset) or reset <= 0):
            raise ValueError
        local = datetime.fromtimestamp(reset, timezone.utc).astimezone(EASTERN)
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("Invalid Codex resets_at") from exc
    return "%d:%02d" % ((local.hour % 12) or 12, local.minute)


def payloads(snapshot, lifetime_ms):
    """The approved pixel layout, encoded as AWTRIX's native RGB888 bitmap."""
    pixels = bytearray(32 * 8 * 3)

    def pixel(x, y, color):
        if not (0 <= x < 32 and 0 <= y < 8):
            raise ValueError("Codex layout exceeds the 32x8 display")
        offset = (y * 32 + x) * 3
        pixels[offset:offset + 3] = bytes.fromhex(color)

    def glyph(rows, x, y, color):
        for dy, row in enumerate(rows.split()):
            for dx, bit in enumerate(row):
                if bit == "1":
                    pixel(x + dx, y + dy, color)

    def text(value, x, color):
        for index, char in enumerate(value):
            glyph(FONT[char], x + index * 4, 1, color)

    def big_clock(value, x, width, color):
        """Draw h:mm with the full-size FONT, centered in a `width` column span."""
        widths = [len(FONT[char].split()[0]) for char in value]
        ink = sum(widths) + len(widths) - 1
        if ink > width:
            raise ValueError("Codex clock exceeds its column budget")
        cursor = x + (width - ink) // 2
        for char, glyph_width in zip(value, widths):
            glyph(FONT[char], cursor, 1, color)
            cursor += glyph_width + 1

    def draw_value(x, remaining, color):
        if remaining == 100:
            # A slim 1 and two zeros sharing an edge keep 100% in eleven columns.
            glyph("1 1 1 1 1", x, 1, color)
            glyph(FONT["0"], x + 2, 1, color)
            glyph(FONT["0"], x + 4, 1, color)
            glyph(FONT["%"], x + 8, 1, color)
            return
        text("?" if remaining is None else str(remaining) + "%", x, color)

    def draw_bar(x, width, remaining, color):
        if remaining is None:
            return
        filled = int(math.floor(width * remaining / 100 + 0.5))
        for column in range(width):
            pixel(x + column, 7, color if column < filled else "23313d")

    def draw_gauge(x, width, remaining, color):
        """Full-height vertical bar; the unfilled share sits above the fill."""
        if remaining is None:
            return
        filled = int(math.floor(8 * remaining / 100 + 0.5))
        for row in range(8):
            shade = color if row >= 8 - filled else "23313d"
            for column in range(width):
                pixel(x + column, row, shade)

    # Terminal prompt and underscore; it occupies columns 0..2.
    glyph("100 010 001 010 100", 0, 1, "d7f8ee")
    glyph("11", 1, 6, "d7f8ee")

    primary_remaining = rounded_remaining(snapshot["primary"])
    primary_depleted = (primary_remaining == 0)

    # A depleted primary shows a clock instead of a percentage, so it needs more
    # columns than the purple window. The purple section turns into a full-height
    # gauge, and the reset count keeps its full-size glyph.
    if primary_depleted:
        blue_x, blue_w = 4, 17        # 4..20
        gauge_x, gauge_w = 22, 5      # 22..26, separator at 27
        big_clock(primary_reset_clock(snapshot["primary"]), blue_x, blue_w, "38bdf8")
        draw_bar(blue_x, blue_w, primary_remaining, "38bdf8")
        draw_gauge(gauge_x, gauge_w,
                   rounded_remaining(snapshot.get("secondary")), "c084fc")
    else:
        for x, value, color in ((4, snapshot["primary"], "38bdf8"),
                                (16, snapshot.get("secondary"), "c084fc")):
            remaining = rounded_remaining(value)
            draw_value(x, remaining, color)
            draw_bar(x, 11, remaining, color)

    resets = snapshot.get("available_resets")
    text("?" if resets is None else ("+" if resets >= 10 else str(resets)), 28, "fbbf24")
    bitmap = base64.b64encode(pixels).decode("ascii")
    return {"codex": {"draw": [["bitmap", 0, 0, 32, 8, bitmap]],
                      "lifetimeMs": lifetime_ms, "lifetimeExpiry": "remove"}}


def run():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    max_age = float(os.environ.get("CODEX_MAX_AGE_SECONDS", "3600"))
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("CODEX_MAX_AGE_SECONDS must be a positive finite number")
    ssh_host = os.environ.get("CODEX_SSH_HOST") or None
    # In SSH mode, Codex and CODEX_HOME belong to the Mac, never the Pi.
    snapshot = read_usage(ssh_host, os.environ.get("CODEX_HOME") or None)
    freshness(snapshot, max_age)
    client = Awtrix(os.environ.get("AWTRIX_HOST", "http://192.168.4.94"))
    _, before = client.list_apps()
    if any(app.get("name") == "codex" and app.get("origin") not in (None, "pushed")
           for app in before):
        raise ValueError("AWTRIX has a non-pushed app with a Codex widget name; refusing to replace it")
    # Recheck after preflight to account for network delays.
    age, lifetime_ms = freshness(snapshot, max_age)
    payload = payloads(snapshot, lifetime_ms)["codex"]
    push_status = client.push_app("codex", payload)
    five = rounded_remaining(snapshot["primary"])
    week = rounded_remaining(snapshot.get("secondary"))
    resets = snapshot.get("available_resets")
    print("Sent codex: 5H %s%% left | 7D %s left | RST %s | terminal icon + bars -> %s | PUT HTTP %d" %
          (five, "N/A" if week is None else str(week) + "%",
           "N/A" if resets is None else resets, client.host, push_status), flush=True)
    get_status, apps = client.list_apps()
    def verify_codex(apps):
        if not any(app.get("name") == "codex" and app.get("origin") == "pushed"
                   and all(app.get(key) is True for key in ("present", "enabled", "inLoop")) for app in apps):
            raise ValueError("Push acknowledged, but codex was not verified present, pushed, enabled and inLoop")

    verify_codex(apps)
    # Retire only the old widget's pushed pages, after verifying the replacement.
    removed = []
    for name in ("codex_week", "codex_resets"):
        if any(app.get("name") == name and app.get("origin") == "pushed"
               and app.get("present") is True for app in apps):
            status = client.delete_app(name)
            removed.append(name)
            print("Removed old %s page | DELETE HTTP %d" % (name, status), flush=True)
    if removed:
        get_status, apps = client.list_apps()
        verify_codex(apps)
        if any(app.get("name") in removed and app.get("present") is True for app in apps):
            raise ValueError("Old Codex pages are still present after deletion")
    reset = datetime.fromtimestamp(snapshot["primary"]["resets_at"], timezone.utc).isoformat()
    source = "SSH " + ssh_host if ssh_host else "local"
    print("Verified codex: present, pushed, enabled, inLoop"
          " | GET HTTP %d | %s account query %.0fs old | five-hour reset %s" %
          (get_status, source, age, reset))


if __name__ == "__main__":
    try:
        run()
    except (OSError, ValueError) as exc:
        print("deskmate: " + str(exc), file=sys.stderr)
        sys.exit(1)
