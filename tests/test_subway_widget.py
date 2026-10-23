"""One-shot command ownership, fallback, scheduling, and readback boundaries."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import subway_widget
from test_subway import NOW as FEED_NOW, fixture, train

NOW = FEED_NOW - 3 * 3600

APPS = [{"name": name, "origin": "pushed", "present": True, "enabled": True, "inLoop": True}
        for name in subway_widget.APP_NAMES]


class CommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        with patch("test_subway.NOW", NOW):
            f = fixture()
            train(f)
            train(f, "7", 1800, 1980, "seven", origin="725S", destination="726S")
        patches = [patch("subway_widget.__file__", str(self.root / "src/subway_widget.py")),
                   patch("meeting_mode.__file__", str(self.root / "src/meeting_mode.py")),
                   patch.dict(os.environ, {}, clear=True),
                   patch("subway_widget.time.time", return_value=NOW),
                   patch("subway_widget.load_schedule", return_value=((), 180, "schedule unavailable")),
                   patch("subway_widget.download", return_value=f.SerializeToString()),
                   patch("subway_widget.Awtrix")]
        values = []
        for p in patches:
            values.append(p.start())
            self.addCleanup(p.stop)
        self.clock, self.schedule, self.download, self.factory = values[3:]
        self.window_patch = patch("subway_widget.window_active", return_value=True)
        self.window = self.window_patch.start()
        self.addCleanup(self.window_patch.stop)
        self.client = self.factory.return_value
        self.client.timeout = 5
        self.client.list_apps.side_effect = [(200, []), (200, APPS)]

    def run_command(self, **kwargs):
        with redirect_stdout(io.StringIO()) as output:
            result = subway_widget.run(**kwargs)
        return result, output.getvalue()

    def test_pushes_exact_app_names_checks_ownership_and_readback(self):
        result, output = self.run_command()
        self.assertEqual([c.args[0] for c in self.client.push_app.call_args_list], list(subway_widget.APP_NAMES))
        self.assertIn("~9:33a", result["subway_eta"]["text"])
        self.assertIn("Verified subway_trains and subway_eta", output)
        self.assertEqual(self.client.list_apps.call_count, 2)
        self.assertEqual(result["subway_trains"]["lifetimeMs"], 60000)
        self.assertEqual(result["subway_eta"]["lifetimeMs"], 60000)
        for method in ("delete_app", "set_app_order", "patch_settings", "activate_app", "install_script"):
            getattr(self.client, method).assert_not_called()

    def test_scheduled_monday_poll_publishes_both_apps(self):
        self.window_patch.stop()
        self.clock.return_value = datetime(2026, 10, 26, 9, 0,
                                           tzinfo=ZoneInfo("America/New_York")).timestamp()

        result, output = self.run_command()

        self.assertEqual([c.args[0] for c in self.client.push_app.call_args_list],
                         ["subway_trains", "subway_eta"])
        self.assertEqual(set(result), {"subway_trains", "subway_eta"})
        self.assertTrue(all(payload["lifetimeExpiry"] == "remove" for _, payload in
                            (c.args for c in self.client.push_app.call_args_list)))
        self.assertIn("Verified subway_trains and subway_eta", output)

    def test_dry_run_fetches_prints_payload_and_never_contacts_clock(self):
        result, output = self.run_command(dry_run=True)
        self.assertEqual(json.loads(output), result)
        self.download.assert_called_once_with(subway_widget.REALTIME_URL, 5_000_000)
        self.factory.assert_not_called()

    def test_shell_precedence_env_loading_and_cache_are_worktree_relative(self):
        (self.root / ".env").write_text("AWTRIX_HOST=http://192.0.2.1\n")
        os.environ["AWTRIX_HOST"] = "http://192.0.2.2"
        self.run_command()
        self.factory.assert_called_once_with("http://192.0.2.2")
        self.schedule.assert_called_once_with(self.root / ".subway/schedule.zip", NOW)

    def test_collision_with_either_foreign_app_refuses_all_pushes(self):
        for name in subway_widget.APP_NAMES:
            for origin in ("script", "native", None):
                with self.subTest(name=name, origin=origin):
                    self.client.list_apps.side_effect = [(200, [{"name": name, "present": True, "origin": origin}])]
                    with self.assertRaisesRegex(ValueError, "non-pushed"):
                        self.run_command()
                    self.client.push_app.assert_not_called()

    def test_expired_origin_null_tombstone_is_safe_to_recreate(self):
        self.client.list_apps.side_effect = [(200, [{"name": "subway_eta", "present": False, "origin": None}]),
                                             (200, APPS)]
        self.run_command()
        self.assertEqual(self.client.push_app.call_count, 2)

    def test_missing_disabled_or_wrong_origin_readback_fails(self):
        for key, value in (("present", False), ("enabled", False), ("inLoop", False), ("origin", "script")):
            with self.subTest(key=key):
                after = [APPS[0], {**APPS[1], key: value}]
                self.client.list_apps.side_effect = [(200, []), (200, after)]
                with self.assertRaisesRegex(ValueError, "not verified"):
                    self.run_command()

    def test_push_error_is_not_retried_or_claimed_verified(self):
        self.client.push_app.side_effect = ValueError("AWTRIX failed")
        with redirect_stdout(io.StringIO()) as output, self.assertRaisesRegex(ValueError, "failed"):
            subway_widget.run()
        self.assertNotIn("Verified", output.getvalue())
        self.assertEqual(self.client.push_app.call_count, 1)
        self.assertEqual(self.client.list_apps.call_count, 1)

    def test_feed_failures_push_explicit_no_estimate_and_data_warning(self):
        for failure in (OSError("offline"), ValueError("too large"), b"<Error>secret body</Error>", b""):
            with self.subTest(failure=failure):
                self.client.list_apps.side_effect = [(200, []), (200, APPS)]
                self.download.side_effect = failure if isinstance(failure, Exception) else None
                self.download.return_value = failure if isinstance(failure, bytes) else b""
                result, output = self.run_command()
                self.assertIn("3 no estimate | 2 no estimate", result["subway_eta"]["text"])
                self.assertEqual(result["subway_eta"]["icon"], "attentionwarning")
                self.assertNotIn("secret body", output)

    def test_meeting_and_idle_takeovers_defer_without_fetch_or_device_changes(self):
        for name in (".meeting-mode-state.json", ".idle-mode-state.json"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text('{"active": true}')
                result, output = self.run_command()
                self.assertIsNone(result)
                self.assertIn("deferred", output)
                self.download.assert_not_called()
                self.factory.assert_not_called()
                path.unlink()

    def test_custom_takeover_paths_and_invalid_state_fail_closed(self):
        path = self.root / "custom.json"
        os.environ["MEETING_STATE_PATH"] = str(path)
        path.write_text('{"active": true}')
        self.assertIsNone(self.run_command()[0])
        path.write_text("bad state")
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.run_command()
        self.factory.assert_not_called()

    def test_takeover_started_during_fetch_defers_before_push(self):
        def preflight():
            (self.root / ".meeting-mode-state.json").write_text('{"active": true}')
            return 200, []
        self.client.list_apps.side_effect = preflight
        result, _ = self.run_command()
        self.assertIsNone(result)
        self.client.push_app.assert_not_called()

    def test_catchability_is_recomputed_after_preflight(self):
        def preflight():
            self.clock.return_value = NOW + 121
            return 200, APPS
        self.client.list_apps.side_effect = preflight
        result, _ = self.run_command()
        self.assertIn("3 no estimate", result["subway_eta"]["text"])


    def test_command_uses_real_wall_clock_policy(self):
        self.window_patch.stop()
        # Thursday noon in New York is outside the window.
        self.clock.return_value = FEED_NOW
        self.client.list_apps.side_effect = [(200, APPS), (200, [])]
        self.run_command()
        self.client.push_app.assert_not_called()
        self.assertEqual(self.client.delete_app.call_count, 2)
        self.download.assert_not_called()

    def test_outside_window_cleanup_is_targeted_and_idempotent(self):
        self.window.return_value = False
        other = {"name": "calendar", "origin": "pushed", "present": True}
        tombstones = [{"name": name, "present": False, "origin": None} for name in subway_widget.APP_NAMES]
        self.client.list_apps.side_effect = [(200, APPS + [other]), (200, tombstones + [other]),
                                             (200, tombstones + [other]), (200, tombstones + [other])]
        self.run_command()
        self.run_command()
        self.assertEqual([c.args[0] for c in self.client.delete_app.call_args_list], list(subway_widget.APP_NAMES))
        self.assertEqual(self.client.list_apps.call_count, 4)
        self.schedule.assert_not_called()
        self.download.assert_not_called()
        self.client.push_app.assert_not_called()

    def test_cleanup_deletes_only_present_pushed_apps(self):
        self.window.return_value = False
        self.client.list_apps.side_effect = [(200, [APPS[0], {"name": "subway_eta", "present": False}]), (200, [])]
        self.run_command()
        self.client.delete_app.assert_called_once_with("subway_trains")

    def test_cleanup_refuses_either_foreign_app_before_any_deletion(self):
        self.window.return_value = False
        for name in subway_widget.APP_NAMES:
            for origin in ("native", "script", None):
                with self.subTest(name=name, origin=origin):
                    self.client.list_apps.side_effect = [(200, APPS + [{"name": name, "origin": origin, "present": True}])]
                    with self.assertRaisesRegex(ValueError, "non-pushed"):
                        self.run_command()
                    self.client.delete_app.assert_not_called()

    def test_cleanup_readback_must_verify_both_absent(self):
        self.window.return_value = False
        for app in APPS:
            with self.subTest(name=app["name"]):
                self.client.list_apps.side_effect = [(200, APPS), (200, [app])]
                with self.assertRaisesRegex(ValueError, app["name"] + " was not verified absent"):
                    self.run_command()
        self.client.list_apps.side_effect = [(200, APPS), ValueError("readback failed")]
        with self.assertRaisesRegex(ValueError, "readback failed"):
            self.run_command()

    def test_cleanup_delete_failure_is_not_retried_or_claimed_verified(self):
        self.window.return_value = False
        self.client.list_apps.side_effect = [(200, APPS)]
        self.client.delete_app.side_effect = ValueError("delete failed")
        with redirect_stdout(io.StringIO()) as output, self.assertRaisesRegex(ValueError, "delete failed"):
            subway_widget.run()
        self.assertNotIn("Verified", output.getvalue())
        self.client.delete_app.assert_called_once_with("subway_trains")
        self.assertEqual(self.client.list_apps.call_count, 1)

    def test_outside_window_dry_run_prints_policy_without_fetch_or_device_calls(self):
        self.window.return_value = False
        result, output = self.run_command(dry_run=True)
        self.assertEqual(json.loads(output), result)
        self.assertEqual(result["action"], "cleanup")
        self.assertEqual(result["apps"], list(subway_widget.APP_NAMES))
        self.schedule.assert_not_called()
        self.download.assert_not_called()
        self.factory.assert_not_called()

    def test_outside_window_takeovers_defer_before_cleanup(self):
        self.window.return_value = False
        self.test_meeting_and_idle_takeovers_defer_without_fetch_or_device_changes()
        self.schedule.assert_not_called()
        self.window.assert_not_called()

    def test_takeover_started_during_cleanup_preflight_defers(self):
        self.window.return_value = False
        def preflight():
            (self.root / ".idle-mode-state.json").write_text('{"active": true}')
            return 200, APPS
        self.client.list_apps.side_effect = preflight
        self.assertIsNone(self.run_command()[0])
        self.client.delete_app.assert_not_called()
        self.client.push_app.assert_not_called()

    def test_hostname_refuses_live_publication_before_any_clock_request(self):
        for host in ("http://clock.local", "https://clock.example:443", "http://2130706433"):
            with self.subTest(host=host):
                os.environ["AWTRIX_HOST"] = host
                with self.assertRaisesRegex(ValueError, "literal IP.*DNS.*socket timeout"):
                    self.run_command()
                self.factory.assert_not_called()

    def test_hostname_refusal_never_reaches_real_client_dns(self):
        from awtrix import Awtrix
        os.environ["AWTRIX_HOST"] = "http://clock.local"
        with patch("subway_widget.Awtrix", Awtrix), patch("socket.getaddrinfo") as dns:
            with self.assertRaisesRegex(ValueError, "literal IP"):
                self.run_command()
        dns.assert_not_called()

    def test_hostname_dry_run_still_prints_payloads_without_clock_requests(self):
        os.environ["AWTRIX_HOST"] = "http://clock.local"
        result, output = self.run_command(dry_run=True)
        self.assertEqual(json.loads(output), result)
        self.factory.assert_not_called()

    def test_hostname_outside_window_still_cleans_up(self):
        os.environ["AWTRIX_HOST"] = "http://clock.local"
        self.window.return_value = False
        self.client.list_apps.side_effect = [(200, APPS), (200, [])]
        self.run_command()
        self.factory.assert_called_once_with("http://clock.local")
        self.assertEqual(self.client.delete_app.call_count, 2)
        self.client.push_app.assert_not_called()

    def test_literal_ipv4_and_ipv6_with_ports_allow_publication(self):
        for host in ("http://192.0.2.1:7000", "http://[::1]:7000"):
            with self.subTest(host=host):
                os.environ["AWTRIX_HOST"] = host
                self.client.list_apps.side_effect = [(200, []), (200, APPS)]
                result, _ = self.run_command()
                self.assertEqual(set(result), set(subway_widget.APP_NAMES))

    def boundary_clock(self, seconds_before_cutoff):
        self.window_patch.stop()
        cutoff = datetime(2026, 10, 22, 10, tzinfo=ZoneInfo("America/New_York")).timestamp()
        self.clock.return_value = cutoff - seconds_before_cutoff
        return cutoff

    def test_last_second_skips_all_writes_and_verifies_cleanup(self):
        self.boundary_clock(1)
        self.client.list_apps.side_effect = [(200, APPS), (200, APPS), (200, [])]
        result, output = self.run_command()
        self.assertIsNone(result)
        self.client.push_app.assert_not_called()
        self.assertEqual([c.args[0] for c in self.client.delete_app.call_args_list], list(subway_widget.APP_NAMES))
        self.assertEqual(self.client.list_apps.call_count, 3)
        self.assertIn("absent", output)

    def test_each_put_caps_ttl_for_its_own_start_time_and_request_timeout(self):
        cutoff = self.boundary_clock(20)
        self.client.timeout = 7
        def delayed_push(name, payload):
            self.clock.return_value += 2
        self.client.push_app.side_effect = delayed_push
        result, _ = self.run_command()
        self.assertEqual(result["subway_trains"]["lifetimeMs"], 5750)
        self.assertEqual(result["subway_eta"]["lifetimeMs"], 3750)
        for call, started in zip(self.client.push_app.call_args_list, (cutoff - 20, cutoff - 18)):
            payload = call.args[1]
            self.assertEqual(payload["lifetimeExpiry"], "remove")
            self.assertLessEqual(started + 2 * self.client.timeout + 0.25 + payload["lifetimeMs"] / 1000, cutoff)
        self.client.delete_app.assert_not_called()

    def test_connect_and_response_delays_leave_device_expiry_before_cutoff(self):
        cutoff = self.boundary_clock(20)
        expiries = []
        def delayed_push(name, payload):
            # Almost five seconds each for connection and response; model receipt
            # at the end too, conservatively later than normal device receipt.
            self.clock.return_value += 2 * self.client.timeout - 1
            expiries.append(self.clock.return_value + payload["lifetimeMs"] / 1000)
        self.client.push_app.side_effect = delayed_push
        result, _ = self.run_command()
        self.assertEqual([result[name]["lifetimeMs"] for name in subway_widget.APP_NAMES], [9750, 750])
        self.assertEqual(len(expiries), 2)
        self.assertTrue(all(expiry < cutoff for expiry in expiries))
        self.client.delete_app.assert_not_called()

    def test_delayed_first_put_crossing_cutoff_skips_second_and_rereads_ownership(self):
        cutoff = self.boundary_clock(12)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff + 1
        self.client.push_app.side_effect = delayed_push
        other = {"name": "calendar", "origin": "pushed", "present": True}
        self.client.list_apps.side_effect = [(200, []), (200, APPS + [other]), (200, [other])]
        result, output = self.run_command()
        self.assertIsNone(result)
        self.client.push_app.assert_called_once()
        self.assertEqual(self.client.push_app.call_args.args[1]["lifetimeMs"], 1750)
        self.assertEqual([c.args[0] for c in self.client.delete_app.call_args_list], list(subway_widget.APP_NAMES))
        self.assertEqual(self.client.list_apps.call_count, 3)
        self.assertNotIn("realtime=", output)

    def test_delayed_second_put_crossing_cutoff_cleans_up_and_verifies_absence(self):
        cutoff = self.boundary_clock(20)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff - 12 if name == "subway_trains" else cutoff + 1
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, APPS), (200, [])]
        result, output = self.run_command()
        self.assertIsNone(result)
        self.assertEqual([c.args[1]["lifetimeMs"] for c in self.client.push_app.call_args_list], [9750, 1750])
        self.assertEqual(self.client.delete_app.call_count, 2)
        self.assertEqual(self.client.list_apps.call_count, 3)
        self.assertIn("absent", output)
        self.assertNotIn("realtime=", output)

    def test_timed_out_put_crossing_cutoff_reconciles_without_retry(self):
        cutoff = self.boundary_clock(12)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff + 1
            raise ValueError("AWTRIX connection failed")
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, APPS), (200, [])]
        with self.assertRaisesRegex(ValueError, "connection failed"):
            self.run_command()
        self.client.push_app.assert_called_once()
        self.assertEqual(self.client.delete_app.call_count, 2)
        self.assertEqual(self.client.list_apps.call_count, 3)

    def test_first_put_leaving_insufficient_budget_skips_second_and_cleans_up(self):
        cutoff = self.boundary_clock(14)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff - 9
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, [APPS[0]]), (200, [])]
        result, output = self.run_command()
        self.assertIsNone(result)
        self.client.push_app.assert_called_once()
        self.assertEqual(self.client.push_app.call_args.args[1]["lifetimeMs"], 3750)
        self.client.delete_app.assert_called_once_with("subway_trains")
        self.assertEqual(self.client.list_apps.call_count, 3)
        self.assertIn("absent", output)

    def test_timeout_budget_requires_at_least_one_millisecond(self):
        self.boundary_clock(10.25)
        self.client.list_apps.side_effect = [(200, APPS), (200, APPS), (200, [])]
        self.run_command()
        self.client.push_app.assert_not_called()
        self.assertEqual(self.client.delete_app.call_count, 2)

    def test_cutoff_ttl_uses_local_time_in_both_dst_offsets(self):
        self.window_patch.stop()
        for month, day in ((1, 5), (7, 6), (3, 9), (11, 2)):
            with self.subTest(month=month):
                cutoff = datetime(2026, month, day, 10, tzinfo=ZoneInfo("America/New_York")).timestamp()
                self.clock.return_value = cutoff - 15.25
                self.client.list_apps.side_effect = [(200, []), (200, APPS)]
                result, _ = self.run_command()
                for payload in result.values():
                    self.assertEqual(payload["lifetimeMs"], 5000)
                    self.assertEqual(payload["lifetimeExpiry"], "remove")

    def test_cutoff_cleanup_refuses_new_foreign_ownership(self):
        cutoff = self.boundary_clock(12)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff + 1
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, [APPS[0], {**APPS[1], "origin": "script"}])]
        with self.assertRaisesRegex(ValueError, "non-pushed"):
            self.run_command()
        self.client.push_app.assert_called_once()
        self.client.delete_app.assert_not_called()

    def test_cutoff_cleanup_requires_absent_readback(self):
        cutoff = self.boundary_clock(12)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff + 1
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, APPS), (200, [APPS[1]])]
        with self.assertRaisesRegex(ValueError, "subway_eta was not verified absent"):
            self.run_command()
        self.client.push_app.assert_called_once()
        self.assertEqual(self.client.delete_app.call_count, 2)

    def test_cutoff_cleanup_defers_to_takeover_started_during_put(self):
        cutoff = self.boundary_clock(12)
        def delayed_push(name, payload):
            self.clock.return_value = cutoff + 1
            (self.root / ".meeting-mode-state.json").write_text('{"active": true}')
        self.client.push_app.side_effect = delayed_push
        self.client.list_apps.side_effect = [(200, []), (200, APPS)]
        result, output = self.run_command()
        self.assertIsNone(result)
        self.assertIn("deferred", output)
        self.client.push_app.assert_called_once()
        self.client.delete_app.assert_not_called()

    def test_readback_delay_crossing_cutoff_cleans_up_before_success(self):
        cutoff = self.boundary_clock(12)
        def delayed_readback():
            if self.client.list_apps.call_count == 1:
                return 200, []
            if self.client.list_apps.call_count == 2:
                self.clock.return_value = cutoff + 1
                return 200, APPS
            return 200, []
        self.client.list_apps.side_effect = delayed_readback
        result, output = self.run_command()
        self.assertIsNone(result)
        self.assertNotIn("realtime=", output)
        self.assertEqual(self.client.delete_app.call_args_list, [call("subway_trains"), call("subway_eta")])
        self.assertEqual(self.client.list_apps.call_count, 3)

    def test_window_ending_during_fetch_cleans_up_instead_of_publishing(self):
        self.window.side_effect = [True, False]
        self.client.list_apps.side_effect = [(200, APPS), (200, [])]
        self.run_command()
        self.assertEqual(self.client.delete_app.call_count, 2)
        self.client.push_app.assert_not_called()


class WindowTests(unittest.TestCase):
    def test_weekdays_and_exact_boundaries_in_both_dst_offsets(self):
        zone = ZoneInfo("America/New_York")
        for month, monday in ((1, 5), (7, 6), (3, 9), (11, 2)):
            for day in range(7):
                for hour, minute, second, within in ((8, 44, 59, False), (8, 45, 0, True),
                                                      (9, 59, 59, True), (10, 0, 0, False)):
                    local = datetime(2026, month, monday + day, hour, minute, second, tzinfo=zone)
                    with self.subTest(local=local):
                        self.assertEqual(subway_widget.window_active(local.timestamp()), day < 4 and within)

    def test_utc_instants_follow_eastern_dst_transition(self):
        for date, hour in (((2026, 3, 5), 13), ((2026, 3, 9), 12),
                           ((2026, 10, 29), 12), ((2026, 11, 2), 13)):
            with self.subTest(date=date):
                start = datetime(*date, hour, 45, tzinfo=timezone.utc).timestamp()
                self.assertFalse(subway_widget.window_active(start - 1))
                self.assertTrue(subway_widget.window_active(start))
                self.assertTrue(subway_widget.window_active(start + 4499))
                self.assertFalse(subway_widget.window_active(start + 4500))
