---
name: rabbitlands-map-visual-quality
description: Audit and improve how Rabbit Lands maps look up close and from above - harsh transitions and ruled edges between paths, paving, sand and grass, patches that read as primitive shapes, ground textures that are recoloured copies or tile visibly, and roads that jog, zigzag or hairpin. Use before or after editing a map's ground, roads or look data, when reviewing a region's visuals, or when generating ground textures.
---

# Rabbit Lands map visual quality

Natural ground has no ruled lines. Most harsh-looking maps fail in a few repeatable
ways:
- edges cut too crisply or along straight lines;
- patches drawn as discs, squares and ovals;
- one texture recoloured into several surfaces;
- textures that repeat as a grid or as stripes;
- roads that jog, zigzag or hairpin.

This skill finds them with numbers and renders, and fixes each at the cheapest layer
that can fix it.

Work from the client checkout, in your own worktree (other sessions edit the main
checkout). The scripts are in `scripts/` beside this file and change nothing unless
stated.

## 1. Audit

```powershell
python .agents/skills/rabbitlands-map-visual-quality/scripts/map_audit.py overlay --out .local/video-generation/map-audit
python .agents/skills/rabbitlands-map-visual-quality/scripts/map_audit.py roads
python .agents/skills/rabbitlands-map-visual-quality/scripts/map_audit.py patches
python .agents/skills/rabbitlands-map-visual-quality/scripts/map_audit.py drift
```

- `overlay` draws authored roads (red), road findings (yellow rings) and flagged
  patches (cyan squares) over each map's `map-detail.webp`.
- `roads` reports out-and-back stretches, sharp single-vertex corners and the tightest
  turning radius per road.
- `patches` reports paving with too little blend, natural ground with hard edges,
  rectangles of natural ground and long thin shapes.
- `drift` lists maps whose saved scene differs from the last published bake. A
  content fix there publishes those changes too.

The default map set is every registry map with status `continent-v2-served` (the
Landfall isles); pass `--maps` for others.

Then look in game. Write views (a target point, a compass heading, a pitch and a
distance) to a JSON file and turn them into trailer-camera shots with
`scripts/audit_shots.py`. Render stills before and after with the trailer camera's
`--preview` mode (`godot-client/src/dev/trailer_camera/README.md`). The camera was on
client branch `feature/trailer-camera` when this skill was written; until it is merged,
copy that folder into your worktree, untracked, to render.
`references/audit-checklist.md` lists what to look at and in which views.

## 2. Choose the layer

| Problem | Fix | Cost |
|---|---|---|
| Edges too crisp or straight within the authored blend; dark outlines on roads | Look constants in `godot-client/src/world/look/look_profile.gd` (`*_RIM`, `*_RIM_LOBE`, `RIM_LOBE_METRES`, `EDGE_BAND`) | Runtime only, all maps |
| A surface has no structure, or the wrong family (wall masonry as paving) | Runtime class texture: `ground.class_textures` in the map's look overrides | Runtime only, per map |
| A patch is a primitive shape; its blend is too narrow; a texture needs to belong to the authored design | Edit the scene's `Ground/Regions` and surfaces | Republish |
| A road jogs, kinks or hairpins | Edit the scene's `Roads`; re-grade for hairpins | Republish, owner confirmation for reroutes |

How a coverage value travels from the scene to a pixel, and every place an edge
gets hard, is in `references/edge-pipeline.md`. Read it before changing a constant.

## 3. Rules that hold

- **Edges.** Cut the exporter's coverage ramp with a short step that wanders in broad
  lobes (about 5 m) and follows the texture's grain. Do not widen it into a feather:
  a linear ramp drew 1-3 m "airbrushed" rims and was rejected.
  - Paving keeps nearly all its geometry. Where two paving patches meet, their low
    weights must not open a green veil.
- **Blend widths.** Paving at least 3 m, natural ground (sand, meadow, forest floor)
  6-8 m. The exporter samples weights on a 2 m lattice, so a 1 m blend is one hard
  cell.
- **Shapes.** Build natural ground from several overlapping, rotated ellipses of
  different sizes, never one disc or a long thin oval. Keep rectangles for built
  surfaces: courts, quays, fields.
- **Roads.** Keep the turning radius at least about 1.25 road widths and no
  out-and-back jogs. Vary width about ±15% and widen at junctions.
  - Round small kinks within a quarter of the road's width, so the road stays on its
    graded corridor.
  - Hairpins need a turnaround pad or a re-graded switchback.
  - The owner's road rules (bridges, cut 4 m / fill 3 m, reroutes confirmed) are in
    shared memory note `continent-road-rules`.
- **Textures.**
  - Never ship one texture under several tints as different surfaces, or a wall
    texture as ground.
  - Every ground tile must wrap without a grid at a 3x3 repeat. Directional detail
    must not stripe at the tile's world repeat.
  - Follow `references/textures.md`.
- **Between maps.** Biome transitions are gradual: about a 260 m interfingered blend
  with a meadow ecotone (shared memory note `region-transitions-gradual`).

## 4. Fix

- **Runtime look.** Change the constants or the look overrides.
  - `publish_look.py` cannot run in Rabbit Lands. Edit
    `eloria-assets/maps/continent-v2/<map>/content/look-overrides.json`, then merge the
    same keys into `godot-client/src/world/look/regions/<map>.json`.
  - Update `notes.overrides.sha256`.
  - Run `tests/look/test_look_regions.gd` and `tests/look/test_look_ground.gd`
    headless.
- **Textures.** Generate, then run `scripts/make_seamless.py`, record provenance, and
  route as in `references/textures.md`.
- **Roads and patches.** Edit the saved scene in the editor or by script, committed
  first.
  - Then follow the publication order in
    `eloria-assets/maps/continent-v2/_continent_v2/README.md`: bake every catalog map,
    `publish_client`, collision and crossings, then `publish_server --apply`, commit,
    and apply again.
  - Check served reach and walk the changed roads.
  - `references/road-shapes.md` has the road specifics.

## 5. Verify and record

- Re-take every audit view after the change: same views, same hour, one GPU job at a
  time.
- Look constants apply to every map, so check one map outside the change too (a
  Nymara region).
- Keep the before/after sheets with the change.
- Write down anything the next person needs, such as a constant's measured effect or
  a rejected setting, as a comment beside the constant.

## Findings from the first audit (2026-10-17, the 15 Landfall isles)

- **Edges:** 0.05-0.35 m on paving and about 0.16 m on roads, with a 0.9 m wobble. The
  authored 3-8 m blends were cut away at runtime.
- **Shapes:** 269 ground patches, all ellipses or rectangles. 36 are thin (aspect over
  3). 12 paving patches have blends of 1 m or less (Landfall's keep forecourt, courts
  and paved avenue; the seam-mole pavings; Tollholm's square).
- **Textures:** roads, sand, soil and lawns were one tinted texture, and paving was
  wall masonry. The coastal gravel showed a repeat grid.
- **Roads:**
  - Hairpins: Boarsend R41 (two V switchbacks) and Hearthcroft's terrace roads.
  - Jogs and kinks: Greenlight R29's start, Ringholm's east road and Twinbrook's north
    road.
- **Fixed at runtime:** edge lobes and grain, plus three class textures (packed earth
  on roads, flagstone on paving, beach sand on sand) on all 15 isles.
  - Paving gained the most: it now ends stone by stone.
  - Roads changed texture, but their edges can only move within the exporter's one
    1.3 m rim strip.
  - A meadow turf texture was tried and dropped: its fine detail went flat green at
    the game camera.
- **Still need a republish:** road shapes, patch shapes, narrow blends and road edge
  ramps. They are recorded as follow-ups.
