# Vampire Awakens Halloween Animation

## Goal

Add one elegant gothic vampire animation to the existing AWTRIX Halloween pack.
The animation must read clearly on the 32x8 display and preserve the pack's
existing generated outputs and validation contract.

## Visual design

The new animation is named `vampire-awakens` and uses a near-black and indigo
sky, a pale moon, a low castle silhouette, and restrained crimson accents.
It contains no text.

Its five-second seamless cycle has four beats:

1. Establish a moonlit castle scene.
2. Reveal the vampire cloak and two crimson eyes.
3. Send bats outward in staggered arcs while the eyes pulse once.
4. Recede the bats and dim the vampire back into the opening composition.

## Implementation

Create `packs/halloween/vampire-awakens.be` using the pack's existing Berry
helpers and lifecycle/config conventions. Register it in the Halloween
renderer metadata with the title `Vampire Awakens`, a concise description, and
the `ELEGANT GOTHIC` style. Do not alter existing animation behavior.

The renderer remains the source of truth for previews and packaging. Running
the existing Halloween build must regenerate the new GIF and poster, the
contact sheet, gallery, manifest, and `halloween-spooky-pack.zip` coherently.

## Validation

Run the Halloween renderer build and the focused pack tests. The build must
prove Berry execution, lifecycle/config behavior, 200 frames, 256 valid RGB
pixels per frame, meaningful motion and color variation, GIF pixel parity, and
the registered five-second cycle. The generated artifacts do not prove the
physical AWTRIX display; device verification remains a separate step.

## Scope boundaries

This change does not install or activate the animation on the AWTRIX device,
change idle mode, alter the pack's existing animations, or rename the pack.
