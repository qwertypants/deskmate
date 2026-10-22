"""135 St downtown 3/2 -> Times Sq -> Hudson Yards 7 estimates, in seconds."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as gtfs
from nyct_subway import nyct_feed_header, nyct_trip_descriptor, nyct_stop_time_update

ZONE = ZoneInfo("America/New_York")
ROUTES = ("3", "2")
LEGS = {"3": ("224S", "127S"), "2": ("224S", "127S"),
        "7": ("725S", "726S"), "7X": ("725S", "726S")}
WALK_SECONDS = 360
FRESH_SECONDS = 90
MAX_AGE_SECONDS = 300
HORIZON_SECONDS = 3600
# Southbound origin terminals verified in MTA stops.txt. Track differences at
# terminals are normal and do not, by themselves, make predictions unreliable.
ORIGIN_TERMINALS = {"201S", "301S", "701S"}


@dataclass(frozen=True)
class Leg:
    route: str
    trip_id: str
    start: int
    end: int | None
    warnings: tuple = ()
    arrival: int | None = None


@dataclass(frozen=True)
class Feed:
    timestamp: int
    legs: tuple = ()
    replacement_ends: tuple = ()
    warning: str = ""
    realtime_trips: tuple = ()


def event_time(update, field):
    event = getattr(update, field)
    return event.time if event.HasField("time") and event.time > 0 else None


def parse_feed(data, now):
    feed = gtfs.FeedMessage()
    try:
        feed.ParseFromString(data)
    except DecodeError as exc:
        raise ValueError("Invalid MTA protobuf") from exc
    if not feed.IsInitialized() or not feed.header.HasField("timestamp"):
        raise ValueError("MTA feed lacks required header/timestamp")
    stamp = feed.header.timestamp
    if feed.header.incrementality != gtfs.FeedHeader.FULL_DATASET:
        raise ValueError("MTA differential feed is unsupported")
    if stamp > now + 30 or now - stamp > MAX_AGE_SECONDS:
        raise ValueError("MTA feed timestamp outside usable window")
    common = ("old feed",) if now - stamp > FRESH_SECONDS else ()
    vehicles, alerts, realtime_trips = {}, set(), []
    for entity in feed.entity:
        if entity.HasField("trip_update") and entity.trip_update.trip.route_id in LEGS:
            trip = entity.trip_update.trip
            realtime_trips.append((trip.start_date, trip.trip_id))
        if entity.is_deleted:
            continue
        if entity.HasField("vehicle") and entity.vehicle.HasField("timestamp"):
            v = entity.vehicle
            vehicles[(v.trip.trip_id, v.trip.start_date)] = v.timestamp
        if entity.HasField("alert"):
            for item in entity.alert.informed_entity:
                if item.HasField("trip"):
                    alerts.add((item.trip.trip_id, item.trip.start_date))
    legs = []
    for entity in feed.entity:
        if entity.is_deleted or not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        trip = update.trip
        if trip.route_id not in LEGS or trip.schedule_relationship in (3, 7):
            continue  # CANCELED or DELETED; never revive from schedules.
        origin, destination = LEGS[trip.route_id]
        stops = list(update.stop_time_update)
        board = next((s for s in stops if s.stop_id == origin), None)
        if board is None or board.schedule_relationship in (1, 2):
            continue  # SKIPPED or NO_DATA at the boarding stop.
        start = event_time(board, "departure") or event_time(board, "arrival")
        if start is None or not now <= start <= now + HORIZON_SECONDS:
            continue
        warnings = list(common)
        ext = trip.Extensions[nyct_trip_descriptor]
        if not ext.HasField("is_assigned"):
            warnings.append("assignment unknown")
        elif not ext.is_assigned:
            warnings.append("unassigned train")
        movement = vehicles.get((trip.trip_id, trip.start_date))
        if movement is None:
            warnings.append("movement unknown")
        elif movement > now + 30:
            warnings.append("movement unknown")
        elif stamp - movement > 90:
            warnings.append("train stalled")
        if update.HasField("timestamp") and (now - update.timestamp > 90 or update.timestamp > now + 30):
            warnings.append("old trip data")
        if (trip.trip_id, trip.start_date) in alerts or (trip.trip_id, "") in alerts:
            warnings.append("train delayed")
        for stop in stops:
            if stop.stop_id in ORIGIN_TERMINALS or stop == stops[-1]:
                continue
            tracks = stop.Extensions[nyct_stop_time_update]
            if tracks.scheduled_track and tracks.actual_track and tracks.scheduled_track != tracks.actual_track:
                warnings.append("track changed")
        if any(e.HasField("uncertainty") and e.uncertainty > 0
               for s in stops for e in (s.arrival, s.departure)):
            warnings.append("uncertain times")
        # Arrival and departure can differ at held stations. Boarding uses departure.
        alight = next((s for s in stops[stops.index(board) + 1:] if s.stop_id == destination), None)
        end = None
        if alight is not None and alight.schedule_relationship not in (1, 2):
            end = event_time(alight, "arrival") or event_time(alight, "departure")
        if end is not None and not 0 < end - start <= HORIZON_SECONDS:
            end = None
        legs.append(Leg(trip.route_id, trip.start_date + ":" + trip.trip_id,
                        start, end, tuple(dict.fromkeys(warnings)), event_time(board, "arrival")))
    periods = []
    for period in feed.header.Extensions[nyct_feed_header].trip_replacement_period:
        # Omitted start means the replacement period covers now.
        span = period.replacement_period
        if span.HasField("end") and (not span.HasField("start") or span.start <= now):
            periods.append((period.route_id, span.end))
    return Feed(stamp, tuple(legs), tuple(periods), realtime_trips=tuple(realtime_trips))


def selected(legs, route, earliest, latest, limit):
    # Stable train identity deduplication; never order routes by final arrival.
    unique = {leg.trip_id: leg for leg in legs if leg.route == route and earliest <= leg.start <= latest}
    return sorted(unique.values(), key=lambda leg: (leg.start, leg.trip_id))[:limit]


def estimate(first, connections, transfer_seconds):
    if first.end is None:
        return None
    choices = [leg for leg in connections if leg.end is not None
               and first.end + transfer_seconds <= leg.start]
    return min(choices, key=lambda leg: (leg.start, leg.trip_id)) if choices else None


def clock_text(stamp, now):
    moment = datetime.fromtimestamp(stamp, ZONE)
    day = (moment.date() - datetime.fromtimestamp(now, ZONE).date()).days
    text = moment.strftime("%I:%M%p").lstrip("0").lower().replace("am", "a").replace("pm", "p")
    return text + ("+%dd" % day if day else "")


def payload(text, warnings, lifetime):
    if warnings:
        text += " | " + ", ".join(dict.fromkeys(warnings))
    result = {"text": text, "repeat": 1,
              "scroll": {"mode": "wrap", "speed": 100, "direction": "left",
                         "entry": "offscreen", "whenFits": "scroll"},
              "lifetimeMs": max(1, min(60000, int(lifetime * 1000))),
              "lifetimeExpiry": "remove"}
    if warnings:
        result["icon"] = "attentionwarning"
    return result


def payloads(feed, scheduled, transfer_seconds, now):
    """Show two upcoming trains, and the next catchable train per route."""
    usable = -30 <= now - feed.timestamp <= MAX_AGE_SECONDS and not feed.warning
    live = feed.legs if usable else ()
    schedule_warning = ("schedule only", feed.warning or "feed expired")
    first_legs = live if usable else tuple(Leg(l.route, l.trip_id, l.start, l.end, l.warnings + schedule_warning)
                                          for l in scheduled if l.route in ROUTES)
    connections = [l for l in live if l.route in ("7", "7X")]
    # Static trains must not resurrect trips absent from the realtime replacement window.
    periods = dict(feed.replacement_ends)
    # The published feed has sometimes supplied replacement end == header time.
    # Keep a conservative 30-minute floor, and never insert scheduled trains
    # among the live 7 predictions. These are later connection fallbacks only.
    boundary = max(feed.timestamp + 1800, periods.get("7", 0), periods.get("7X", 0),
                   max((l.start for l in connections), default=0))
    for leg in scheduled:
        if leg.route in ("7", "7X"):
            date, _, trip_id = leg.trip_id.partition(":")
            if usable and any((not day or day == date) and trip_id.endswith(identifier)
                              for day, identifier in feed.realtime_trips if identifier):
                continue  # Includes cancelled, skipped, and incomplete realtime trips.
            if not usable or (boundary and leg.start > boundary):
                warnings = ("7 schedule",) + tuple(w for w in leg.warnings if w != "schedule only")
                connections.append(Leg(leg.route, leg.trip_id, leg.start, leg.end, warnings))
    trains_text, eta_text, trains_warnings, eta_warnings = [], [], [], []
    trains_life, eta_life = 60, 60
    if usable:
        trains_life = eta_life = min(60, MAX_AGE_SECONDS - (now - feed.timestamp))
        if now - feed.timestamp > FRESH_SECONDS:
            trains_warnings.append("old feed")
            eta_warnings.append("old feed")
        else:
            trains_life = eta_life = min(trains_life, FRESH_SECONDS - (now - feed.timestamp))
    for route in ROUTES:
        upcoming = selected(first_legs, route, now, now + HORIZON_SECONDS, 2)
        arrivals = ["now" if (l.arrival or l.start) <= now else clock_text(l.arrival or l.start, now)
                    for l in upcoming]
        trains_text.append(route + " " + (",".join(arrivals) or "--"))
        for leg in upcoming:
            trains_warnings.extend(leg.warnings)
            trains_life = min(trains_life, leg.start - now)
        catchable = selected(first_legs, route, now + WALK_SECONDS, now + HORIZON_SECONDS, 1)
        if not catchable:
            eta_text.append(route + " no estimate")
            continue
        first = catchable[0]
        connection = estimate(first, connections, transfer_seconds) if transfer_seconds is not None else None
        eta_life = min(eta_life, first.start - now - WALK_SECONDS)
        if connection is None:
            eta_text.append(route + " no estimate")
            eta_warnings.extend(first.warnings)
            eta_warnings.append("trip data missing" if first.end is None else
                                "transfer unavailable" if transfer_seconds is None else "7 data missing")
        else:
            eta_text.append("%s@%s ~%s" % (route, clock_text(first.start, now), clock_text(connection.end, now)))
            eta_warnings.extend(first.warnings + connection.warnings)
    if not usable:
        trains_warnings.extend(schedule_warning)
        eta_warnings.extend(schedule_warning)
    return {"subway_trains": payload("135 " + " | ".join(trains_text), trains_warnings, trains_life),
            "subway_eta": payload("HY " + " | ".join(eta_text), eta_warnings, eta_life)}
