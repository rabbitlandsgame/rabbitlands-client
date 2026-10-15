# Whitehorn inhabited landscape pass

Whitehorn is the second compact region after Amberwood. It tests the same
principles in an alpine landscape and completes a reciprocal forest-to-mountain
view. Its served extent is 396 x 396 metres, down from 576 x 576. Amberwood
remains 384 x 384. Other regions retain their existing dimensions until their
individual design passes.

## Landscape and movement

The lower refuge exists to provision pilgrims and mine traffic. Its shelters
share a gravel court, with stores against the walls and grazing clearings
outside. Conifers collect on sheltered lower slopes. Their crowns retain their
size during compaction, with spacing checked again after placement transforms.

The gorge now has an explicit downstream floor profile rather than the sum of
two deep channel cuts. Two surveyed suspension bridges retain their bank
positions, deck profiles and navigation geometry. The pilgrim road climbs past
icefalls placed against connected ledges. The mine mouth enters a rising rock
shoulder, while the temple stair, court and side walks share a surveyed datum.
The temple's collision follows its podium rather than a circle around the
entire landmark.

Snow, blue ice and exposed rock use quieter regional texture recipes. Formal
marble remains at the temple; ordinary work courts use gravel. The three passes
have visible receiving terrain beyond their road crossings. The Amberwood pair
also includes the neighboring map's ordinary tree silhouettes. Dedicated march
monuments and redundant runtime portal models are omitted, while ordinary signs,
shelters and server destinations remain.

## Rebuild and contracts

Run from the client checkout, with the server checkout and generated map-data
directory supplied explicitly:

```powershell
python eloria-assets/maps/nymara-regions/whitehorn_range/source/rebuild_landscape.py --server ../wt-continent-server --data ../work-output/inhabited-amberwood/eloria-data
```

The wrapper builds exterior/interior sources, refines collision against walking
geometry, builds secret rooms, migrates the server coordinates once, vendors the
collision grids, regenerates served maps, and synchronizes portals and content.
It rejects relocations greater than 12 tiles so an inaccessible post requires a
designed approach. `server_posts.py` persists the authoritative NPC and resource
records for subsequent builds. Package hashes update only this region's three
packages. The continent's required connections, secret keys, species and
resource identities remain intact.

Border views read neighboring packages. Rebuild a changed source region before
its neighbor. Views copy only terrain and ordinary trees, so reciprocal views
never recursively copy one another. After both geometries settle, refresh the
receiving package's metadata and digest with another reproducible build.

## Verification and limits

The final Whitehorn client run completed 16 routes and 229 checks: four refuge
NPC approaches, two bridges, three regional round trips, all seven interior
entrances and returns, the unlocked Cascade Spring, a Peat post and a yak
clearing. Every exterior portal, NPC, resource, spawn and interactive is reachable
from the main arrival under the server's actual climb rule.

Static terrain views provide visual continuity over 140 metres; simulation still
changes at the crossing. They do not stream neighboring actors or services, and
their ground palette is an approximation of the receiving region. Existing
angular seracs and modular shelter/shrine geometry remain stylistic limitations.
The overlap audit retains 43.0 square metres of mostly internal prop and trim
overlap, down from 49.3 before this pass. Runtime surface checks report no missing
ground and 108 height discontinuities, principally cliffs and the blocked rim.

The detailed annotated captures, overview, route records, performance samples,
test results and regional rollout are in
`work-output/inhabited-whitehorn/review.html` at the workspace root.
