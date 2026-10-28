---
name: deskmate-awtrix-hub-publishing
description: Use when publishing a Desk Mate Berry animation or script to AWTRIX Hub, especially when a public listing needs source code, metadata, and an animation preview verified together.
---

# Desk Mate AWTRIX Hub publishing

Use this after the animation has passed the local pack checks. AWTRIX Hub's
Berry animation is a public AWTRIX NG script listing even when its resulting
URL contains `/flow/`.

## Prepare the listing

- Publish the `.be` source as a script, not an unrelated Home Assistant or
  Node-RED flow. Select the Animations topic and AWTRIX NG compatibility.
- Match the published Mushroom Run listing: System **AWTRIX NG Scripts**
  (implicit on `/new/script`), Topic **Animations**, Made for **Every clock**,
  and Needs **Nothing extra** for these dependency-free pack animations. State
  the actual 32x8 design target in the description and retain `@display 32x8`.
- Use the **Code text field only**: paste the complete authoritative `.be`
  source and leave **Upload a file** empty. Do not attach the `.be` file as
  well. The Hub accepts code uploads with extensions `xml,json,yaml,yml,ax`,
  not `be`, and rejects a request containing both pasted code and a file.
  If file-only submission is specifically needed, use an identical `.ax`
  copy, leave the Code field empty, and verify the current allowed formats.
- Use the animation's real name, a short behavior-focused description, and
  setup text that states display size, dependencies, duration/configuration,
  and installation/rotation expectations.
- Provide the generated GIF (or a native-size screenshot when a GIF is not
  appropriate) as the cover. Respect the Hub's visible format, duration, and
  size limits.

## Required verification before publishing

- Verify the actual Code editor contains the full Berry source through the
  final `return App()` and that the code upload input has zero selected files.
  A filename label alone does not prove the editor was populated. Never fill
  both code inputs to compensate for an import that did not populate the editor.
- After a failed submission, inspect all retained fields before retrying.
  Browsers clear file selections after server validation; confirm that the Code
  text and GIF cover are still present. Old server error text may remain until
  the next submission; do not publish just to clear it.
- For Chrome uploads, use the actual observed file input with the supported
  file-chooser API. The GIF cover editor uses a separate input from the disabled
  original cover input; inspect the current DOM rather than assuming the visible
  upload button targets the correct chooser. A native picker is a fallback.
- Verify the cover list contains the intended preview and the listing card
  visibly shows the animation. Check the source and preview are from the same
  revision.
- Stage the complete form and stop at the final Publish button. Public
  publication is an external representational action; ask for confirmation
  immediately before clicking it, even if the user earlier requested
  publication.

## After publication

- Verify the resulting public URL, title, author, topic, AWTRIX NG status,
  download/code availability, and cover image. Do not infer a URL from a
  guessed slug.
- Report publication separately from device installation or preview. A public
  Hub page does not prove the animation is active on hardware.
- Publish individual entries deliberately; do not automate bulk submissions or
  repeated Publish clicks. If the site rate-limits or loses the staged form,
  stop and reconcile before retrying.
