# Amethyst Barrens — change log

## From placeholder to production

The starting package was at `terrain-landmark-material-pass` and carried every
defect the region production guide lists.

| Starting defect | Resolution |
| --- | --- |
| Terrain flat: one `Terrain_ELM_Authority` mesh at y = 0, `terrainHeightRange: [0.0, 0.0]` | Sculpted heightfield, playable range -22.0 m to 62.8 m, six surface classes |
| 12 of 55 landmarks belonged to other regions (Ssarathi, Mirrorhold, Sunmane, Manymouth x3, Orun x2, Crownwater, Whitehorn, Amberwood) | None preserved. 47 landmarks, all region-correct |
| `references/00-concept-detail-board.png` truncated to 786,444 bytes; only 113 of 793 rows decode (14%) | Intact board supplied by the user and installed. Full decode |
| `references/01-concept-aerial-overview.png` missing | Copied from `eloria-assets/concepts/nymara-regions/` |
| `server-collision/amethyst_barrens.bin` a flat placeholder: 32x32 tiles, height 11 everywhere | Regenerated at 96x96 tiles, 576x576 cells, 52 distinct height bytes |
| `world.json` had no `bounds`, no `coordinateTransform`, no collision | Complete against the schema; `collision.bin` written |
| `production-index.json` recorded `water: false` | Corrected. The aerial shows sea in two corners |
| Package carried loose `textures/` PNGs | Removed; the GLB is self-contained |

## Build history, in the order things were found

1. **Terrain first.** Heightfield, surface classes, roads and terraces built and
   verified before any detail work, as the guide requires: `validate_gltf` 0/0,
   `verify_runtime` 0 errors with 331,776 tiles sampled and 0 grounding misses.
   Committed on its own.

2. **Basin lowered from 26 m to 5.5 m.** The server's ELM height byte is six
   bits spanning -2.0 m to 10.4 m. A 26 m basin saturates it everywhere, and
   the client's verifier skips saturated cells rather than flagging them, so
   the map validates while the server gets a flat plateau. 90.4% of walkable
   ground now falls inside the encodable band.

3. **Placement passes ran before surfaces were painted.** The crystal and
   ground-dressing passes choose sites by surface class, so they scattered
   nothing. Reordered.

4. **Kit material names.** The shared kits use Amberwood's names (`ashlar`,
   `shingles`, `dark_iron`); every one is now mapped into this region's palette
   at the point of use. An unmapped name is a `KeyError` at export, not a silent
   fallback.

5. **`walk_surface=True` on `MeshGroup` placements made whole buildings
   walkable.** The flag renames the container node to `Walk_`, and every solid
   child inherits the prefix — the observatory's dome and armillary sphere
   became walk surfaces, so the grounding ray would put actors on the roof.
   17 `LANDMARK_BELOW_SURFACE` warnings; walk-surface nodes fell from 86 to 24
   when it was dropped.

6. **Bridge decks were placed by a no-op.** `deck = max(4.5, ground - ground +
   6.5)` is a constant, which put every deck 0.2 m above the terrain with its
   arches buried — a bridge lying on the ground rather than spanning anything.
   Deck height is now taken from the banks the roadway meets. This also cleared
   the last 7 `COLLISION_SURFACE_MISMATCH` cells once the collision footprint
   became a rotated rectangle instead of a circle on the smaller half-extent.

7. **`mesh.stairs` takes rise per step, not total.** The observatory's steps
   were built 23 m tall and stood as a slab in front of the dome. The offline
   preview hid it; the first real Godot frame showed it immediately. The same
   bug was in the resonant-cluster steps.

8. **Fully metallic materials render black.** With no reflection probe, a
   metallic surface has no diffuse term and nothing to reflect, so every brass
   pole, crane and spire cap came out as a charcoal stick — in the offline
   preview and in the client. `amethyst_verdigris` went to metallic 0.12 and
   `amethyst_brass` to 0.40.

9. **Crystal reads as crystal only when flat shaded.** A lofted prism shares
   vertices between adjacent faces, so `recompute_normals` can only average them
   however small the smoothing angle. `crystalcraft.facet()` explodes each
   triangle onto its own vertices. The profile also changed from a taper to a
   near-parallel prism with a short termination — the first version read as
   violet carrots.

10. **Crystal ground patches were pale continents.** Radii were cut roughly
    four-fold across two passes, the river veining narrowed, `CRYSTAL_FIELD`
    removed from `AUTHORED_SURFACES` so its boundary dithers, and the dither run
    twice. The transition is now carried by 260 scattered outcrop meshes.

## Shared toolkit changes

All additive; nothing forked. Coordinated with the Mirrorhold, Whitehorn and
Crownwater sessions running concurrently.

- `terrain.py`: surface classes 15-18 from an agreed per-region block (7-10
  Mirrorhold, 11-14 Whitehorn, 15-18 here, 19-22 Crownwater); `AUTHORED_SURFACES`
  and `UNDITHERED_SURFACES` so a region can protect a class it authors without
  editing the rules; `sea_shelf(side=...)` because Amberwood's coast is western
  and this region's sea is eastern.
- `textures.py`, `materials.py`: nine `amethyst_*` recipes and specs, appended.
- `crystalcraft.py`: new. Shards, clusters, outcrops, spires, floating fields,
  geode mouths and vein scatter, parameterised on material so any region with
  crystal or ice can use it.
- `regionbuild.py`: `Placement` and `RegionBuild` moved out of Amberwood's
  `region.py`; they carry no region-specific data and every region needs them.
- `regionpaths.load_region_build()`: `capture_views.py` did
  `from build_amberwood import build_region`, so it could only ever capture
  Amberwood.
- `export_server_collision.py`: took `SERVER_CELLS` from Amberwood's region module,
  which would size every region's ELM to Amberwood's grid.
- `capture_views.py`: a region may supply its own `LIGHTING` dict. The default
  is Amberwood's warm afternoon sun, which turns a bruised violet basin into a
  pleasant summer field.
- `make_comparison.py`: sheets are labelled with the region being built rather
  than always "Amberwood build".
- `godot_capture.gd`: new. Renders real client frames by loading `world.json`
  through the client's own `WorldLoader.load_world()`, taking sun, ambient, sky
  and fog from the manifest's `environment` block.

## Server

`feature/amethyst-barrens-576m-server-map` in `eloria-server` adds the region to
`MAP_TILES_WIDE_BY_NAME` at 96 tiles with arrival (174, 174), and extends
`tests/test_nymara_collision_contract.py`. `eloria/collision.py` needed no
change: the ELM loader is size-agnostic.

## The ground is cut inside the cell, not at its corners

The heightfield is sampled every two metres and `build_meshes` gave each quad
whole to the class of one corner, so a road could only ever turn on a cell
boundary and read as a flight of two-metre steps.

A class now takes every quad it touches and carries a per-vertex coverage in
COLOR_0's alpha, drawn with an alpha-tested copy of its material, so each pixel
goes to whichever class covers it. Where an operator knows its own edge -
`grade_path` for a road, `plateau` for a rim - `Terrain.surface_strength` puts
the cut on the real edge; elsewhere it falls half way between samples, which is
still a diagonal rather than a staircase. `despeckle_surfaces` clears class
islands under six cells first, because a crumb that read as a stray square at
whole-quad ownership reads as a deliberate blob once it is cut smoothly.

An alpha test is opaque, so it writes depth and sorts like any other ground.
The classes overlap where they meet by design, and `check_zfighting.py` skips
pairs that are both alpha-tested with vertex coverage.

See `whitehorn_range/change-log.md` for the full account, including why the
heightfield was not taken to one metre instead.

## September 2026 — Glasswarden survey district

The bridges stood near crossings without forming a coherent road network.
Seven spans now use exact bank surveys, with shared arcaded geometry, cart
widths, end lanterns and graded approaches. Roads skirt the worked clusters and
stations. A purple-roof assay exchange groups the existing services by arrival;
named residents work at their stations, diggings and freight landing.

The Crownwater ferry moved from the eastern inland ridge to a real jetty in the
south-east inlet. The Mirrorhold trigger moved outside its tower. The
observatory recipe moved into the shared toolkit; its stair now climbs toward
the podium through an opening in the balustrade, and the vault is entered
through a framed door in the lower drum. Walking strips surround its closed
interior instead of making the entire floor walkable.

The river previously lay below its bed. A shared incision pass makes a
continuous downstream channel; the water is above the frozen bed, and the
tributary joins the main river. Roads are graded afterwards. The distant
backdrop clips out of the playable terrain and opens east. The manifest sun
direction and the region's offline lighting hook were corrected.

Player-height captures prompted removal of duplicate podium faces and internal
drum caps. A cramped crab habitat was moved onto reachable coastal ground to
retain both original spawns. No imported assets or surface-class changes were
needed. Current measurements and remaining limitations are in layout-review.md.
