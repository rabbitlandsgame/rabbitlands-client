# Whitehorn Range coverage map

What exists where, and which concept source each place answers to. Design-space
coordinates are the 192 m authoring space; world coordinates are those times
`region.SCALE` (3.0). North is `-Z`.

## Composition spine

The region is read from the aerial as a bowl opening south. The pilgrim road is
the spine and every detail-board panel sits on or beside it:

```
  south (low, inhabited)                        north (high, glaciated)
  Whitehorn Gate -> cairn switchbacks -> gorge + rope bridge -> frozen
  cascade -> temple stair -> Glacier Temple -> glacier head
```

## Places

| Place | Design (x, z) | World (x, z) | Ground | Source |
| --- | --- | --- | --- | --- |
| Arrival / spawn | (0, 0) | (0, 0) | 17.6 m | aerial, south approach |
| Whitehorn Gate | (-4, 28) | (-12, 84) | — | panel 1 |
| Gate shrine | (-11, 33) | (-33, 99) | — | panel 4 |
| Lower cairn field | (6, 13) | (18, 39) | — | panels 1, 5 |
| Pine shelf | (-26, 18) | (-78, 54) | — | aerial, lower slopes |
| South camp | (24, 22) | (72, 66) | — | aerial |
| Gorge (west→east) | (-34,-20)→(108,-30) | — | floor -26.7 m | aerial |
| Rope bridge (lower) | (17, -25) | (51, -75) | deck 16.9 m | panel 3 |
| Rope bridge (upper) | (62, -33) | (186, -99) | deck 32.6 m | panel 3 |
| Bridge watch | (30, -18) | (90, -54) | — | aerial |
| Ice cave | (-38, -14) | (-114, -42) | — | panel 6 |
| Cairn ridge | (-29, -68) | (-87, -204) | — | panels 5, 9 |
| West watch | (-44, -44) | (-132, -132) | — | aerial |
| Frozen cascade (lower) | (26, -58) | (78, -174) | 20 m fall | panels 3, 8 |
| Frozen cascade (upper) | (44, -74) | (132, -222) | 15 m fall | panel 8 |
| Temple stair | (34, -80) | (102, -240) | — | panels 2, 9 |
| Temple forecourt | (34, -91) | (102, -273) | — | panel 2 |
| Glacier Temple | (34, -103) | (102, -309) | deck 70.4 m | panel 2 |
| North shrine | (9, -119) | (27, -357) | — | panel 4 |
| Glacier head | (34, -112) | (102, -336) | — | aerial |
| Mine portal | (96, -46) | (288, -138) | — | panel 7 |
| Mine yard | (89, -40) | (267, -120) | — | panel 7 |
| East camp | (110, -6) | (330, -18) | — | aerial |
| Overlook | (74, 9) | (222, 27) | — | panel 9 |
| East shrine | (118, -64) | (354, -192) | — | panel 4 |

## Population

| Kind | Count | Placement rule |
| --- | --- | --- |
| Cairns | 177 | along every route at fixed spacing, alternating side; dense clusters at the cairn ridge, lower bend and west watch |
| Waystones | 17 | at shrines, the cascade foot, the temple forecourt and the ridge |
| Seracs | 77 | along the authored glacier route, not by surface lookup, so they follow the ice below the snow line |
| Conifers | 870 | below snow line + 16 m, slope < 0.85, on snow or turf, density-gated |
| Rock clusters | 759 | anywhere not built, paved or blocked |
| Landmarks (metadata) | 14 | — |
| NPC markers | 6 | server authority |
| Harvestables | 30 | ore, ice, herb, wood; server authority |
| Portals | 4 | temple interior + three edges pinned to server tiles |
| Spawns | 3 | arrival, temple forecourt, mine yard |

## Surface classes in use

`Terrain_Snow`, `Terrain_Ice`, `Terrain_Rock`, `Terrain_Trail`,
`Terrain_Paving`, `Terrain_Marble`, `Terrain_AlpineTurf`.

Snow is the base class; rock breaks through where slope exceeds an
altitude-dependent threshold; ice is authored along the glacier route; turf is
restricted to low, sheltered, shallow southern ground.

## Walk surfaces

Only four, all under the `Walk_` prefix: the two rope-bridge decks, the temple
stair, and the temple forecourt deck. Everything else built is structural.

## Coverage gaps

- No interior for the mine or the ice cave; both are facades.
- No settlement. The aerial shows scattered structures rather than a village,
  and none of the ten panels is a dwelling, so none was authored.
- The eastern third of the map is thinner than the west: the mine, its yard and
  the east camp carry it, where the west has the cave, ridge and cairn fields.

## September 2026 layout coverage

The south gate now has the Ration House, repair shelter and grouped services.
Lower Camp, Bridge Watch, High Overlook, East Camp, Mine Yard and Last Pilgrim
Rest have weather protection, fuel or route markers. The eastern haul road
takes the gorge head; the temple road skirts the cascades and climbs in
switchbacks. Both rope crossings have explicit bank surveys and continuous
decks. The western watch's Cascade Cave has an authored mouth and approach.

All 24 departures, 14 NPCs, 59 creature spawns, 55 harvest nodes and 21
interactives are reachable from the gate arrival. The seven formerly isolated
secret entrances now have reachable sites. references/layout-audit contains
the Godot contact sheets; layout-review.md records the final measurements.
