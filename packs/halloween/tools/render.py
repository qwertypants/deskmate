#!/usr/bin/env python3
"""Render the shipped Berry code with a real interpreter and AWTRIX drawing stubs.

Usage: python3 tools/render.py --berry /path/to/berry
Requires Pillow only on the development computer, never on the clock.
"""
import argparse
from html import escape
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.1.0'
NAMES = {
    'bat-outta-here': ('Bat Outta Here', 'A late little bat races to catch the swarm.'),
    'boo-cruise': ('Boo Cruise', 'A curious ghost takes the scenic route.'),
    'pumpkin-chomp': ('Pumpkin Chomp', 'A toothy pumpkin bites off more than it can chew.'),
    'slime-time': ('Slime Time', 'Drip, bubble, flood, and disappear.'),
    'web-pull': ('Web Pull', 'Two tiny spiders put on a bouncy curtain call.'),
    'whos-there': ("Who’s There?", 'A pair of eyes discovers it has company.'),
    'witching-hour': ('Witching Hour', 'A storybook witch swoops past the moon on a star-dusted broom.'),
    'bone-boogie': ('Bone Boogie', 'A rubber-hose skeleton kicks, shimmies, and takes a bow.'),
    'knock-knock': ('Knock Knock', 'A cinematic haunted door creaks open to a surprise visitor.'),
    'hex-spin': ('Hex Spin', 'Geometric spell rings spiral into a tiny magical singularity.'),
    'crawl-call': ('Crawl Call', 'A stop-motion hand tiptoes across the screen and gives a wave.'),
    'vampire-awakens': ('Vampire Awakens', 'A cloaked vampire wakes beneath a blood moon as bats take flight.'),
    'black-cat-crosses': ('Black Cat Crosses', 'A sleek black cat slips through the moonlight and disappears.'),
    'cat-at-the-window': ('Cat at the Window', 'A curious cat rises from the darkness, looks around, and sinks away.'),
    'skulls-in-space': ('Skulls in Space', 'Emoji-like skulls drift through empty space at different depths.'),
}
STYLES = {'witching-hour': 'STORYBOOK', 'bone-boogie': 'RUBBER HOSE',
          'knock-knock': 'CINEMATIC', 'hex-spin': 'GEOMETRIC', 'crawl-call': 'STOP MOTION',
          'vampire-awakens': 'ELEGANT GOTHIC', 'black-cat-crosses': 'SILHOUETTE',
          'cat-at-the-window': 'SILHOUETTE', 'skulls-in-space': 'DEPTH STUDY'}
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


def verify(berry, source):
    # Re-show resets animation after interruption; invalid numeric settings clamp.
    execute(berry, source, '''
configured=5000 assert(app.duration()==5000)
clock=10000 app.on_show() clear() app.draw()
var initial=json.dump(canvas)
clock=12750 clear() app.draw()
clock=500000 app.on_show() clear() app.draw()
assert(json.dump(canvas)==initial)
configured=750 app.on_show() assert(app.duration()==1000)
configured=9000 app.on_show() assert(app.duration()==5000)
configured=2500 app.on_show() assert(app.duration()==2500)
clock+=2500 clear() app.draw()
clock+=1000 clear() app.draw()
''')


def image_for(frame, scale=16):
    image = Image.new('RGB', (32, 8))
    image.putdata([((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in frame])
    return image.resize((32*scale,8*scale), Image.Resampling.NEAREST)


def write_gallery():
    """Keep the download gallery in sync with the pack's animation registry."""
    cards = []
    for index, (slug, (title, desc)) in enumerate(NAMES.items(), 1):
        title = escape(title)
        style = STYLES.get(slug, '32 × 8')
        cards.append(f'''<article class="card" id="{slug}"><div class="card-top"><span class="number">{index:02}</span><span class="tag">5 SEC / {style}</span></div><div class="display"><img src="previews/{slug}.gif" data-gif="previews/{slug}.gif" data-poster="previews/{slug}.png" alt="{title} pixel animation" width="512" height="128"></div><div class="copy"><h2>{title}</h2><p>{escape(desc)}</p><div class="actions"><button type="button" class="toggle" aria-label="Pause {title}">Pause</button><button type="button" class="replay" aria-label="Replay {title}">Replay ↻</button><a href="{slug}.be" download>Get script ↓</a></div></div></article>''')
    template = (ROOT / 'tools' / 'gallery.html').read_text()
    page = template.replace('{{cards}}', '\n'.join(cards)).replace('{{count}}', str(len(NAMES))).replace('{{version}}', VERSION)
    (ROOT / 'index.html').write_text(page)


def build(berry):
    write_gallery()
    previews = ROOT / 'previews'
    previews.mkdir(exist_ok=True)
    summary = []
    contact = Image.new('RGB', (640, len(NAMES)*160), '#100e18')
    pen = ImageDraw.Draw(contact)
    for index, (slug, (title, desc)) in enumerate(NAMES.items()):
        source = (ROOT / f'{slug}.be').read_text()
        verify(berry, source)
        frames = frames_for(berry, source)
        short = frames_for(berry, source, 1000)
        assert len(frames) == 200 and len(short) == 200
        assert all(len(f) == 256 and all(isinstance(c, int) and 0 <= c <= 0xFFFFFF for c in f) for f in frames)
        assert len({tuple(f) for f in frames}) >= 15, f'{slug}: insufficient motion'
        assert max(sum(c != 0 for c in f) for f in frames) > 5
        images = [image_for(f) for f in frames]
        # GIF time uses centiseconds: sample 20fps for an exact 5000ms cycle.
        palette = Image.new('P', (1, 1))
        palette.putpalette([0,0,0, 255,136,24, 168,85,247, 148,224,68, 221,248,245,
                            7,9,29, 111,120,168, 16,14,40, 240,75,95, 49,32,95,
                            142,43,131, 255,138,92, 255,216,90, 37,37,37,
                            48,48,48, 119,119,119, 184,184,184, 255,255,255] + [0]*699)
        gif_frames = [img.quantize(palette=palette, dither=Image.Dither.NONE) for img in images[::2]]
        gif_frames[0].save(previews / f'{slug}.gif', save_all=True, append_images=gif_frames[1:],
                           duration=50, loop=0, optimize=False, disposal=1, background=0)
        poster_index = max(range(len(frames)), key=lambda i: sum(c != 0 for c in frames[i]))
        image_for(frames[poster_index]).save(previews / f'{slug}.png')
        pen.text((32,index*160+8), title.replace("’", "'"), fill='#DDF8F5')
        contact.paste(image_for(frames[poster_index]), (32,index*160+28))
        with Image.open(previews / f'{slug}.gif') as gif:
            total = 0
            for i in range(gif.n_frames):
                gif.seek(i)
                duration = gif.info['duration']
                decoded = gif.convert('RGB').tobytes()
                for tick in range(total, total + duration, 50):
                    assert decoded == images[tick // 25].tobytes(), (slug, 'GIF pixel mismatch', tick)
                total += duration
            assert total == 5000, (slug, total)
        summary.append({'id':slug,'name':title,'description':desc,'durationMs':5000,'style':STYLES.get(slug, 'PIXEL CARTOON'),
                        'sourceBytes':len(source.encode()), 'distinctFrames':len({tuple(f) for f in frames})})
        print(f'{slug}: compiled, lifecycle/config checks passed; 200 frames rendered, GIF pixel parity and 5000ms passed')
    contact.save(previews / 'contact-sheet.png')
    (ROOT / 'manifest.json').write_text(json.dumps({'version':VERSION,'display':'32x8','animations':summary}, indent=2)+'\n')
    with zipfile.ZipFile(ROOT / 'halloween-spooky-pack.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file() and path.suffix not in ('.zip', '.pyc') and '__pycache__' not in path.parts:
                archive.write(path, 'halloween-spooky-pack/' + str(path.relative_to(ROOT)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--berry', required=True, help='Path to a compiled berry-lang interpreter')
    args = parser.parse_args()
    build(args.berry)
