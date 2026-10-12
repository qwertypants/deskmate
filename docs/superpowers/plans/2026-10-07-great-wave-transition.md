# Great Wave Transition Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an original, seamlessly looping Great Wave AWTRIX transition to the existing pack with a configurable 7000 ms default cycle and verified generated artifacts.

**Architecture:** Add one self-contained Berry app whose motion is driven only by periodic functions of elapsed time. Extend the existing Python renderer to keep each animation's registered duration, calculate GIF timing from that duration, and assert the Great Wave's exact seam. Regenerate all pack artifacts through the renderer; do not hand-edit generated files.

**Tech Stack:** Berry, AWTRIX NG 32×8 drawing API, Python 3, Pillow, the repository's Berry interpreter, standard `git`.

## Global Constraints

- Target the existing `packs/transitions` pack and preserve its `Color Current` ZIP/gallery identity.
- Great Wave uses `durationMs` default `7000`, clamped to `1000–7000` ms; existing animations retain their current defaults and limits.
- Every sampled frame must contain exactly 256 valid RGB integers and every pixel must be nonzero.
- Great Wave's frame at `t=0` must equal its frame exactly one configured duration later.
- Berry drawing must use `now_ms()` and periodic phase functions; no frame arrays, blocking loops, or uploaded icons.
- Generated previews, gallery, manifest, contact sheet, and ZIP are renderer outputs and must not be hand-edited.
- Physical AWTRIX installation or display readback is out of scope for this change.

---

### Task 1: Add renderer timing regression coverage

**Files:**
- Create: `packs/transitions/tools/test_render.py`
- Modify: `packs/transitions/tools/render.py:18-22`

**Interfaces:**
- Produces `MAX_DURATIONS` and `gif_duration_ms(slug)` for the renderer and its focused unit tests.
- `gif_duration_ms(slug)` returns the integer duration of each of the 100 GIF frames sampled from 200 Berry frames.

- [ ] **Step 1: Write the failing timing tests**

```python
import unittest

from render import DEFAULT_DURATIONS, MAX_DURATIONS, gif_duration_ms


class TransitionTimingTests(unittest.TestCase):
    def test_great_wave_is_a_seven_second_animation(self):
        self.assertEqual(DEFAULT_DURATIONS["great-wave"], 7000)
        self.assertEqual(MAX_DURATIONS["great-wave"], 7000)
        self.assertEqual(gif_duration_ms("great-wave"), 70)

    def test_existing_animation_durations_remain_unchanged(self):
        self.assertEqual(DEFAULT_DURATIONS["aurora-tide"], 3000)
        self.assertEqual(DEFAULT_DURATIONS["ocean-drops"], 5000)
        self.assertEqual(DEFAULT_DURATIONS["prism-loom"], 3000)
        self.assertEqual(gif_duration_ms("ocean-drops") * 100, 5000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
PYTHONPATH=packs/transitions/tools python3 -m unittest packs/transitions/tools/test_render.py -v
```

Expected: FAIL because `great-wave`, `MAX_DURATIONS`, and `gif_duration_ms` do not yet exist.

- [ ] **Step 3: Add the timing registry and helper**

Extend the renderer registry without changing the three existing entries:

```python
NAMES = {
    'aurora-tide': ('Aurora Tide', 'A luminous aurora sweeps across the display in teal, blue, violet, and coral.'),
    'ocean-drops': ('Ocean Drops', 'Layered ocean ripples expand and roll across the full display.'),
    'prism-loom': ('Prism Loom', 'Color curtains weave around a bright seam, then resolve into a warm glow.'),
    'great-wave': ('Great Wave', 'An original indigo wave curls and rolls across the display in a woodblock-inspired palette.'),
}
STYLES = {
    'aurora-tide': 'GRADIENT WAVES',
    'ocean-drops': 'OCEAN RIPPLE',
    'prism-loom': 'COLOR CURTAINS',
    'great-wave': 'WOODBLOCK WAVE',
}
DEFAULT_DURATIONS = {
    'aurora-tide': 3000,
    'ocean-drops': 5000,
    'prism-loom': 3000,
    'great-wave': 7000,
}
MAX_DURATIONS = {
    'aurora-tide': 5000,
    'ocean-drops': 5000,
    'prism-loom': 5000,
    'great-wave': 7000,
}
GIF_FRAME_COUNT = 100


def gif_duration_ms(slug):
    duration = DEFAULT_DURATIONS[slug]
    if duration % GIF_FRAME_COUNT:
        raise ValueError(f'{slug}: duration must divide evenly into {GIF_FRAME_COUNT} GIF frames')
    return duration // GIF_FRAME_COUNT
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run the same unittest command. Expected: PASS with both timing tests green.

- [ ] **Step 5: Commit the focused renderer-registry test and implementation**

Inspect with `git status` and `git diff`, then stage only the two paths and commit them:

```bash
git diff
git add packs/transitions/tools/test_render.py packs/transitions/tools/render.py
git diff --cached --stat
```

Confirm the staged stat shows only `test_render.py` and `render.py`, then commit on the feature branch. Do not include unrelated workspace changes.

### Task 2: Generalize renderer validation to registered durations

**Files:**
- Modify: `packs/transitions/tools/render.py:76-195`

**Interfaces:**
- `verify(berry, source, default_duration, max_duration)` validates lifecycle, clamping, and the exact-cycle seam.
- `frames_for(berry, source, duration)` continues to return 200 sampled frames for any registered duration.
- `build(berry)` uses the registered duration for Berry execution, GIF frame duration, parity checks, manifest metadata, and build output.

- [ ] **Step 1: Make the existing validation call duration-aware**

Change `verify` so its generated Berry assertions use the supplied values:

```python
def verify(berry, source, default_duration, max_duration):
    execute(berry, source, f'''
configured={default_duration} assert(app.duration()=={default_duration})
clock=10000 app.on_show() clear() app.draw()
var initial=json.dump(canvas)
clock=10000+{default_duration} clear() app.draw()
assert(json.dump(canvas)==initial)
configured=750 app.on_show() assert(app.duration()==1000)
configured=9000 app.on_show() assert(app.duration()=={max_duration})
configured=2500 app.on_show() assert(app.duration()==2500)
clock+=2500 clear() app.draw()
clock+=1000 clear() app.draw()
''')
```

The exact-duration comparison is the seam regression: it must run for every registered animation, and Great Wave must pass it at 7000 ms.

- [ ] **Step 2: Run the existing focused tests before changing the build loop**

Run:

```bash
PYTHONPATH=packs/transitions/tools python3 -m unittest packs/transitions/tools/test_render.py -v
```

Expected: PASS; no Berry build is expected yet because the new source is not present.

- [ ] **Step 3: Make GIF timing and parity use the registered duration**

Inside `build`, bind `duration = DEFAULT_DURATIONS[slug]`, call `verify(berry, source, duration, MAX_DURATIONS[slug])`, and call `frames_for(berry, source, duration)`. Replace the fixed GIF timing/parity assumptions with:

```python
gif_duration = gif_duration_ms(slug)
gif_frames = [img.quantize(palette=palette, dither=Image.Dither.NONE) for img in images[::2]]
gif_frames[0].save(
    previews / f'{slug}.gif', save_all=True, append_images=gif_frames[1:],
    duration=gif_duration, loop=0, optimize=False, disposal=1, background=0,
)

with Image.open(previews / f'{slug}.gif') as gif:
    total = 0
    for index in range(gif.n_frames):
        gif.seek(index)
        self_frame = gif.convert('RGB').tobytes()
        expected_frame = gif_frames[index].convert('RGB').tobytes()
        assert self_frame == expected_frame, (slug, 'GIF pixel mismatch', index)
        total += gif.info['duration']
    assert total == duration, (slug, total, duration)
```

Keep the existing 200-frame, 256-pixel, motion, color, and manifest assertions unchanged except for using the local `duration` variable.

- [ ] **Step 4: Run the renderer timing tests again**

Run the focused unittest command. Expected: PASS.

- [ ] **Step 5: Commit the duration-aware renderer validation**

Inspect with `git diff`, stage only `packs/transitions/tools/render.py`, and confirm with `git diff --cached --stat` before committing.

### Task 3: Implement the seamless Great Wave Berry animation

**Files:**
- Create: `packs/transitions/great-wave.be`

**Interfaces:**
- AWTRIX app name: `Great Wave` from the `@name` header; source filename is `great-wave.be`.
- Config key: `durationMs`, default `7000`, minimum `1000`, maximum `7000`, step `100`.
- Lifecycle: `init()`, `duration()`, `on_show()`, and `draw()` only.

- [ ] **Step 1: Add the Berry source with periodic motion and the 7-second config**

Use this header and app structure:

```berry
# @name Great Wave
# @desc An original indigo wave curls and rolls across the display in a woodblock-inspired palette.
# @author Deskmate
# @version 1.0.0
# @display 32x8
# @config durationMs number "Duration" default=7000 min=1000 max=7000 step=100 unit=ms

import math

class App
  var started, ms

  def init()
    self.started = now_ms()
    self.ms = self.duration()
  end

  def duration()
    var value = int(store.get('durationMs'))
    if value < 1000 value = 1000 end
    if value > 7000 value = 7000 end
    return value
  end

  def on_show()
    self.started = now_ms()
    self.ms = self.duration()
  end

  def draw()
    clear()
    var t = (now_ms() - self.started) * 1.0 / self.ms
    t = t - int(t)
    var phase = t * 6.28318
    var w = width(), h = height()
    for y : 0..h-1
      for x : 0..w-1
        var row = y * 1.0 / (h - 1)
        var swell = 0.5 + 0.5 * math.sin(phase * 2.0 - x * 0.13 + y * 0.72)
        var fold = 0.5 + 0.5 * math.cos(phase - x * 0.22 + y * 0.54)
        var red = 4 + int(5 * row + 5 * swell)
        var green = 16 + int(28 * row + 38 * fold)
        var blue = 42 + int(48 * row + 76 * swell)

        var center = t * w
        var dx = x - center
        if dx < -w * 0.5 dx += w end
        if dx > w * 0.5 dx -= w end
        var crestY = 3.0 + 1.25 * math.sin(dx * 0.24 + phase * 1.2) + 0.75 * math.sin(dx * 0.58 - phase * 0.8)
        var depth = y - crestY
        var foam = 0.5 + 0.5 * math.cos(dx * 0.82 + phase * 1.7 + y * 0.7)
        if depth > -1.0 && depth < 1.4 && foam > 0.28
          red += 80 + int(70 * foam)
          green += 86 + int(92 * foam)
          blue += 54 + int(76 * foam)
        elif depth > 0.8 && depth < 2.1
          red += 10
          green += 30
          blue += 42
        end
        var hook = math.sin(dx * 1.45 - phase * 2.4 + y * 0.9)
        if depth > -0.45 && depth < 0.35 && hook > 0.62
          red += 46
          green += 42
          blue += 22
        end
        if red > 255 red = 255 end
        if green > 255 green = 255 end
        if blue > 255 blue = 255 end
        pixel(x, y, (red << 16) | (green << 8) | blue)
      end
    end
  end
end

return App()
```

The implementation must keep the wrapped-distance geometry, periodic `math.sin`/`math.cos` bands, and channel clamps shown above. Do not add one-way entrance/exit fades; they would make the cycle seam visible.

- [ ] **Step 2: Run the renderer against the new source**

Run with the available Berry interpreter:

```bash
BERRY_INTERPRETER="$(command -v berry)" && test -n "$BERRY_INTERPRETER" && python3 packs/transitions/tools/render.py --berry "$BERRY_INTERPRETER"
```

Expected: the build reaches Great Wave, compiles it, validates its 200 frames, and reports its exact 7000 ms GIF cycle. If no Berry interpreter is installed, stop with that explicit environment blocker rather than treating Python-only checks as compilation proof.

- [ ] **Step 3: Review the generated Great Wave preview**

Open `packs/transitions/previews/great-wave.gif` and `packs/transitions/previews/contact-sheet.png`. Confirm the crest reads as a large curling wave at pixel scale, the indigo/teal/foam palette is legible, the motion wraps cleanly, and no frame is black or empty.

- [ ] **Step 4: Commit the Berry source**

Inspect with `git diff`, stage only `packs/transitions/great-wave.be`, and confirm with `git diff --cached --stat` before committing.

### Task 4: Regenerate and verify the complete transition pack

**Files:**
- Modify/generated by renderer: `packs/transitions/index.html`
- Modify/generated by renderer: `packs/transitions/manifest.json`
- Modify/generated by renderer: `packs/transitions/previews/great-wave.gif`
- Modify/generated by renderer: `packs/transitions/previews/great-wave.png`
- Modify/generated by renderer: `packs/transitions/previews/contact-sheet.png`
- Modify/generated by renderer: `packs/transitions/color-current-transition-pack.zip`

**Interfaces:**
- The renderer is the sole producer of all listed artifacts.
- The manifest entry must identify `great-wave`, report `durationMs: 7000`, and include the measured distinct-frame count and source byte count.

- [ ] **Step 1: Run focused unit coverage**

```bash
PYTHONPATH=packs/transitions/tools python3 -m unittest packs/transitions/tools/test_render.py -v
```

Expected: all timing tests pass.

- [ ] **Step 2: Run the full transitions build**

```bash
BERRY_INTERPRETER="$(command -v berry)" && test -n "$BERRY_INTERPRETER" && python3 packs/transitions/tools/render.py --berry "$BERRY_INTERPRETER"
```

Expected: all four animations report compilation, lifecycle/configuration, 200-frame, full-panel, motion/color, GIF parity, and exact-cycle success; Great Wave reports a 7000 ms cycle.

- [ ] **Step 3: Check the generated metadata and ZIP contents**

```bash
python3 - <<'PY'
import json
from pathlib import Path
import zipfile

root = Path('packs/transitions')
manifest = json.loads((root / 'manifest.json').read_text())
wave = next(item for item in manifest['animations'] if item['id'] == 'great-wave')
assert wave['durationMs'] == 7000
assert (root / 'previews/great-wave.gif').exists()
assert (root / 'previews/great-wave.png').exists()
with zipfile.ZipFile(root / 'color-current-transition-pack.zip') as archive:
    names = set(archive.namelist())
assert 'color-current-transition-pack/great-wave.be' in names
assert 'color-current-transition-pack/previews/great-wave.gif' in names
PY
```

Expected: the manifest, previews, and ZIP all contain the Great Wave entry and source.

- [ ] **Step 4: Inspect the final diff**

Run `git diff` and confirm the change contains only the approved design follow-up, implementation-plan/source/renderer work, focused tests, and renderer-generated transition artifacts. Preserve unrelated workspace changes in the meeting-in-progress plan and `opencode.json`.

- [ ] **Step 5: Commit generated pack artifacts**

Stage only the renderer-generated outputs by explicit path, then confirm the staged set with `git diff --cached --stat` before committing. Never use `git add -A`: the generated previews and ZIP sit next to unrelated workspace changes.

- [ ] **Step 6: Report the verification boundary**

Report the Berry renderer/build evidence and generated preview paths. State explicitly that the physical AWTRIX display was not installed or read back in this change.
