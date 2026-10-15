@tool
class_name MapAuthoringGroundRegion
extends Marker3D

enum Shape {
	ELLIPSE,
	RECTANGLE,
}

## Draw this local ground patch. The Scene-tree eye can temporarily hide an
## enabled patch without changing this saved setting.
@export var enabled := false:
	set(value):
		enabled = value
		_refresh_editor_outline()
@export_enum("Ellipse", "Rectangle") var shape: int = Shape.ELLIPSE:
	set(value):
		shape = clampi(value, Shape.ELLIPSE, Shape.RECTANGLE)
		_refresh_editor_outline()
@export var size := Vector2(10.0, 7.0):
	set(value):
		size = Vector2(maxf(value.x, 0.1), maxf(value.y, 0.1))
		_refresh_editor_outline()
@export_range(0.0, 8.0, 0.05) var blend_width := 1.25
@export_range(0.0, 1.0, 0.01) var opacity := 1.0
@export_range(-1000, 1000, 1) var priority := 0
## Optional hard mask in this node's local X/Z metres; original shape/blend stay unchanged.
@export var clip_polygon := PackedVector2Array()
## Preserve source texture phase when an authored region moves to a new territory frame.
@export var uv_anchor_continent_enabled := false
@export var uv_anchor_continent := Vector2.ZERO
## Original zero-based sorted (priority, id) position; -1 retains legacy ordering.
@export var source_layer_ordinal := -1
@export_group("Appearance")
## Choose a ready ground texture without expanding the Surface resource.
@export var texture: String:
	get:
		return (surface.texture_preset if surface != null
			else MapAuthoringTexturePresets.CUSTOM)
	set(value):
		_ensure_surface()
		surface.texture_preset = value
		if value != MapAuthoringTexturePresets.CUSTOM and \
				MapAuthoringTexturePresets.PRESET_NAMES.has(value) and \
				not surface.source_material is BaseMaterial3D:
			surface.source_material = \
				MapAuthoringTexturePresets.create_material(value)
## Rotate this region's texture in degrees without rotating its footprint.
@export_range(-180.0, 180.0, 1.0, "degrees") var texture_rotation: float:
	get:
		return surface.rotation_degrees if surface != null else 0.0
	set(value):
		_ensure_surface()
		surface.rotation_degrees = value
## Advanced local material controls. Use the top-level Texture controls for
## common choices; expand Surface for Custom source material editing.
@export var surface: MapAuthoringSurface

var _bound_surface: MapAuthoringSurface
var _outline_signature: Array = []
var _warning_signature: Array = []


func _validate_property(property: Dictionary) -> void:
	if property.name == &"texture":
		property.hint = PROPERTY_HINT_ENUM
		property.hint_string = ",".join(MapAuthoringTexturePresets.PRESET_NAMES)
	if property.name in [&"texture", &"texture_rotation"]:
		property.usage = int(property.usage) & ~PROPERTY_USAGE_STORAGE


func _ready() -> void:
	gizmo_extents = 0.7
	set_process(true)
	sync_surface_binding()
	_refresh_editor_outline()


func _process(_delta: float) -> void:
	if surface != _bound_surface:
		sync_surface_binding()
	if Engine.is_editor_hint():
		var current := [enabled, shape, size, clip_polygon]
		if current != _outline_signature:
			_refresh_editor_outline()
		var warnings_current := [enabled, global_transform, surface != null,
			surface != null and surface.source_material is BaseMaterial3D, clip_polygon]
		if warnings_current != _warning_signature:
			_warning_signature = warnings_current
			update_configuration_warnings()


func sync_surface_binding() -> void:
	if surface == _bound_surface:
		return
	if surface != null:
		surface = surface.duplicate(true) as MapAuthoringSurface
		surface.resource_local_to_scene = true
	_bound_surface = surface
	notify_property_list_changed()


func _ensure_surface() -> void:
	if surface == null:
		surface = MapAuthoringSurface.from_preset(
			MapAuthoringTexturePresets.CUSTOM)
	sync_surface_binding()


func region_signature() -> Array:
	sync_surface_binding()
	return [name, global_transform, enabled, is_visible_in_tree(), shape, size, blend_width,
		opacity, priority, clip_polygon, uv_anchor_continent_enabled, uv_anchor_continent, source_layer_ordinal, surface.signature() if surface != null else []]


func projected_world_to_local() -> Variant:
	var projected: Variant = _projected_transform()
	if projected == null:
		return null
	return (projected as Transform2D).affine_inverse()


func world_bounds() -> Rect2:
	var half := size * 0.5
	var projected_value: Variant = _projected_transform()
	if projected_value == null:
		return Rect2()
	var projected := projected_value as Transform2D
	var corners := [projected * Vector2(-half.x, -half.y),
		projected * Vector2(half.x, -half.y),
		projected * Vector2(half.x, half.y),
		projected * Vector2(-half.x, half.y)]
	var minimum: Vector2 = corners[0]
	var maximum: Vector2 = corners[0]
	for corner: Vector2 in corners:
		minimum = minimum.min(corner)
		maximum = maximum.max(corner)
	return Rect2(minimum, maximum - minimum)


func _projected_transform() -> Variant:
	var projected := Transform2D(
		Vector2(global_basis.x.x, global_basis.x.z),
		Vector2(global_basis.z.x, global_basis.z.z),
		Vector2(global_position.x, global_position.z))
	if not projected.x.is_finite() or not projected.y.is_finite() or \
			not projected.origin.is_finite() or \
			absf(projected.determinant()) <= 0.000001:
		return null
	return projected


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if enabled and surface == null:
		warnings.append("Enabled ground regions need a Surface; this region is skipped.")
	elif enabled and not surface.source_material is BaseMaterial3D:
		warnings.append("This ground region cannot draw its current Surface. Choose a named Texture such as Grass, Soil, or Sand, or use a supported standard 3D material source.")
	if enabled and projected_world_to_local() == null:
		warnings.append("Ground region X/Z scale is singular; this region is skipped.")
	var mask_error := clip_error(clip_polygon)
	if not mask_error.is_empty():
		warnings.append(mask_error)
	if uv_anchor_continent_enabled and not uv_anchor_continent.is_finite():
		warnings.append("Ground UV source anchor must be finite.")
	if source_layer_ordinal < -1 or source_layer_ordinal > 126:
		warnings.append("Ground source layer ordinal must be -1 or 0 through 126.")
	return warnings


func _refresh_editor_outline() -> void:
	if not is_inside_tree() or not Engine.is_editor_hint():
		return
	_outline_signature = [enabled, shape, size, clip_polygon]
	var outline := get_node_or_null("__GroundRegionFootprint") as MeshInstance3D
	if outline == null:
		outline = MeshInstance3D.new()
		outline.name = "__GroundRegionFootprint"
		add_child(outline)
		# Deliberately no owner: this is an editor aid, never authored scene data.
	var immediate := ImmediateMesh.new()
	immediate.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	var half := size * 0.5
	if shape == Shape.ELLIPSE:
		for index in 49:
			var angle := TAU * float(index) / 48.0
			immediate.surface_add_vertex(Vector3(cos(angle) * half.x, 0.06,
				sin(angle) * half.y))
	else:
		for point: Vector2 in [Vector2(-half.x, -half.y), Vector2(half.x, -half.y),
				Vector2(half.x, half.y), Vector2(-half.x, half.y),
				Vector2(-half.x, -half.y)]:
			immediate.surface_add_vertex(Vector3(point.x, 0.06, point.y))
	immediate.surface_end()
	if not clip_polygon.is_empty():
		immediate.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for index in clip_polygon.size() + 1:
			var point := clip_polygon[index % clip_polygon.size()]
			immediate.surface_add_vertex(Vector3(point.x, 0.08, point.y))
		immediate.surface_end()
	outline.mesh = immediate
	outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.78, 0.18, 0.9 if enabled else 0.45)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	outline.material_override = material
	update_configuration_warnings()


static func clip_error(polygon: PackedVector2Array) -> String:
	if polygon.is_empty(): return ""
	if polygon.size() < 3 or polygon.size() > 64:
		return "Ground clip polygon must contain 3 through 64 points."
	var area := 0.0
	for i in polygon.size():
		var a := polygon[i]
		var b := polygon[(i + 1) % polygon.size()]
		if not a.is_finite() or a == b:
			return "Ground clip polygon contains a nonfinite point or empty edge."
		area += a.cross(b)
		for j in range(i + 1, polygon.size()):
			if j == i + 1 or (i == 0 and j == polygon.size() - 1): continue
			var c := polygon[j]
			var d := polygon[(j + 1) % polygon.size()]
			if Geometry2D.segment_intersects_segment(a, b, c, d) != null:
				return "Ground clip polygon must be a simple ring."
	if absf(area) <= 0.000001 or Geometry2D.triangulate_polygon(polygon).is_empty():
		return "Ground clip polygon has zero area or invalid topology."
	return ""
