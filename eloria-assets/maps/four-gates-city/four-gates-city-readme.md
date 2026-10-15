# Four Gates City GLB + JSON package

Production-oriented textured environment derived from the supplied Four Gates references. The square aerial controls layout; perspective images inform silhouettes and materials. Asset version 0.9 retains the art-directed material/skyline pass and adds a gameplay-distance detail layer: integrated gate ornament, radial civic gardens, bespoke broadleaf planting, lived-in market dressing, residential balconies, and rocky waterfall edges.

## Scene conventions

- Meters, right-handed, +Y up, -Z north, origin at the central plaza.
- Defensive-ring diameter: 720 m. Authored walking terraces: approximately Y=24–36 m. Water: Y=-2 m. Lowest useful terrain: Y=-40 m.
- Named hierarchy, interaction parts, collision proxies, markers, PBR materials, and stable JSON identifiers are included.

## Loading

Load `four-gates-city.glb` with any glTF 2.0 loader, then parse `four-gates-city.json`. Resolve metadata `node` fields by exact GLB node name. Atlas rectangles are baked into primitive UVs and require no optional glTF extension. Unknown extras and JSON extensions should be ignored safely.

Rebuild from the compact checked-in blockout seed with `python3 eloria-assets/tools/rebuild_four_gates_glb.py`. Run `python3 eloria-assets/tools/validate_four_gates_package.py` after any binary or metadata change; it rejects truncated containers, out-of-bounds buffer views, undecodable embedded images, duplicate node names, and stale JSON node references.

## Materials and effects

The package uses 19 metallic-roughness materials. An art-directed three-map citywide atlas covers general assets, while a dedicated four-map landmark family provides base color, tangent normal, packed ORM, and emissive detail for monumental stone, bronze trim, foundations, and blue-energy inlays. Primitive UVs directly address their material rectangle, and normal derivation is isolated per tile so colors and normals never bleed across material cells. Source and derived maps are included under `textures/`.

## LOD, collision, navigation

The main GLB contains gameplay-distance LOD1 plus `_LOD0` landmark overlays and 267 `Detail_` close-detail nodes. `four-gates-city-lod2.glb` is a resource-pruned distant sibling with 663 active nodes, 26 meshes, 17 materials, overview textures capped at 512 px, no animations, and no close-detail overlays. Low-poly `COLLISION_*` nodes remain separate. Navigation includes ten conservative convex walkable polygons, monument and wall exclusions, agent dimensions, and an off-mesh sanctuary link. New civic planting is diagonal to the axes, and the generator enforces a 30 m half-width visual-clearance contract around principal roads.

## Animation

Seven optional standard glTF clips are embedded: five portcullis open/close clips and pulse clips for the sanctuary beacon and plaza crystal. Static initial transforms remain correct when animation is ignored.

## Portable gameplay package

The retired `package_four_gates_world.py` built a portable package under `runtime/maps/four_gates/` for the C client; the map the Godot client loads is `eloria-assets/maps/four-gates/`, built by `eloria-assets/tools/four_gates/`. That portable package included the authored GLB, terrain- and building-aware EWCG collision, convex navigation data, portal hooks, NPC/creature/harvest markers, five gameplay regions, eight waterfall effect stacks, and a matching four-mip `four_gates.dds` minimap. The client applies manifest-driven water UV scrolling and landmark-energy pulsing; static geometry remains the fallback.

## Reference coverage

`references/` contains 20 indexed verification views and a labeled 20-view contact sheet.

## Known limitations

This is a textured gameplay environment with authored modular landmark geometry, landmark UVs, sculpted concentric terrain and shoreline transitions, building blockers, waterfall effect locators, an alpine skyline, concept-aligned close detail, and a resource-pruned LOD2 sibling. Water, foam, mist, and energy remain understandable as static glTF geometry/locators when effects are disabled. Remaining work is primarily bespoke district UVs plus production turbulence, depth-fade, refraction, and particle shaders.
