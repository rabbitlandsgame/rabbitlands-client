# Mirrorhold coverage map

What occupies the region and where, so a reviewer can find a thing and so the
empty parts are stated rather than discovered.

Coordinates are Godot metres. North is -Z. The playable footprint is
x in [-174, 401], z in [-401, 174]; server tile (174, 174) is the origin.

## Bands, north to south

| Band | z range | What is there |
| --- | --- | --- |
| Ice and peaks | -401 to -280 | Two glacier cirques, bare rock, the north wall. Not settled; the north portal to Whitehorn crosses at (336, 558) in server tiles. |
| Summit citadel | -280 to -190 | The orrery on its open drum at 124 m, the high court at 112 m, the great court at 98 m, two lens towers, the rose gallery. |
| Gate and upper terraces | -190 to -120 | The gate wall and its two wings at 84 m, the mirror basins, the north overlook pavilion, the upper falls terrace at 70 m. |
| Civic descent | -120 to -20 | The fountain plaza at 58 m, the canal terraces at 46 m with five channels and three falls, the aqueduct on the east shoulder, the stair town on the west shoulder in five shelves from 17 m, the east stair. |
| Lake shore | -20 to +40 | The north quay and its three docks at 4.5 m, the arrival terrace at 8 m, shore rows east and west, the west gorge. |
| The lake | +40 to +160 | Water at y = 0 over a floor at -11 m. The ring at its centre on four causeways, two islets, the south watch. |

## Named places

Sixteen principal landmarks and eighteen satellite sites are recorded in
`world.json`. The principal ones:

| id | What |
| --- | --- |
| `orrery` | The mirror-sphere in its armillary mount, the region's summit landmark |
| `citadel` | The observatory citadel's high court |
| `gate` | The lens gate and its wall-walk |
| `rose-gallery` | The blue rose window and its gallery |
| `lens-tower-west`, `lens-tower-east` | The two observation towers |
| `mirror-basins` | The still terrace pools the region is named for |
| `plaza` | The fountain plaza |
| `canal-district` | The canal terraces and their falls |
| `aqueduct` | The meltwater aqueduct |
| `overlook` | The north overlook, the view back up to the peaks |
| `cliff-town` | The stair town on the west shoulder |
| `east-stair` | The east ascent |
| `ring` | The colonnaded island, "The Drowned Crown" |
| `harbour` | The north quay |
| `south-watch` | The tower on the south shore |

Satellites: `west-bench`, `west-shrine`, `gorge-head`, `lower-terrace`,
`mid-bench`, `cistern-yard`, `lens-works`, `east-bench`, `east-post`,
`north-post`, `upper-shrine`, `quarry-shelf`, `lake-north`, `lake-east`,
`south-shore`, `west-shore`, `far-south`, `far-west`.

## Movement

Four graded routes: the great road from the arrival terrace up to the citadel
gate, the shore road round to the harbour, the stair-town road on the west
shoulder, and the east ascent past the aqueduct. Roads are paved surface class
and carry crystal lamps and retaining walls where they cut the slope.

Four edge portals (Whitehorn north, Westhaven south, Amethyst Barrens east,
Crownwater west) and two interior entrances (`drowned_crown` at the ring,
`resonant_vault` at the orrery). The server owns the transitions.

## Where the region is thin

Stated rather than left to be found:

- **The east quarter, roughly x > 300, is sparse.** It carries the aqueduct,
  the east bench and two posts, but between them it is bare rock and scree. The
  aerial concept has built terraces across that ground.
- **The far south, z > +120 beyond the lake, is largely empty** apart from the
  south watch and the south shore row.
- **Overall built density is below the concept.** The painting shows the whole
  middle band terraced and walled; this build has the citadel, the civic
  descent, the stair town and eighteen satellites, which is a coherent region
  but a quieter one.
- **No interiors.** The two interior entrances point at map ids the client
  registry already carries; the interior packages themselves are not part of
  this work.


## 2026-09-07 access coverage

The Sanctuary Road now joins the city through the ring and North Quay.
All five exterior crossings and all three cellar thresholds must be reachable
from the default arrival in both the client grid and the server export.
Views 21 and 22 cover the shore join and the bridge-to-ring join at player
height; views 23-25 cover the three visible cellar entrances.

The plaza's southern apron groups the information point, storage, crafting
and training services. The cellar lane descends from the western arrival,
turns below the houses, and ends in a court with room to gather.

The wider cliff town, mountain silhouette and quarry access remain candidates
for further layout work. This pass does not claim that their existing hard
terraces or every remote resource have been redesigned.
