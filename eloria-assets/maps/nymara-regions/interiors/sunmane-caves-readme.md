# Sunmane cave interiors - production packages

Two explorable interiors sit behind cave mouths modelled on the Sunmane Steppe
surface map. Each is a complete schema 1.1 package in its own directory, so the
destination exists client-side and only the map registration is still owed to
the server.

| Directory | Server map id | Entrance on the steppe |
|---|---|---|
| `sunmane_wind_caves/` | `maps/nymara/sunmane_wind_caves.elm` | server `(128, 175)`, south face of the eastern butte |
| `sunmane_crystal_hollow/` | `maps/nymara/sunmane_crystal_hollow.elm` | server `(182, 154)`, Amethyst badland |

The other two cave mouths on the surface - the drovers' shelter and the eastern
adit - are modelled shelters with a closed back, not doorways. They have no
interior and need no registration.

## What is in each

**Sunmane Wind Caves** is a wind-scoured limestone system the Orun drovers use:
an entrance hall off the desert road, a tall wind gallery, a drovers' camp with
a cart and picket, a whistle shaft nine metres to the roof, and a still pool at
the bottom of the system. Timber sets hold the worked passages open, braziers
light the chambers, and bleached bone lies where animals have sheltered.

**Amethyst Crystal Hollow** is a geode opened by prospectors on the badland
margin: an adit mouth, a wide geode chamber banked with amethyst, a violet
gallery, a prospectors' cut with their camp, and a shard store. The crystal is
the same family as the badland's surface clusters, darker underground and softly
emissive, and three of the largest banks are declared as light markers.

## How the cavern is built

The shell is not a box with a ceiling on top. `maps/nymara-regions/sunmane_steppe/source/caves.py` samples a
clearance field around a network of chambers and passages; the roof height is
driven by that field, so the roof comes down to meet the floor at the walls and
the cavern reads as one continuous piece of rock. How quickly it comes down is
scaled by the local volume, so a narrow passage closes over a short distance
while a big chamber's roof rises gradually - a single fixed distance left the
small rooms too low to stand in. The outermost samples are tied down to the
floor, which is what stops the cavern ending in a ring of vertical facets
stepping along the sample grid.

The floor carries the `Terrain_` prefix, so the client's grounding raycast lands
on it. The roof and the wall skirt carry structural collision, which is what
keeps a player inside the system.

## Runtime files

| File | Purpose |
|---|---|
| `world.glb` | Self-contained glTF 2.0 interior: cavern shell, formations, timber, props, embedded PBR textures |
| `world.json` | Schema 1.1 manifest: bounds, coordinate transform, spawn points, chambers, collision, navigation, landmarks, interactives, environment, lighting markers, minimap transform, exit portal |
| `minimap.webp` | Rendered orthographically from `world.glb` with the roof hidden, the way a floor plan omits a ceiling |
| `world.glb.validator.json` | Khronos glTF-Validator report |

## Lighting

Interiors declare a `cave-interior` environment profile: no sky contribution,
dense short fog, and a low fill, so the braziers and the crystal carry the
lighting. The lights themselves are declared as `lighting.markers` - named
positions with a colour, an energy hint and a range hint - and the client binds
them through `src/world/light_marker_binder.gd`. The package therefore depends
on no glTF light extension.

## Rebuilding

```sh
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/caves.py                 # both interiors
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/caves.py --system sunmane_wind_caves

godot --headless --path godot-client --script res://tests/integration/sunmane_caves.gd
xvfb-run -a godot --path godot-client --rendering-driver opengl3 \
  --script res://tests/integration/sunmane_caves_rendered.gd
```

All geometry and textures are original Eloria project work under CC-BY-4.0. No
third-party asset packs and no Eternal Lands assets were used, converted or
traced.
