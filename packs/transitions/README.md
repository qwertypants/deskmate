# Color Current — AWTRIX Transition Pack

Color Current is a set of seven full-screen interludes for AWTRIX NG's 32 × 8 display. Aurora gradients, ocean ripples, prism curtains, an indigo wave, a cyberpunk highway, arcade ghosts, and an 8-bit mushroom power-up sequence fill all 256 pixels in every animation frame.

The Berry scripts run between widget apps as interludes. They do not replace the firmware's native transition effects. Aurora Tide and Prism Loom default to three seconds; Ocean Drops defaults to five seconds; Great Wave, Neon Highway, Ghost Parade, and Mushroom Run default to seven seconds. The first three support one to five seconds, and the remaining animations support one to seven seconds.

## Pack contents

- `aurora-tide.be` — a teal-to-coral aurora wave wipe.
- `ocean-drops.be` — layered, expanding ocean rings and a moving crest.
- `prism-loom.be` — sliding color curtains with a bright weaving seam.
- `great-wave.be` — a curling indigo wave with pale foam highlights.
- `neon-highway.be` — a fixed pink-orange sunset above a moving cyan and magenta perspective highway.
- `ghost-parade.be` — red, pink, cyan, and orange arcade ghosts march together from left to right.
- `mushroom-run.be` — Mario hits a question block, grabs a mushroom, grows, and runs past a green pipe beneath a bright 8-bit sky.
- `manifest.json` — animation metadata for the pack.
- `previews/*.png` — cover frames rendered from Berry source.
- `previews/*.gif` — animated previews rendered from Berry source.
- `tools/render.py` — renderer and packager; running it creates GIF/PNG previews, an offline gallery, and the ZIP bundle.

## AWTRIX Hub

- [Aurora Tide](https://awtrix.de/flow/9tbUOBFb3sSR)
- [Ocean Drops](https://awtrix.de/flow/QVamcPqYPPwh)
- [Prism Loom](https://awtrix.de/flow/kpvjzu2GZlqv)

## Install on AWTRIX NG

1. Open the device settings and choose **Scripts**.
2. Choose **Import**, select one `.be` script, then choose **Save**.
3. Repeat for the other scripts. Use **Show on AWTRIX** to preview an animation.
4. Add the saved scripts to the app rotation on the **Apps** page if you want them to play between widgets.

The script files are also usable individually without the preview tooling.

## Build previews and the ZIP

The build tool uses the Berry interpreter and Pillow. From the repository root, run:

```sh
python3 packs/transitions/tools/render.py --berry /path/to/berry
```

The renderer checks lifecycle and duration behavior, 200 frames per configured duration, full-panel RGB coverage, motion and color variation, exact GIF timing and pixel parity, and the exact-cycle seams of Great Wave and Neon Highway. It builds outputs in staging before publishing previews, manifest, gallery, and ZIP. A Berry interpreter is required; these generated files may be absent until the build succeeds.

## Compatibility note

The host renderer validates Berry behavior and preview output. It does not emulate device brightness, panel color calibration, or the app-rotation settings. Check the animations on your clock after importing them.

## Credits and license

Animations and artwork are original to this pack. Distributed under the MIT License; see `LICENSE`.
