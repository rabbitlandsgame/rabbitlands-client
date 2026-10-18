# Road and path shapes

## What reads as unnatural

- **Out-and-back jogs.** The line runs a few metres one way, then turns back.
  These are often left where route stations were joined; Greenlight's R29 runs
  3.5 m east, then turns back south-west. At road width this reads as a notch.
- **V switchbacks.** Two legs meet at a point instead of an arc. Boarsend's R41 has
  two, about 25 m apart, and Hearthcroft's terrace road has tight U turns.
- **Single-vertex kinks.** One point turns more than about 50°.
- **Ruled straights.** Long straight runs with constant width are natural only for
  causeways, quays and town streets.

`scripts/map_audit.py roads` finds all four:
- `doubles_back`: over a stretch of about 3 road widths, the straight distance is
  under 0.55 of the distance walked.
- `sharp_corner`: one vertex turns more than 50°.
- `min_radius_m`: the tightest turning radius over 3 m chords. A road should not turn
  tighter than about 1.25 road widths (10 m on an 8 m road).

`map_audit.py overlay` draws roads (red), findings (yellow rings) and flagged
patches (cyan squares) over each `map-detail.webp`.

## What can be fixed where

- **Small jogs and kinks** round off within the road's own graded corridor: move no
  point more than about a quarter of the width. The road stays on the ground the
  grading pass shaped. Measured 2026-10-17 with a constrained Laplacian smoothing:
  - Greenlight R29's start went from a 1.7 m to an 11 m radius.
  - Ringholm's east road went from 1.9 m to 24 m.
  - Twinbrook's north road went from 2.1 m to 7 m.
- **True hairpins**, where two legs run side by side about a road-width apart, cannot
  be rounded inside the corridor. They need a turnaround pad (a radius of at least
  the road width, on graded ground), or a longer, gentler switchback re-graded into
  the sculpt layer.
  - That is a reroute. The owner's road rules apply: cut 4 m, fill 3 m, then
    reroute, then authored switchbacks.
  - Reroutes need the owner's confirmation.
  - Served walkability needs grades of 0.65 or less and a fresh served-grid
    reach check.

## Grading a reroute

These are from the 2026-10-17 content pass (Boarsend R41, Hearthcroft R30, R32 and R27).
- Fade the new bed in from each join over 6 m of the rerouted span (a smoothstep
  weight on the height change). At the joins the old road's bed is already right.
- Do not smooth the height change. A Gaussian on it blurred the bed into its banks
  and steepened the centreline to grades of 0.82.
- Do not add a flat shoulder past the widest deck edge. 1 m of shoulder pushed fill
  banks out to 6 m on steep slopes. Bank straight out from the deck edge (the pass
  used slope 0.7, banks 3-6 m wide).
- Afterwards, check the terrain gradient in every 2 m cell under the decks (road
  half-width × 1.15) against 0.65, `export_collision.py`'s `MAX_GRADE`. Compare with
  the scene before the change and list the cells that are newly steep. A rerouted
  deck over a steep cell is unwalkable on the served grid.
- Then compare served reach from the arrival point, before and after. Hearthcroft's
  reroute banks blocked 475 tiles and closed three small pockets. The publisher rows
  still passed.

## Publishing

Every road change is authored content. It changes the walk decks, `collision.bin`
and the server's served grid, so it needs the full publication order in
`eloria-assets/maps/continent-v2/_continent_v2/README.md`:
1. Bake every catalog map from committed scenes.
2. Run `publish_client`, export collision and crossings.
3. Run `publish_server --apply`, commit, then apply again.

Run `map_audit.py drift` first: a map whose saved scene already differs from its
last bake will publish those other changes too. Coordinate with anyone else
publishing; generated files are regenerated after a merge, never hand-merged.

The 2026-10-16 procedural-model retirement left three guards that a republish trips.
Patch rebuilds trip them too:
- **Pinned chunk hashes.** `godot-client/data/assets/retired_procedural_models.json`
  `mapMeshCopies` pins the SHA-256 (and retired mesh indices) of chunk GLBs that held
  a retired mesh. `render_minimap.py` refuses a rebuilt chunk whose bytes changed
  ("retired mesh index needs refresh"). Refresh the entry, or drop it when the chunk
  no longer contains a retired mesh. The content pass dropped the four cave-mouth
  chunks' entries. `godot-client/tests/test_retired_procedural_models.gd` reads the same index.
- **Wrappers naming deleted models.** The retirement emptied some `AuthoredAssets`
  wrappers but left their `catalog_asset_id` naming the deleted model. Those scenes
  stop baking with "source asset is missing" (`region_snapshot.gd`). The content pass
  removed six of them with the owner's approval (fecac386). Look for others in any
  scene you bake.
- **Builder digest.** `underground.py` checks each underground package's
  `provenance.builderSha256` against `build_underground.py`. The retirement added a
  raising guard to that builder, which changed its digest, so `publish_server`
  refused every continent-v2 publish. The builder can no longer run. The owner chose
  to advance `landfall_insides`' `builderSha256` to the guarded builder's digest
  (e7fd821c) rather than patch the check. Do the same if the builder changes again.

## Path character beyond geometry

A natural path varies: worn centre, grass reaching in at the verges, width that
breathes. The runtime look gives the edge lobes and grain, and the grass beds grow
on the verge. In content:
- Vary `point_widths` along a path by about ±15%. Don't keep one width end to end.
- Let paths widen at junctions, gates and stops.
- Prefer gentle curves that follow contours over straight segments between stations.
