# Eloria Client modifications

**This is a historical record.** Eloria Client began as a modified version of
the Eternal Lands Official Client source, and the entries below are the change
notices section 3(c) of the Eternal Lands Client Public License 1.0 required
while that source was present.

On 2026-09-03 the C client and everything that existed to serve it were removed
from this repository. Nothing in the working tree is derived from the Eternal
Lands client source any more; see [Removal](#2026-09-03--removal-of-the-c-client)
below for what went and what took its place. `eternal_lands_license.txt` is kept
because the history reachable from this repository still contains that source,
and `eloria-assets/tools/check_provenance.py` fails the build if Eternal Lands
names or file formats reappear.

Eloria is not affiliated with or endorsed by Eternal Lands, Radu Privantu, or
Maura Privantu. No Eternal Lands Binary Data was ever included.

## 2026-09-03 — Removal of the C client

- Removed the Eternal Lands C/C++ client fork: every root source file, the
  CMake/Make/meson/Android build files, the Debian, macOS, snap and pkgfiles
  packaging, and the `eye_candy`, `map_editor`, `io`, `engine`, `pawn`, `xz`,
  `shader`, `fsaa`, `exceptions`, `xml` and `nlohmann_json` trees.
- Removed the Eternal Lands data the client loaded: `books/`, `dev-data-files/`,
  `pawn_scripts/`, `shaders/`, `skybox/`, `textures/` and `templates/`.
- Removed the generators that produced that data pack — the Cal3D actor,
  native-E3D scenery, ELM region and BMP/DDS atlas chain under
  `eloria-assets/tools/generate_*.py`, its `validate_*` and `render_*`
  companions, and `generate_all_assets.py` which drove them.
- Removed the Eternal Lands format asset packs: `eloria-assets/nymara-packs/`
  (E3D objects, DDS textures, 2D objects and the retired portable Four Gates
  package) and `eloria-assets/ui/` (DDS atlases, branding and generated pack
  textures). The item atlases the client samples are the PNGs under
  `godot-client/assets/ui/items/`, which are now their own source;
  `atlas_layout.json` moved to `godot-client/data/items/`.
- Removed the portable world-package validator, fixture and schema
  (`tools/eloria-map-validate`, `tests/fixtures/world_package/`,
  `docs/world-package*`), which described the C client's map loader and not the
  manifests the Godot client reads.
- Replaced the ELM map export with an Eloria-native walk grid.
  `maps/nymara-regions/source-elm/*.elm` existed so eloria-server could read a
  height field; the eight composed interiors it actually sourced are now
  `maps/nymara-regions/server-collision/*.bin`, EWCG grids holding the identical
  bytes. The nine `export_*_elm.py` scripts became
  `export_insides_collision.py` over a shared `_toolkit` module, each stating
  the downsample its map shipped with. eloria-server was changed to match in
  the same cycle: it reads no ELM at all now, and re-running its
  `tools/sync_authored_collision.py` against this tree reproduces all 23 of its
  vendored walk grids byte for byte.
- Renamed every map key from the Eternal Lands file path to the Eloria map id:
  `maps/nymara/westhaven.elm` is `westhaven`, and the city served as
  `maps/startmap.elm` is `four_gates`. eloria-server sends that id now: its map
  definitions gained a `client_name`, which is the id, while `file` stays the
  server's own height map. `MapRegistry.normalize_server_map_id` still reduces
  a path-shaped name to its id, as tolerance for an older server rather than as
  a contract; both ends pin their half of the naming contract in tests.
- Dropped the `Build check` and `independent-data` workflows and the C half of
  `world-package`. `Godot Client` now runs on the whole repository and includes
  the provenance guard and the shared asset contracts under `tests/`.

## 2026-08-22

- Added independent Eloria product branding and project links.
- Disabled the official Eternal Lands web-update endpoint.
- Added a reproducible generator for an original bootstrap data pack and map.
- Added asset provenance and compliance checks.
- Added a single Eloria server profile targeting TCP port 2000.
- Added command 247 for 16-bit actor types while retaining legacy actor packets.
- Expanded the actor registry to 1024 entries and made attachments sparse.

## 2026-08-23

- Extended spell-cast packets with an optional one-byte power selection.
- Added power display and right-click adjustment to the spell window.
- Added user-configurable `#K_SPELLPOWERUP` and `#K_SPELLPOWERDOWN` hotkeys.
- Preserved server-side per-effect preferences whenever the client has no explicit override.
- Replaced the generic essence economy with catalyst, resonant, and anchor materials.
- Added four item atlases for original magical materials, focuses, charges, and Echoes.

## 2026-08-28

- Rebuilt equipment attachment on character-space sockets solved from the rig,
  replacing identity parenting that put every weapon sideways through the actor.
- Skinned capes, leg armour, body armour and boots to the shared 65-joint rig so
  worn equipment deforms with every clip instead of riding one bone.
- Reauthored all 66 equipment GLBs against the measured body silhouette at body
  scale, with PBR base-colour and normal maps and roughly five times the mesh
  density of the previous primitives.
- Moved the boots part from the pelvis to both feet and the cape behind the
  actor rather than in front of it.
- Added a rig fit scale so one authored asset fits every race and both body
  variants.
- Realigned the item icon atlases to the grid the client samples, restored the
  icons that the placeholder block had truncated, repainted the sixteen Nymara
  material icons, and added an explicit unknown-item glyph.
- Authored a generic equipment tier claiming the legacy visual-id space
  directly: 155 ids across seven parts, served by 43 meshes under a runtime
  tint, so the craftable economy has geometry instead of drawing nothing.
- Added great sword, battle axe, cutlass, rapier, club, quiver and glove
  shapes, and enchanted-metal finishes for the elemental weapon ladders.
- Corrected sRGB palettes being written into glTF's linear colour factors,
  which had untextured equipment surfaces rendering about forty percent bright;
  creature, race, and hair rebuilds remain separate asset work.
- Removed the three visual-id aliases, which now collide with real generic ids,
  and made an authored NPC look outrank the server's appearance bytes.
- Cached parsed equipment geometry and rebound skins per model.
- Audited the harvestable layer and recorded the findings in `docs/harvestable-audit.md`.
- Added `eloria-assets/tools/harvestables.py` as the single harvestable catalogue.
- Rebuilt every harvest node model at the fidelity of the surrounding landmark kit.
- Gave foliage harvestables alpha-tested, double-sided materials.
- Added sixteen general-purpose harvestables covering the everyday crafting economy.
- Wrote `harvestable.lst` and `entrable.lst` as the lowercase basenames the client looks up.
- Scattered harvest nodes across each region instead of repeating four fixed coordinates.
- Wrote ELM object and light coordinates in world units instead of height-map cells.
- Added decorative 2D ground flora and the map writer support the client already had.
- Moved harvestable item ids out of the equipment range and added `validate_harvestables.py`.
