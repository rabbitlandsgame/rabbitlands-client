# Crownwater modelling assumptions

The 2026-09-07 layout pass supersedes older statements about shared causeway
length classes, landmark-centred door triggers and random harbour services.
See [layout-review.md](layout-review.md) for the current surveyed routes,
service court, habitat rings, captures and measurements.


Decisions taken where the brief, the concept art and the existing runtime did
not fully determine the answer. Each is a place a reviewer may reasonably want
to overrule the build.

1. **Region extent.** 576 m x 576 m at one metre per tile, matching Amberwood,
   so the server map is 96x96 ELM tiles and the arrival datum is server
   (174, 174). The composition is authored in a 192 m design space and scaled by
   `region.SCALE`, so the aerial concept's layout is preserved rather than
   stretched. `../server-collision/crownwater.bin` is regenerated to match and must be
   loaded server-side.

2. **The lagoon floor is terrain, not a hole.** The client casts its grounding
   ray at *every* server tile, not only walkable ones, so a region that is
   mostly water still needs a continuous surface under it. The heightfield
   covers the whole footprint and sits below sea level across most of it. Those
   tiles ground successfully and are marked unwalkable in `collision.bin`. This
   is why zero grounding misses is achievable on a map that is 74% water.

3. **Islands are plateaus, not domes.** A dome of the right height has almost no
   usable ground - everything but the tip exceeds the walkable slope limit, and
   the first pass came out at 4.7% walkable. The concept's islands are built-up
   platforms behind retaining walls, which is a flat top with a defined edge.
   That reads correctly *and* gives 25.6%.

4. **No world-boundary wall.** Amberwood closes its world with mountain walls
   because it is land. Crownwater's horizon is open water. A raised rim outside
   the playable footprint reads from any elevated camera as a dark slab floating
   at the map edge, which is how the first in-client aerial came back. The world
   is closed by the collision grid instead: water is not walkable, and the
   lagoon floor still grounds every tile, so nothing reaches a void.

5. **Causeways are bridges, and their decks own their server cells.** A flat
   server grid cannot hold two levels, so each deck takes its footprint in
   `collision.bin` at deck height and the water beneath is not separately
   walkable. 84 elevated decks. The terrain gets a level landing at each end and
   nothing in between - grading terrain along a causeway's whole length raises a
   ridge under the water it is supposed to cross, and drags the quay at the far
   end down with it.

6. **Islands are planted, plazas are paved.** Paving whole islands made the
   aerial read as one continuous white slab. In the concept the pale stone is
   the *buildings and their plazas*; the ground between them is green. Paving is
   therefore applied only by the terraces, where something is actually built.

7. **Crownwater's six material recipes are shared and registered at build
   time.** They live in `_toolkit/amberwood/crownmaterials.py`; the region's
   `crownkit` module is a compatibility entry point. `register()` appends
   missing specs in memory before either registrar reads them, preserving
   existing names and IDs. All eighteen texture arrays were compared at
   their default full sizes during the 2026-09-08 promotion and are identical.
   The exterior and Drowned Arcades now use one source for this palette.

8. **The package pins its material set by name.** `only=crownkit.MATERIALS`
   keeps the eleven forest and burnt-country materials Crownwater never
   references out of the GLB - about 3 MB - and makes this region's bytes
   independent of whatever any other region appends to the shared table. A
   build-time guard fails loudly if a kit piece introduces an unpinned material.

9. **`world-lod2.glb` saves bytes, not geometry.** It is 42% smaller but only
   12.9% fewer triangles. The toolkit's reduced package drops vegetation detail
   tiers, and Crownwater is architecture and terrain, not forest. It is worth
   shipping for its half-resolution textures and not much else. Nothing in the
   current loader selects between the two packages.

10. **`collision.bin` height bytes clamp at 63.** The legacy six-bit field
    encodes `byte * 0.2 - 2.2`, so it saturates at 10.4 m. Crownwater's relief
    is modest and most of the map is under that, but the cathedral platform and
    the causeway decks are not. The grid is authoritative for *walkability*; the
    Godot loader takes elevation from the rendered walk surfaces.

11. **Lore names are invented.** No authoritative written region description or
    server name data was available to this build. "The Drowned Crown", "The Tide
    Campanile", "The Sunken Court" and every pavilion name are placeholders
    chosen to fit the concept art, and are expected to be replaced. Each carries
    `"note": "placeholder name"` in `world.json`.

12. **Portals are quays, not roads.** Every land route out of an archipelago is
    a boat, so the four edge portals sit on outer islets and are named as packet
    services. Destinations follow the client registry's map ids; the server owns
    the actual transitions.

13. **Population markers are metadata.** NPCs, harvestables and interactives are
    positions carrying `"authority": "server"`. Nothing dynamic is baked into
    the static mesh.

14. **The sunken court's level is authored absolutely** (-1.90 m), not read from
    the terrain. Panel 7 depends on seeing tiling through clear water; read from
    the lagoon floor it lands wherever the noise and the nearest channel put it,
    which was 8 m down and invisible.

15. **The cathedral is "The Crown Basilica", not "The Drowned Crown".** The
    interior beneath it - `interiors/drowned_crown`, whose concept file names
    Crownwater as its parent - is the drowned palace the basilica was built over.
    Two things could not carry the same name, and the older ruin has the better
    claim to it since its name was given rather than invented here.

16. **A customs house stands on the harbour islet.** The islet had quays, lamps,
    stalls and boats but no building, so `interiors/crownwater_customs_hall` had
    no surface entrance to hang off. It is deliberately the plainest structure in
    the region - ashlar base, plastered wall, verdigris roof - because Crownwater's
    marble is for its monuments and a bonded warehouse is built to keep rain off
    crates.

17. **Four interior entrances are declared on this manifest, and all four lead
    to the same map.** Crownwater's insides share one map with unwalkable
    blackspace between them, as Eternal Lands lays out a region's interiors and
    as `amethyst_barrens_insides` already does here, so the destination is one
    elm and the section is chosen by the spawn id. They are portals of type
    `interior-entrance` sitting on the landmark each belongs to. The server owns
    the actual transition; these are alignment metadata, as the edge portals
    are. See `../interiors/CROWNWATER_INTERIORS.md`.
