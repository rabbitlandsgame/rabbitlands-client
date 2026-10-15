class_name MapPicture
extends RefCounted
## The region's own top-down picture, laid on the ground for the map cameras.
##
## A chunk-streamed territory holds only the chunks around the player, so a
## live render of the world framed to the whole region showed the resident
## chunks in a field of nothing. Every region ships its picture already:
## `minimap.webp`, one pixel a metre, north up, framed by cartography.json
## exactly as the full-map camera frames the region. This lays that picture on
## the ground a metre under the lowest terrain, on a visual layer only the map
## cameras render, so the Tab map and the minimap read the whole region
## whatever is resident, while the actor dots and marks are drawn over it as
## before. Maps without a picture (interiors) keep the live render.

## World-XZ rectangle the picture covers: the region's minimap frame, cut to
## the tab map's crop when cartography frames a part of it.
static func extent(minimap: Dictionary, tab_map: Dictionary) -> Rect2:
	var world_min: Array = minimap.get("worldMin", []) as Array
	var world_max: Array = minimap.get("worldMax", []) as Array
	if world_min.size() < 2 or world_max.size() < 2:
		return Rect2()
	var pixels_per_metre: float = maxf(0.0001, float(minimap.get("pixelsPerMetre", 1.0)))
	var origin := Vector2(float(world_min[0]), float(world_min[1]))
	var full := Vector2(float(world_max[0]), float(world_max[1])) - origin
	var crop: Array = tab_map.get("region", []) as Array
	if crop.size() == 4:
		return Rect2(origin + Vector2(float(crop[0]), float(crop[1])) / pixels_per_metre,
			Vector2(float(crop[2]), float(crop[3])) / pixels_per_metre)
	return Rect2(origin, full)

## The rect a region's picture covers in its own metres, from the cartography
## alone: what extent() derives from a manifest, for a region whose package is
## not loaded. The published tab map carries the crop already applied.
static func tab_map_extent(tab_map: Dictionary) -> Rect2:
	var low: Array = tab_map.get("worldMin", []) as Array
	var high: Array = tab_map.get("worldMax", []) as Array
	if low.size() < 2 or high.size() < 2:
		return Rect2()
	var origin := Vector2(float(low[0]), float(low[1]))
	return Rect2(origin, Vector2(float(high[0]), float(high[1])) - origin)

## A metre under the lowest ground the picture frames, so no terrain the map
## cameras might still render could sit beneath it; the cameras look straight
## down, so the height itself is never seen.
static func height_below(manifest_data: Dictionary) -> float:
	var minimap: Dictionary = manifest_data.get("minimap", {}) as Dictionary
	var bounds: Dictionary = minimap.get("bounds", {}) as Dictionary
	var low: Array = bounds.get("min", []) as Array
	if low.size() != 3:
		var asset_bounds: Dictionary = (manifest_data.get("asset", {}) as Dictionary).get("mapBounds", {}) as Dictionary
		low = asset_bounds.get("min", []) as Array
	return (float(low[1]) if low.size() == 3 else 0.0) - 1.0

## The picture as a flat unshaded quad: its top row at the north edge (-Z) of
## `extent`, drawn from either side so no winding convention can hide it.
static func build(texture: Texture2D, extent: Rect2, height: float, layer: int) -> MeshInstance3D:
	var vertices := PackedVector3Array([
		Vector3(extent.position.x, height, extent.position.y),
		Vector3(extent.end.x, height, extent.position.y),
		Vector3(extent.end.x, height, extent.end.y),
		Vector3(extent.position.x, height, extent.end.y)])
	var uvs := PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)])
	var normals := PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP])
	var indices := PackedInt32Array([0, 2, 1, 0, 3, 2])
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = "MapPicture"
	node.mesh = mesh
	node.layers = layer
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return node
