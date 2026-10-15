@tool
extends RefCounted
## A clean top-down picture of the open territory, north up, for minimaps and
## as a tracing reference.
##
## An orthographic camera in a private SubViewport renders the edited scene's
## own World3D. Editor helpers (ghost, cursor grid, sculpt ring) are hidden for
## the shot, and neighbour references are hidden unless asked for. Fog is left
## out so distance never washes the map.
##
## A territory's terrain grid is a rectangle larger than the land it owns, so by
## default the image is framed to the ownership polygon, and pixels outside it
## are made transparent. Beside the PNG, a JSON sidecar records the
## territory-local bounds and metres per pixel, so a pixel maps straight back to
## authoring metres and server tiles.

const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const REFERENCE_SCRIPT := preload("res://addons/map_authoring_workspace/reference_preview.gd")
const MAX_SIDE := 8192
const HELPER_PREFIXES := ["__MapAssetGhost", "__MapAuthoringCursorGrid", "__TerrainSculptCursor",
	"__MapAuthoringMarkerOverlay", "__MapAuthoringWalkability", "__MapAuthoringPathDraft",
	"__MapAuthoringCopyDrag", "__MapAuthoringPlaytest", "__MapAuthoringFocus"]
const CAMERA_CLEARANCE := 60.0
const MAP_MINIMUM_AMBIENT := 0.9


## Frames the territory: returns bounds (territory-local X/Z), image size, the
## effective pixels per metre after the MAX_SIDE clamp, and the camera setup.
static func plan(root: Node3D, pixels_per_metre: float,
		clip_polygon: Variant = PackedVector2Array()) -> Dictionary:
	var bounds := _local_bounds(root)
	if bounds.is_empty():
		return {"error": "No authored terrain to frame in this scene."}
	var rect: Rect2 = bounds.rect
	var polygons := GEOMETRY.polygons(clip_polygon)
	if not polygons.is_empty():
		var owned := GEOMETRY.bounds(polygons)
		if rect.intersects(owned):
			rect = rect.intersection(owned)
	var ppm := maxf(pixels_per_metre, 0.01)
	var longest := maxf(rect.size.x, rect.size.y)
	if longest * ppm > float(MAX_SIDE):
		ppm = float(MAX_SIDE) / longest
	var size := Vector2i(maxi(ceili(rect.size.x * ppm), 1), maxi(ceili(rect.size.y * ppm), 1))
	# Square pixels: the camera keeps height, so derive the covered width from it.
	var covered := Vector2(float(size.x) / ppm, float(size.y) / ppm)
	var centre_local := Vector3(rect.position.x + covered.x * 0.5,
		float(bounds.max_height) + CAMERA_CLEARANCE, rect.position.y + covered.y * 0.5)
	var camera_local := Transform3D(Basis.looking_at(Vector3.DOWN, Vector3.FORWARD), centre_local)
	return {
		"rect": Rect2(rect.position, covered),
		"size": size,
		"pixels_per_metre": ppm,
		"camera_transform": root.global_transform * camera_local,
		"camera_size": covered.y,
		"near": 0.05,
		"far": float(bounds.max_height) - float(bounds.min_height) + CAMERA_CLEARANCE * 2.0,
		"min_height": bounds.min_height,
		"max_height": bounds.max_height,
	}


## Renders and saves the capture. `path` is an absolute or res:// PNG path.
## Awaits two frames; returns {"path", "sidecar", "size"} or {"error"}.
static func capture(root: Node3D, path: String, pixels_per_metre: float,
		include_references: bool, time_label: String = "",
		clip_to_ownership: bool = true) -> Dictionary:
	var rendered: Dictionary = await render(root, pixels_per_metre, include_references,
		clip_to_ownership)
	if rendered.has("error"):
		return rendered
	var image: Image = rendered.image
	var framing: Dictionary = rendered.framing
	var polygons: Array[PackedVector2Array] = rendered.polygons
	var absolute := ProjectSettings.globalize_path(path)
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var save_error := image.save_png(absolute)
	if save_error != OK:
		return {"error": "Could not write %s (%s)." % [absolute, error_string(save_error)]}
	var rect: Rect2 = framing.rect
	var sidecar := {
		"schema": "eloria-map-top-down-capture-v1",
		"regionId": String(root.get("region_id")) if root.get("region_id") != null else "",
		"scene": root.scene_file_path,
		"image": absolute.get_file(),
		"widthPixels": image.get_width(),
		"heightPixels": image.get_height(),
		"metresPerPixel": 1.0 / float(framing.pixels_per_metre),
		"orientation": "north-up; +X east to the right, +Z south downward",
		"territoryLocalBounds": {"minX": rect.position.x, "minZ": rect.position.y,
			"maxX": rect.end.x, "maxZ": rect.end.y},
		"heightRange": [framing.min_height, framing.max_height],
		"includesReferences": include_references,
		"clippedToOwnership": not polygons.is_empty(),
		"lighting": time_label,
		"capturedAt": Time.get_datetime_string_from_system(true) + "Z",
	}
	var sidecar_path := absolute.get_basename() + ".json"
	var file := FileAccess.open(sidecar_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(sidecar, "  ") + "\n")
		file.close()
	return {"path": absolute, "sidecar": sidecar_path, "size": image.get_size()}


## Renders the top-down image in memory. Awaits two frames; returns
## {"image", "framing", "polygon"} or {"error"}. Pixels outside the ownership
## polygon are transparent when `clip_to_ownership` is set.
static func render(root: Node3D, pixels_per_metre: float, include_references: bool,
		clip_to_ownership: bool = true) -> Dictionary:
	var polygons := ownership_polygons_local(root) if clip_to_ownership else GEOMETRY.polygons([])
	var framing := plan(root, pixels_per_metre, polygons)
	if framing.has("error"):
		return framing
	if DisplayServer.get_name() == "headless":
		return {"error": "The headless editor has no renderer to capture with."}
	var viewport := SubViewport.new()
	viewport.name = "__MapAuthoringTopDownCapture"
	viewport.size = framing.size
	viewport.transparent_bg = true
	viewport.own_world_3d = false
	viewport.world_3d = root.get_world_3d()
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.size = float(framing.camera_size)
	camera.near = float(framing.near)
	camera.far = float(framing.far)
	camera.environment = _map_environment(root.get_world_3d())
	viewport.add_child(camera)
	var hidden := _hide_helpers(root, include_references)
	root.add_child(viewport, false, Node.INTERNAL_MODE_BACK)
	camera.global_transform = framing.camera_transform
	camera.current = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	var tree := root.get_tree()
	await tree.process_frame
	await tree.process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	for node: Node3D in hidden:
		if is_instance_valid(node):
			node.visible = true
	if is_instance_valid(root) and viewport.get_parent() == root:
		root.remove_child(viewport)
	viewport.queue_free()
	if image == null or image.is_empty():
		return {"error": "The renderer returned no image."}
	image.convert(Image.FORMAT_RGBA8)
	if not polygons.is_empty():
		var clipped := Image.create_empty(image.get_width(), image.get_height(), false,
			Image.FORMAT_RGBA8)
		clipped.blend_rect_mask(image, ownership_mask(framing, polygons),
			Rect2i(Vector2i.ZERO, image.get_size()), Vector2i.ZERO)
		image = clipped
	return {"image": image, "framing": framing,
		"polygon": polygons[0] if not polygons.is_empty() else PackedVector2Array(), "polygons": polygons}


## The pixel a territory-local point lands on in a capture described by `framing`.
static func pixel_for(framing: Dictionary, local: Vector3) -> Vector2:
	var rect: Rect2 = framing.rect
	var ppm := float(framing.pixels_per_metre)
	return Vector2((local.x - rect.position.x) * ppm, (local.z - rect.position.y) * ppm)


## The open territory's ownership polygon in its own local X/Z metres, read from
## the Territories plugin's catalog entry (continent coordinates minus the
## territory's continent translation, as the sculpt border uses). Empty when the
## scene is not a catalogued territory.
static func ownership_polygon_local(root: Node3D) -> PackedVector2Array:
	var polygons := ownership_polygons_local(root)
	return polygons[0] if not polygons.is_empty() else PackedVector2Array()


static func ownership_polygons_local(root: Node3D) -> Array[PackedVector2Array]:
	for child in root.get_children(true):
		if not child.has_meta(&"map_authoring_reference_host"):
			continue
		var entry: Variant = child.get("active_entry")
		if not entry is Dictionary:
			continue
		var translation: Variant = entry.get("translation")
		if translation is Vector3:
			return GEOMETRY.local(GEOMETRY.from_entry(entry), translation)
	return []


## An RGBA mask the size of the capture: opaque inside `polygon` (territory-local
## X/Z), transparent outside. Filled one pixel row at a time from the polygon's
## edge crossings, so it stays fast for large images.
static func ownership_mask(framing: Dictionary, polygon: Variant) -> Image:
	var size: Vector2i = framing.size
	var rect: Rect2 = framing.rect
	var ppm := float(framing.pixels_per_metre)
	var mask := Image.create_empty(size.x, size.y, false, Image.FORMAT_RGBA8)
	mask.fill(Color(0, 0, 0, 0))
	for ring in GEOMETRY.polygons(polygon):
		for row in size.y:
			var z := rect.position.y + (float(row) + 0.5) / ppm
			var crossings: Array[float] = []
			for index in ring.size():
				var first := ring[index]
				var second := ring[(index + 1) % ring.size()]
				if (first.y <= z and second.y > z) or (second.y <= z and first.y > z):
					crossings.append(first.x + (z - first.y) * (second.x - first.x) /
						(second.y - first.y))
			crossings.sort()
			for pair in range(0, crossings.size() - 1, 2):
				var start := ceili((crossings[pair] - rect.position.x) * ppm - 0.5)
				var finish := floori((crossings[pair + 1] - rect.position.x) * ppm - 0.5)
				start = clampi(start, 0, size.x)
				finish = clampi(finish, -1, size.x - 1)
				if finish >= start:
					mask.fill_rect(Rect2i(start, row, finish - start + 1, 1), Color(1, 1, 1, 1))
	return mask


static func _local_bounds(root: Node3D) -> Dictionary:
	var terrain := Probe.region_terrain(root)
	if terrain != null:
		var origin: Vector2 = terrain.get("origin")
		var cell: float = terrain.get("cell_metres")
		var grid: Vector2i = terrain.get("grid_size")
		var heights: PackedFloat32Array = terrain.call("effective_heights")
		if heights.is_empty():
			return {}
		var low := INF
		var high := -INF
		for value in heights:
			low = minf(low, value)
			high = maxf(high, value)
		var to_root: Transform3D = root.global_transform.affine_inverse() * terrain.global_transform
		var first: Vector3 = to_root * Vector3(origin.x, low, origin.y)
		var last: Vector3 = to_root * Vector3(origin.x + float(grid.x - 1) * cell, high,
			origin.y + float(grid.y - 1) * cell)
		return {"rect": Rect2(Vector2(minf(first.x, last.x), minf(first.z, last.z)),
			Vector2(absf(last.x - first.x), absf(last.z - first.z))),
			"min_height": minf(first.y, last.y) - 5.0, "max_height": maxf(first.y, last.y) + 30.0}
	var mesh := root.get_node_or_null("GeneratedPreview/Terrain/TerrainMesh") as MeshInstance3D
	if mesh == null or mesh.mesh == null:
		return {}
	var box: AABB = root.global_transform.affine_inverse() * mesh.global_transform * mesh.get_aabb()
	return {"rect": Rect2(Vector2(box.position.x, box.position.z), Vector2(box.size.x, box.size.z)),
		"min_height": box.position.y - 5.0, "max_height": box.end.y + 30.0}


static func _map_environment(world: World3D) -> Environment:
	var source := world.environment if world != null else null
	var environment: Environment
	if source != null:
		environment = source.duplicate() as Environment
	else:
		environment = Environment.new()
		environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.ambient_light_color = Color(0.8, 0.82, 0.86)
		environment.ambient_light_energy = 1.0
	# The in-game minimap's rule (main.gd MAP_MINIMUM_AMBIENT): a floor under the
	# ambient keeps a map legible, and fog never reaches a map camera.
	environment.ambient_light_energy = maxf(environment.ambient_light_energy, MAP_MINIMUM_AMBIENT)
	environment.fog_enabled = false
	environment.volumetric_fog_enabled = false
	environment.background_mode = Environment.BG_CLEAR_COLOR
	return environment


static func _hide_helpers(root: Node, include_references: bool) -> Array[Node3D]:
	var hidden: Array[Node3D] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		for child in node.get_children(true):
			stack.append(child)
			if not child is Node3D or not (child as Node3D).visible:
				continue
			var helper := false
			for prefix: String in HELPER_PREFIXES:
				if String(child.name).begins_with(prefix):
					helper = true
			if not include_references and child.get_script() == REFERENCE_SCRIPT:
				helper = true
			if helper:
				(child as Node3D).visible = false
				hidden.append(child as Node3D)
	return hidden
