"""Calendar command safety at the Google and AWTRIX boundaries."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import calendar_widget

NOW = datetime(2026, 10, 4, 16, tzinfo=timezone.utc)
APP = {"name": "google_calendar", "origin": "pushed", "present": True,
       "enabled": True, "inLoop": True}
EVENT = {"summary": "Private Team sync", "start": {"dateTime": "2026-10-04T17:00:00Z"},
         "end": {"dateTime": "2026-10-04T18:00:00Z"}}
SECOND_EVENT = {"summary": "Private Retro", "start": {"dateTime": "2026-10-04T19:00:00Z"},
                "end": {"dateTime": "2026-10-04T20:00:00Z"}}
CANCELLED_EVENT = {"summary": "Private Cancelled", "status": "cancelled",
                   "start": {"dateTime": "2026-10-04T17:00:00Z"},
                   "end": {"dateTime": "2026-10-04T18:00:00Z"}}
ONGOING = {"summary": "Private Team sync", "start": {"dateTime": "2026-10-04T15:00:00Z"},
           "end": {"dateTime": "2026-10-04T18:00:00Z"}}
WAVE_APP = {"name": "deskmate-wave", "origin": "script", "present": True,
            "enabled": True, "inLoop": True, "error": None}
DISABLED_APP = {**APP, "enabled": False, "inLoop": False}


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.patches = [patch("calendar_widget.__file__", str(self.root / "src/calendar_widget.py")),
                        patch.dict(os.environ, {}, clear=True),
                        patch("calendar_widget.utcnow", return_value=NOW),
                        patch("calendar_widget.load_credentials"),
                        patch("calendar_widget.calendar_service"),
                        patch("calendar_widget.fetch_events", return_value=[EVENT]),
                        patch("calendar_widget.Awtrix")]
        values = []
        for patcher in self.patches:
            values.append(patcher.start())
            self.addCleanup(patcher.stop)
        self.clock, self.auth, self.service, self.fetch, self.factory = values[2:]
        self.client = self.factory.return_value
        self.client.list_apps.side_effect = [(200, []), (200, [APP])]
        self.client.get_settings.return_value = (200, {"brightness": 120, "autoBrightness": False})
        self.client.get_device.return_value = (200, {"currentApp": "google_calendar"})
        self.client.push_app.return_value = 200

    def test_pushes_calendar_and_verifies_without_logging_title(self):
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run()
        name, payload = self.client.push_app.call_args.args
        self.assertEqual(name, "google_calendar")
        self.assertEqual(payload["text"], "1:00 PM Private Team sync")
        self.assertEqual(payload["icon"], "calendardots")
        self.assertEqual(payload["lifetimeMs"], 120000)
        self.assertNotIn("Private Team sync", output.getvalue())
        self.assertIn("timezone=America/New_York local_date=2026-10-04", output.getvalue())
        self.assertIn("Verified google_calendar", output.getvalue())
        self.client.delete_app.assert_not_called()
        self.service.return_value.close.assert_called_once()

    def test_pushes_several_events_as_one_scrolling_line(self):
        self.fetch.return_value = [CANCELLED_EVENT, SECOND_EVENT, EVENT]
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run()
        payload = self.client.push_app.call_args.args[1]
        self.assertEqual(payload["text"], "1:00 PM Private Team sync | 3:00 PM Private Retro")
        self.assertEqual(payload["icon"], "calendardots")
        self.assertEqual(payload["lifetimeMs"], 120000)
        self.client.delete_app.assert_not_called()
        self.assertNotIn("Private", output.getvalue())

    def test_underway_meeting_hands_the_display_to_the_wave(self):
        # An underway meeting takes the display exclusively, so the agenda's
        # "meeting in progress" line is not pushed for this run.
        os.environ["MEETING_STATE_PATH"] = str(self.root / ".meeting-mode-state.json")
        self.fetch.return_value = [EVENT, SECOND_EVENT]
        self.clock.side_effect = None
        self.clock.return_value = datetime(2026, 10, 4, 17, 30, tzinfo=timezone.utc)
        self.client.list_apps.side_effect = [(200, [APP]), (200, [APP]),
                                             (200, [APP]), (200, [DISABLED_APP, WAVE_APP])]
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run()
        self.client.push_app.assert_not_called()
        self.assertNotIn("Private", output.getvalue())
        self.assertIn("timezone=America/New_York local_date=2026-10-04", output.getvalue())

    def test_shell_overrides_env_and_relative_paths_resolve_from_repo(self):
        (self.root / ".env").write_text("AWTRIX_HOST=http://file\n"
                                        "GOOGLE_CALENDAR_TOKEN_PATH=secrets/token.json\n"
                                        "GOOGLE_CALENDAR_TIMEZONE=America/Los_Angeles\n")
        os.environ["AWTRIX_HOST"] = "http://shell"
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.factory.assert_called_once_with("http://shell")
        self.auth.assert_called_once_with(self.root / ".google-calendar/credentials.json",
                                          self.root / "secrets/token.json", authorize=False)
        self.assertEqual(self.client.push_app.call_args.args[1]["text"], "10:00 AM Private Team sync")

    def test_explicit_authorization_does_not_contact_clock_or_calendar_api(self):
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run(authorize=True)
        self.assertTrue(self.auth.call_args.kwargs["authorize"])
        self.factory.assert_not_called()
        self.service.assert_not_called()
        self.assertNotIn("Private", output.getvalue())

    def test_auth_or_fetch_failure_never_contacts_clock(self):
        for boundary in (self.auth, self.fetch):
            with self.subTest(boundary=boundary):
                boundary.side_effect = ValueError("Calendar unavailable")
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    calendar_widget.run()
                self.factory.assert_not_called()
                boundary.side_effect = None

    def test_refuses_a_present_non_pushed_name_for_both_push_and_removal(self):
        for events in ([EVENT], []):
            for origin in ("script", "native"):
                with self.subTest(events=events, origin=origin):
                    self.fetch.return_value = events
                    self.client.list_apps.side_effect = None
                    self.client.list_apps.return_value = (
                        200, [{"name": "google_calendar", "origin": origin, "present": True}])
                    with self.assertRaisesRegex(ValueError, "refusing"):
                        calendar_widget.run()
                    self.client.push_app.assert_not_called()
                    self.client.delete_app.assert_not_called()

    def test_tombstone_from_self_removal_does_not_lock_out_the_widget(self):
        # A pushed app removed by its own lifetimeExpiry leaves origin null and
        # present false; treating that as a foreign app blocked every later push.
        tombstone = {"name": "google_calendar", "origin": None, "present": False,
                     "enabled": True, "inLoop": False}
        self.client.list_apps.side_effect = [(200, [tombstone]), (200, [APP])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.assertEqual(self.client.push_app.call_args.args[0], "google_calendar")
        self.assertEqual(self.client.push_app.call_args.args[1]["text"],
                         "1:00 PM Private Team sync")
        self.client.delete_app.assert_not_called()

    def test_absent_app_with_null_origin_also_pushes(self):
        self.client.list_apps.side_effect = [
            (200, [{"name": "google_calendar", "origin": None}]), (200, [APP])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.push_app.assert_called_once()
        self.client.delete_app.assert_not_called()

    def test_tombstone_with_no_eligible_events_still_hides_normally(self):
        self.fetch.return_value = []
        tombstone = {"name": "google_calendar", "origin": None, "present": False,
                     "enabled": True, "inLoop": False}
        self.client.list_apps.side_effect = [(200, [tombstone]), (200, [tombstone])]
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run()
        self.client.delete_app.assert_not_called()
        self.client.push_app.assert_not_called()
        self.assertIn("hidden", output.getvalue())

    def test_empty_calendar_deletes_only_its_pushed_page_and_verifies(self):
        self.fetch.return_value = []
        codex = {**APP, "name": "codex"}
        self.client.list_apps.side_effect = [(200, [APP, codex]), (200, [codex])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.delete_app.assert_called_once_with("google_calendar")
        self.client.push_app.assert_not_called()

    def test_events_that_are_all_ineligible_hide_the_page_and_verify(self):
        self.fetch.return_value = [CANCELLED_EVENT]
        codex = {**APP, "name": "codex"}
        self.client.list_apps.side_effect = [(200, [APP, codex]), (200, [codex])]
        with redirect_stdout(io.StringIO()) as output:
            calendar_widget.run()
        self.client.delete_app.assert_called_once_with("google_calendar")
        self.client.push_app.assert_not_called()
        self.assertIn("hidden", output.getvalue())

    def test_malformed_event_never_hides_or_replaces_the_existing_page(self):
        self.fetch.return_value = [EVENT, {"start": {"dateTime": "not-a-time"}}]
        with self.assertRaisesRegex(ValueError, "invalid timed event"):
            calendar_widget.run()
        self.client.push_app.assert_not_called()
        self.client.delete_app.assert_not_called()

    def test_clock_failure_never_deletes_or_replaces_the_existing_page(self):
        self.client.list_apps.side_effect = ValueError("clock down")
        with self.assertRaisesRegex(ValueError, "AWTRIX"):
            calendar_widget.run()
        self.client.push_app.assert_not_called()
        self.client.delete_app.assert_not_called()

    def test_already_absent_calendar_is_noop(self):
        self.fetch.return_value = []
        self.client.list_apps.side_effect = [(200, [])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.delete_app.assert_not_called()
        self.client.push_app.assert_not_called()

    def test_failed_removal_verification(self):
        self.fetch.return_value = []
        self.client.list_apps.side_effect = [(200, [APP]), (200, [APP])]
        with self.assertRaisesRegex(ValueError, "still present"):
            calendar_widget.run()

    def test_failed_push_verification(self):
        for verified in ([], [{**APP, "enabled": False}], [{**APP, "inLoop": False}],
                         [{**APP, "present": False}], [{**APP, "origin": "script"}]):
            with self.subTest(apps=verified):
                self.client.list_apps.side_effect = [(200, []), (200, verified)]
                with self.assertRaisesRegex(ValueError, "not verified"):
                    calendar_widget.run()

    def test_clock_error_does_not_expose_response_body_or_title(self):
        self.client.push_app.side_effect = ValueError("error with Private Team sync and token")
        with self.assertRaisesRegex(ValueError, "AWTRIX") as caught:
            calendar_widget.run()
        self.assertNotIn("Private", str(caught.exception))
        self.assertNotIn("token", str(caught.exception))

    def test_reselects_after_network_delay_at_event_end(self):
        self.clock.side_effect = [NOW, NOW + timedelta(hours=2)]
        self.client.list_apps.side_effect = [(200, [APP]), (200, [])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.push_app.assert_not_called()
        self.client.delete_app.assert_called_once_with("google_calendar")

    def test_invalid_timezone_never_fetches_or_contacts_clock(self):
        os.environ["GOOGLE_CALENDAR_TIMEZONE"] = "Not/AZone"
        with self.assertRaisesRegex(ValueError, "TIMEZONE"):
            calendar_widget.run()
        self.auth.assert_not_called()
        self.fetch.assert_not_called()
        self.factory.assert_not_called()

    def test_ongoing_meeting_takes_over_the_display_and_skips_the_push(self):
        os.environ["MEETING_STATE_PATH"] = str(self.root / ".meeting-mode-state.json")
        self.fetch.return_value = [ONGOING]
        # The wave is absent on the device, so this run installs it.
        self.client.list_apps.side_effect = [(200, [APP]), (200, [APP]),
                                             (200, [APP]), (200, [DISABLED_APP, WAVE_APP])]
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.push_app.assert_not_called()
        self.client.install_script.assert_called_once()
        name, source = self.client.install_script.call_args.args
        self.assertEqual(name, "deskmate-wave")
        self.assertIn("# @name Great Wave", source)

    def test_no_meeting_never_installs_a_script(self):
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.install_script.assert_not_called()
        self.client.delete_app.assert_not_called()

    def test_ended_meeting_releases_the_wave_before_pushing_text(self):
        os.environ["MEETING_STATE_PATH"] = str(self.root / ".meeting-mode-state.json")
        wave_state = self.root / ".meeting-mode-state.json"
        wave_state.write_text(json.dumps({"active": True, "brightness": 120, "autoBrightness": False,
                                          "order": ["google_calendar"], "disabled": [],
                                          "activeApp": "google_calendar"}))
        self.client.list_apps.side_effect = None
        self.client.list_apps.return_value = (200, [APP, WAVE_APP])
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        calls = [call.args for call in self.client.set_app_order.call_args_list]
        self.assertEqual(calls, [(["google_calendar"], ["deskmate-wave"])])
        self.client.push_app.assert_called_once()
        self.assertFalse(wave_state.exists())

    def test_emptied_calendar_releases_a_live_wave(self):
        os.environ["MEETING_STATE_PATH"] = str(self.root / ".meeting-mode-state.json")
        wave_state = self.root / ".meeting-mode-state.json"
        wave_state.write_text(json.dumps({"active": True, "brightness": 120, "autoBrightness": False,
                                          "order": ["codex"], "disabled": [], "activeApp": "codex"}))
        self.fetch.return_value = []
        self.client.list_apps.side_effect = None
        self.client.list_apps.return_value = (200, [WAVE_APP])
        with redirect_stdout(io.StringIO()):
            calendar_widget.run()
        self.client.set_app_order.assert_called_once_with(["codex"], ["deskmate-wave"])
        self.assertFalse(wave_state.exists())

    def test_fetch_failure_never_touches_a_live_wave(self):
        os.environ["MEETING_STATE_PATH"] = str(self.root / ".meeting-mode-state.json")
        wave_state = self.root / ".meeting-mode-state.json"
        wave_state.write_text(json.dumps({"active": True, "brightness": 120, "autoBrightness": False,
                                          "order": ["google_calendar"], "disabled": [],
                                          "activeApp": "google_calendar"}))
        self.fetch.side_effect = ValueError("Calendar unavailable")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            calendar_widget.run()
        self.client.set_app_order.assert_not_called()
        self.assertTrue(wave_state.exists())


if __name__ == "__main__":
    unittest.main()
