import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

import render
from render import DEFAULT_DURATIONS, MAX_DURATIONS, gif_duration_ms


class TransitionTimingTests(unittest.TestCase):
    def test_manifest_matches_registered_transitions(self):
        manifest = json.loads((render.ROOT / "manifest.json").read_text())
        self.assertEqual(
            [animation["id"] for animation in manifest["animations"]],
            list(render.NAMES),
        )
        self.assertEqual(manifest["animations"][-1]["durationMs"], 7000)

    def test_great_wave_is_a_seven_second_animation(self):
        self.assertEqual(DEFAULT_DURATIONS["great-wave"], 7000)
        self.assertEqual(MAX_DURATIONS["great-wave"], 7000)
        self.assertEqual(gif_duration_ms("great-wave"), 70)

    def test_existing_animation_durations_remain_unchanged(self):
        self.assertEqual(DEFAULT_DURATIONS["aurora-tide"], 3000)
        self.assertEqual(DEFAULT_DURATIONS["ocean-drops"], 5000)
        self.assertEqual(DEFAULT_DURATIONS["prism-loom"], 3000)
        self.assertEqual(gif_duration_ms("ocean-drops") * 100, 5000)

    def test_exact_cycle_seam_is_opt_in(self):
        self.assertEqual(render.SEAM_VALIDATED, frozenset({"great-wave", "neon-highway", "mushroom-run"}))
        for slug in render.NAMES:
            with self.subTest(slug=slug), patch.object(render, "execute") as execute:
                render.verify("berry", "source", DEFAULT_DURATIONS[slug],
                              MAX_DURATIONS[slug], slug in render.SEAM_VALIDATED)
                script = execute.call_args.args[2]
                seam_clock = f"clock=10000+{DEFAULT_DURATIONS[slug]} clear() app.draw()"
                self.assertEqual(seam_clock in script, slug in render.SEAM_VALIDATED)
                self.assertIn("clock=500000 app.on_show()", script)
                self.assertIn("configured=750 app.on_show() assert(app.duration()==1000)", script)
                self.assertIn(f"configured=9000 app.on_show() assert(app.duration()=={MAX_DURATIONS[slug]})", script)

    def test_near_seam_delta_is_checked_for_seam_validated_animations(self):
        for slug in render.NAMES:
            with self.subTest(slug=slug), patch.object(render, "execute") as execute:
                duration = DEFAULT_DURATIONS[slug]
                render.verify("berry", "source", duration, MAX_DURATIONS[slug],
                              slug in render.SEAM_VALIDATED)
                script = execute.call_args.args[2]
                for offset in ("-50", "-25", "", "+25", "+50"):
                    sample = f"clock=10000+{duration}{offset} clear() app.draw()"
                    self.assertEqual(sample in script, slug in render.SEAM_VALIDATED)
                self.assertEqual("var seam_delta=max(frame_delta(before,at),frame_delta(at,after))" in script,
                                 slug in render.SEAM_VALIDATED)
                self.assertEqual("assert(seam_delta<=160)" in script, slug in render.SEAM_VALIDATED)
                self.assertEqual("assert(seam_delta<=nearby*2+8)" in script, slug in render.SEAM_VALIDATED)
        self.assertIn("def frame_delta(a,b)", render.PRELUDE)
        self.assertIn("for i : 0..255", render.PRELUDE)
        self.assertIn("if delta > largest largest = delta end", render.PRELUDE)

    def test_great_wave_uses_continuous_color_weights(self):
        source = (render.ROOT / "great-wave.be").read_text()
        for weight in ("foamWeight", "shadowWeight", "hookWeight"):
            self.assertIn(weight, source)
        self.assertGreaterEqual(source.count("clamp("), 7)
        self.assertNotRegex(source, r"\b(?:if|elif)\s+(?:depth|foam|hook)\s*[<>]")
        self.assertNotIn("&& foam >", source)
        self.assertNotIn("&& hook >", source)

    def test_build_passes_seam_flag_for_seam_validated_animations(self):
        for slug in render.NAMES:
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as temp:
                Path(temp, f"{slug}.be").write_text("source")
                with patch.object(render, "ROOT", Path(temp)), \
                        patch.object(render, "NAMES", {slug: render.NAMES[slug]}), \
                        patch.object(render, "verify") as verify, \
                        patch.object(render, "frames_for", side_effect=RuntimeError("stop after verify")):
                    with self.assertRaisesRegex(RuntimeError, "stop after verify"):
                        render.build("berry")
                    self.assertEqual(verify.call_args.args[-1], slug in render.SEAM_VALIDATED)


class FrameValidationTests(unittest.TestCase):
    @staticmethod
    def sample_frames():
        return [[1 + (((pixel // 32) + ((frame >> (pixel % 8)) & 1)) % 8) * 256
                 for pixel in range(256)] for frame in range(200)]

    def test_rejects_bad_frame_count_shape_and_colors(self):
        valid = [[1] * 256 for _ in range(200)]
        bad_cases = (
            (valid[:-1], "expected 200 frames"),
            (valid[:-1] + [[1] * 255], "expected 256 pixels"),
            (valid[:-1] + [[1] * 255 + [0x1000000]], "invalid RGB color"),
            (valid[:-1] + [[1] * 255 + [1.5]], "invalid RGB color"),
            (valid[:-1] + [[1] * 255 + [True]], "invalid RGB color"),
            (valid[:-1] + [[1] * 255 + [0]], "every pixel must be colored"),
        )
        render.validate_frames(valid, "sample")
        for frames, message in bad_cases:
            with self.subTest(message=message), self.assertRaisesRegex(AssertionError, message):
                render.validate_frames(frames, "sample")

    def test_build_rejects_zero_pixel_in_short_sample(self):
        frames = [[1] * 256 for _ in range(200)]
        short = [[1] * 256 for _ in range(200)]
        short[-1][-1] = 0
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "aurora-tide.be").write_text("source")
            with patch.object(render, "ROOT", Path(temp)), \
                    patch.object(render, "NAMES", {"aurora-tide": ("Aurora Tide", "sample")}), \
                    patch.object(render, "write_gallery"), \
                    patch.object(render, "verify"), \
                    patch.object(render, "frames_for", side_effect=(frames, short)):
                with self.assertRaisesRegex(AssertionError, "every pixel must be colored"):
                    render.build("berry")

    def test_failed_later_animation_preserves_published_outputs(self):
        frames = self.sample_frames()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for slug in ("aurora-tide", "great-wave"):
                (root / f"{slug}.be").write_text("source")
            previews = root / "previews"
            previews.mkdir()
            original = {"index.html": b"old gallery", "manifest.json": b"old manifest",
                        "previews/aurora-tide.gif": b"old GIF", "previews/contact-sheet.png": b"old sheet",
                        "color-current-transition-pack.zip": b"old ZIP",
                        "previews/personal-note.txt": b"user file"}
            for name, content in original.items():
                (root / name).write_bytes(content)
            with patch.object(render, "ROOT", root), \
                    patch.object(render, "NAMES", {slug: render.NAMES[slug]
                                                    for slug in ("aurora-tide", "great-wave")}), \
                    patch.object(render, "verify", side_effect=(None, RuntimeError("Berry failed"))), \
                    patch.object(render, "frames_for", side_effect=(frames, frames)):
                with self.assertRaisesRegex(RuntimeError, "Berry failed"):
                    render.build("berry")
            for name, content in original.items():
                self.assertEqual((root / name).read_bytes(), content, name)

    def test_success_publishes_complete_bundle_and_preserves_user_file(self):
        frames = self.sample_frames()
        # GIF encoders merge adjacent identical frames into a longer duration.
        # Playback must still equal the 100 sampled ticks exactly.
        frames[2] = frames[0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "great-wave.be").write_text("source")
            (root / "previews").mkdir()
            (root / "previews/personal-note.txt").write_text("keep")
            with patch.object(render, "ROOT", root), \
                    patch.object(render, "NAMES", {"great-wave": render.NAMES["great-wave"]}), \
                    patch.object(render, "verify"), \
                    patch.object(render, "frames_for", side_effect=(frames, frames)):
                render.build("berry")
            self.assertEqual((root / "previews/personal-note.txt").read_text(), "keep")
            self.assertEqual(json.loads((root / "manifest.json").read_text())["animations"][0]["durationMs"], 7000)
            with zipfile.ZipFile(root / "color-current-transition-pack.zip") as archive:
                names = set(archive.namelist())
                for name in ("great-wave.be", "index.html", "manifest.json",
                             "previews/great-wave.gif", "previews/great-wave.png",
                             "previews/contact-sheet.png"):
                    self.assertIn("color-current-transition-pack/" + name, names)
            with Image.open(root / "previews/great-wave.gif") as gif:
                durations = []
                decoded_ticks = []
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    frame_duration = gif.info["duration"]
                    durations.append(frame_duration)
                    self.assertEqual(frame_duration % gif_duration_ms("great-wave"), 0)
                    decoded = gif.convert("RGB").tobytes()
                    decoded_ticks.extend([decoded] * (frame_duration // gif_duration_ms("great-wave")))
                palette_source = Image.new("RGB", (32 * 16, 8 * 13))
                for sample_index, frame in enumerate(frames):
                    palette_source.paste(render.image_for(frame, scale=1),
                                         ((sample_index % 16) * 32, (sample_index // 16) * 8))
                palette = palette_source.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                                  dither=Image.Dither.NONE)
                expected_ticks = [image.quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB").tobytes()
                                  for image in [render.image_for(frame) for frame in frames][::2]]
                self.assertEqual(decoded_ticks, expected_ticks)
                self.assertLess(gif.n_frames, render.GIF_FRAME_COUNT)
                self.assertEqual(sum(durations), DEFAULT_DURATIONS["great-wave"])

    def test_publish_failure_restores_every_original_generated_output(self):
        frames = self.sample_frames()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "great-wave.be").write_text("source")
            (root / "previews").mkdir()
            names = ("index.html", "manifest.json", "previews/great-wave.gif",
                     "previews/great-wave.png", "previews/contact-sheet.png",
                     "color-current-transition-pack.zip")
            original = {name: f"old {name}".encode() for name in names}
            for name, content in original.items():
                (root / name).write_bytes(content)
            (root / "previews/personal-note.txt").write_text("keep")
            replace = render.os.replace

            def fail_on_zip(source, target):
                if target == root / "color-current-transition-pack.zip":
                    raise OSError("injected ZIP publish failure")
                return replace(source, target)

            with patch.object(render, "ROOT", root), \
                    patch.object(render, "NAMES", {"great-wave": render.NAMES["great-wave"]}), \
                    patch.object(render, "verify"), \
                    patch.object(render, "frames_for", side_effect=(frames, frames)), \
                    patch.object(render.os, "replace", side_effect=fail_on_zip):
                with self.assertRaisesRegex(OSError, "injected ZIP publish failure"):
                    render.build("berry")
            for name, content in original.items():
                self.assertEqual((root / name).read_bytes(), content, name)
            self.assertEqual((root / "previews/personal-note.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
