# Grey Moors — modelling assumptions

Everything here is a decision that was not forced by the concept art, the
runtime contract or an existing file. Where something is a guess, it says so.

## Extent and coordinates

**576 m x 576 m at one metre per tile, arrival at server (174, 174).** Not an
assumption so much as a convention: Amberwood, Crownwater, Whitehorn Range,
Amethyst Barrens and Mirrorhold are all authored this way, and the placeholder's
192 m would not hold the aerial's composition at a legible scale. It requires a
server-side change, which is made on `feature/grey-moors-96-server-map` in
`eloria-server`.

**The composition is written in the placeholder's 192 m design space and scaled
by `region.SCALE = 3.0`.** Changing the extent is one constant, not a rewrite.
Distances between places scale; the places themselves are sized by
`region.LOCAL = 1.5`, so a stone circle is sized by the stones standing in it
rather than inflating with the map.

**Design space maps to the aerial concept linearly.** Design `(x, z)` maps to
the 512 px painting as `px = (x + 58) * 512 / 192`, `py = (z + 134) * 512 / 192`.
Every anchor in `region._DESIGN_ANCHORS` was read off the painting that way.

## Neighbours — corrected, not assumed

An earlier pass of this package invented four neighbours because no region's
`world.json` declares a portal to Grey Moors. That was wrong: the server's
`config/eloria/maps.txt` is the authoritative statement of adjacency, and it
gives Grey Moors exactly **two** neighbours — `sunmane_steppe` on the west edge
and `westhaven` on the east. The package now ships those two and no others, at
the waygate tiles that file names, rescaled from the 192-cell grid to this
region's 576-cell one the same way Whitehorn Range's were: `(6, 58)` and
`(110, 58)` become `(18, 174)` and `(330, 174)`.

There is no declared northern or southern neighbour. None is invented.

## Height band

**The whole walkable surface is authored inside the server's six-bit height
byte.** The ELM encodes `elevation = byte * 0.2 - 2.2`, which spans -2.0 m to
10.4 m. A low wet moor is the one Nymara biome that fits that honestly, so the
bog sits near 1.2 m, the moor near 3.6 m, and the crown of the Great Barrow near
9.6 m. **2.95% of walkable cells still saturate**; those are the shoulders of
the closing rim, and they are the only places a player can stand where the
server's idea of the height is not the real one.

The rim is deliberately cut narrow relative to its height so its flanks exceed
the collision slope limit and it is scenery rather than reachable ground. A
wide, gentle rim was walkable and put a tenth of the reachable surface over the
ceiling.

## Barrows are terrain

**A barrow mound is a terrain dome, not a mesh.** The client grounds actors with
a downward ray against meshes carrying the navigation prefix; a dome placed as
geometry over ground that is still there means a character walks *inside* the
hill. So `region.build_terrain` raises each mound, `assign_surfaces` paints it
`BARROW_TURF`, and `moorcraft.barrow_portal` supplies only the stonework cut
into its face. The same reasoning puts the peat cuttings' stepped banks on top
of a terrain terrace rather than replacing it.

## Bog and water

**Bog is ground you wade; only the deep middles are blocked.** Each basin gets a
water skin from `moorcraft.bog_pool_skin` and a blocked disc at 86% of the
pool's radius. The margins stay walkable. This is a reading of the concept, in
which figures stand in the shallows and the deep parts are bridged; a different
reading — bog wholly impassable — is equally defensible and is one blocked-disc
radius away.

**Bog water is opaque, the sea is not.** Peat stain kills every ray that enters
it, so `grey_bog_water` is an opaque near-black mirror rather than a BLEND
surface; a transparent one over a carved basin only showed the basin.

**The bay was widened after the first pass.** It originally covered 2.6% of the
playable area and the "coastal panorama" capture looked down a drain channel.
It is now 5.8%, which is nearer the wedge of teal the aerial shows in the
south-west corner.

## Toolkit additions

This region needed capability the toolkit did not have. Per the production
guide, it was **added to `_toolkit/`, not forked**:

| file | what was added |
| --- | --- |
| `amberwood/terrain.py` | surface classes 23–27: `HEATHER_MOOR`, `PEAT_BOG`, `CAUSEWAY`, `BARROW_TURF`, `MOOR_TRACK` |
| `amberwood/textures.py` | 14 `grey_`-prefixed recipes, and `_bleed_into_alpha` |
| `amberwood/materials.py` | the matching specs, plus `grey_moor_track` |
| `amberwood/moorcraft.py` | new module: the whole moor kit |

Everything is appended, never inserted or reordered, because a region pins the
material set it embeds by name and reordering `materials.SPECS` would rewrite
another region's GLB.

Two notes on the block allocation. `terrain.py` reserves classes in blocks of
four per region and names 19–22 for Crownwater; Grey Moors took **23–27, five
rather than four**, because it needs a worn track distinct from its laid
causeway and reusing the generic `PATH` would have put Amberwood's amber leaf
litter down the middle of a moor. `MOOR_TRACK` reuses the toolkit's existing
`packed_earth` texture under a tinted material rather than adding a recipe.

`_bleed_into_alpha` is general and the toolkit's own `foliage_atlas` and
`undergrowth_atlas` would benefit from it, but they are pinned by packages
already built against them, so it is applied only to the new atlas.

## Names

**Every place name in this package is a placeholder.** The authoritative written
descriptions for Nymara were not available in this session, exactly as they were
not available to Amberwood's. "The Great Barrow", "The Hanged Oak", "The Court
of Standing Stones", "Warden of the Great Barrow", "Widow of the Last Croft" and
the rest are invented to be replaceable. The landmark *ids* are stable and
mechanical (`grey-barrow-0`, `grey-stone-ring-3`) so renaming is a display-string
change, not a data migration.

The interior doors target `maps/nymara/grey_moor_barrows.elm`, which is a real
planned map — `server-collision/grey_moor_barrows.bin` and
`interiors/grey_moor_barrows/` both already exist. That interior is **not built
by this package** and is out of scope for this branch.

## Inventory

The QA brief at `eloria-assets/qa/regions/grey-moors/README.md` gives counts that
agree with the painting, so they are honoured: six barrows, eight standing-stone
groups, eight boardwalks, four crypt entrances, six abandoned cottages, ten dead
trees, five ritual shrines. The painting adds what the brief omits and this
package builds it too: six broken towers on the skyline, four peat workings,
three causeway bridges, and the waymarkers and cairns that make the track web
legible from the air.

## Environment

The manifest's `environment` block describes permanent overcast: a weak
directional key, a strong ambient term, saturation below 1.0, and low fog. That
is a reading of the concept, which has no sun in it. It is also what
`source/views.py` uses for the offline captures, so the two agree.

**The real client captures do not use it.** `_toolkit/godot_capture.gd` lights
every region the same way on purpose, so regions can be compared with each
other. The frames in `references/client-captures/` are therefore correct
geometry and materials under *standard comparison light*, not under this
region's authored weather. Judge silhouette, scale, placement and material from
them; judge mood from the offline captures and from the manifest.


## September 2026 layout revision — current assumptions

This section supersedes the historical adjacency, height and capture notes
above. CONTINENT.md and region-connections.json are the authoritative graph:
Westhaven, Crownwater, Amberwood and Manymouth Delta are the four neighbours.
The historical east-waygate id is retained for the ferry, now placed on a real
jetty in the south-west cove rather than on the eastern ridge.

The surviving crofts remain ruins. One low, open working refuge near the
arrival supplies dry service ground for the peat road; it uses the existing
drystone, bog timber and turf-roof palette. A holding pen, fuel stack and lit
road posts explain why the shopkeeper, chandler, smith and drover gather here.
The client draws the actual services from server records.

The Great Barrow keeps a taller terrain mound and a stone crown. A side track
climbs its shoulder, leaving the lower entrance aligned with the avenue.
The old hard court has been reduced so it no longer cuts a broad flat shelf
through the mound. The coastal shrine and beacon stand above the actual shore.

Wet crossings follow the routes and survey both bank heights. Pools retain
their pre-road water levels, walking skins have shallow rebates beneath them,
and the distant backdrop is clipped out of the playable terrain. The three
collision corrections encode full precision after each raw build.

The manifest sun now points downward. Offline views use the moor's overcast
preset, including deck cameras; Godot review frames use --environment=manifest.
No material class was allocated and no imported asset was used.
