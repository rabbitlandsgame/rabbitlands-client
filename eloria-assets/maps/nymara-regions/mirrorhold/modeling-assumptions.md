# Mirrorhold modelling assumptions

These are the decisions taken where the brief, the concept art and the existing
runtime did not fully determine the answer. Each one is a place a reviewer may
reasonably want to overrule the build.

1. **Region extent.** Mirrorhold is authored at 576 m x 576 m, three times its
   original linear extent, at one metre per tile. The server map grows from
   32x32 to 96x96 ELM tiles (192 to 576 height cells) and the arrival datum
   moves from server (58, 58) to (174, 174), so it still lands on the Godot
   origin. This follows the shape of the change Amberwood already made rather
   than inventing a second convention. `../server-collision/mirrorhold.bin` is
   regenerated to match and must be loaded server-side; the matching server
   change is on `feature/mirrorhold-576m-server-map`.

   The whole composition is written in the original 192 m design space and
   scaled by `region.SCALE`, so the aerial concept's layout is preserved rather
   than stretched. `region.LOCAL` scales places, not distances: a terrace is
   sized by the buildings on it, so it must not triple with the map.

2. **The region is named for its pools, not its lake.** The concept's aerial
   shows still cyan basins stepping down the citadel's terraces, and a lake at
   the bottom of the valley. The reading taken here is that the mirrors are the
   terrace basins - `landmarks.reflecting_basin` - and the lake is the water
   they drain to. If the written lore says otherwise, the emphasis is one
   placement pass to change.

3. **The lake is the datum, and there is no sea.** Water level is y = 0 and the
   lake floor is -11 m. Unlike Amberwood there is no open side: all four
   boundaries are mountain.

4. **The world boundary is authored, not clamped.** `Terrain.clamp_edges`
   raises a uniform rim, which on a map walled on all four sides reads as a
   rectangular box - and on this map the boundary is the most-looked-at thing
   from every high terrace. `region._close_world` replaces it with a ridged
   wall on an irregular foot. The reachable footprint is unchanged.

5. **Relief is 0 to about 195 m**, far steeper than Amberwood's 0 to 100. This
   is a mountain hold: the citadel courts stand 84 to 124 m above the lake and
   the peaks go higher. The consequence is 434 grounding discontinuities
   greater than 6 m, which are cliffs and terrace faces and are expected.

6. **Elevated decks own their server cell.** The client grounds actors on the
   highest walk surface below a downward ray and the server grid is flat, so
   the ring, its four causeways, the quay, the docks and the wall-walks take
   their footprint in `collision.bin` at deck height, and the water or ground
   beneath them is not separately walkable. 23 elevated decks are recorded.

7. **A `MeshGroup` declares its own walk surfaces; the placement must not.**
   `Placement.walk_surface=True` renames the node, and the exporter then
   prefixes every part of the group with `Walk_`, including roofs and domes.
   Groups built with `add_walk` are therefore placed with the flag off. Getting
   this wrong put the orrery's walk surface on top of a gilded dome 18 m above
   its terrace. Only the east stair, which is a bare mesh that is entirely a
   walk surface, sets the flag.

8. **Snow is an altitude, not a texture.** The snow line is 150 m with a narrow
   noise band, and the two glaciers are confined to the northern cirques above
   128 m. An earlier pass with the line at 104 m put snow patches across the
   civic terraces and made a stone city read as a ski slope.

9. **Trees are an alpine belt, not a forest.** Spruce take the turf benches and
   the gentler scree between 2 m and 118 m, and stop well below the snow. The
   region is stone; the vegetation is there to break up the slopes, not to
   cover them.

10. **`collision.bin` height bytes clamp at 63.** The legacy six-bit field
    cannot express 195 m of relief. The grid is authoritative for walkability;
    the Godot loader takes elevation from the rendered walk surfaces, not from
    this file. The encoding datum is recorded in `world.json`.

11. **The server's generated map is a traversability grid, not a height copy.**
    `generate_nymara_maps.py` synthesises its own heights procedurally. Its
    dimensions and arrival now match this package; its elevations do not, and
    are not meant to.

12. **Tangents are not exported.** Godot's glTF importer generates them for
    normal-mapped materials, and shipping them would add sixteen bytes a vertex
    to a package already dominated by vertex data.

13. **The reduced package is a second GLB, not a runtime LOD switch.**
    `world-lod2.glb` carries far-tier vegetation only and no ground clutter.
    Nothing in the current Godot loader selects between them.

14. **Every name is a placeholder.** No authoritative written description of
    Mirrorhold was available to this build, and none of the names in
    `world.json` should be treated as lore. "The Drowned Crown" for the ring is
    taken from the interior map id the client registry already points at; the
    rest are invented to fit the concept art.

15. **Population markers are metadata.** NPCs, creature groups, harvestables
    and portals are recorded as positions carrying `"authority": "server"`.
    Nothing dynamic is baked into the static mesh.

16. **The intact detail board is not in the repository.** The committed
    `references/00-concept-detail-board.png` is the truncated 786,446-byte file
    every region package ships. The panel-level work in this build was done
    from an intact copy supplied in conversation, which could not be written to
    disk. The comparison sheet therefore compares against the truncated board,
    whose bottom row does not decode. See `validation-report.md`.


## 2026-09-07: Sanctuary approach and cellar addresses

The isolated Four Gates crossing is on the southern shore. Both northern
passes were already connected in the native grid. The new Sanctuary bridge
crosses the lake through the colonnaded island, keeping the citadel above the
player's forward view. Its northern arm meets the quay road; the shorter east
and west arms are fishing piers with skiffs and crates.

The Lens Vault threshold is below and west of the orrery platform, the cistern
threshold is beside the fountain court, and the Stair Cellars open at the foot
of the town. Their previous positions were display-landmark centres, including
the middle of the fountain and the armillary mount. Each now has a visible
stone entrance, an apron and an approach drawn by the region.

The information point, bank, crafting station and trainer share the south
side of the fountain court. These services remain server-authored world
objects, with positions constrained by the package's contentLayout.

These changes reuse the existing pale masonry, marble, slate and carved wood.
The common routecraft module supplies continuous decks, annular walking floors
and cellar entrances. No surface classes or external assets were added.
