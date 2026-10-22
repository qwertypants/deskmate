"""One-shot command ownership, fallback, scheduling, and readback boundaries."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import subway_widget
from test_subway import NOW, fixture, train

APPS = [{"name": name, "origin": "pushed", "present": True, "enabled": True, "inLoop": True}
        for name in subway_widget.APP_NAMES]


class CommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
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
        self.client = self.factory.return_value
        self.client.list_apps.side_effect = [(200, []), (200, APPS)]

    def run_command(self, **kwargs):
        with redirect_stdout(io.StringIO()) as output:
            result = subway_widget.run(**kwargs)
        return result, output.getvalue()

    def test_pushes_exact_app_names_checks_ownership_and_readback(self):
        result, output = self.run_command()
        self.assertEqual([c.args[0] for c in self.client.push_app.call_args_list], list(subway_widget.APP_NAMES))
        self.assertIn("~12:33p", result["subway_eta"]["text"])
        self.assertIn("Verified subway_trains and subway_eta", output)
        self.assertEqual(self.client.list_apps.call_count, 2)
        for method in ("delete_app", "set_app_order", "patch_settings", "activate_app", "install_script"):
            getattr(self.client, method).assert_not_called()

    def test_dry_run_fetches_prints_payload_and_never_contacts_clock(self):
        result, output = self.run_command(dry_run=True)
        self.assertEqual(json.loads(output), result)
        self.download.assert_called_once_with(subway_widget.REALTIME_URL, 5_000_000)
        self.factory.assert_not_called()

    def test_shell_precedence_env_loading_and_cache_are_worktree_relative(self):
        (self.root / ".env").write_text("AWTRIX_HOST=http://from-file\n")
        os.environ["AWTRIX_HOST"] = "http://from-shell"
        self.run_command()
        self.factory.assert_called_once_with("http://from-shell")
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
        self.clock.side_effect = [NOW, NOW, NOW + 121]
        result, _ = self.run_command()
        self.assertIn("3 no estimate", result["subway_eta"]["text"])
