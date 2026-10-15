# GLB world runtime

The runtime loads every world through `WorldLoader`: JSON validation, native Godot glTF scene generation, declared collision, then gameplay systems. Four Gates has no engine special case.

## Package

A package contains `map.glb` and a sibling JSON manifest matching `world-manifest-1.schema.json`. GLB owns visual hierarchy, meshes, materials, skins, and authored animation. JSON owns stable gameplay identifiers and metadata.

During repository development, the Godot project is a sibling of `eloria-assets`. Call the loader with an absolute path produced from:

```gdscript
ProjectSettings.globalize_path("res://../eloria-assets/maps/four-gates-city/four-gates-city.json")
```

Export packaging must copy approved world packages into the exported content directory without rewriting the GLB.

## Coordinates

Godot is Y-up, metres, right-handed, north = -Z. Server `(x, y)` tiles map to Godot `(x * metresPerTile, elevation, -y * metresPerTile) + origin`. Conversion is exclusively owned by `CoordinateAdapter`.

The registry supplies the verified development binding for Four Gates: one metre
per server tile, server origin `(360, 360)` - the centre of the 720-tile server
grid, which is the plaza - authored walk surface Y=31 with
an actor baseline of 31.15 to prevent terrain z-fighting, and
inverted server Y. Server IDs `maps/startmap.elm`, `startmap.elm`, `four_gates`,
`four-gates`, and `maps/four_gates.elm` resolve to the same canonical entry. The bare
`four_gates` alias is required by the development-server state observed in the 2026-08-27
runtime capture; without it the renderer retained only the blue fallback world.

The minimap and full-map SubViewports share the gameplay `World3D` and each TextureRect
is bound directly to its corresponding live viewport texture. The supplied compass and
HUD atlas regions are opaque, so they are never placed above either map render.
Each TextureRect also owns an explicit `gui_input` route. A left click is scaled into its
SubViewport coordinates, projected through the matching orthographic camera, converted
by the shared `CoordinateAdapter`, and sent as `MOVE_TO` (or `RUN_TO` while Shift is held).
The shared world is resolved from `WorldRoot.get_world_3d()` after it enters the scene
tree; reading `SubViewport.world_3d` directly can return null even while its Node3D
children resolve an inherited world. Picking and terrain rays use the resolved, guarded
reference.

The inline navigation polygons are converted into static concave collision shapes at
load time. Actor X/Z remains server-authoritative; presentation Y is ray-projected onto
that navigation surface after the first physics frame and after subsequent actor state
updates. This prevents player models from being buried by local terrain elevations while
leaving server tile authority unchanged.

## Collision and navigation

Collision node names are resolved recursively and receive trimesh static bodies. This is appropriate for static authored structures; frequently updated or simple props must use primitive collision declarations in a subsequent schema revision. Navigation metadata remains separate and will be used to construct/bake `NavigationRegion3D`; visual meshes are never implicitly considered walkable.
