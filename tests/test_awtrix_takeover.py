import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from awtrix_takeover import claim, release, save, snapshot

FIREPLACE = {"name": "Pixel-Fireplace", "origin": "script", "enabled": True,
             "inLoop": True, "present": True}
WAVE = {"name": "deskmate-wave", "origin": "script", "enabled": True,
        "inLoop": True, "present": True}
CODEX = {"name": "codex", "origin": "pushed", "present": True,
         "enabled": True, "inLoop": True}


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.client = Mock()

    def test_snapshot_excludes_owned_names_and_records_display_state(self):
        apps = [FIREPLACE, CODEX, {"name": "Battery", "present": True, "enabled": False, "inLoop": False}]
        state = snapshot(apps, {"brightness": 120, "autoBrightness": True},
                         {"Pixel-Fireplace", "pixel-fireplace"}, "codex")
        self.assertEqual(state, {"active": True, "brightness": 120, "autoBrightness": True,
                                 "order": ["codex"], "disabled": ["Battery"], "activeApp": "codex"})

    def test_snapshot_only_saves_enabled_apps_that_were_in_the_loop(self):
        apps = [
            {"name": "active-script", "enabled": True, "inLoop": True, "present": True},
            {"name": "enabled-paused-script", "origin": "script", "enabled": True,
             "inLoop": False, "present": False},
            {"name": "disabled-script", "origin": "script", "enabled": False,
             "inLoop": True, "present": False},
        ]
        state = snapshot(apps, {}, set(), "active-script")
        self.assertEqual(state["order"], ["active-script"])
        self.assertEqual(state["disabled"], ["enabled-paused-script", "disabled-script"])
        self.assertEqual(state["activeApp"], "active-script")

    def test_snapshot_does_not_restore_current_app_outside_saved_loop(self):
        apps = [{"name": "enabled-paused-script", "enabled": True,
                 "origin": "script", "inLoop": False, "present": True}]
        state = snapshot(apps, {}, set(), "enabled-paused-script")
        self.assertEqual(state["activeApp"], None)
        self.assertEqual(state["disabled"], ["enabled-paused-script"])

    def test_claim_reuses_the_first_snapshot_across_repeated_runs(self):
        self.client.list_apps.side_effect = [(200, [FIREPLACE, CODEX]), (200, [WAVE])]
        self.client.get_settings.return_value = (200, {"brightness": 120, "autoBrightness": True})
        # The first listed/present app is not necessarily the app on screen.
        self.client.get_device.return_value = (200, {"currentApp": "codex"})
        first = claim(self.client, self.path, "deskmate-wave", {"deskmate-wave"}, 120, None)
        self.client.get_settings.return_value = (200, {"brightness": 120, "autoBrightness": False})
        second = claim(self.client, self.path, "deskmate-wave", {"deskmate-wave"}, 120, None)
        self.assertEqual(first, second)
        # The wave owns only itself, so the fireplace stays in the restored loop.
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["order"], ["Pixel-Fireplace", "codex"])
        self.assertEqual(saved["activeApp"], "codex")
        self.assertEqual(saved["autoBrightness"], True)

    def test_claim_defers_when_another_controller_is_active(self):
        other = Path(self.directory.name) / "idle.json"
        save(other, {"active": True, "brightness": 10, "autoBrightness": False,
                     "order": [], "disabled": [], "activeApp": "Pixel-Fireplace"})
        self.assertIsNone(claim(self.client, self.path, "deskmate-wave", {"deskmate-wave"}, 120, other))
        self.assertFalse(self.path.exists())
        self.client.set_app_order.assert_not_called()

    def test_claim_refuses_a_non_script_owner(self):
        self.client.list_apps.return_value = (200, [{"name": "deskmate-wave", "origin": "pushed", "present": True}])
        with self.assertRaises(ValueError):
            claim(self.client, self.path, "deskmate-wave", {"deskmate-wave"}, 120, None)
        self.assertFalse(self.path.exists())

    def test_release_restores_order_brightness_and_disables_the_owner(self):
        self.client.list_apps.return_value = (200, [WAVE, CODEX])
        save(self.path, {"active": True, "brightness": 10, "autoBrightness": False,
                         "order": ["Pixel-Fireplace"], "disabled": ["Battery"],
                         "activeApp": "Pixel-Fireplace"})
        release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
        self.client.set_app_order.assert_called_once_with(["Pixel-Fireplace"], ["Battery", "deskmate-wave"])
        self.client.patch_settings.assert_called_once_with({"autoBrightness": False, "brightness": 10})
        self.client.activate_app.assert_called_once_with("Pixel-Fireplace", fast=True)
        self.assertFalse(self.path.exists())

    def test_release_does_not_restore_disabled_or_enabled_out_of_loop_scripts(self):
        self.client.list_apps.return_value = (200, [WAVE, CODEX])
        save(self.path, {"active": True, "brightness": 50, "autoBrightness": False,
                         "order": ["active-script"],
                         "disabled": ["enabled-paused-script", "disabled-script"],
                         "activeApp": "active-script"})
        release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
        self.client.set_app_order.assert_called_once_with(
            ["active-script"], ["enabled-paused-script", "disabled-script", "deskmate-wave"])
        self.client.activate_app.assert_called_once_with("active-script", fast=True)

    def test_release_filters_disabled_apps_from_legacy_snapshot_order(self):
        self.client.list_apps.return_value = (200, [WAVE])
        save(self.path, {"active": True, "brightness": 50, "autoBrightness": False,
                         "order": ["enabled-script", "legacy-disabled"],
                         "disabled": ["legacy-disabled"], "activeApp": "legacy-disabled"})
        release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
        self.client.set_app_order.assert_called_once_with(
            ["enabled-script"], ["legacy-disabled", "deskmate-wave"])
        self.client.activate_app.assert_not_called()

    def test_release_keeps_the_owner_script_installed(self):
        self.client.list_apps.return_value = (200, [WAVE, CODEX])
        save(self.path, {"active": True, "brightness": 120, "autoBrightness": False,
                         "order": ["google_calendar"], "disabled": [], "activeApp": "codex"})
        release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
        self.client.delete_app.assert_not_called()

    def test_release_is_idempotent_without_a_state_file(self):
        self.client.list_apps.return_value = (200, [CODEX])
        release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
        self.assertFalse(self.path.exists())
        self.assertEqual(self.client.patch_settings.call_count, 0)

    def test_unreadable_state_fails_loudly(self):
        self.path.write_text("{not json")
        with self.assertRaises(ValueError):
            release(self.client, self.path, "deskmate-wave", {"deskmate-wave"})
