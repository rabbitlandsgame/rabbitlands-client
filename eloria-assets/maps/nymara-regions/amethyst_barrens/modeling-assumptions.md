# Amethyst Barrens — modelling assumptions

Everything here is a decision that was not forced by the concept art or the
runtime contract, recorded so the next person can disagree with it deliberately.

## Extent and coordinates

- **576 m × 576 m at one metre per tile**, i.e. 96 × 96 ELM tiles. Chosen to
  match Amberwood, because the server already carries that precedent and the
  concept's composition needs the room. The arrival datum keeps its position
  relative to the map — 30% in from the south-west, server (174, 174).
- The composition is authored in the placeholder's **192 m design space** and
  scaled by `region.SCALE = 3.0`. Changing the region's extent is one constant.
- `region.LOCAL = 1.5` scales the *places* rather than the distances between
  them. A courtyard is sized by the buildings in it, so it must not triple when
  the map does.

## Terrain height, and why the basin is low

The server's ELM height byte is six bits under
`elevation = byte * 0.2 - 2.2`, so it can only express **-2.0 m to 10.4 m**.

Amberwood's basin sits near 28 m, which saturates that byte across roughly 90%
of its map. The client's own `verify_runtime.py` skips saturated cells rather
than flagging them (`if grid[cz, cx] < 63 and ...`), so this passes validation
silently while leaving the server with a flat plateau and no usable elevation.

Amethyst Barrens is authored with `BASIN_LEVEL = 5.5` so that **90.4% of
walkable ground falls inside the encodable band**. The exported ELM carries 52
distinct height bytes with only 8% saturated. The saturated remainder is the
mountain flanks and the massif, which is correct — that ground is barely
walkable and its exact height does not matter.

This costs the composition nothing: the concept is a flat storm-scoured basin
ringed by mountains, not a highland. It would be the wrong call for a region
whose art demands real relief across the playable area; such a region needs the
height encoding widened instead.

## What the concept decides, and what it does not

The aerial concept is the composition authority and the ten-panel detail board
is the player-scale authority. Both were read directly; the QA brief at
`eloria-assets/qa/regions/amethyst-barrens/README.md` agrees with them and its
landmark counts are reproduced exactly.

**Place names are taken as canon, not invented.** Unlike Amberwood — whose names
were all placeholders because no written region description was available — the
placeholder `world.json` for this region already carried region-correct names
(Glasswarden Observatory, Amethyst Crystal Bridge, Geode Cave, Levitating
Shards, Storm Ruin, Resonant Crystal Cluster, Glasswarden Field Station) and the
QA brief corroborates the counts. Those names are used. Three names are mine and
should be checked against any written source: **The Amethyst Massif**, **The
Resonance Ring**, and the **Glasswarden Watchtower** trio.

Twelve of the placeholder's 55 landmarks belonged to other regions (Ssarathi,
Mirrorhold, Sunmane, Manymouth, Orun, Crownwater, Whitehorn, Amberwood). None of
them was preserved.

## Water

`production-index.json` recorded `water: false` for this region. That is wrong:
the aerial clearly shows sea in the north-east corner and again in the
south-east, with a dry rocky headland between them on the east edge. The
shoreline function reproduces exactly that, and the index entry is corrected.

The sea is drawn as one plane clipped to where the ground is below sea level, so
both corners are covered by a single body. The river gets a swept ribbon that
follows its carved bed downhill rather than a flat plane, because it falls
several metres across the map.

## The navigation contract

- Terrain sub-meshes are `Terrain_<class>`; built walk surfaces are `Walk_*`.
  Both prefixes are in `navigation.surfaceNodePrefixes`.
- **`walk_surface=True` is not set on any placement whose mesh is a `MeshGroup`
  with its own `add_walk` parts.** Setting it renames the container node to
  `Walk_…`, and every solid child then inherits that prefix — the observatory's
  dome and armillary sphere became walk surfaces, so the grounding ray put
  actors on the roof. The group's own walk parts already carry the prefix.
  This is the guide's rule 2 in a form that is easy to trip over.
- Bridge decks own their footprint in `collision.bin` at deck height; the gully
  or river beneath is not separately walkable. The footprint is a **rotated
  rectangle**, not a circle on the smaller half-extent: a bridge deck is long
  and narrow, and a circle leaves both ends encoding the channel floor while the
  ray overhead finds the deck.
- Levitating shards are neither walk surfaces nor colliders. A player walks
  under them.

## Materials and the shared toolkit

Nine `amethyst_*` texture recipes and material specs were **appended** to the
shared tables, never inserted, and the build pins `only=<used set>` when
registering materials so this package embeds 13 materials and 39 images rather
than the whole shared library.

Two material values are deliberately not physically ideal:

- `amethyst_verdigris` metallic **0.12** and `amethyst_brass` metallic **0.40**.
  A fully metallic surface has no diffuse term, so with no reflection probe in
  the scene every spire cap and brass fitting rendered as a black stick — in the
  offline preview *and* in a real Godot frame. Verdigris is a mineral crust
  rather than bare metal, so a low value is also the more honest choice; the
  brass is a compromise that reads as metal in a scene without image-based
  lighting. If the client gains reflection probes, both should go back up.

Terrain surface classes 15–18 (`BARRENS`, `CRYSTAL_FIELD`, `RESONANT_ROAD`,
`STORM_ROCK`) were allocated from a block agreed with the other region sessions
running concurrently: 7–10 Mirrorhold, 11–14 Whitehorn, 15–18 here, 19–22
Crownwater.

## Budgets

444,492 unique and 601,200 instanced triangles over 331,776 m² is **1.34 and
1.81 triangles per square metre**. Amberwood is about 9.5. That is well inside
the repository's 1.5 M visible-triangle desktop guideline, and it is also a fair
description of a gap: this region is sparser than the concept's density
warrants. See `comparison-report.md`.

## September 2026 layout decisions

The Glasswarden exchange occupies the sheltered side of the arrival, before
the open basin routes divide. Its low roof preserves views of both the
observatory and the Amethyst Massif. It supplies the existing services through
server content, with no duplicate baked service objects.

Work camps and extraction remain distinct: the through roads bypass cranes,
specimens and tents, with short approaches into each workplace. Stronger
creatures occupy the northern massif and ruins; easier wildlife occupies
worked southern and western ground. Levels and rewards were not retuned.

The packet landing belongs in the actual south-east cove, not on the dry east
ridge. Its east-shore id still names the same Crownwater connection. West-road
connects to Mirrorhold as the authoritative continent graph specifies; the old
coverage note naming Amberwood is superseded.

The old six-bit and saturation notes above describe the original build.
The shipped package uses the documented refine/open/stamp correction sequence.
The new bank survey is frozen before grading and stored per terrain instance;
near and far builds do not share mutable survey state. Water levels come from
the incised channel before any road or bridge construction.
