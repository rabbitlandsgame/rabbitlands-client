# Sunmane Steppe modelling assumptions

Recorded so a reviewer can tell a deliberate choice from an oversight.

## Coordinates and scale

- One metre per server tile, matching the entry already committed in
  `godot-client/data/maps/registry.json` and every sibling Nymara region. The
  source ELM's height grid is 192 x 192, which with the datum at `(58, 58)`
  makes the addressable band Godot X -58..133 and Z -133..58. The authored
  region is a 280 m square centred on Godot `(36, -36)` - offset from the datum,
  not centred on it - so that the band sits inside it with the desert, the
  badland and the mountain front beyond. Everything outside the band is scenery
  a player can see but never stand on, which is what makes it a natural world
  boundary; the builder refuses to emit an interaction on an unreachable
  landmark, and the package validator asserts it.
- The datum `(58, 58)` sits on the ceremonial crossroads inside the palisade,
  so an arriving player lands in the settlement rather than outside it.
- Travel distances: about 190 m across the playable band, so crossing the
  region on foot is a little over a minute at normal walking speed. The desert
  road, the mountain approach and the east pass carry that distance into the new
  ground rather than adding a second settlement to fill it.

## Grounding

- Every terrain chunk carries the `Terrain_` prefix, so the client's
  navigation-surface layer covers the whole landform, including the shallow
  shelf below sea level and a skirt that extends past the declared bounds.
  A grounding raycast can therefore never miss and fall back to
  `walkingHeight`, which is the failure that drops an actor under the map.
- `walkingHeight` is nevertheless set to the arrival plateau rather than zero,
  so even a miss would place an actor above the landform rather than inside it.
- Water is not walkable by construction, but it is still covered by the
  navigation surface. Movement is server-authoritative - the client only
  converts a picked point to a server tile - so making the surface continuous
  is the safe choice and does not grant sea access by itself.

## Structures on terrain

- Anything with a real footprint gets a levelled building pad in the
  heightfield, with a graded skirt. Without pads a wide structure has to be
  sunk to the lowest point under it, which buried the central hall by 2.2 m in
  an earlier pass.
- Pads are applied before the stream, waterholes and road corridors are cut, so
  water and routes are carved into levelled ground rather than filled in by it.

## Materials

- Twelve tileable PBR families with world-scale UVs, of which the surface
  package embeds ten, rather than one atlas with
  baked UVs. World-scale UVs keep texel density uniform across terrain,
  architecture and props without per-asset bookkeeping, and tiling families
  avoid the mip bleed an atlas suffers at distance.
- The nine terrain classes tint one shared detail map through material
  base-colour factors - the ground map for grassland, road and sand, the stone
  map for shore rock, badland and mountain scree. That keeps a single texel density and avoids
  splat seams; glTF clamps `baseColorFactor` to 0..1, so the ground map is
  authored bright and tinted down.
- Only core glTF 2.0 is emitted. No extensions are used, so the client's stock
  `GLTFDocument` needs no change.

## Terrain shading and projection

- Ground is textured by projecting the map straight down, which is right for
  anything a player walks on and wrong for a cliff: past about 63 degrees one
  texel covers metres of rock face. A quad steeper than that is textured on
  whichever vertical plane faces it instead, so texel density stays even and
  strata run across the face the way bedding does.
- Shading is smooth except where the smoothed normal genuinely opposes the face
  it belongs to, which happens where the heightfield folds; there the quad is
  faceted, as one facet rather than two, so the halves of a quad are not lit
  differently.
- Both decisions are made from the quad's own normal, not from a threshold on
  how much it drops. A relief threshold flips neighbouring quads between two
  treatments all along a hillside, and the alternation renders as a
  chequerboard - it was the most visible procedural artifact this terrain had.
- Neighbour lookups in the road smoothing and the slope limiter replicate the
  edge rather than wrapping. `np.roll` wraps, which averaged the northern edge
  against the southern one 38 m below it and dug a trench around the entire map.

## Cave interiors

- The two interiors are separate map packages, not rooms inside the surface
  GLB. A cave mouth on the surface is a real recessed throat closed at the back,
  so a player can never see into an empty shell, and the interior is reached
  through an ordinary map transition.
- The cavern shell is a clearance field rather than modelled walls: the roof
  height is driven by how far inside the cavern each sample lies, so the roof
  descends to meet the floor and the wall is the same continuous surface. The
  rate is scaled by the local volume, because one fixed distance made small
  chambers too low to stand in.
- The floor takes the navigation prefix and the roof takes structural collision.
  Containment is therefore a consequence of the shape, not of an invisible wall:
  where the roof has pinched down, a player-sized body does not fit.
- Cave surfaces use a purpose-authored `cavern` material family. The surface
  `stone` family carries worley pitting, which over a chamber floor tens of
  metres across repeats into a spotted pattern.

## Tangents

- Tangents are emitted for exactly the primitives whose material carries a
  normal map. Emitting them everywhere wasted about a fifth of the package on
  data no renderer reads; omitting them where a normal map exists makes the
  tangent frame renderer-dependent and the Khronos validator warns about
  portability. Deciding per primitive satisfies both, and the package validates
  with zero warnings.

## Roads

- The caravan roads are terrain, not an overlaid surface: the landform grades a
  corridor and classifies it as `caravan_road`. There is therefore no road
  decal to z-fight with the ground. Roads are dressed with wayposts, pennants
  and kerb stones instead.
- The one authored ground overlay is the crossroads plaza, lifted 0.11 m and
  following the heightfield, on flat pad ground where that clearance is safe.

## Population

- Livestock are scenery, not networked actors: no actor id, no collision, and
  deliberately not baked into the world mesh, where they would have become part
  of the collision surface. They are declared in the manifest and instanced by
  `AmbientPopulation` at runtime.
- NPCs, harvestables and hostile creature spawns are the server's to own. They
  are recorded under `runtimePopulation` with the hooks from
  `regions-connections.json` so the server profile has an exact list.
- The horses are new assets. The shared creature generator builds every animal
  from the same sphere-and-cylinder blank, which cannot produce a horse, so the
  geometry is authored to equine proportions on the same rig, with the same
  joint names, animation names and attachment points the client already
  expects.

## Known simplifications

- Grass is opaque tapered blade geometry rather than alpha cards, so there is no
  alpha sorting cost and no cutout artefacts, at the price of a sparser sward
  than a painted concept implies.
- Ambient animals do not wander; they idle in place with offset animation
  phases. Movement belongs to the server-driven actor path.
- Human inhabitants are not placed by the client. The concept art's crowds are
  server-owned NPCs, listed in `runtimePopulation.npcs`.

## September 2026 circulation and content

The coordinate datum (58, 58) remains the world origin; it is not the current
server arrival, which is (79, 37). source/layout.py owns explicit route
stations, bridge banks, building courts, grain plots and content habitats.
The beck has a surveyed downhill water line. All three bridges use the shared
sloped_boardwalk recipe and only their decks enter the walking bucket.
Waterholes use clipped shared watercraft geometry rather than square cells.

The collision build must use the same building pads as the render. Structural
triangles stored in world space are compared with the terrain beneath them,
not their node's translation, so palisades remain solid. Geometry supplies
the standing surface; the three correction passes restore its usable grid.

Client resource markers retain their stable IDs and use short display names;
the existing global server identity Iron Ore is retained. A region rebuild
reapplies server-owned tile posts from source/server-content.json against the
actual LOD's walk triangles. Build timings stay in standalone statistics and
are omitted from world.json so the package is reproducible.
