@tool
class_name MapAuthoringAssetControl
extends Node3D

const SURFACE_OVERRIDE_SCRIPT := preload(
	"res://src/dev/map_authoring_region/asset_surface_override.gd")

@export var asset_id := ""
@export var node_name := ""
@export var catalog_asset_id := ""
@export_file("*.glb", "*.gltf", "*.tscn", "*.scn") var scene_path := ""
@export var source_node := ""
@export_enum("none", "solid", "walk_surface") var collision_role := "none"
@export var metadata: Dictionary = {}
@export var material_overrides: Array[Resource] = []

var _override_signature: Array = []
var _applied_override_targets: Array[Dictionary] = []


func _ready() -> void:
	set_process(true)
	_apply_material_overrides()


func _process(_delta: float) -> void:
	var current: Array = []
	for override in material_overrides:
		current.append(override.call("signature") if _is_surface_override(override) else [])
	if current != _override_signature:
		_apply_material_overrides()


func content_root() -> Node3D:
	for child in get_children():
		if child is Node3D and not String(child.name).begins_with("__"):
			return child as Node3D
	return null


func material_override_records(surface_encoder: Callable) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for override in material_overrides:
		if not _is_surface_override(override):
			continue
		override.call("bind_local_surface")
		result.append({
			"meshNodePath": override.mesh_node_path,
			"surfaceIndex": override.surface_index,
			"surface": surface_encoder.call(override.surface,
				get_path_to(self) if is_inside_tree() else NodePath(".")),
		})
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var left := "%s:%08d" % [String(a.meshNodePath), int(a.surfaceIndex)]
		var right := "%s:%08d" % [String(b.meshNodePath), int(b.surfaceIndex)]
		return left < right)
	return result


func _apply_material_overrides() -> void:
	var root := content_root()
	if root != null:
		for target in _applied_override_targets:
			var old_mesh := root.get_node_or_null(NodePath(String(target.path))) as MeshInstance3D
			var old_index := int(target.index)
			if old_mesh != null and old_mesh.mesh != null and old_index >= 0 and \
					old_index < old_mesh.mesh.get_surface_count():
				old_mesh.set_surface_override_material(old_index, null)
	_applied_override_targets.clear()
	_override_signature.clear()
	if root == null:
		return
	for override in material_overrides:
		if not _is_surface_override(override):
			continue
		override.call("bind_local_surface")
		_override_signature.append(override.call("signature"))
		var mesh := root.get_node_or_null(NodePath(override.mesh_node_path)) as MeshInstance3D
		if mesh == null or mesh.mesh == null or override.surface_index >= mesh.mesh.get_surface_count():
			continue
		mesh.set_surface_override_material(override.surface_index,
			override.surface.get_material() if override.surface != null else null)
		_applied_override_targets.append({"path": override.mesh_node_path,
			"index": override.surface_index})


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if asset_id.strip_edges().is_empty():
		warnings.append("Placed assets need a stable Asset Id before export.")
	if node_name.strip_edges().is_empty():
		warnings.append("Placed assets need a stable production Node Name.")
	if scene_path.strip_edges().is_empty():
		warnings.append("Placed assets need their source Scene Path.")
	if content_root() == null:
		warnings.append("Placed asset wrapper has no Node3D content child.")
	for override in material_overrides:
		if not _is_surface_override(override) or override.surface == null:
			warnings.append("Every asset material override needs a local Surface.")
			continue
		var root := content_root()
		var mesh := root.get_node_or_null(NodePath(override.mesh_node_path)) as MeshInstance3D \
			if root != null else null
		if override.surface_index < 0 or mesh == null or mesh.mesh == null or \
				override.surface_index >= mesh.mesh.get_surface_count():
			warnings.append("Material override target '%s' surface %d does not exist." % [
				override.mesh_node_path, override.surface_index])
	return warnings


func _is_surface_override(value: Variant) -> bool:
	return value is Resource and (value as Resource).get_script() == SURFACE_OVERRIDE_SCRIPT
