# Amberwood modelling assumptions

These are the decisions taken where the brief, the concept art and the existing
runtime did not fully determine the answer. Each one is a place a reviewer may
reasonably want to overrule the build.

1. **Region extent.** Amberwood is authored at 576 m x 576 m - three times its
   original linear extent, nine times the area. One metre per tile is kept, so
   movement granularity is unchanged; the server map grows instead, from 32x32
   to 96x96 ELM tiles (192 to 576 height cells). The arrival datum keeps its
   position relative to the map, moving from server (58, 58) to (174, 174), so
   it still lands on the Godot origin. `../server-collision/amberwood.bin` is
   regenerated to match and must be loaded server-side.
   The whole composition is written in the original 192 m design space and
   scaled by `region.SCALE`, so the aerial concept's layout is preserved rather
   than stretched; the space this opens up is filled with new authored places
   - three rings of them now: the original composition, then a second ring
   (a cove and its huts, a forest lake and lodge, a deep old-growth grove, amber
   diggings, a northern hamlet, a second ravine crossing, a hill shrine, an
   orchard, a quarry, a south watch, an eastern hamlet, a burnt battlefield, a
   cinder tower and a burnt mill), then a third (a far grove and its camp, a sea
   arch, a kelp landing, a long orchard and skep rows, the long meadow, a
   standing-stone ring, a western lodge, the upper falls, a coppice, an east
   grove, a ridge camp, a marchstone, a cinder chapel, a cinder field, smoking
   ground, an east quarry and a far watch) - not by spreading the original
   objects thinner.
   Vertical relief is deliberately *not* doubled: a 2x wider region with 2x
   taller hills would read as the same picture and would double every slope a
   player has to climb. Relief grows by about a third.
2. **The previous package's bounds were wrong.** It centred a flat ±96 m terrain
   on the origin, which leaves server tiles above roughly (154, 154) with no
   ground under them. This build covers the whole reachable footprint and
   verifies it tile by tile.
3. **Sea level is y = 0** and the west coast is the natural world boundary; the
   other three sides are closed by mountain walls raised inside a 16 m margin.
4. **Forest density is per-area, not per-region.** The enlargement thins the
   stands deliberately: tree spacing goes from 4.9 m to 6.6 m, so the forest is
   roughly 45% less dense on the ground than the 384 m build. Coverage goes the
   other way - the density floor is raised and the burnt country's boundary
   pushed east - so the forest reaches across more of the map while any given
   stand is airier. Most instances are at the far detail tier, which is what
   keeps the triangle count from tracking the area.
5. **Elevated decks own their server cell.** The client grounds actors on the
   highest walk surface below a downward ray, and a flat server grid cannot hold
   two levels. Bridge decks, canopy platforms and the dock therefore take their
   footprint in `collision.bin` at deck height; the ground beneath them is not
   separately walkable. This is a design decision, not an oversight.
6. **Tangents are not exported.** Godot's glTF importer generates them for
   normal-mapped materials, and shipping them would add sixteen bytes a vertex
   to a package already dominated by vertex data.
7. **The reduced package is a second GLB, not a runtime LOD switch.**
   `world-lod2.glb` carries far-tier vegetation only, no ground clutter and
   half-resolution textures. Nothing in the current Godot loader selects between
   them; it is there for low-end machines and for whoever adds streaming.
8. **`collision.bin` height bytes clamp at 63.** The legacy six-bit height field
   cannot express Amberwood's 0–100 m relief. The grid is authoritative for
   walkability; the Godot loader takes elevation from the rendered walk
   surfaces, not from this file. The encoding datum is recorded in `world.json`.
9. **Lore names are invented.** The brief said to take official names from the
   written region description and server data; neither was available to this
   build (see `validation-report.md`). Every name in `world.json` is a
   placeholder chosen to fit the concept art and is expected to be replaced.
10. **Portal destinations follow the client registry's map ids.** The server owns
   the actual transitions; the portal entries are alignment metadata.
11. **Population markers are metadata.** NPCs, creature groups and harvestables
   are recorded as positions with `"authority": "server"`. Nothing is baked into
   the static mesh.

## September 2026 inhabited terraces

The market court at world (24, -171) is the safe arrival, above a mill on the
outlet rather than in a stream. The north beck passes west of the court.
Buildings face the streets; their actual closed footprints are stamped as
solids. The Mother is enlarged uniformly to carry the settlement silhouette.

The two western cove groups occupy dry benches. The quay has a descending
timber deck and an offshore packet. Industry follows its access: the mill
has an exposed wheel in the race, the quarry has a six-metre cart road,
and cultivated rows sit beside the lower orchard approach.

Seven exact bank surveys are declared in source/layout.py. Road shoulders
meet them; terrain beneath a walking skin is recessed. Wildlife occupies
successive meadow, working forest and remote ridge/ash habitats. Species,
resource names, secret keys and room contents remain the existing roster.
