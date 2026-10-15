@tool
extends RefCounted
## The coordinate-locked concept masters (work-output/continent-region-masters,
## the visual boundary authority) laid over the open territory as a design
## reference: on the terrain, and as a minimap mode.
##
## Each region folder's contract.json places its master: cropRectWorld is
## [x0, z0, x1, z1] in continent metres at exactly one metre a pixel, north
## (-Z) at the top. The territory frame subtracts the scene's
## continent_translation. The contract carries the current (develop) and the
## proposed ownership polygons; both are drawn, white and magenta. This is
## concept art, not a heightmap, and not an ownership change: nothing here
## edits the scene or the masters, and the overlay is never saved.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const Settings := preload("res://addons/map_authoring_usability/usability_settings.gd")
const PACKAGE := "work-output/continent-region-masters"
const NODE_NAME := "__MapAuthoringConceptMaster"
const CURRENT_COLOR := Color(1.0, 1.0, 1.0, 0.95)
const PROPOSED_COLOR := Color(1.0, 0.3, 0.9, 0.95)
const SHADER_CODE := """
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, blend_mix;

uniform sampler2D master : filter_linear, repeat_disable;
uniform mat4 region_inverse;
uniform vec4 master_rect;
uniform float opacity = 0.6;
varying vec3 local_position;

void vertex() {
	VERTEX += NORMAL * 0.05;
	local_position = (region_inverse * MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = (local_position.xz - master_rect.xy) / master_rect.zw;
	if (any(lessThan(uv, vec2(0.0))) || any(greaterThanEqual(uv, vec2(1.0)))) discard;
	ALBEDO = texture(master, uv).rgb;
	ALPHA = opacity;
}
"""

var last_message := ""
var _node: MeshInstance3D
var _lines: MeshInstance3D
var _root: Node3D


## The package folder: Editor Settings > Map Authoring > Concept > Masters
## Folder when set, else the first work-output/continent-region-masters found
## above the project. "" when there is none.
static func folder() -> String:
	var chosen := String(Settings.value("concept/masters_folder"))
	if not chosen.is_empty() and DirAccess.dir_exists_absolute(chosen):
		return chosen
	var directory := ProjectSettings.globalize_path("res://").trim_suffix("/")
	for _level in 7:
		var candidate := directory.path_join(PACKAGE)
		if FileAccess.file_exists(candidate.path_join("continent-master-manifest.json")):
			return candidate
		var parent := directory.get_base_dir()
		if parent == directory or parent.is_empty():
			break
		directory = parent
	return ""


## {"image", "rect" (territory-local Rect2), "current", "proposed" (local
## polygons), "path"} for `root`'s region, or {"error"}.
static func load_for(root: Node3D, package: String = "") -> Dictionary:
	var base := package if not package.is_empty() else folder()
	if base.is_empty():
		return {"error": ("The concept masters were not found. Set Editor Settings > Map Authoring > " +
			"Concept > Masters Folder to work-output/continent-region-masters.")}
	var region := String(root.get("region_id"))
	var contract_path := base.path_join("regions").path_join(region.replace("_", "-")).path_join(
		"contract.json")
	var contract: Variant = JSON.parse_string(FileAccess.get_file_as_string(contract_path)) \
		if FileAccess.file_exists(contract_path) else null
	if not contract is Dictionary or String((contract as Dictionary).get("id", "")) != region:
		return {"error": "No concept master for %s in %s." % [region, base]}
	var data: Dictionary = contract
	var crop: Array = data.get("cropRectWorld", [])
	if crop.size() != 4:
		return {"error": "%s has no cropRectWorld." % contract_path.get_file()}
	var image_path := contract_path.get_base_dir().path_join(String(data.get("master", "")))
	var image := Image.load_from_file(image_path) if FileAccess.file_exists(image_path) else null
	if image == null or image.is_empty():
		return {"error": "The concept master %s is missing." % image_path.get_file()}
	var translation: Vector3 = root.get("continent_translation") \
		if root.get("continent_translation") is Vector3 else Vector3.ZERO
	var rect := Rect2(float(crop[0]) - translation.x, float(crop[1]) - translation.z,
		float(crop[2]) - float(crop[0]), float(crop[3]) - float(crop[1]))
	if image.get_width() != roundi(rect.size.x) or image.get_height() != roundi(rect.size.y):
		return {"error": "%s is %d x %d px, not the %d x %d m its contract places at 1 m/px." % [
			image_path.get_file(), image.get_width(), image.get_height(), roundi(rect.size.x),
			roundi(rect.size.y)]}
	image.convert(Image.FORMAT_RGBA8)
	return {"image": image, "rect": rect, "path": image_path,
		"current": _local_polygon(data.get("developOwnershipPolygon", []), translation),
		"proposed": _local_polygon(data.get("ownershipPolygon", []), translation)}


## The master cut to a minimap `framing` (top_down_capture.plan), or null.
static func minimap_picture(root: Node3D, framing: Dictionary, package: String = "") -> Dictionary:
	var loaded := load_for(root, package)
	if loaded.has("error"):
		return {"note": String(loaded.error)}
	var rect: Rect2 = loaded.rect
	var picture := resample(loaded.image, rect, framing)
	return {"image": picture, "note": "Concept master (%s): design reference, not a heightmap." %
		String(loaded.path).get_file()}


## Nearest-pixel resample of a 1 m/px master covering `rect` onto `framing`.
static func resample(source: Image, rect: Rect2, framing: Dictionary) -> Image:
	var size: Vector2i = framing.size
	var frame: Rect2 = framing.rect
	var picture := Image.create_empty(maxi(size.x, 1), maxi(size.y, 1), false, Image.FORMAT_RGBA8)
	for y in picture.get_height():
		var z := frame.position.y + (float(y) + 0.5) * frame.size.y / float(picture.get_height())
		var v := floori(z - rect.position.y)
		if v < 0 or v >= source.get_height():
			continue
		for x in picture.get_width():
			var along := frame.position.x + (float(x) + 0.5) * frame.size.x / float(picture.get_width())
			var u := floori(along - rect.position.x)
			if u >= 0 and u < source.get_width():
				picture.set_pixel(x, y, source.get_pixel(u, v))
	return picture


## Shows the master on `root`'s terrain with both ownership lines.
func show_on(root: Node3D) -> bool:
	release()
	var terrain := Probe.region_terrain(root)
	var preview := terrain.get_node_or_null("__TerrainPreview") as MeshInstance3D \
		if terrain != null else null
	if preview == null:
		last_message = "Open a territory with region terrain to see its concept master."
		return false
	var loaded := load_for(root)
	if loaded.has("error"):
		last_message = String(loaded.error)
		return false
	_root = root
	var shader := Shader.new()
	shader.code = SHADER_CODE
	var material := ShaderMaterial.new()
	material.shader = shader
	material.render_priority = 2
	var rect: Rect2 = loaded.rect
	material.set_shader_parameter("master", ImageTexture.create_from_image(loaded.image))
	material.set_shader_parameter("master_rect", Vector4(rect.position.x, rect.position.y,
		rect.size.x, rect.size.y))
	material.set_shader_parameter("region_inverse", Projection(root.global_transform.affine_inverse()))
	material.set_shader_parameter("opacity", float(Settings.value("concept/opacity")))
	_node = MeshInstance3D.new()
	_node.name = NODE_NAME
	_node.top_level = true
	_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_node.mesh = preview.mesh
	_node.material_override = material
	root.add_child(_node, false, Node.INTERNAL_MODE_BACK)
	_node.global_transform = preview.global_transform
	_lines = MeshInstance3D.new()
	_lines.name = "Boundaries"
	var lines := ImmediateMesh.new()
	_lines.mesh = lines
	_lines.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var line_material := StandardMaterial3D.new()
	line_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	line_material.vertex_color_use_as_albedo = true
	line_material.no_depth_test = true
	_lines.material_override = line_material
	_node.add_child(_lines)
	_lines.top_level = true
	_lines.global_transform = root.global_transform
	lines.surface_begin(Mesh.PRIMITIVE_LINES)
	for pair: Array in [[loaded.current, CURRENT_COLOR], [loaded.proposed, PROPOSED_COLOR]]:
		var polygon: PackedVector2Array = pair[0]
		for index in polygon.size():
			var a := polygon[index]
			var b := polygon[(index + 1) % polygon.size()]
			var steps := clampi(ceili(a.distance_to(b) / 4.0), 1, 64)
			for step in steps:
				for point: Vector2 in [a.lerp(b, float(step) / float(steps)),
						a.lerp(b, float(step + 1) / float(steps))]:
					lines.surface_set_color(pair[1])
					lines.surface_add_vertex(_draped(root, point))
	lines.surface_end()
	var same := (loaded.current as PackedVector2Array) == (loaded.proposed as PackedVector2Array)
	last_message = ("Concept master %s on the terrain (%.0f%% opacity): white is the current " +
		"ownership, magenta the proposed one%s. A design reference only: not a heightmap and " +
		"not an ownership change.") % [String(loaded.path).get_file(),
		float(Settings.value("concept/opacity")) * 100.0,
		" (the same here)" if same else ""]
	return true


func is_shown() -> bool:
	return _node != null and is_instance_valid(_node)


## Keeps the overlay on the terrain preview mesh, which sculpting rebuilds.
func sync() -> void:
	if not is_shown() or _root == null or not is_instance_valid(_root):
		return
	var terrain := Probe.region_terrain(_root)
	var preview := terrain.get_node_or_null("__TerrainPreview") as MeshInstance3D 		if terrain != null else null
	if preview == null:
		return
	if _node.mesh != preview.mesh:
		_node.mesh = preview.mesh
	_node.global_transform = preview.global_transform


func node() -> MeshInstance3D:
	return _node if is_shown() else null


func release() -> void:
	if _node != null and is_instance_valid(_node):
		if _node.get_parent() != null:
			_node.get_parent().remove_child(_node)
		_node.queue_free()
	_node = null
	_lines = null
	_root = null


static func _local_polygon(points: Array, translation: Vector3) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point: Variant in points:
		if point is Array and (point as Array).size() >= 2:
			result.append(Vector2(float(point[0]) - translation.x, float(point[1]) - translation.z))
	return result


static func _draped(root: Node3D, point: Vector2) -> Vector3:
	var world := root.global_transform * Vector3(point.x, 0.0, point.y)
	var height := Probe.height_at(root, world)
	var local: Vector3 = root.global_transform.affine_inverse() * Vector3(world.x,
		height if not is_nan(height) else world.y, world.z)
	return local + Vector3(0.0, 0.4, 0.0)
