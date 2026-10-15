# Biome and object materials

## Editing materials

Open a saved region scene and select its `Terrain` node. In the Inspector,
`base_surface` holds the terrain's base material. Its `texture_preset` dropdown
offers the named textures below; `biome_blend_enabled` opts that region into
the shared natural border blend. The blend spans about 24 m by default. Leave
it off to keep that region on its base texture alone.

An opted-in region can have one secondary material in `biome_palette`. Add or
select a `MapAuthoringBiomePaletteEntry`, choose its `role` (such as woodland,
heath, rock, or snow), then choose the entry's `surface.texture_preset`. The
role uses the continent's existing biome field; it does not add or move
vegetation. Texture, tint, and rotation edits preview on the active region and
selected read-only neighbours. A changed role distribution takes effect in the
refreshed terrain catalog. Neighbour scenes are references; edit their own
scene to change them.

For an individual imported mesh, select its `AssetControl` under the region's
`Assets` node. In `material_overrides`, add or select a
`MapAuthoringAssetSurfaceOverride`; set its `mesh_node_path` and `surface_index`
to identify the target mesh material, then edit its `surface` resource. Choose
`texture_preset` and adjust `rotation_degrees`; its UV scale is in
`source_material` when `show_advanced_materials` is enabled. These choices are
saved per object and do not change the region's terrain palette.

The named preset dropdowns include the ten new albedo choices:

- Ground: Moor peat heather, Delta silt, Coastal limestone gravel, Alpine
  scree lichen, Forest floor moss, and Alpine snow crust.
- Object materials: Weathered limestone masonry, Jade masonry, Marine timber,
  and Reed thatch.

Ground presets use a 4 m repeat scale. Object presets follow the mesh's saved
UVs and authored material scale, which can be adjusted per object. The new
packs contain albedo only. Ordinary preset materials and per-object shaders
may reuse compatible existing ground, stone, timber, or thatch normal and ORM
maps; no new normal or ORM artwork was generated. The blended terrain shader
uses albedo with each surface's roughness and metallic scalars, not normal or
ORM maps. Existing presets and exact object overrides remain available.

## Save, bake, and refresh

Save each changed region scene with **Ctrl+S**. The root region node's **Bake
continent authoring snapshot** button saves the scene and exports its snapshot
for review. The normal continent build reads all registered saved region
scenes; the button is not needed for the build.

After changing terrain palettes, secondary biome roles, or object materials,
bake the changed scenes and run both appearance-catalog refreshes from the
repository root:

```powershell
python eloria-assets/maps/nymara-regions/_continent/refresh_biome_catalog.py
python eloria-assets/maps/nymara-regions/_continent/refresh_object_material_catalog.py
```

The first command refreshes terrain-blend masks and
`godot-client/assets/world/biome_blend/catalog.json` from the twelve saved
regions. The second writes
`godot-client/assets/world/biome_blend/object-materials.json` by resolving
saved object overrides against the published child mesh assets. These
appearance refreshes do not change geometry, collision, routes, or navigation.
Run the normal continent build for those changes; it consumes the saved scenes
and emits blended terrain data with the chunk manifests. These shortcuts apply
to currently published chunks that use the sidecar catalogs. A normal
continent export writes `biomeBlend` and `objectMaterialOverrides` into each
child chunk; those saved chunk records then take precedence over the global
catalogs. After such an export, make material changes through the normal
continent build. The shortcut commands stop before writing if a targeted child
already has either inline field. The current published children use sidecar
catalogs, so these refreshes apply until the next normal export.

## Technical contract

The base and optional secondary surfaces remain authored on the saved region
scene. Painted ground regions, paths, water, and per-object overrides stay
independent. Each 96 m chunk uses two RGBA masks on a common 1.5 m grid with a
one-pixel gutter. Their four channels encode normalized neighbouring-region
weights and each region's local secondary fraction. A chunk with more than
four contributors fails export rather than dropping a palette.

Chunk manifests bind ordered region IDs, mask paths and SHA-256 digests, and
the saved terrain surfaces' texture paths, hashes, colors, roughness, UV
transforms, and rotation. UVs start in global continent XZ space. The object
material catalog binds saved per-mesh overrides to their published child
assets. The editor preview and runtime loader use these catalogs; imported
terrain keeps its ordinary PBR material as a fallback.
