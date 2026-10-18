# How a ground edge is made (continent maps)

Traced on 2026-10-17 for the Landfall isles. Paths are from the client checkout.

## Ground patches (scene `Ground/Regions`)

1. **Scene.** Each region has `shape` (0 ellipse, 1 rectangle), `size`, `blend_width`,
   `opacity`, `priority`, `surface` (a texture preset) and `clip_polygon` (on the isles,
   the territory's ownership ring). The inspector slider caps `blend_width` at 8 m
   (`src/dev/map_authoring_pilot/ground_region.gd`). The saved file can hold more
   (Greenlight's `n10-lawn` is 10 m).
2. **Snapshot.** `src/dev/map_authoring_region/region_snapshot.gd` writes `blendWidth`
   and the other fields.
3. **Export.** `eloria-assets/maps/nymara-regions/_continent/terrain_export.py`,
   `ground_region_faces`:
   - The patch is the terrain's own 2 m lattice triangles.
   - Its coverage is `smoothstep(0, blend, inside_distance) * opacity`, written per
     vertex into vertex alpha and therefore linear across each 2 m triangle.
   - Rectangles measure `inside` as `min(half - |x|, half - |y|)`, so their iso-lines
     are straight sides with mitred corners.
   - Nothing is exported beyond the footprint: alpha is 0 on the shape's edge and
     zero-weight faces are dropped.
   - The result is a separate `AuthoredGround_<region>_<id>_...` node with an
     alpha-blended material, lifted a few millimetres.
4. **Runtime look** (`src/world/look/look_ground.gd`, `painted_for`):
   - Patches are classed paving, meadow, rock, kept or glaze.
   - The vertex alpha is cut in `painted_ground_surface.gdshaderinc`, at
     `look_rim.x` ± `look_rim.y`, with a fine noise wobble (`look_rim.z`,
     `RIM_NOISE_METRES`). Since 2026-10-17 the cut also moves in broad lobes
     (`*_RIM_LOBE.x`, `RIM_LOBE_METRES`) and follows the texture's grain (`*_RIM_LOBE.y`).
   - Constants live in `src/world/look/look_profile.gd` (`DECK_RIM`, `PATCH_RIM`,
     `PAVING_RIM`, `MEADOW_RIM` and the lobes).

With the look off, a blended import ignores vertex alpha and every patch is its
cell-stepped triangle footprint. The look is on by default.

## Roads (scene `Roads`)

- Each road is a `Path3D` polyline (Curve3D points with zero handles) plus
  `default_width`, `point_widths` and a surface. "Worn earth" uses `material_mode = 1`
  and `edge_feather = 0.16`.
- `terrain_export.py`, `authored_road_faces`: the ribbon is resampled to about 1 m
  along and 6 lateral strips across (`lateral_steps = 6`). Alpha is
  `smoothstep(0, edgeFeather, distance_from_edge)` at the strip vertices. At feather
  0.16 the whole edge ramp is the outermost strip: 1.33 m on an 8 m road.
- On continent-v2 maps roads are only the `Walk_*` decks. Nothing is painted into the
  terrain's vertex colour.
- At runtime a deck is cut with `DECK_RIM` and its lobe and grain. Beyond the cut,
  `EDGE_BAND` darkens a verge strip (a curb inside paving, `EDGE_BAND_PAVING`).

## Grass at paving (`src/world/look/grass_beds.gd`)

- The grass beds read pale paving's own coverage (`_paving_share`) and work out the
  paint's cut with the paint's noise (`paving_share`: `PAVING_RIM`, `PAVING_RIM_LOBE`,
  `paint_noise` is the shader's `look_value_noise`). They stop `GRASS_PAVING_PULL` short
  of it and thin out over `GRASS_PAVING_FEATHER`, so the grass follows a turned or
  round court and its wandering edge.
- Seams between paving patches stay bare: a spot on two paving footprints, or with
  painted paving on both sides within `GRASS_PAVING_SEAM_METRES` across x or z.
  Footprints of patches that only touch abut without overlapping, so the first test
  alone let grass up the seam.
- A candidate's tufts spread half a cell (about 0.3 m) round it, so beside paving
  each tuft's foot is judged again.
- Until 2026-10-17 grass stopped at each paving patch's AABB grown by 0.5 m: every
  turned court, round court or diagonal avenue stood in a bald axis-aligned
  rectangle.
- `tests/look/probe_paving_grass.gd` draws the bed around paving from above
  (headless) and counts tufts on the paint and bald ground inside the old bounds.

## Opaque kit paving (`ground.kit_paving`)

- Landfall's garden walks (`garden_paving.py`) are opaque `Walk_` strips with no
  vertex colour, so the look left them alone and they ended on their raw mesh edges.
- A region names such decks in `ground.kit_paving` (words in the node name). The look
  then gives the deck's mesh a coverage, as a copy (`LookGround.kit_paving_mesh`): 0
  on its outer edge, 1 from the next vertex in. It cuts that coverage at
  `KIT_PAVING_RIM` and `KIT_PAVING_RIM_LOBE` in the deck's own texture and colour.
  - Painted as paving instead, the walks took Landfall's paving tint and flagstone and
    turned brown, the dirt they were paved to replace.
- What is not an outer edge in `garden_paving.py`'s meshes:
  - edges along the 96 m publish-chunk sides a walk was cut on (local ±48 m);
  - T-junctions where a round end's fan spoke spans two strip rows.
  - Two walks whose sides coincide keep both edges.
- The arrival rosette is an inlay on the plaza's paving, kept by `props.keep_words`,
  and left crisp.

## Every place an edge gets hard

| Cause | Where | Fix layer |
|---|---|---|
| Narrow rim cut with a 0.9 m wobble | `look_profile.gd` rims | runtime (done 2026-10-17: lobes + grain) |
| Rectangle iso-lines are straight sides | `terrain_export.py` | content: ellipses or several overlapping shapes; runtime lobes hide most of it |
| Blend ≤ 2 m spans at most one 2 m lattice cell | export lattice | content: blend ≥ 3 m (paving) or ≥ 6 m (natural ground) |
| No geometry outside the footprint | export | content: enlarge the shape when the edge must reach further out |
| Road ramp is one lateral strip | `lateral_steps`, `edgeFeather` | content: raise `edge_feather` on the road surface (needs a republish) |
| Dark edging band outlines roads | `EDGE_BAND` | runtime |
| Grass stops on straight, axis-aligned lines round paving | `grass_beds.gd` paving AABB + `GRASS_PAVING_MARGIN` | runtime (done 2026-10-17: follows the coverage, `_paving_share`) |
| Opaque kit decks (garden paving) have no coverage | `garden_paving.py` strips, published as `Walk_` decks | runtime (done 2026-10-17: `ground.kit_paving`, Landfall) |
| Hard clip at the map edge | `clip_weighted_ground_faces` | expected: the neighbour owns the ground beyond |

## Per-map tuning

Region look files `src/world/look/regions/<id>.json` are validated by
`LookProfile.typed_region` and `tests/look/test_look_regions.gd`. On the isles they are
generated from pinned source palettes plus `eloria-assets/maps/continent-v2/<map>/content/look-overrides.json`
by `_continent_v2/publish_look.py`. That tool replays a commit from the old repository
and cannot run in Rabbit Lands. Edit the overrides file (the source of truth), then
merge the same keys into the region file. Update `notes.overrides.sha256`, and the
`notes.origin` sentence when the map had no overrides before. Re-serialise with tab
indentation; a round trip of an unchanged file is byte-identical.

The ground keys a region may set are in `LookProfile.REGION_SECTIONS["ground"]`.
`class_textures` maps the slots `deck`, `paving`, `sand` and `meadow` to the names in
`LookProfile.CLASS_TEXTURES`.
