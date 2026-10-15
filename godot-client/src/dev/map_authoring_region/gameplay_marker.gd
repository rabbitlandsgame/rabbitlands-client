@tool
class_name MapAuthoringGameplayMarker
extends Marker3D

const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")

@export var record_id := ""
@export_enum("spawn", "portal", "interactive", "landmark", "harvestable",
	"npc_marker", "ambient_population", "runtime_point") var kind := "landmark"
@export var label := ""
@export var destination_map := ""
@export var destination_spawn := ""
@export var key_id := ""
@export var default_spawn := false
@export var facing := Vector3(0.0, 0.0, -1.0)
@export var linked_node_name := ""
## Optional explicit relationship to an authored asset. The saved local offset
## makes this marker follow that asset when it is moved, rotated, or scaled.
@export var follow_asset_id := ""
@export var follow_asset_offset := Vector3.ZERO
@export_tool_button("Capture offset from linked asset", "Callable") \
	var capture_follow_offset_action := capture_follow_offset
@export var extras: Dictionary = {}
## Exact server records controlled by this marker. Positions stay on the marker;
## these records only bind stable runtime identities and certified provenance.
@export var runtime_bindings: Array[Dictionary] = []


func _ready() -> void:
	gizmo_extents = 0.8
	set_process(true)


func _process(_delta: float) -> void:
	if not Engine.is_editor_hint() or follow_asset_id.strip_edges().is_empty():
		return
	var asset := _follow_asset()
	if asset != null:
		global_position = asset.global_transform * follow_asset_offset


func capture_follow_offset() -> void:
	var asset := _follow_asset()
	if asset == null:
		push_warning("Gameplay marker could not find its Follow Asset Id.")
		return
	follow_asset_offset = asset.global_transform.affine_inverse() * global_position
	update_configuration_warnings()


func followed_asset() -> Node3D:
	return _follow_asset()


func _follow_asset() -> Node3D:
	if follow_asset_id.strip_edges().is_empty():
		return null
	var current: Node = self
	while current != null and not current.has_node("AuthoredAssets"):
		current = current.get_parent()
	if current == null:
		return null
	var container := current.get_node_or_null("AuthoredAssets")
	if container == null:
		return null
	for child in container.get_children():
		if child is Node3D and child.get_script() == ASSET_SCRIPT and \
				String(child.get("asset_id")) == follow_asset_id:
			return child as Node3D
	return null


func output_section() -> String:
	match kind:
		"spawn": return "spawnPoints"
		"portal": return "portals"
		"interactive": return "interactives"
		"landmark": return "landmarks"
		"harvestable": return "harvestables"
		"npc_marker": return "npcMarkers"
		"ambient_population": return "ambientPopulation"
		"runtime_point": return "runtimePoints"
	return ""


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if record_id.strip_edges().is_empty():
		warnings.append("Gameplay markers need a stable Record Id before export.")
	if kind == "portal" and (destination_map.strip_edges().is_empty() or \
			destination_spawn.strip_edges().is_empty()):
		warnings.append("Portals need Destination Map and Destination Spawn.")
	if not follow_asset_id.strip_edges().is_empty() and _follow_asset() == null:
		warnings.append("Follow Asset Id does not match an AuthoredAssets control.")
	return warnings
