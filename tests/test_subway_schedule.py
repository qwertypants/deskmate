"""Small GTFS ZIP fixtures, service calendars, and bounded cache behavior."""
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from subway import Feed, Leg, ZONE, payloads
from subway_schedule import (REALTIME_URL, SCHEDULE_URL, compact_schedule, download,
                             load_schedule, parse_schedule, service_epoch, service_seconds)

NOW = int(datetime(2026, 10, 22, 12, tzinfo=ZONE).timestamp())


def archive(**overrides):
    files = {
        "feed_info.txt": "feed_start_date,feed_end_date\n20261001,20261231\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                        "weekday,1,1,1,1,1,0,0,20261001,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\n",
        "trips.txt": "route_id,service_id,trip_id\n3,weekday,three\n2,weekday,two\n7,weekday,seven\n1,weekday,one\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                          "three,12:08:00,12:08:30,224S,1,0,0\n"
                          "three,12:25:00,12:25:00,127S,2,0,0\n"
                          "two,12:10:00,12:10:00,224S,1,0,0\n"
                          "two,12:28:00,12:28:00,127S,2,0,0\n"
                          "seven,12:08:00,12:08:00,701S,1,0,0\n"
                          "seven,12:32:00,12:32:00,725S,2,0,0\n"
                          "seven,12:35:00,12:35:00,726S,3,0,0\n"
                          "one,12:08:00,12:08:00,224S,1,0,0\n",
        "transfers.txt": "from_stop_id,to_stop_id,transfer_type,min_transfer_time\n127,725,2,180\n",
    }
    files.update(overrides)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if data is not None:
                z.writestr(name, data)
    return output.getvalue()


class ScheduleTests(unittest.TestCase):
    def test_static_pairs_and_minimum_transfer_from_published_columns(self):
        legs, transfer = parse_schedule(archive(), NOW)
        self.assertEqual(transfer, 180)
        self.assertEqual([(l.route, l.start - NOW, l.end - NOW) for l in legs],
                         [("3", 510, 1500), ("2", 600, 1680), ("7", 1920, 2100)])
        self.assertEqual(legs[-1].origin_start, NOW + 480)

    def test_scheduled_seven_origin_time_is_retained_for_replacement_filtering(self):
        data = archive(**{"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "seven,12:10:00,12:10:00,701S,1\n"
                          "seven,12:45:00,12:45:00,725S,2\n"
                          "seven,12:48:00,12:48:00,726S,3\n"})
        legs, _ = parse_schedule(data, NOW)
        seven = next(leg for leg in legs if leg.route == "7")
        self.assertEqual(seven.start, NOW + 45 * 60)
        self.assertEqual(seven.origin_start, NOW + 10 * 60)

    def test_compaction_keeps_first_seven_stop_for_origin_time(self):
        compact = compact_schedule(archive())
        with zipfile.ZipFile(io.BytesIO(compact)) as z:
            rows = z.read("stop_times.txt").decode()
        self.assertIn("seven,12:08:00,12:08:00,701S,1,0,0", rows)

    def test_compaction_preserves_parsing_and_discards_unrelated_routes(self):
        original = archive()
        compact = compact_schedule(original)
        self.assertEqual(parse_schedule(compact, NOW), parse_schedule(original, NOW))
        with zipfile.ZipFile(io.BytesIO(compact)) as z:
            self.assertNotIn(b"one", z.read("trips.txt"))
            self.assertNotIn(b"one", z.read("stop_times.txt"))

    def test_service_date_exception_can_remove_or_add_service(self):
        removed = archive(**{"calendar_dates.txt": "service_id,date,exception_type\nweekday,20261022,2\n"})
        self.assertEqual(parse_schedule(removed, NOW)[0], ())
        added = archive(**{"calendar.txt": None,
                           "calendar_dates.txt": "service_id,date,exception_type\nweekday,20261022,1\n"})
        self.assertEqual(len(parse_schedule(added, NOW)[0]), 3)

    def test_service_weekday_and_validity_are_not_assumed(self):
        sunday = int(datetime(2026, 10, 25, 12, tzinfo=ZONE).timestamp())
        self.assertEqual(parse_schedule(archive(), sunday)[0], ())
        with self.assertRaisesRegex(ValueError, "cover today"):
            parse_schedule(archive(**{"feed_info.txt": "feed_end_date\n20260930\n"}), NOW)

    def test_no_pickup_and_wrong_station_direction_are_excluded(self):
        times = ("trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                 "three,12:08:00,12:08:00,224S,1,1,0\n"
                 "three,12:25:00,12:25:00,127S,2,0,0\n"
                 "two,12:08:00,12:08:00,224N,1,0,0\n"
                 "two,12:25:00,12:25:00,127N,2,0,0\n")
        self.assertEqual(parse_schedule(archive(**{"stop_times.txt": times}), NOW)[0], ())

    def test_after_midnight_uses_previous_service_day_and_over_24h_times(self):
        times = ("trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                 "three,24:08:00,24:08:00,224S,1\nthree,24:25:00,24:25:00,127S,2\n")
        midnight = int(datetime(2026, 10, 23, 0, tzinfo=ZONE).timestamp())
        legs, _ = parse_schedule(archive(**{"stop_times.txt": times}), midnight)
        self.assertEqual([(l.start - midnight, l.end - midnight) for l in legs], [(480, 1500)])
        self.assertTrue(legs[0].trip_id.startswith("20261022:"))

    def test_gtfs_noon_minus_12h_epoch_handles_dst(self):
        spring = datetime(2026, 3, 8).date()
        fall = datetime(2026, 11, 1).date()
        self.assertEqual(service_epoch(spring), datetime(2026, 3, 8, 4, tzinfo=timezone.utc).timestamp())
        self.assertEqual(service_epoch(fall), datetime(2026, 11, 1, 5, tzinfo=timezone.utc).timestamp())
        self.assertEqual(service_seconds("25:01:30"), 90090)
        for invalid in ("12:60:00", "48:00:00", "garbage"):
            with self.assertRaises(ValueError):
                service_seconds(invalid)

    def test_missing_or_prohibited_transfer_is_not_invented(self):
        missing = archive(**{"transfers.txt": "from_stop_id,to_stop_id,transfer_type,min_transfer_time\n"})
        self.assertIsNone(parse_schedule(missing, NOW)[1])
        prohibited = archive(**{"transfers.txt": "from_stop_id,to_stop_id,transfer_type,min_transfer_time\n127,725,3,\n"})
        self.assertIsNone(parse_schedule(prohibited, NOW)[1])


class CacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "subway/schedule.zip"

    def save(self, data, age=0):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_bytes(data)
        os.utime(self.path, (NOW - age, NOW - age))

    @patch("subway_schedule.download")
    def test_first_run_downloads_compacts_and_next_run_uses_cache(self, fetch):
        fetch.return_value = archive()
        legs, transfer, warning = load_schedule(self.path, NOW)
        self.assertEqual((len(legs), transfer, warning), (3, 180, ""))
        fetch.assert_called_once_with(SCHEDULE_URL, 40_000_000)
        # File mtimes use the actual OS clock; fix it to the fixture clock.
        os.utime(self.path, (NOW, NOW))
        self.assertEqual(load_schedule(self.path, NOW + 60)[1:], (180, ""))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["schedule.zip"])

    @patch("subway_schedule.download", side_effect=OSError("offline"))
    def test_refresh_failure_reuses_recent_cache_with_warning(self, fetch):
        data = archive(**{"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                                    "three,12:08:00,12:08:30,224S,1,0,0\n"
                                    "three,12:25:00,12:25:00,127S,2,0,0\n"
                                    "two,12:10:00,12:10:00,224S,1,0,0\n"
                                    "two,12:28:00,12:28:00,127S,2,0,0\n"
                                    "seven,12:40:00,12:40:00,701S,1,0,0\n"
                                    "seven,13:04:00,13:04:00,725S,2,0,0\n"
                                    "seven,13:07:00,13:07:00,726S,3,0,0\n"
                                    "one,12:08:00,12:08:00,224S,1,0,0\n"})
        self.save(data, age=4000)
        legs, transfer, warning = load_schedule(self.path, NOW)
        self.assertEqual((len(legs), transfer, warning), (3, 180, "old schedule"))
        self.assertIn("old schedule", legs[0].warnings)
        seven = next(leg for leg in legs if leg.route == "7")
        self.assertEqual(seven.origin_start, NOW + 2400)
        live_three = Leg("3", "live-three", NOW + 480, NOW + 1500)
        result = payloads(Feed(NOW, (live_three,), (("7", NOW + 1800),)), legs, transfer, NOW)
        self.assertIn("~1:07p", result["subway_eta"]["text"])

    @patch("subway_schedule.download", side_effect=OSError("offline"))
    def test_absent_expired_corrupt_and_future_cache_fail_safely(self, fetch):
        self.assertEqual(load_schedule(self.path, NOW), ((), 180, "schedule unavailable"))
        for data, age in ((archive(), 86401), (b"bad zip", 10), (archive(), -60)):
            with self.subTest(age=age):
                self.save(data, age)
                self.assertEqual(load_schedule(self.path, NOW), ((), 180, "schedule unavailable"))

    @patch("subway_schedule.download", return_value=b"<Error/>")
    def test_bad_refresh_preserves_previous_cache(self, fetch):
        data = archive()
        self.save(data, age=4000)
        self.assertEqual(load_schedule(self.path, NOW)[2], "old schedule")
        self.assertEqual(self.path.read_bytes(), data)

    @patch("subway_schedule.download")
    def test_read_only_cache_still_uses_valid_downloaded_data(self, fetch):
        fetch.return_value = archive()
        self.path.parent.write_text("blocks cache directory creation")
        legs, transfer, warning = load_schedule(self.path, NOW)
        self.assertEqual((len(legs), transfer, warning), (3, 180, ""))

    @patch("subway_schedule.urlopen")
    def test_download_has_timeout_size_limit_and_no_credentials(self, open_url):
        response = open_url.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b"data"
        self.assertEqual(download(REALTIME_URL, 10), b"data")
        response.read.assert_called_once_with(11)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, REALTIME_URL)
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(open_url.call_args.kwargs, {"timeout": 20})
        response.read.return_value = b"x" * 11
        with self.assertRaisesRegex(ValueError, "size limit"):
            download(REALTIME_URL, 10)
        response.status = 503
        with self.assertRaisesRegex(ValueError, "download failed"):
            download(REALTIME_URL, 10)
