#!/usr/bin/env python3
"""Render the shipped Berry code with a real interpreter and AWTRIX drawing stubs.

Usage: python3 tools/render.py --berry /path/to/berry
Requires Pillow only on the development computer, never on the clock.
"""
import argparse
from html import escape
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0'
NAMES = {
    'aurora-tide': ('Aurora Tide', 'A luminous aurora sweeps across the display in teal, blue, violet, and coral.'),
    'ocean-drops': ('Ocean Drops', 'Layered ocean ripples expand and roll across the full display.'),
    'prism-loom': ('Prism Loom', 'Color curtains weave around a bright seam, then resolve into a warm glow.'),
    'great-wave': ('Great Wave', 'An original indigo wave curls and rolls across the display in a woodblock-inspired palette.'),
    'neon-highway': ('Neon Highway', 'A retro cyberpunk sunset anchors a luminous highway while cyan and magenta road lines stream toward the viewer.'),
    'ghost-parade': ('Ghost Parade', 'Red, pink, cyan, and orange arcade ghosts march across a glowing full-screen backdrop.'),
    'mushroom-run': ('Mushroom Run', 'Mario hits a question block, grabs a mushroom, grows, and runs past a green pipe beneath a bright 8-bit sky.'),
    'space-invaders': ('Space Invaders', 'A pixel spaceship sweeps beneath a descending invader wave, firing until the screen clears.'),
    'nyc-after-dark': ('NYC After Dark', 'Stars and drifting clouds reveal a glowing Manhattan skyline rising into the night.'),
    'pellet-chase': ('Pellet Chase', 'Pac-Man collects pellets, glows after a power pellet, and chases two frightened ghosts out of a blue maze corridor.'),
}
STYLES = {'aurora-tide': 'GRADIENT WAVES', 'ocean-drops': 'OCEAN RIPPLE',
          'prism-loom': 'COLOR CURTAINS', 'great-wave': 'WOODBLOCK WAVE',
          'neon-highway': 'CYBERPUNK SUNSET', 'ghost-parade': 'ARCADE GHOSTS',
          'mushroom-run': '8-BIT PLATFORMER', 'space-invaders': 'ARCADE SHOOTER',
          'nyc-after-dark': 'CITY NIGHTFALL', 'pellet-chase': 'ARCADE CHASE'}
DEFAULT_DURATIONS = {'aurora-tide': 3000, 'ocean-drops': 5000, 'prism-loom': 3000,
                     'great-wave': 7000, 'neon-highway': 7000, 'ghost-parade': 7000,
                     'mushroom-run': 7000, 'space-invaders': 7000, 'nyc-after-dark': 7000,
                     'pellet-chase': 8000}
MAX_DURATIONS = {'aurora-tide': 5000, 'ocean-drops': 5000, 'prism-loom': 5000,
                 'great-wave': 7000, 'neon-highway': 7000, 'ghost-parade': 7000,
                 'mushroom-run': 7000, 'space-invaders': 7000, 'nyc-after-dark': 7000,
                 'pellet-chase': 8000}
SEAM_VALIDATED = frozenset({'great-wave', 'neon-highway', 'mushroom-run', 'space-invaders'})
GIF_FRAME_COUNT = 100


def gif_duration_ms(slug):
    duration = DEFAULT_DURATIONS[slug]
    if duration % GIF_FRAME_COUNT:
        raise ValueError(f'{slug}: duration must divide evenly into {GIF_FRAME_COUNT} GIF frames')
    return duration // GIF_FRAME_COUNT


# Drawing functions clip exactly at the simulated 32x8 panel boundary.
PRELUDE = '''
import json
var clock = 0
var configured = 5000
var canvas = []
def abs(v) return v < 0 ? -v : v end
def width() return 32 end
def height() return 8 end
def now_ms() return clock end
def clamp(v, lo, hi) return v < lo ? lo : (v > hi ? hi : v) end
def min(a,b) return a < b ? a : b end
def max(a,b) return a > b ? a : b end
class Store
  def get(key, fallback) return configured end
end
var store = Store()
def clear(color)
  if color == nil color = 0 end
  canvas = []
  for i : 0..255 canvas.push(color) end
end
def pixel(x,y,color)
  x = int(x)
  y = int(y)
  if x >= 0 && x < 32 && y >= 0 && y < 8
    canvas[y*32+x] = color
  end
end
def rect_fill(x,y,w,h,color)
  x=int(x) y=int(y) w=int(w) h=int(h)
  if w <= 0 || h <= 0 return end
  for yy : y..y+h-1
    for xx : x..x+w-1 pixel(xx,yy,color) end
  end
end
def line(x0,y0,x1,y1,color)
  x0=int(x0) y0=int(y0) x1=int(x1) y1=int(y1)
  var dx=abs(x1-x0), sx=x0<x1 ? 1 : -1
  var dy=-abs(y1-y0), sy=y0<y1 ? 1 : -1
  var err=dx+dy
  while true
    pixel(x0,y0,color)
    if x0==x1 && y0==y1 break end
    var e=2*err
    if e>=dy err+=dy x0+=sx end
    if e<=dx err+=dx y0+=sy end
  end
end
def frame_delta(a,b)
  var largest = 0
  for i : 0..255
    var left = a[i], right = b[i]
    var delta = abs(((left >> 16) & 255) - ((right >> 16) & 255))
    delta += abs(((left >> 8) & 255) - ((right >> 8) & 255))
    delta += abs((left & 255) - (right & 255))
    if delta > largest largest = delta end
  end
  return largest
end
'''


def execute(berry, source, suffix):
    program = PRELUDE + '\nvar app = compile(' + json.dumps(source) + ')()\n' + suffix
    with tempfile.TemporaryDirectory(prefix='halloween-') as temp:
        script = Path(temp) / 'render.be'
        script.write_text(program)
        result = subprocess.run([berry, str(script)], capture_output=True, text=True, timeout=30)
    if result.returncode or result.stderr or 'error' in result.stdout.lower():
        raise RuntimeError(result.stdout + result.stderr)
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('[')]


def frames_for(berry, source, duration=5000):
    return execute(berry, source, f'''
configured={duration}
clock=987654
app.on_show()
assert(app.duration()=={duration})
for step : 0..199
  clock=987654+int(step*{duration}/200)
  clear()
  app.draw()
  print(json.dump(canvas))
end
''')


def verify(berry, source, default_duration, max_duration, check_seam=False):
    # Re-show resets animation after interruption; invalid numeric settings clamp.
    seam = f'''
clock=10000+{default_duration}-50 clear() app.draw()
var earlier=canvas
clock=10000+{default_duration}-25 clear() app.draw()
var before=canvas
clock=10000+{default_duration} clear() app.draw()
assert(json.dump(canvas)==initial)
var at=canvas
clock=10000+{default_duration}+25 clear() app.draw()
var after=canvas
clock=10000+{default_duration}+50 clear() app.draw()
var later=canvas
var nearby=max(frame_delta(earlier,before),frame_delta(after,later))
var seam_delta=max(frame_delta(before,at),frame_delta(at,after))
# Maximum RGB change in any pixel over one 25ms frame; allow room for the moving crest.
assert(seam_delta<=160)
assert(seam_delta<=nearby*2+8)
''' if check_seam else ''
    execute(berry, source, f'''
configured={default_duration} assert(app.duration()=={default_duration})
clock=10000 app.on_show() clear() app.draw()
var initial=json.dump(canvas)
{seam}
clock=500000 app.on_show() clear() app.draw()
assert(json.dump(canvas)==initial)
configured=750 app.on_show() assert(app.duration()==1000)
configured=9000 app.on_show() assert(app.duration()=={max_duration})
configured=2500 app.on_show() assert(app.duration()==2500)
clock+=2500 clear() app.draw()
clock+=1000 clear() app.draw()
''')


def image_for(frame, scale=16):
    image = Image.new('RGB', (32, 8))
    image.putdata([((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in frame])
    return image.resize((32*scale,8*scale), Image.Resampling.NEAREST)


def validate_frames(frames, slug, allow_black=False):
    assert len(frames) == 200, f'{slug}: expected 200 frames'
    assert all(len(frame) == 256 for frame in frames), f'{slug}: expected 256 pixels per frame'
    assert all(type(color) is int and 0 <= color <= 0xFFFFFF for frame in frames for color in frame), \
        f'{slug}: invalid RGB color'
    assert allow_black or all(color != 0 for frame in frames for color in frame), \
        f'{slug}: every pixel must be colored in every frame'


def write_gallery(output_root=ROOT):
    """Create a small offline-friendly gallery that matches the source registry."""
    cards = []
    for slug, (title, desc) in NAMES.items():
        style = STYLES.get(slug, '32 × 8')
        cards.append(f'''<article><div class="preview"><img src="previews/{slug}.gif" alt="{escape(title)} animation preview"></div><h2>{escape(title)}</h2><p>{escape(desc)}</p><p class="style">{escape(style)} · 32 × 8 · {DEFAULT_DURATIONS[slug] / 1000:g} seconds by default</p><a href="{slug}.be" download>Download Berry script</a></article>''')
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Color Current · AWTRIX Transition Pack</title>
<style>
:root{{color-scheme:dark;--ink:#eef8ff;--muted:#a7bfd0;--panel:#102333;--edge:#26465b}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at 50% -20%,#17384d,#08131d 65%);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1000px;margin:auto;padding:40px 24px 64px}}header{{margin-bottom:30px}}h1{{font-size:clamp(2rem,6vw,3.4rem);line-height:1.05;margin:0 0 12px}}header p{{color:var(--muted);max-width:680px}}
section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}}article{{background:var(--panel);border:1px solid var(--edge);border-radius:18px;padding:16px;overflow:hidden}}.preview{{background:#02070b;border-radius:12px;overflow:hidden;aspect-ratio:4/1}}img{{display:block;width:100%;height:100%;image-rendering:pixelated;object-fit:cover}}h2{{margin:16px 0 4px}}article p{{color:var(--muted);margin:6px 0}}.style{{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em}}a{{display:inline-block;margin-top:12px;color:#7ce7e4;font-weight:700}}
</style><main><header><p>AWTRIX NG · COMMUNITY ANIMATION PACK · v{VERSION}</p><h1>Color Current</h1><p>{len(cards)} vivid interludes for the 32 × 8 display, from full-panel color to black-backed arcade scenes. Import an individual <code>.be</code> script in the AWTRIX NG Scripts settings.</p></header><section>{''.join(cards)}</section></main></html>'''
    (output_root / 'index.html').write_text(page)


def publish_outputs(output_root, generated):
    """Publish staged files, restoring the previous bundle if a replacement fails."""
    backups = output_root / 'previous-outputs'
    backups.mkdir()
    existing = set()
    for relative in generated:
        target = ROOT / relative
        if target.exists():
            backup = backups / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            existing.add(relative)

    previews = ROOT / 'previews'
    created_previews = not previews.exists()
    previews.mkdir(exist_ok=True)
    attempted = []
    try:
        for relative in generated:
            attempted.append(relative)
            os.replace(output_root / relative, ROOT / relative)
    except Exception:
        for relative in reversed(attempted):
            target = ROOT / relative
            if relative in existing:
                shutil.copy2(backups / relative, target)
            else:
                target.unlink(missing_ok=True)
        if created_previews:
            previews.rmdir()
        raise


def build(berry):
    with tempfile.TemporaryDirectory(prefix='transitions-', dir=ROOT.parent) as temp:
        output_root = Path(temp)
        previews = output_root / 'previews'
        previews.mkdir()
        write_gallery(output_root)
        summary = []
        contact = Image.new('RGB', (640, len(NAMES)*160), '#100e18')
        pen = ImageDraw.Draw(contact)
        for index, (slug, (title, desc)) in enumerate(NAMES.items()):
            source = (ROOT / f'{slug}.be').read_text()
            duration = DEFAULT_DURATIONS[slug]
            verify(berry, source, duration, MAX_DURATIONS[slug], slug in SEAM_VALIDATED)
            frames = frames_for(berry, source, duration)
            short = frames_for(berry, source, 1000)
            allow_black = slug in {'space-invaders', 'pellet-chase'}
            validate_frames(frames, slug, allow_black=allow_black)
            validate_frames(short, slug, allow_black=allow_black)
            assert len({tuple(f) for f in frames}) >= 15, f'{slug}: insufficient motion'
            assert len({c for f in frames for c in f}) >= 8, f'{slug}: insufficient color variation'
            images = [image_for(f) for f in frames]
            # Build one 256-color palette from the whole animation for stable GIF frames.
            palette_source = Image.new('RGB', (32 * 16, 8 * 13))
            for sample_index, frame in enumerate(frames):
                palette_source.paste(image_for(frame, scale=1),
                                     ((sample_index % 16) * 32, (sample_index // 16) * 8))
            palette = palette_source.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                              dither=Image.Dither.NONE)
            # GIF time uses centiseconds; 100 frames span the registered cycle.
            gif_duration = gif_duration_ms(slug)
            gif_frames = [img.quantize(palette=palette, dither=Image.Dither.NONE) for img in images[::2]]
            gif_frames[0].save(previews / f'{slug}.gif', save_all=True, append_images=gif_frames[1:],
                               duration=gif_duration, loop=0, optimize=False, disposal=1, background=0)
            poster_index = max(range(len(frames)), key=lambda i: sum(frames[i]))
            image_for(frames[poster_index]).save(previews / f'{slug}.png')
            pen.text((32,index*160+8), title.replace("’", "'"), fill='#DDF8F5')
            contact.paste(image_for(frames[poster_index]), (32,index*160+28))
            with Image.open(previews / f'{slug}.gif') as gif:
                total = 0
                decoded_ticks = []
                for frame_index in range(gif.n_frames):
                    gif.seek(frame_index)
                    decoded = gif.convert('RGB').tobytes()
                    frame_duration = gif.info['duration']
                    assert frame_duration % gif_duration_ms(slug) == 0, (slug, 'GIF frame duration', frame_index)
                    tick_count = frame_duration // gif_duration_ms(slug)
                    expected = gif_frames[len(decoded_ticks):len(decoded_ticks) + tick_count]
                    assert all(decoded == image.convert('RGB').tobytes() for image in expected), (slug, 'GIF pixel mismatch', frame_index)
                    decoded_ticks.extend([decoded] * tick_count)
                    total += frame_duration
                assert len(decoded_ticks) == GIF_FRAME_COUNT, (slug, 'GIF playback tick count', len(decoded_ticks))
                assert decoded_ticks == [image.convert('RGB').tobytes() for image in gif_frames], (slug, 'GIF playback mismatch')
                assert total == duration, (slug, total, duration)
            summary.append({'id':slug,'name':title,'description':desc,'durationMs':duration,'style':STYLES.get(slug, 'PIXEL CARTOON'),
                            'sourceBytes':len(source.encode()), 'distinctFrames':len({tuple(f) for f in frames})})
            print(f'{slug}: compiled, full-panel color, lifecycle/config, motion and {duration}ms GIF checks passed')
        contact.save(previews / 'contact-sheet.png')
        (output_root / 'manifest.json').write_text(json.dumps({'version':VERSION,'display':'32x8','animations':summary}, indent=2)+'\n')
        zip_name = 'color-current-transition-pack.zip'
        generated = [Path('index.html'), Path('manifest.json'),
                     *(Path('previews') / f'{slug}.{ext}' for slug in NAMES for ext in ('gif', 'png')),
                     Path('previews/contact-sheet.png')]
        with zipfile.ZipFile(output_root / zip_name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(ROOT.rglob('*')):
                relative = path.relative_to(ROOT)
                if (path.is_file() and relative not in generated and path.suffix not in ('.zip', '.pyc')
                        and '__pycache__' not in path.parts and 'previews' not in relative.parts):
                    archive.write(path, 'color-current-transition-pack/' + str(relative))
            for relative in generated:
                archive.write(output_root / relative, 'color-current-transition-pack/' + str(relative))
        publish_outputs(output_root, (*generated, Path(zip_name)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--berry', required=True, help='Path to a compiled berry-lang interpreter')
    args = parser.parse_args()
    build(args.berry)
