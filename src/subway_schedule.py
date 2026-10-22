"""Bounded public MTA downloads and a small, hourly supplemented-GTFS cache."""
import csv
from datetime import datetime, timedelta
import io
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
import zipfile

from subway import HORIZON_SECONDS, LEGS, Leg, ZONE

REALTIME_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
SCHEDULE_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_supplemented.zip"
# Published 127 -> 725 minimum in MTA transfers.txt, verified 2026-10-22.
TRANSFER_SECONDS = 180
CACHE_SECONDS = 3600
MAX_CACHE_SECONDS = 86400


def download(url, limit):
    request = Request(url, headers={"User-Agent": "DeskMate-subway/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("MTA download failed")
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("MTA response exceeds size limit")
    return body


def rows(archive, name):
    info = archive.getinfo(name)
    if info.file_size > 200_000_000:
        raise ValueError("MTA schedule member exceeds size limit")
    with archive.open(name) as source:
        yield from csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))


def compact_schedule(data):
    """Keep only our four platforms and route trips; never extract ZIP paths."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        if sum(info.file_size for info in source.infolist()) > 240_000_000:
            raise ValueError("MTA schedule exceeds expanded size limit")
        trips = [r for r in rows(source, "trips.txt") if r["route_id"] in LEGS]
        trip_routes = {r["trip_id"]: r["route_id"] for r in trips}
        trip_ids = set(trip_routes)
        stops = {stop for pair in LEGS.values() for stop in pair}
        first_seven_stops = {}
        for row in rows(source, "stop_times.txt"):
            trip_id = row["trip_id"]
            if trip_routes.get(trip_id) in ("7", "7X"):
                previous = first_seven_stops.get(trip_id)
                if previous is None or int(row["stop_sequence"]) < int(previous["stop_sequence"]):
                    first_seven_stops[trip_id] = row
        first_seven_keys = {(r["trip_id"], r["stop_id"], r["stop_sequence"])
                            for r in first_seven_stops.values()}
        for name in ("calendar.txt", "calendar_dates.txt", "transfers.txt", "feed_info.txt"):
            if name in source.namelist():
                target.writestr(name, source.read(name))
        for name, records in (("trips.txt", trips),
                              ("stop_times.txt", (r for r in rows(source, "stop_times.txt")
                                                  if r["trip_id"] in trip_ids
                                                  and (r["stop_id"] in stops
                                                       or (r["trip_id"], r["stop_id"], r["stop_sequence"])
                                                       in first_seven_keys)))):
            text = io.StringIO(newline="")
            writer = None
            for row in records:
                if writer is None:
                    writer = csv.DictWriter(text, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
            if writer is None:
                raise ValueError("MTA schedule has no relevant trips/stops")
            target.writestr(name, text.getvalue())
    return output.getvalue()


def service_seconds(value):
    hour, minute, second = map(int, value.split(":"))
    if not 0 <= hour <= 47 or not 0 <= minute < 60 or not 0 <= second < 60:
        raise ValueError("Invalid GTFS time")
    return hour * 3600 + minute * 60 + second


def service_epoch(day):
    # GTFS times are seconds after local noon minus 12 elapsed hours, including DST days.
    return datetime(day.year, day.month, day.day, 12, tzinfo=ZONE).timestamp() - 43200


def parse_schedule(data, now):
    current_day = datetime.fromtimestamp(now, ZONE).date()
    legs = []
    transfer = None
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        calendar = list(rows(archive, "calendar.txt")) if "calendar.txt" in archive.namelist() else []
        exceptions = list(rows(archive, "calendar_dates.txt")) if "calendar_dates.txt" in archive.namelist() else []
        if "feed_info.txt" in archive.namelist():
            info = next(rows(archive, "feed_info.txt"))
            date = current_day.strftime("%Y%m%d")
            if info.get("feed_start_date", "") > date or info.get("feed_end_date", "99999999") < date:
                raise ValueError("MTA schedule does not cover today")
        trips = {r["trip_id"]: r for r in rows(archive, "trips.txt") if r["route_id"] in LEGS}
        stops = {}
        for r in rows(archive, "stop_times.txt"):
            if r["trip_id"] in trips and (r["stop_id"] in LEGS[trips[r["trip_id"]]["route_id"]]
                                           or trips[r["trip_id"]]["route_id"] in ("7", "7X")):
                stops.setdefault(r["trip_id"], {})[r["stop_id"]] = r
        for delta in (-1, 0, 1):
            day = current_day + timedelta(days=delta)
            date = day.strftime("%Y%m%d")
            weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
            active = {r["service_id"] for r in calendar
                      if r["start_date"] <= date <= r["end_date"] and r[weekday] == "1"}
            for r in exceptions:
                if r["date"] == date:
                    if r["exception_type"] == "1":
                        active.add(r["service_id"])
                    elif r["exception_type"] == "2":
                        active.discard(r["service_id"])
            epoch = service_epoch(day)
            for trip_id, trip in trips.items():
                if trip["service_id"] not in active:
                    continue
                start_id, end_id = LEGS[trip["route_id"]]
                calls = stops.get(trip_id, {})
                if start_id not in calls or end_id not in calls:
                    continue
                board, alight = calls[start_id], calls[end_id]
                if board.get("pickup_type") == "1" or alight.get("drop_off_type") == "1":
                    continue
                if int(board["stop_sequence"]) >= int(alight["stop_sequence"]):
                    continue
                start = int(epoch + service_seconds(board["departure_time"] or board["arrival_time"]))
                end = int(epoch + service_seconds(alight["arrival_time"] or alight["departure_time"]))
                origin_start = None
                if trip["route_id"] in ("7", "7X"):
                    first_stop = min(calls.values(), key=lambda stop: int(stop["stop_sequence"]))
                    origin_time = first_stop["departure_time"] or first_stop["arrival_time"]
                    if origin_time:
                        origin_start = int(epoch + service_seconds(origin_time))
                if now <= start <= now + HORIZON_SECONDS * 2 and 0 < end - start <= HORIZON_SECONDS:
                    legs.append(Leg(trip["route_id"], date + ":" + trip_id, start, end,
                                    ("schedule only",), origin_start=origin_start))
        for r in rows(archive, "transfers.txt"):
            if r["from_stop_id"] in ("127", "127S") and r["to_stop_id"] in ("725", "725S"):
                if r["transfer_type"] == "3":
                    return tuple(legs), None
                if r["transfer_type"] == "2":
                    seconds = int(r["min_transfer_time"])
                    if not 0 < seconds <= 1800:
                        raise ValueError("Invalid MTA transfer time")
                    transfer = seconds if transfer is None else max(transfer, seconds)
    return tuple(legs), transfer


def load_schedule(cache_path, now):
    """Refresh hourly, reuse a <=24h cache on failure, otherwise let live data stand."""
    cache_path = Path(cache_path)
    cached = None
    age = None
    try:
        age = now - cache_path.stat().st_mtime
        if 0 <= age <= MAX_CACHE_SECONDS:
            cached = cache_path.read_bytes()
    except OSError:
        pass
    warning = ""
    try:
        if cached is None or age >= CACHE_SECONDS:
            compact = compact_schedule(download(SCHEDULE_URL, 40_000_000))
            # Validate before replacing the last usable cache.
            parse_schedule(compact, now)
            cached = compact
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=cache_path.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    try:
                        handle.write(compact)
                        handle.close()
                        temporary.replace(cache_path)
                    finally:
                        temporary.unlink(missing_ok=True)
            except OSError:
                pass  # A cache write failure does not invalidate current source data.
    except (OSError, ValueError, KeyError, TypeError, csv.Error, zipfile.BadZipFile, UnicodeError, StopIteration):
        warning = "old schedule" if cached is not None else "schedule unavailable"
    try:
        if cached is None:
            raise ValueError("No schedule")
        legs, transfer = parse_schedule(cached, now)
        if warning:
            legs = tuple(Leg(l.route, l.trip_id, l.start, l.end, l.warnings + (warning,),
                             l.arrival, l.origin_start) for l in legs)
        return legs, transfer, warning
    except (OSError, ValueError, KeyError, TypeError, csv.Error, zipfile.BadZipFile, UnicodeError, StopIteration):
        return (), TRANSFER_SECONDS, "schedule unavailable"
