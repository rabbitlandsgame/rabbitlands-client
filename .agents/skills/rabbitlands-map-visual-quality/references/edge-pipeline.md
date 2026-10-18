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

### Splitting or resizing a patch

Each authored patch is its own mesh, and the runtime cuts each one separately at
its class's threshold (`look_ground.gd` picks the rim per material):
`PATCH_RIM.x` 0.42, `MEADOW_RIM.x` 0.14 (Grass) and `PAVING_RIM.x` 0.12. Overlapping
pieces never add up. The visible shape is the union of each piece's own cut contour.
- A piece becomes visible `blend × smoothstep⁻¹(cut / opacity)` inside its outline.
  At opacity 1 that is 0.45 of the blend for a patch (2.7 m on a 6 m blend), 0.24
  for a meadow and 0.22 for paving. At opacity 0.8 a patch's inset is 0.52 of the
  blend.
- So every piece of a split patch keeps the original opacity. Lowering it to
  "share" the coverage only pushes each cut inward.
- Every piece must be wider than twice the inset, or it vanishes. The 2026-10-17
  content pass kept each piece's half-width at least the inset plus 1.5 m.
- Widening a paving blend moves its 0.12 contour inward. Grow the size by
  `2 × smoothstep⁻¹(0.12 / opacity) × (new blend − old blend)` (about 0.43 m per
  metre of extra blend at opacity 1) so the paving edge stays where it was.

## Reading scenes by script

- A `.tscn` `Transform3D(t0 … t11)` lists the basis ROWS, then the origin:
  `world = (t0 x + t1 y + t2 z + t9, t3 x + t4 y + t5 z + t10, t6 x + t7 y + t8 z + t11)`.
  In x/z the node's X axis is `(t0, t6)` and its Z axis is `(t2, t8)`. This was
  measured against Landfall `meadow-16`'s exported mesh, whose long axis is
  (-0.921, 0.389). Reading them as columns mirrors every rotated piece. The content
  pass did that once, then fixed it (f4945e14).
- Older ground-region `clip_polygon`s were written in the transposed frame. Read with
  axes `(t0, t2)` and `(t6, t8)`, each one equals its territory's ownership ring. The
  exporter reads them with the true axes, so a rotated original patch near a border
  is clipped by a turned ring. This is known and was left alone. Write new pieces'
  rings in their true frame.
- Godot 4.7 writes `unique_id=NNN` (and can write more) after `parent=` in node
  headers. Every Nymara region scene has it, and the isles do not. Allow a trailing
  remainder when matching headers. When nodes under a parent you read go unmatched,
  fail instead of reporting zero.

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

## Every place an edge gets hard

| Cause | Where | Fix layer |
|---|---|---|
| Narrow rim cut with a 0.9 m wobble | `look_profile.gd` rims | runtime (done 2026-10-17: lobes + grain) |
| Rectangle iso-lines are straight sides | `terrain_export.py` | content: ellipses or several overlapping shapes; runtime lobes hide most of it |
| Blend ≤ 2 m spans at most one 2 m lattice cell | export lattice | content: blend ≥ 3 m (paving) or ≥ 6 m (natural ground) |
| No geometry outside the footprint | export | content: enlarge the shape when the edge must reach further out |
| Road ramp is one lateral strip | `lateral_steps`, `edgeFeather` | content: raise `edge_feather` on the road surface (needs a republish) |
| Dark edging band outlines roads | `EDGE_BAND` | runtime |
| Grass stops on straight, axis-aligned lines round paving | `grass_beds.gd` paving AABB + `GRASS_PAVING_MARGIN` | runtime (open) |
| Opaque kit decks (garden paving, plaza rosette) have no coverage | `publish_client.py` kit `Walk_` decks | content: dress their edges with props or a blended patch |
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
