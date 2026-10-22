"""Deterministic MTA protobuf parsing and leave-now display semantics."""
from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from google.transit import gtfs_realtime_pb2 as gtfs
from nyct_subway import nyct_feed_header, nyct_trip_descriptor, nyct_stop_time_update
from subway import Feed, Leg, ZONE, clock_text, estimate, parse_feed, payloads, selected

NOW = int(datetime(2026, 10, 22, 12, tzinfo=ZONE).timestamp())


def fixture():
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "1.0"
    feed.header.timestamp = NOW
    for route in ("2", "3", "7"):
        period = feed.header.Extensions[nyct_feed_header].trip_replacement_period.add(route_id=route)
        period.replacement_period.end = NOW + 1800
    return feed


def train(feed, route="3", start=480, end=1500, name="train", movement=0, assigned=True,
          origin="224S", destination="127S"):
    entity = feed.entity.add(id=name)
    update = entity.trip_update
    update.trip.trip_id = name
    update.trip.start_date = "20261022"
    update.trip.route_id = route
    update.trip.Extensions[nyct_trip_descriptor].is_assigned = assigned
    for stop_id, seconds in ((origin, start), (destination, end)):
        stop = update.stop_time_update.add(stop_id=stop_id)
        stop.arrival.time = NOW + seconds
        stop.departure.time = NOW + seconds
    if movement is not None:
        vehicle = feed.entity.add(id=name + "-vehicle").vehicle
        vehicle.trip.CopyFrom(update.trip)
        vehicle.timestamp = NOW + movement
    return update


def parse(feed, now=NOW):
    return parse_feed(feed.SerializeToString(), now)


class ParsingTests(unittest.TestCase):
    def test_both_legs_and_westbound_7_are_in_the_same_feed(self):
        f = fixture()
        train(f)
        train(f, "2", name="two")
        train(f, "7", 1800, 1980, "seven", origin="725S", destination="726S")
        train(f, "7X", 1900, 2080, "express", origin="725S", destination="726S")
        legs = parse(f).legs
        self.assertEqual([l.route for l in legs], ["3", "2", "7", "7X"])
        self.assertEqual(legs[0], Leg("3", "20261022:train", NOW + 480, NOW + 1500, (), NOW + 480))
        self.assertEqual(dict(parse(f).replacement_ends)["7"], NOW + 1800)

    def test_boarding_uses_departure_alighting_uses_arrival(self):
        f = fixture()
        update = train(f)
        update.stop_time_update[0].arrival.time = NOW + 300
        update.stop_time_update[1].departure.time = NOW + 1800
        leg = parse(f).legs[0]
        self.assertEqual((leg.arrival, leg.start, leg.end), (NOW + 300, NOW + 480, NOW + 1500))
        self.assertIn("3 12:05p", payloads(parse(f), (), 180, NOW)["subway_trains"]["text"])

    def test_departure_only_transit_times_are_supported(self):
        f = fixture()
        update = train(f)
        for stop in update.stop_time_update:
            stop.ClearField("arrival")
        self.assertEqual(parse(f).legs[0].end, NOW + 1500)

    def test_wrong_platform_route_and_direction_are_ignored(self):
        f = fixture()
        train(f, origin="224N", destination="127N")
        train(f, "1", name="one")
        train(f, "7", name="east", origin="725N", destination="726N")
        self.assertEqual(parse(f).legs, ())

    def test_cancelled_deleted_skipped_and_no_data_boarding_are_excluded(self):
        for mode in ("cancelled", "deleted", "skipped", "no_data", "entity_deleted"):
            with self.subTest(mode=mode):
                f = fixture()
                update = train(f)
                if mode in ("cancelled", "deleted"):
                    update.trip.schedule_relationship = 3 if mode == "cancelled" else 7
                elif mode == "entity_deleted":
                    f.entity[0].is_deleted = True
                else:
                    update.stop_time_update[0].schedule_relationship = 1 if mode == "skipped" else 2
                self.assertEqual(parse(f).legs, ())

    def test_missing_skipped_and_reversed_alight_keep_train_but_no_eta_leg(self):
        for mode in ("missing", "skipped", "reversed", "nonmonotonic"):
            with self.subTest(mode=mode):
                f = fixture()
                update = train(f)
                if mode == "missing":
                    del update.stop_time_update[1:]
                elif mode == "skipped":
                    update.stop_time_update[1].schedule_relationship = 1
                elif mode == "reversed":
                    update.stop_time_update.reverse()
                else:
                    update.stop_time_update[1].arrival.time = NOW + 200
                self.assertIsNone(parse(f).legs[0].end)

    def test_unusable_absolute_times_are_not_zero_or_scheduled_arrivals(self):
        f = fixture()
        update = train(f)
        update.stop_time_update[0].ClearField("arrival")
        update.stop_time_update[0].ClearField("departure")
        update.stop_time_update[0].arrival.delay = 30
        self.assertEqual(parse(f).legs, ())

    def test_bad_xml_truncated_empty_differential_and_future_feeds_fail(self):
        for raw in (b"<Error>NoSuchKey</Error>", b"\x0a\xff", b""):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_feed(raw, NOW)
        for offset in (-301, 31):
            f = fixture()
            f.header.timestamp = NOW + offset
            with self.assertRaises(ValueError):
                parse(f)
        f = fixture()
        f.header.incrementality = gtfs.FeedHeader.DIFFERENTIAL
        with self.assertRaises(ValueError):
            parse(f)
        f = fixture()
        f.header.ClearField("timestamp")
        with self.assertRaises(ValueError):
            parse(f)

    def test_rough_feed_usable_with_old_feed_warning(self):
        f = fixture()
        train(f)
        f.header.timestamp = NOW - 120
        self.assertIn("old feed", parse(f).legs[0].warnings)

    def test_reliability_uses_mta_assignment_movement_track_and_alert_signals(self):
        f = fixture()
        update = train(f, assigned=False, movement=-100)
        update.timestamp = NOW - 120
        track = update.stop_time_update[0].Extensions[nyct_stop_time_update]
        track.scheduled_track, track.actual_track = "2", "1"
        update.stop_time_update[0].arrival.uncertainty = 60
        f.entity.add(id="alert").alert.informed_entity.add().trip.CopyFrom(update.trip)
        self.assertEqual(parse(f).legs[0].warnings,
                         ("unassigned train", "train stalled", "old trip data", "train delayed",
                          "track changed", "uncertain times"))

    def test_missing_assignment_or_vehicle_warns_without_discarding_estimate(self):
        f = fixture()
        update = train(f, movement=None)
        update.trip.ClearExtension(nyct_trip_descriptor)
        self.assertEqual(parse(f).legs[0].warnings, ("assignment unknown", "movement unknown"))

    def test_terminal_track_difference_alone_is_not_a_warning(self):
        f = fixture()
        update = train(f)
        terminal = update.stop_time_update.add(stop_id="250S")
        terminal.arrival.time = NOW + 3500
        tracks = terminal.Extensions[nyct_stop_time_update]
        tracks.scheduled_track, tracks.actual_track = "1", "2"
        origin = update.stop_time_update.add(stop_id="301S")
        origin.departure.time = NOW + 100
        tracks = origin.Extensions[nyct_stop_time_update]
        tracks.scheduled_track, tracks.actual_track = "1", "2"
        update.stop_time_update.sort(key=lambda s: s.arrival.time or s.departure.time)
        self.assertEqual(parse(f).legs[0].warnings, ())

    def test_vehicle_identity_includes_service_date(self):
        f = fixture()
        train(f)
        f.entity[1].vehicle.trip.start_date = "20261021"
        self.assertIn("movement unknown", parse(f).legs[0].warnings)


class EstimateTests(unittest.TestCase):
    def setUp(self):
        self.three = Leg("3", "three", NOW + 480, NOW + 1500)
        self.two = Leg("2", "two", NOW + 600, NOW + 1200)
        self.seven = Leg("7", "seven", NOW + 1800, NOW + 1980)
        self.feed = Feed(NOW, (self.two, self.three, self.seven), (("7", NOW + 1800),))

    def test_selection_sorts_by_boarding_and_deduplicates(self):
        later = Leg("3", "later", NOW + 900, NOW + 1800)
        self.assertEqual(selected((later, self.three, self.three), "3", NOW, NOW + 3600, 2),
                         [self.three, later])

    def test_transfer_minimum_and_first_departure_not_fastest_arrival(self):
        too_soon = Leg("7", "missed", NOW + 1679, NOW + 1800)
        first = Leg("7", "first", NOW + 1680, NOW + 2200)
        faster = Leg("7X", "faster", NOW + 1700, NOW + 1900)
        self.assertEqual(estimate(self.three, (too_soon, faster, first), 180), first)
        self.assertIsNone(estimate(self.three, (too_soon,), 180))
        distant = Leg("7", "distant", NOW + 4000, NOW + 4200)
        self.assertEqual(estimate(self.three, (distant,), 180), distant)

    def test_payloads_keep_3_first_and_show_hudson_yards_arrival(self):
        result = payloads(self.feed, (), 180, NOW)
        self.assertEqual(result["subway_trains"]["text"], "135 3 12:08p | 2 12:10p")
        self.assertEqual(result["subway_eta"]["text"], "HY 3@12:08p ~12:33p | 2@12:10p ~12:33p")
        for value in result.values():
            self.assertNotIn("icon", value)
            self.assertEqual(value["lifetimeMs"], 60000)
            self.assertEqual(value["lifetimeExpiry"], "remove")
            self.assertEqual(value["scroll"]["whenFits"], "scroll")
            self.assertEqual(value["repeat"], 1)

    def test_next_catchable_per_route_includes_exact_walk_boundary(self):
        missed = Leg("3", "missed", NOW + 359, NOW + 1000)
        exact = Leg("3", "exact", NOW + 360, NOW + 1000)
        feed = Feed(NOW, (missed, exact, self.seven))
        result = payloads(feed, (), 180, NOW)
        self.assertEqual(result["subway_eta"]["text"], "HY 3@12:06p ~12:33p | 2 no estimate")
        self.assertEqual(result["subway_eta"]["lifetimeMs"], 1)
        self.assertEqual(payloads(feed, (), 180, NOW + 1)["subway_eta"]["text"],
                         "HY 3 no estimate | 2 no estimate")

    def test_expiry_is_capped_by_catchability_and_feed_age(self):
        first = Leg("3", "near", NOW + 370, NOW + 1000)
        result = payloads(Feed(NOW, (first, self.seven)), (), 180, NOW)
        self.assertEqual(result["subway_eta"]["lifetimeMs"], 10000)
        self.assertEqual(payloads(Feed(NOW - 290, (self.three,)), (), 180, NOW)
                         ["subway_trains"]["lifetimeMs"], 10000)
        self.assertEqual(payloads(Feed(NOW - 80, (self.three,)), (), 180, NOW)
                         ["subway_trains"]["lifetimeMs"], 10000)

    def test_rough_estimate_retains_outcome_and_attentionwarning(self):
        rough = Leg("3", "rough", self.three.start, self.three.end, ("train stalled",))
        feed = Feed(NOW, (rough, self.seven))
        for p in payloads(feed, (), 180, NOW).values():
            self.assertEqual(p["icon"], "attentionwarning")
            self.assertIn("train stalled", p["text"])
            self.assertNotIn("late", p["text"])
        self.assertIn("~12:33p", payloads(feed, (), 180, NOW)["subway_eta"]["text"])

    def test_unrelated_unreliable_train_does_not_warn_on_selected_eta(self):
        unrelated = Leg("2", "gone", NOW - 100, NOW + 100, ("train delayed",))
        feed = Feed(NOW, (self.three, self.seven, unrelated))
        self.assertNotIn("icon", payloads(feed, (), 180, NOW)["subway_eta"])

    def test_no_live_7_or_missing_first_leg_end_is_no_estimate(self):
        for feed, reason in ((Feed(NOW, (self.three,)), "7 data missing"),
                             (Feed(NOW, (Leg("3", "gap", NOW + 480, None), self.seven)), "trip data missing")):
            value = payloads(feed, (), 180, NOW)["subway_eta"]
            self.assertIn("3 no estimate", value["text"])
            self.assertIn(reason, value["text"])
            self.assertEqual(value["icon"], "attentionwarning")

    def test_static_7_only_fills_beyond_live_coverage_and_replacement_window(self):
        before = Leg("7", "static-before", NOW + 1690, NOW + 1850, ("schedule only",))
        after = Leg("7", "static-after", NOW + 1801, NOW + 2000, ("schedule only",))
        feed = Feed(NOW, (self.three,), (("7", NOW + 1800),))
        result = payloads(feed, (before, after), 180, NOW)["subway_eta"]
        self.assertIn("~12:33p", result["text"])
        self.assertIn("7 schedule", result["text"])
        self.assertEqual(result["icon"], "attentionwarning")
        # A real 7 prediction takes priority over an earlier scheduled insertion.
        result = payloads(self.feed, (before,), 180, NOW)["subway_eta"]
        self.assertNotIn("7 schedule", result["text"])
        # No replacement extension: still reserve the first 30 minutes.
        result = payloads(Feed(NOW, (self.three,)), (before,), 180, NOW)["subway_eta"]
        self.assertIn("3 no estimate", result["text"])

    def test_healthy_empty_feed_never_resurrects_static_first_leg(self):
        result = payloads(Feed(NOW), (self.three, self.seven), 180, NOW)
        self.assertEqual(result["subway_trains"]["text"], "135 3 -- | 2 --")
        self.assertEqual(result["subway_eta"]["text"], "HY 3 no estimate | 2 no estimate")
        self.assertNotIn("icon", result["subway_eta"])

    def test_cancelled_live_7_is_not_resurrected_from_matching_static_trip(self):
        f = fixture()
        train(f)
        cancelled = train(f, "7", 2000, 2200, "seven", origin="725S", destination="726S")
        cancelled.trip.schedule_relationship = gtfs.TripDescriptor.CANCELED
        scheduled = Leg("7", "20261022:Weekday_seven", NOW + 2000, NOW + 2200)
        result = payloads(parse(f), (scheduled,), 180, NOW)
        self.assertIn("3 no estimate", result["subway_eta"]["text"])

    def test_feed_outage_uses_schedule_or_explicit_no_estimate(self):
        for stamp in (NOW, NOW - 301):
            feed = Feed(stamp, warning="feed offline")
            result = payloads(feed, (self.three, self.seven), 180, NOW)
            self.assertIn("~12:33p", result["subway_eta"]["text"])
            self.assertIn("schedule only", result["subway_eta"]["text"])
            self.assertEqual(result["subway_eta"]["icon"], "attentionwarning")
        empty = payloads(Feed(NOW, warning="feed offline"), (), 180, NOW)
        self.assertIn("3 no estimate | 2 no estimate", empty["subway_eta"]["text"])

    def test_midnight_next_day_and_new_york_timezone(self):
        moment = int(datetime(2026, 10, 22, 23, 55, tzinfo=ZONE).timestamp())
        self.assertEqual(clock_text(moment + 600, moment), "12:05a+1d")
        self.assertEqual(clock_text(NOW, NOW), "12:00p")
