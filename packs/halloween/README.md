# Halloween Spooky Pack · 1.1.0

Fifteen tiny frights for the space between your widgets. Original, silent pixel animations for **AWTRIX NG on a 32×8 TC001**, each lasting **5 seconds** by default, adjustable from **1 to 5 seconds** in the app settings.

Open `index.html` for the replay gallery. The fifteen enlarged GIFs in `previews/` are rendered from the actual Berry scripts with a host drawing adapter. They loop every five seconds; loop repetition is for preview only. On the clock each script plays once per turn.

| Script / install name | Scene |
| --- | --- |
| `bat-outta-here` | Flapping bats sweep across the night; a little straggler catches up. |
| `boo-cruise` | A friendly ghost floats in, notices you, gives a silent boo, and scoots away. |
| `pumpkin-chomp` | A pumpkin grows, chomps twice amid creeping embers, and collapses into a spark. |
| `slime-time` | Green drips flood the panel, a bubble rises, and the slime drains away. |
| `web-pull` | Two spiders drop on violet threads, bounce, and zip away. |
| `whos-there` | Eyes glance and blink in the darkness before a tiny ghost peeks out. |
| `witching-hour` | **Storybook:** a pointed-hat witch swoops past a crescent on a magic broom. |
| `bone-boogie` | **Rubber-hose cartoon:** a skull-and-ribs dancer kicks, shimmies, and bows. |
| `knock-knock` | **Cinematic:** a haunted doorway creaks open and slams on a surprise visitor. |
| `hex-spin` | **Geometric:** stepped spell rings spiral, expand, and collapse into sparks. |
| `crawl-call` | **Stop-motion:** a detached hand crawls on its fingers, pauses, and waves. |
| `vampire-awakens` | **Elegant gothic:** a cloaked vampire wakes beneath a blood moon as bats take flight. |
| `black-cat-crosses` | **Silhouette:** a sleek black cat slips through the moonlight and disappears. |
| `cat-at-the-window` | **Silhouette:** a curious cat rises from the darkness, looks around, and sinks away. |
| `skulls-in-space` | **Depth study:** emoji-like skulls drift left to right, with smaller dimmer skulls moving more slowly in the distance. |

## Install the animations

1. Open your clock's web UI and go to **Scripts**. Create a new script with one of the install names above. Pick an unused name if that name is already taken.
2. Paste the matching `.be` file and save. Use **Show on the clock** to preview it.
3. On **Apps**, open that script's settings to change Duration; default is `5000` milliseconds. Saved numeric values are clamped to `1000–5000`.
4. Drag its app into your preferred place in the rotation. For example: **Time → Bat Outta Here → Calendar → Boo Cruise → Codex**. Install any subset of the fifteen.
5. For the same animation at several positions, install separate copies under distinct names, such as `boo-cruise-2`. Each copy has its own duration setting.

These are **animated interlude apps**, not custom firmware transition effects. They draw on their own black canvas and do not read or blend the neighboring widgets. Existing device-wide transitions still run on entry and exit and can add time around the animation. For clean cuts, optionally set **transitionDurationMs to 0** in your clock's transition settings; record your previous value to restore it later. This affects all apps and is never changed by these scripts.

Normal automatic rotation must be enabled. Left/right buttons continue to work normally. Scripts restart their scene every time they are shown and remain installed after reboot. Disable or delete only the pack apps to remove them; restore any transition setting you changed manually.

No sounds, downloaded icons, internet connection, Pi daemon, shared modules, or firmware changes are required. This pack does not alter existing widgets, their settings, or their stored data.

## Share with the community

Share `halloween-spooky-pack.zip`, or upload each `.be` script and its matching GIF to the AWTRIX Hub. The headers contain the title, description, author, version, display requirement, and duration setting. This pack's code and original pixel art use the included MIT license.

Suggested pack description:

> Fifteen little frights for your widget rotation: a bat swarm with a straggler, a ghost with stage presence, a chomping pumpkin, bubbling slime, bouncy spiders, eyes in the dark, a moonlit witch, a dancing skeleton, a haunted door, a geometric spell, a crawling hand, a vampire beneath a blood moon, sleek black cats in the moonlight, and drifting skulls in space. Silent, self-contained 32×8 Berry scripts. Each scene plays for up to five seconds. Install your favorites and place them between apps.

## Verification and rebuilding

Local verification compiles and executes all fifteen original scripts with a real **berry-lang** interpreter. The host adapter implements a clipped 32×8 drawing canvas, a controllable millisecond clock, and the duration store. It checks repeat appearances after interruption, 1/2.5/5-second timing, numeric bounds, moving frames, valid RGB output, and exact 5000ms GIF cycles.

This confirms Berry syntax and drawing behavior in the adapter. **AWTRIX firmware integration, physical LED readability/brightness, reboot persistence, and automatic rotation on a TC001 remain unverified until tested on hardware.** A desktop GIF cannot establish those properties. Clock time-wrap behavior is likewise delegated to the firmware time API.

To regenerate GIFs, the contact sheet, manifest, and ZIP:

```sh
python3 -m pip install -r tools/requirements.txt
python3 tools/render.py --berry /path/to/berry
```

Run that command from this pack's directory. It regenerates the gallery as well as previews and the bundle. Build the interpreter from [berry-lang/berry](https://github.com/berry-lang/berry) using its Makefile. The gallery is regenerated from the same animation registry as the manifest, using `tools/gallery.html`. The interpreter is a development tool; it is not included in the download or required on the clock. `tools/render.py` does not connect to a clock or change device settings.

Reference documentation: [scripting lifecycle](https://ang.blueforcer.de/guides/scripting/), [script settings](https://ang.blueforcer.de/guides/scripting/storage/), [sharing scripts](https://ang.blueforcer.de/guides/scripting/sharing/), [app duration](https://ang.blueforcer.de/guides/scripting/several-apps/), and [native transitions](https://ang.blueforcer.de/reference/visuals/).
