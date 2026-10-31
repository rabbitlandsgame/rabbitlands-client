# Starting-look portraits

Starting-look cards load baked images. Only the selected character uses the live creation preview. Opening, filtering or scrolling the picker never creates a card actor or render viewport. A missing image or an appearance that differs from the bake shows a static placeholder.

`CreationBaseLibrary` supplies a stable `portrait_id`. `CreationBasePortraits` reads `godot-client/data/ui/creation_base_portraits.json` and selects a primary image or a protocol variant by the exact look fingerprint: `JSON.stringify(look, "", true).sha256_text()`. This includes the actor type, appearance and equipment. Protocol metadata is descriptive; the fingerprint determines which image matches.

The manifest uses `schema_version: 1` and a `portraits` dictionary keyed by catalog ID. Each entry contains `texture`, `look_sha256` and optional bake metadata. Its optional `variants` array contains the same descriptors for differing older-protocol appearances. Identical looks can share a descriptor. Texture paths must name static PNG, WebP or JPEG resources; there is no scene or runtime-render fallback.

The offline authoring tool is `godot-client/tools/bake_creation_base_portraits.gd`. Run it with the supported real renderer in a task worktree under the shared GPU lock. It renders one look at a time using the existing portrait framing and lighting, and writes 512px PNGs plus a hash-bound manifest for protocols 0–3. Review all current catalog entries and protocol variants before integrating a rebake. Appearance, model, material or portrait-rendering changes can require new images even if the catalog IDs stay the same.

Keep native actor GLBs protected from editor importing. Import the new portrait PNGs using the established image-resource contract; local caches and authoring evidence remain ignored. The focused static-portrait, picker and creation-flow tests check manifest coverage, exact-look matching, missing-image behavior, interactions, and a single active character preview. The Flow fixture can save UI evidence with `-- --no-map-cache --capture-dir=<ignored-directory>` when run with the real renderer.
