@tool
class_name MapAuthoringRegionWater
extends Node3D

## Saved plan-water authority for the currently supported elliptical lakes.
## Moving this node changes the lake centre and water level. The radii remain
## editable; imported legacy depth is reference-only because saved terrain is
## the bed. Rotation and scale are rejected because the production lake domain
## does not support them as independent transforms.

@export var water_id := ""
@export var replaces_plan_feature_id := ""
@export var display_name := ""
@export var radii := Vector2.ONE
@export var preview_enabled := true
## Imported legacy bed-carving parameter.  Authored regions keep their saved
## resolved ground; changing the actual bed is done with terrain controls.
@export_storage var baseline_plan_depth := 1.0

const PREVIEW_SEGMENTS := 96

var _preview_signature: Array = []
var _preview_elapsed := 0.0


func _get_property_list() -> Array[Dictionary]:
	return [{
		"name": &"legacy_plan_depth_reference",
		"type": TYPE_FLOAT,
		"hint": PROPERTY_HINT_NONE,
		"hint_string": "Reference only. Actual water depth is level minus saved ground.",
		"usage": PROPERTY_USAGE_EDITOR | PROPERTY_USAGE_READ_ONLY,
	}]


func _get(property: StringName) -> Variant:
	if property == &"legacy_plan_depth_reference":
		return baseline_plan_depth
	return null


func _ready() -> void:
	set_process(true)
	refresh_preview()


func _process(delta: float) -> void:
	if not Engine.is_editor_hint():
		return
	_preview_elapsed += delta
	if _preview_elapsed < 0.18:
		return
	_preview_elapsed = 0.0
	if _current_preview_signature() != _preview_signature:
		refresh_preview()


func refresh_preview() -> void:
	_preview_signature = _current_preview_signature()
	var mesh_instance := get_node_or_null("__WaterRegionPreview") as MeshInstance3D
	if mesh_instance == null:
		mesh_instance = MeshInstance3D.new()
		mesh_instance.name = "__WaterRegionPreview"
		mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mesh_instance)
	if not preview_enabled or radii.x <= 0.0 or radii.y <= 0.0:
		mesh_instance.mesh = null
		return
	var vertices := PackedVector3Array([Vector3.ZERO])
	var uvs := PackedVector2Array([Vector2(0.5, 0.5)])
	for index in PREVIEW_SEGMENTS + 1:
		var angle := TAU * float(index) / float(PREVIEW_SEGMENTS)
		vertices.append(Vector3(cos(angle) * radii.x, 0.0,
			sin(angle) * radii.y))
		uvs.append(Vector2(cos(angle), sin(angle)) * 0.5 + Vector2(0.5, 0.5))
	var indices := PackedInt32Array()
	for index in PREVIEW_SEGMENTS:
		indices.append_array(PackedInt32Array([0, index + 1, index + 2]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var normals := PackedVector3Array()
	normals.resize(vertices.size())
	normals.fill(Vector3.UP)
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh_instance.mesh = mesh
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.16, 0.45, 0.64, 0.72)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.roughness = 0.42
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh_instance.material_override = material


func _current_preview_signature() -> Array:
	return [transform, water_id, display_name, radii, preview_enabled]


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if water_id.strip_edges().is_empty():
		warnings.append("Water regions need a stable Water Id before export.")
	if replaces_plan_feature_id.strip_edges().is_empty():
		warnings.append("Water regions must name the planned feature they replace.")
	if not radii.is_finite() or radii.x <= 0.0 or radii.y <= 0.0:
		warnings.append("Water region radii must be positive and finite.")
	if not is_finite(baseline_plan_depth) or baseline_plan_depth < 0.0:
		warnings.append("Imported plan-depth reference must be finite and non-negative.")
	return warnings
