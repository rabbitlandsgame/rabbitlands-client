# Map visuals audit checklist

Work map by map, from far to near. Capture evidence for every finding: a top-down
overlay, an in-game view, or a number. Every fix is judged against the same views
afterwards.

## 1. Top down: shapes

Run `python scripts/map_audit.py overlay --out <dir>` and read each map's image.

- Patches that are visibly an ellipse or a rectangle: a lawn disc, a square plaza, a
  sand oval. Natural ground has irregular outlines.
- Long thin ellipses: they read as ruled stripes, even with the maximum blend.
- Rows of identical lobes ("fish-bone" sand), and overlapping discs of scree that
  read as stamps.
- Roads that jog, zigzag or hairpin (yellow rings), and roads straighter than the
  ground they cross.
- Straight brightness seams between render windows or maps.

## 2. Numbers

- `map_audit.py roads`: `doubles_back`, `sharp_corner`, `min_radius_m` against
  1.25 road widths.
- `map_audit.py patches`:
  - paving blend under 3 m (no room for an edge);
  - natural ground under 2 m;
  - aspect over 3;
  - rectangles of natural ground.
- `map_audit.py drift`: which saved scenes are not yet published. A content fix there
  ships those changes too.

`roads` and `patches` exit non-zero, naming the scene and the first header they
could not read, when a node under `Roads` or `Ground/Regions` goes unread. Before
that check existed, the Godot 4.7 `unique_id` attribute hid all 323 Nymara roads and
454 patches behind a clean report of zero. Treat a map that reports zero roads as a
fact to confirm in its scene, not as a pass.

## 3. In game: edges and textures

Render the same views before and after with the trailer camera's `--preview`, from
`scripts/audit_shots.py`. Use a game-like oblique view (35-45° down, 35-90 m), and one
near the ground for paths. Pick views where:
- paving meets grass;
- a road crosses a lawn;
- sand meets grass;
- a road climbs a slope;
- a plaza meets a street.

Look for:
- edges that are ruled lines, at any distance;
- dark outlines framing a road (`EDGE_BAND`);
- grass stopping on straight axis-aligned lines around paving;
- one pattern recoloured across surfaces that should differ (road, sand, soil);
- wall textures used as ground;
- a visible repeat grid or stripes at 3-4 m;
- opaque kit decks (garden paving, rosettes) with raw mesh edges (a deck on grass can
  be named in the map's `ground.kit_paving`);
- holes or a green veil where two paving patches meet. This is the risk whenever
  paving's cut moves inward.

## 4. Across maps

Transitions between neighbouring maps follow the owner's rule: a gradual ecotone
about 260 m wide, interfingered, not a line. Check a border walk with
`neighbours: "auto"` in a trailer camera shot.

## 5. Decide the layer

| Finding | Layer |
|---|---|
| Edge too crisp or too straight within the authored blend | runtime look constants |
| Surface lacks structure, wrong texture family | runtime class texture, or authored preset |
| Shape is a primitive (disc, square, oval) | content: break into overlapping irregular shapes, each keeping the original opacity and wider than its cut's inset (`edge-pipeline.md`) |
| Blend too narrow for a soft edge | content: raise `blend_width` (grow paving so its 0.12 contour stays put) |
| Road jog or kink | content: round within the corridor |
| Hairpin, or a road on the wrong line | content: reroute plus re-grade, with owner confirmation |
| Repeat grid in a source texture | re-process with `make_seamless.py`, then route as above |

## 6. Verify

- Run `tests/look/test_look_ground.gd`, `tests/look/test_look_regions.gd` and any look
  test touching the constants you changed.
- Take the same before/after views, at the same time of day, rendered serially (one
  GPU job at a time).
- Check one map outside the change's scope (a Nymara region) when you change look
  constants: they apply to every map.
- For content: run the publication checks and the served-grid reach checks, and walk
  the changed roads.
  - Preview split patches as the union of each piece's own cut contour, old beside
    new. Overlapping pieces do not add their coverage.
  - Check rotated pieces against the exported mesh once. A basis read as columns
    instead of rows mirrors them.
  - After a reroute, list deck cells newly steeper than 0.65 (`road-shapes.md`,
    "Grading a reroute").
  - Expect the three retirement guards on a republish: pinned chunk hashes,
    wrappers naming deleted models, and the underground builder digest
    (`road-shapes.md`, "Publishing").
