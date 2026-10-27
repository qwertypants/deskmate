"""Focused checks for source selection and failures before touching the clock."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from awtrix import Awtrix
from codex import account_limits, freshness, normalize_limits, read_local, read_usage
import main

NOW = 1791120000


def snapshot(age=10, used=34, reset=NOW + 500):
    return {"timestamp": datetime.fromtimestamp(NOW - age, timezone.utc).isoformat(),
            "primary": {"used_percent": used, "window_minutes": 300, "resets_at": reset},
            "secondary": {"used_percent": 53, "window_minutes": 10080, "resets_at": NOW + 8000}, "available_resets": 3}


def api_result(count=3):
    return {"rateLimits": {"limitId": "codex", "primary": {
        "usedPercent": 34, "windowDurationMins": 300, "resetsAt": NOW + 500},
        "secondary": {"usedPercent": 53, "windowDurationMins": 10080, "resetsAt": NOW + 8000}},
        "rateLimitResetCredits": {"availableCount": count, "credits": []}}


def fake_server(result):
    return """import sys,json
for line in sys.stdin:
    message=json.loads(line)
    if message.get('id') == 1:
        print(json.dumps({'id':1,'result':{}}),flush=True)
    elif message.get('id') == 2:
        print(json.dumps({'method':'account/rateLimits/updated','params':{}}),flush=True)
        print(json.dumps({'id':2,'result':RESULT}),flush=True)
""".replace("RESULT", repr(result))


class CodexTests(unittest.TestCase):
    def test_live_protocol_with_real_child_process(self):
        result = api_result()
        self.assertEqual(account_limits([sys.executable, "-u", "-c", fake_server(result)]), result)

    def test_protocol_errors_eof_and_timeout(self):
        scripts = ["import sys;sys.exit(1)",
                   "import time;time.sleep(10)",
                   "import sys;sys.stdin.readline();print('not JSON',flush=True)",
                   "import sys,json;sys.stdin.readline();print(json.dumps({'id':1,'error':'unauthenticated'}),flush=True)"]
        for script in scripts:
            with self.subTest(script=script), self.assertRaises(ValueError):
                account_limits([sys.executable, "-u", "-c", script], timeout=0.2)

    def test_normalize_and_authoritative_reset_count(self):
        data = normalize_limits(api_result())
        self.assertEqual(data["primary"], snapshot()["primary"])
        self.assertEqual(data["secondary"], snapshot()["secondary"])
        # Count is authoritative, even when the credit detail list is empty.
        self.assertEqual(data["available_resets"], 3)

    def test_specific_codex_bucket_wins(self):
        result = api_result()
        bucket = result["rateLimits"].copy()
        result["rateLimits"] = {"limitId": "other"}
        result["rateLimitsByLimitId"] = {"codex": bucket}
        self.assertEqual(normalize_limits(result)["primary"]["used_percent"], 34)
        result["rateLimitsByLimitId"] = {"other": bucket}
        with self.assertRaises(ValueError):
            normalize_limits(result)

    def test_zero_and_unknown_resets_are_distinct(self):
        for count in (0, None):
            self.assertEqual(normalize_limits(api_result(count))["available_resets"], count)
        data = api_result()
        data["rateLimitResetCredits"] = None
        self.assertIsNone(normalize_limits(data)["available_resets"])
        for count in (-1, True, "3", 3.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                normalize_limits(api_result(count))

    def test_invalid_percentages(self):
        for value in (-1, 101, True, "34", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                freshness(snapshot(used=value), 3600, NOW)

    def test_lifetime_is_remaining_age_allowance(self):
        self.assertEqual(freshness(snapshot(age=20, reset=NOW + 9000), 100, NOW), (20, 80000))

    def test_lifetime_is_capped_by_each_reset(self):
        self.assertEqual(freshness(snapshot(), 3600, NOW), (10, 500000))
        data = snapshot()
        data["secondary"]["resets_at"] = NOW + 20
        self.assertEqual(freshness(data, 3600, NOW), (10, 20000))

    def test_stale_expired_future_and_invalid_max_age(self):
        cases = [(snapshot(age=3600), 3600), (snapshot(reset=NOW), 3600),
                 (snapshot(age=-1), 3600), (snapshot(), 0), (snapshot(), float("nan"))]
        for data, age in cases:
            with self.subTest(data=data, age=age), self.assertRaises(ValueError):
                freshness(data, age, NOW)
        data = snapshot()
        data["secondary"]["window_minutes"] = 7200
        with self.assertRaisesRegex(ValueError, "seven days"):
            freshness(data, 3600, NOW)

    def test_missing_cli(self):
        with patch("codex.shutil.which", return_value=None), \
                patch("codex.Path.is_file", return_value=False), self.assertRaisesRegex(ValueError, "CLI not found"):
            read_local()

    def test_standard_library_reader_runs_from_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "codex"
            binary.write_text("#!" + sys.executable + "\n" + fake_server(api_result()))
            binary.chmod(0o755)
            real_run = subprocess.run

            def run_remote(command, **kwargs):
                self.assertEqual(command[-1], "python3 - --read-local --home '/a path/codex'")
                self.assertIn("BatchMode=yes", command)
                return real_run([sys.executable, "-", "--read-local", "--home", "/a path/codex"], **kwargs)

            with patch.dict(os.environ, {"PATH": directory}), patch("codex.subprocess.run", side_effect=run_remote):
                data = read_usage("user@mac", "/a path/codex")
                self.assertEqual(data["primary"], snapshot()["primary"])
                self.assertEqual(data["available_resets"], 3)

    def test_ssh_failures(self):
        failures = [subprocess.TimeoutExpired("ssh", 30),
                    Mock(returncode=255, stderr="Permission denied", stdout=""),
                    Mock(returncode=0, stderr="", stdout="not JSON")]
        for failure in failures:
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=failure), patch("codex.subprocess.run", **kwargs), self.assertRaises(ValueError):
                read_usage("user@mac")


class AwtrixTests(unittest.TestCase):
    def response(self, client, body, status=200):
        response = io.BytesIO(json.dumps(body).encode())
        response.status = status
        client.http.open = Mock(return_value=response)

    def test_push_protocol_and_acknowledgement(self):
        client = Awtrix("http://clock/")
        self.response(client, {"ok": True})
        self.assertEqual(client.push_app("codex", {"text": "CODEX 34%"}), 200)
        request = client.http.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://clock/api/v1/apps/pushed/codex")
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {"text": "CODEX 34%"})
        self.response(client, {"ok": False})
        with self.assertRaisesRegex(ValueError, "acknowledge"):
            client.push_app("codex", {"text": "CODEX 34%"})

    def test_delete_protocol_and_acknowledgement(self):
        client = Awtrix("http://clock")
        self.response(client, {"ok": True})
        self.assertEqual(client.delete_app("codex_week"), 200)
        request = client.http.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://clock/api/v1/apps/codex_week")
        self.assertEqual(request.get_method(), "DELETE")
        self.assertIsNone(request.data)
        self.response(client, {"ok": False})
        with self.assertRaisesRegex(ValueError, "acknowledge deletion"):
            client.delete_app("codex_week")

    def test_http_and_connection_failures(self):
        client = Awtrix("http://clock")
        failures = [HTTPError("http://clock", 422, "Invalid", {}, io.BytesIO(b'bad payload')),
                    URLError("unreachable"), TimeoutError("timed out")]
        for failure in failures:
            with self.subTest(failure=failure):
                client.http.open = Mock(side_effect=failure)
                with self.assertRaises(ValueError):
                    client.push_app("codex", {"text": "x"})

    def test_invalid_response_shapes(self):
        client = Awtrix("http://clock")
        self.response(client, {"ok": True})
        with self.assertRaisesRegex(ValueError, "app list"):
            client.list_apps()
        response = io.BytesIO(b"<html>setup</html>")
        response.status = 200
        client.http.open = Mock(return_value=response)
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            client.list_apps()


class CommandTests(unittest.TestCase):
    def pixels(self, data):
        pages = main.payloads(data, 1000)
        self.assertEqual(list(pages), ["codex"])
        page = pages["codex"]
        self.assertEqual(page["lifetimeMs"], 1000)
        bitmap = page["draw"][0]
        self.assertEqual(bitmap[:5], ["bitmap", 0, 0, 32, 8])
        rgb = base64.b64decode(bitmap[5], validate=True)
        self.assertEqual(len(rgb), 32 * 8 * 3)
        self.assertLess(len(json.dumps(page).encode()), 8192)
        return [rgb[i:i+3] for i in range(0,len(rgb),3)]

    def colored_points(self, pixels, color):
        return {(x, y) for y in range(8) for x in range(32)
                if pixels[y * 32 + x] == bytes.fromhex(color)}

    def test_remaining_percentage_conversion(self):
        self.assertEqual(main.rounded_remaining({"used_percent": 67}), 33)
        self.assertEqual(main.rounded_remaining({"used_percent": 58}), 42)
        self.assertEqual(main.rounded_remaining({"used_percent": 0}), 100)
        self.assertEqual(main.rounded_remaining({"used_percent": 100}), 0)
        self.assertEqual(main.rounded_remaining({"used_percent": 34.5}), 66)
        self.assertIsNone(main.rounded_remaining(None))

    def test_selected_layout_and_bar_lengths(self):
        data = snapshot(used=51)
        data["secondary"]["used_percent"] = 55
        pixels = self.pixels(data)
        blue = bytes.fromhex("38bdf8")
        purple = bytes.fromhex("c084fc")
        self.assertEqual(sum(pixels[7*32+x] == blue for x in range(4,15)), 5)
        self.assertEqual(sum(pixels[7*32+x] == purple for x in range(16,27)), 5)
        self.assertEqual(pixels[1*32+0], bytes.fromhex("d7f8ee"))
        self.assertEqual(pixels[6*32+1], bytes.fromhex("d7f8ee"))
        self.assertEqual(pixels[1*32+28], bytes.fromhex("fbbf24"))
        # Empty separator columns distinguish the three values.
        self.assertTrue(all(pixels[y*32+x] == b"\0\0\0" for y in range(8) for x in (3,15,27)))

    def test_unknown_values_have_question_marks_and_no_bar(self):
        data = snapshot()
        data["secondary"] = None
        data["available_resets"] = None
        pixels = self.pixels(data)
        self.assertTrue(all(pixels[7*32+x] == b"\0\0\0" for x in range(16,27)))
        self.assertEqual(pixels[1*32+16], bytes.fromhex("c084fc"))
        self.assertEqual(pixels[1*32+28], bytes.fromhex("fbbf24"))

    def test_all_percentage_values_fit_and_bars_match(self):
        for used in range(101):
            with self.subTest(used=used):
                data = snapshot(used=used)
                data["secondary"]["used_percent"] = 100-used
                pixels = self.pixels(data)
                self.assertEqual(sum(pixels[7*32+x] == bytes.fromhex("38bdf8") for x in range(4,15)),
                                 int(11*(100-used)/100+0.5))
        data = snapshot(used=0)
        pixels = self.pixels(data)
        # The percent sign remains present at 100, in the last three columns.
        self.assertEqual(pixels[1*32+12], bytes.fromhex("38bdf8"))
        self.assertEqual(pixels[1*32+14], bytes.fromhex("38bdf8"))

    def test_depleted_primary_renders_eastern_reset_clock_without_touching_other_fields(self):
        data = snapshot(used=99.6, reset=datetime(2026, 10, 27, 19, 42,
                                                tzinfo=timezone.utc).timestamp())
        depleted = self.pixels(data)
        expected_clock = {(5, 1), (5, 3), (5, 5),
                          (6, 1), (6, 2), (6, 3), (6, 4), (6, 5),
                          (8, 2), (8, 4),
                          (10, 1), (10, 2), (10, 3),
                          (11, 3), (11, 4), (11, 5),
                          (12, 1), (12, 3), (12, 4), (12, 5),
                          (13, 1), (13, 2), (13, 3), (13, 5)}
        self.assertEqual(self.colored_points(depleted, "38bdf8"), expected_clock)
        self.assertTrue(all(depleted[7 * 32 + x] == bytes.fromhex("23313d")
                            for x in range(4, 15)))

        nonzero = snapshot(used=99.4, reset=data["primary"]["resets_at"])
        normal = self.pixels(nonzero)
        for y in range(8):
            for x in range(16, 32):
                self.assertEqual(depleted[y * 32 + x], normal[y * 32 + x], (x, y))
        self.assertTrue(self.colored_points(depleted, "c084fc"))
        self.assertTrue(self.colored_points(depleted, "fbbf24"))
        self.assertEqual(self.colored_points(normal, "38bdf8"),
                         {(5, 1), (4, 2), (5, 2), (5, 3), (5, 4),
                          (4, 5), (5, 5), (6, 5),
                          (8, 1), (10, 1), (10, 2), (9, 3),
                          (8, 4), (8, 5), (10, 5)})

    def test_reset_clock_handles_midnight_noon_and_daylight_saving(self):
        cases = (("2026-01-15T05:00:00+00:00", "12:00"),
                 ("2026-01-15T17:00:00+00:00", "12:00"),
                 ("2026-07-15T19:42:00+00:00", "3:42"),
                 ("2026-11-01T05:30:00+00:00", "1:30"),
                 ("2026-11-01T06:30:00+00:00", "1:30"))
        for timestamp, expected in cases:
            with self.subTest(timestamp=timestamp):
                primary = {"resets_at": datetime.fromisoformat(timestamp).timestamp()}
                self.assertEqual(main.primary_reset_clock(primary), expected)
                data = snapshot(used=100, reset=primary["resets_at"])
                self.assertTrue(all(4 <= x <= 14
                                    for x, _ in self.colored_points(self.pixels(data), "38bdf8")))

    def test_depleted_primary_rejects_missing_or_malformed_reset_time(self):
        bad_values = (None, True, "soon", float("nan"), float("inf"), -1)
        for value in bad_values:
            with self.subTest(value=value):
                data = snapshot(used=100)
                if value is None:
                    del data["primary"]["resets_at"]
                else:
                    data["primary"]["resets_at"] = value
                with self.assertRaisesRegex(ValueError, "Invalid Codex resets_at"):
                    self.pixels(data)

    def test_reset_overflow_is_marked_without_clipping(self):
        for count in (0, 9, 10, 999):
            with self.subTest(count=count):
                data = snapshot()
                data["available_resets"] = count
                pixels = self.pixels(data)
                if count >= 10:
                    self.assertEqual(pixels[3*32+28], bytes.fromhex("fbbf24"))
                    self.assertEqual(pixels[3*32+29], bytes.fromhex("fbbf24"))

    def test_success_and_shell_configuration_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("AWTRIX_HOST=http://from-file\nCODEX_MAX_AGE_SECONDS=100\n")
            with patch("main.__file__", str(root / "src/main.py")), \
                    patch.dict(os.environ, {"AWTRIX_HOST": "http://from-shell"}, clear=True), \
                    patch("main.read_usage", return_value=snapshot(used=34.5)) as reader, \
                    patch("codex.time.time", return_value=NOW), patch("main.Awtrix") as factory, \
                    redirect_stdout(io.StringIO()) as output:
                client = factory.return_value
                client.host = "http://from-shell"
                app = {"name": "codex", "origin": "pushed", "present": True,
                       "enabled": True, "inLoop": True}
                client.list_apps.side_effect = [(200, []), (200, [app])]
                client.push_app.return_value = 200
                main.run()
                factory.assert_called_once_with("http://from-shell")
                reader.assert_called_once_with(None, None)
                client.push_app.assert_called_once()
                args = client.push_app.call_args.args
                self.assertEqual(args[0], "codex")
                self.assertEqual(args[1]["lifetimeMs"], 90000)
                self.assertIn("5H 66% left", output.getvalue())
                self.assertIn("Verified codex", output.getvalue())
                client.delete_app.assert_not_called()

    def test_old_pages_removed_only_after_new_page_verified(self):
        with patch("main.load_dotenv"), patch.dict(os.environ, {}, clear=True), \
                patch("main.read_usage", return_value=snapshot()), \
                patch("codex.time.time", return_value=NOW), patch("main.Awtrix") as factory, \
                redirect_stdout(io.StringIO()):
            client = factory.return_value
            client.host = "http://clock"
            page = {"name": "codex", "origin": "pushed", "present": True, "enabled": True, "inLoop": True}
            old = [{"name": "codex_week", "origin": "pushed", "present": True},
                   {"name": "codex_resets", "origin": "script", "present": True}]
            client.list_apps.side_effect = [(200, old), (200, [page]+old), (200, [page,old[1]])]
            client.push_app.return_value = 200
            client.delete_app.return_value = 200
            main.run()
            client.delete_app.assert_called_once_with("codex_week")
            methods = [call[0] for call in client.mock_calls]
            self.assertLess(methods.index("push_app"), methods.index("delete_app"))
            self.assertEqual(methods[:3], ["list_apps", "push_app", "list_apps"])

    def test_stale_source_never_contacts_awtrix(self):
        with patch("main.load_dotenv"), patch.dict(os.environ, {}, clear=True), \
                patch("main.read_usage", return_value=snapshot(age=4000)), \
                patch("codex.time.time", return_value=NOW), patch("main.Awtrix") as client:
            with self.assertRaisesRegex(ValueError, "stale"):
                main.run()
            client.assert_not_called()

    def test_missing_or_disabled_app_fails_verification(self):
        for after in ([], [{"name": "codex", "origin": "pushed", "present": True,
                          "enabled": False, "inLoop": False}]):
            with patch("main.load_dotenv"), patch.dict(os.environ, {}, clear=True), \
                    patch("main.read_usage", return_value=snapshot()), \
                    patch("codex.time.time", return_value=NOW), patch("main.Awtrix") as factory, \
                    redirect_stdout(io.StringIO()):
                client = factory.return_value
                client.list_apps.side_effect = [(200, []), (200, after)]
                client.push_app.return_value = 200
                with self.assertRaisesRegex(ValueError, "not verified"):
                    main.run()
                client.delete_app.assert_not_called()

    def test_existing_script_is_not_overwritten(self):
        with patch("main.load_dotenv"), patch.dict(os.environ, {}, clear=True), \
                patch("main.read_usage", return_value=snapshot()), \
                patch("codex.time.time", return_value=NOW), patch("main.Awtrix") as factory:
            client = factory.return_value
            client.list_apps.return_value = (200, [{"name": "codex", "origin": "script"}])
            with self.assertRaisesRegex(ValueError, "refusing"):
                main.run()
            client.push_app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
