import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from meeting_mode import APP_NAME, enter, exit_mode, wave_source

WAVE = {"name": APP_NAME, "origin": "script", "enabled": True,
        "inLoop": True, "present": True, "error": None}
CALENDAR = {"name": "google_calendar", "origin": "pushed", "present": True,
            "enabled": True, "inLoop": True}
DISABLED_CALENDAR = {**CALENDAR, "enabled": False, "inLoop": False}
FIREPLACE = {"name": "Pixel-Fireplace", "origin": "script", "present": True,
             "enabled": True, "inLoop": True}
DISABLED_FIREPLACE = {**FIREPLACE, "enabled": False, "inLoop": False}


class MeetingModeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.state, self.idle = base / "wave.json", base / "idle.json"
        self.client = Mock()
        self.client.get_device.return_value = (200, {"currentApp": "google_calendar"})

    def test_source_is_the_shipped_seven_second_wave(self):
        source = wave_source()
        self.assertIn("# @name Great Wave", source)
        self.assertIn("default=7000", source)

    def test_app_name_is_a_valid_awtrix_name_not_the_display_name(self):
        self.assertRegex(APP_NAME, r"[A-Za-z0-9_-]{1,32}")
        self.assertNotIn(" ", APP_NAME)

    def test_enter_installs_verifies_and_takes_the_loop_exclusively(self):
        self.client.list_apps.side_effect = [(200, [CALENDAR]), (200, [WAVE, CALENDAR]),
                                             (200, [WAVE, DISABLED_CALENDAR])]
        self.client.get_settings.return_value = (200, {"brightness": 120, "autoBrightness": True})
        state = enter(self.client, self.state, self.idle, 120)
        self.client.install_script.assert_called_once()
        name, source = self.client.install_script.call_args.args
        self.assertEqual(name, APP_NAME)
        self.assertIn("# @name Great Wave", source)
        self.client.set_app_order.assert_called_once_with([APP_NAME], [CALENDAR["name"]])
        self.assertEqual(state["order"], ["google_calendar"])

    def test_enter_reasserts_order_once_when_another_app_remains_in_loop(self):
        self.client.list_apps.side_effect = [
            (200, [CALENDAR]), (200, [WAVE, CALENDAR]), (200, [WAVE, CALENDAR]),
            (200, [WAVE, DISABLED_CALENDAR]),
        ]
        self.client.get_settings.return_value = (200, {"brightness": 120})

        enter(self.client, self.state, self.idle, 120)

        expected_order = ([APP_NAME], [CALENDAR["name"]])
        self.assertEqual([call.args for call in self.client.set_app_order.call_args_list],
                         [expected_order, expected_order])
        self.assertEqual(self.client.activate_app.call_count, 2)
        self.client.activate_app.assert_called_with(APP_NAME)

    def test_enter_reports_persistent_extra_loop_app(self):
        self.client.list_apps.side_effect = [
            (200, [CALENDAR]), (200, [WAVE, CALENDAR]), (200, [WAVE, CALENDAR]),
            (200, [WAVE, CALENDAR]),
        ]
        self.client.get_settings.return_value = (200, {"brightness": 120})

        with self.assertRaisesRegex(ValueError, "extra active loop apps: google_calendar"):
            enter(self.client, self.state, self.idle, 120)

        expected_order = ([APP_NAME], [CALENDAR["name"]])
        self.assertEqual([call.args for call in self.client.set_app_order.call_args_list],
                         [expected_order, expected_order])
        self.assertEqual(self.client.activate_app.call_count, 2)
        self.client.activate_app.assert_called_with(APP_NAME)

    def test_enter_refuses_a_non_script_collision(self):
        self.client.list_apps.return_value = (200, [{"name": APP_NAME, "origin": "pushed", "present": True}])
        with self.assertRaises(ValueError):
            enter(self.client, self.state, self.idle, 120)
        self.client.install_script.assert_not_called()

    def test_enter_reports_a_script_that_installed_with_an_error(self):
        self.client.list_apps.side_effect = [
            (200, [CALENDAR]),
            (200, [CALENDAR]),
            (200, [{"name": APP_NAME, "origin": "script", "present": True,
                    "enabled": True, "inLoop": True,
                    "error": {"message": "syntax_error", "line": 3}}]),
        ]
        self.client.get_settings.return_value = (200, {"brightness": 120})
        with self.assertRaises(ValueError):
            enter(self.client, self.state, self.idle, 120)

    def test_enter_reuses_the_installed_script_on_a_later_meeting(self):
        self.client.list_apps.side_effect = [(200, [WAVE, DISABLED_CALENDAR]),
                                             (200, [WAVE, DISABLED_CALENDAR]),
                                             (200, [WAVE, DISABLED_CALENDAR])]
        self.client.get_settings.return_value = (200, {"brightness": 120})
        enter(self.client, self.state, self.idle, 120)
        self.client.install_script.assert_not_called()

    def test_enter_preempts_an_active_idle_takeover_and_exit_resumes_it(self):
        self.idle.write_text(json.dumps({"active": True, "brightness": 10, "autoBrightness": False,
                                         "order": ["Pixel-Fireplace"], "disabled": [],
                                         "activeApp": "Pixel-Fireplace"}))
        # During idle the live loop holds only the dimmed fireplace; the wave
        # snapshots that from the device, not from the idle state file.
        self.client.list_apps.side_effect = [(200, [CALENDAR]), (200, [FIREPLACE]),
                                             (200, [WAVE, DISABLED_FIREPLACE])]
        self.client.get_settings.return_value = (200, {"brightness": 10, "autoBrightness": False})
        self.client.get_device.return_value = (200, {"currentApp": "Pixel-Fireplace"})
        state = enter(self.client, self.state, self.idle, 120)
        # The wave snapshotted the dimmed idle state, so the fireplace resumes as it was.
        self.assertEqual(state["brightness"], 10)
        self.client.list_apps.side_effect = None
        self.client.list_apps.return_value = (200, [WAVE, FIREPLACE])
        exit_mode(self.client, self.state)
        self.client.set_app_order.assert_called_with(["Pixel-Fireplace"], [APP_NAME])
        self.client.patch_settings.assert_called_with({"autoBrightness": False, "brightness": 10})

    def test_exit_leaves_the_script_installed_for_the_next_meeting(self):
        self.client.list_apps.return_value = (200, [WAVE, CALENDAR])
        self.state.write_text(json.dumps({"active": True, "brightness": 120, "autoBrightness": False,
                                          "order": ["google_calendar"], "disabled": [], "activeApp": "codex"}))
        exit_mode(self.client, self.state)
        self.client.delete_app.assert_not_called()
        self.client.set_app_order.assert_called_once_with(["google_calendar"], [APP_NAME])
        self.assertFalse(self.state.exists())
