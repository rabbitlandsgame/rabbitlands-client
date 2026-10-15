@tool
class_name MapAuthoringRegion
extends Node3D

const SNAPSHOT := preload("res://src/dev/map_authoring_region/region_snapshot.gd")
const OWNERSHIP := preload("res://src/dev/map_authoring_region/ownership_source.gd")
const TERRAIN_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const WATER_SCRIPT := preload(
	"res://src/dev/map_authoring_region/water_region_control.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")

@export_category("Region contract")
@export var region_id := ""
@export var continent_translation := Vector3.ZERO
@export_range(0.01, 16.0, 0.01, "or_greater") var metres_per_tile := 1.0
@export var server_origin := Vector2i.ZERO
@export var server_cells := Vector2i.ZERO
## Zero means the historical omitted contract, valid only with a zero minimum.
@export var server_storage_version := 0
@export var server_tile_min := Vector2i.ZERO
@export var collision_origin_metres := Vector2.ZERO
@export var ownership_polygon_sha256 := ""
@export var seam_anchors: Array[Dictionary] = []

@export_category("Procedural replacements")
## These registries persist independently of path nodes. Deleting a path never
## silently restores its former procedural route or water feature.
@export var owned_route_ids := PackedStringArray()
@export var owned_plan_feature_ids := PackedStringArray()
## A deleted saved quay stays removed; its connection remains in this registry.
@export var owned_ferry_connection_ids := PackedStringArray()

@export_category("Authority")
@export var authority_terrain := true
@export var authority_water := true
@export var authority_paths := true
@export var authority_objects := true
@export var authority_gameplay := true
## Certified identity registry used to bind runtime server records to saved
## gameplay markers. The file and its reviewed hash travel with the snapshot.
@export_file("*.json") var runtime_binding_seed_path := ""
@export var runtime_binding_seed_sha256 := ""

@export_category("Bake")
@export_dir var export_directory := \
	"res://../eloria-assets/maps/nymara-regions/sunmane_steppe/authoring"
@export_tool_button("Refresh authoring preview", "Callable") var refresh_action := refresh_all
@export_tool_button("Bake continent authoring snapshot", "Callable") var bake_action := save_and_export_snapshot
var last_export_status := ""


func _ready() -> void:
	add_to_group(&"map_authoring_region", true)
	refresh_all()


func refresh_all() -> void:
	var terrain := get_node_or_null("Terrain")
	if _uses_script(terrain, TERRAIN_SCRIPT):
		terrain.refresh_preview()
	for container_name in ["Roads", "Rivers"]:
		var container := get_node_or_null(NodePath(container_name))
		if container == null:
			continue
		for child in container.get_children():
			if _uses_script(child, PATH_SCRIPT):
				child.call_deferred("_refresh_preview")
	var water_regions := get_node_or_null("WaterRegions")
	if water_regions != null:
		for child in water_regions.get_children():
			if _uses_script(child, WATER_SCRIPT):
				child.call_deferred("refresh_preview")


func save_and_export_snapshot() -> Dictionary:
	if Engine.is_editor_hint():
		if scene_file_path.is_empty() or not scene_file_path.begins_with("res://"):
			last_export_status = "Bake failed: save this region scene inside the project first."
			push_error(last_export_status)
			return {}
		var packed := PackedScene.new()
		var pack_error := packed.pack(self)
		if pack_error != OK:
			last_export_status = "Bake failed: could not pack the authoring scene (%s)." % \
				error_string(pack_error)
			push_error(last_export_status)
			return {}
		var save_error := ResourceSaver.save(packed, scene_file_path)
		if save_error != OK:
			last_export_status = "Bake failed: could not save the authoring scene (%s)." % \
				error_string(save_error)
			push_error(last_export_status)
			return {}
	return export_snapshot()


func export_snapshot(output_path: String = "") -> Dictionary:
	var target := output_path
	if target.is_empty():
		target = export_directory.path_join("continent-authoring.json")
	var exporter := SNAPSHOT.new()
	var document: Dictionary = exporter.export_region(self, target)
	if not exporter.errors.is_empty():
		last_export_status = "Bake failed:\n" + "\n".join(exporter.errors)
		for message in exporter.errors:
			push_error("Continent authoring: " + message)
		return {}
	last_export_status = "Baked %s\n%s" % [target,
		FileAccess.get_sha256(ProjectSettings.globalize_path(target))]
	print("continent_authoring_snapshot ", target, " sha256=",
		FileAccess.get_sha256(ProjectSettings.globalize_path(target)))
	return document


func authoring_ground_intersection(ray_origin: Vector3, ray_direction: Vector3,
		max_distance: float = 2048.0) -> Variant:
	if not ray_origin.is_finite() or not ray_direction.is_finite() or \
			ray_direction.length_squared() <= 0.000001 or not is_finite(max_distance) or \
			max_distance <= 0.0:
		return null
	var terrain := get_node_or_null("Terrain")
	if not _uses_script(terrain, TERRAIN_SCRIPT):
		return null
	var inverse: Transform3D = terrain.global_transform.affine_inverse()
	var local_start: Vector3 = inverse * ray_origin
	var local_end: Vector3 = inverse * (ray_origin + ray_direction.normalized() * max_distance)
	var hit: Variant = terrain.intersect_local_segment(local_start, local_end)
	return terrain.global_transform * (hit as Vector3) if hit is Vector3 else null


func prepare_palette_asset(entry: Dictionary, content: Node3D) -> Node3D:
	if content == null:
		return null
	var wrapper := ASSET_SCRIPT.new()
	var identity := _next_asset_id(String(entry.get("id", content.name)))
	wrapper.name = _safe_node_name(String(entry.get("label", content.name)))
	wrapper.asset_id = identity
	wrapper.node_name = "Authored_%s" % identity.replace(":", "_").replace("-", "_")
	wrapper.catalog_asset_id = String(entry.get("id", ""))
	wrapper.scene_path = String(entry.get("scene_path", ""))
	wrapper.source_node = String(entry.get("source_node", ""))
	var category := String(entry.get("category", "")).to_lower()
	wrapper.collision_role = "solid" if "structure" in category or \
		"interactive" in category or "landmark" in category else "none"
	wrapper.set_meta(&"map_authoring_asset_wrapper", true)
	wrapper.add_child(content)
	content.name = "Content"
	return wrapper


func _next_asset_id(catalog_id: String) -> String:
	var base := catalog_id.to_lower().replace(":", "-")
	for invalid in [" ", ".", "/", "\\", "@", "%"]:
		base = base.replace(invalid, "-")
	while "--" in base:
		base = base.replace("--", "-")
	base = base.trim_prefix("-").trim_suffix("-")
	if base.is_empty():
		base = "asset"
	var used := {}
	var container := get_node_or_null("AuthoredAssets")
	if container != null:
		for child in container.get_children():
			if _uses_script(child, ASSET_SCRIPT):
				used[child.asset_id] = true
	var index := 1
	var candidate := "%s-%03d" % [base, index]
	while used.has(candidate):
		index += 1
		candidate = "%s-%03d" % [base, index]
	return candidate


func _safe_node_name(label: String) -> String:
	var result := label.strip_edges()
	for invalid in [".", ":", "@", "/", "\"", "%"]:
		result = result.replace(invalid, "")
	return result if not result.is_empty() else "MapAsset"


func _uses_script(value: Variant, script: Script) -> bool:
	return value is Object and (value as Object).get_script() == script


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	var ownership := OWNERSHIP.region_data(OWNERSHIP.load_source(), region_id)
	var ownership_error := OWNERSHIP.scene_error(ownership, self)
	if not ownership_error.is_empty():
		warnings.append(ownership_error)
	elif ownership.get("selected", false):
		warnings.append("Ownership source hash/frame checked. Strict polygon/partition validation is required and runs during bake.")
	if region_id.strip_edges().is_empty():
		warnings.append("Region Id is required.")
	if server_cells.x <= 0 or server_cells.y <= 0:
		warnings.append("Server Cells must be positive.")
	if not ownership.get("selected", false) and (ownership_polygon_sha256.length() != 64 or \
			not ownership_polygon_sha256.is_valid_hex_number(false)):
		warnings.append("Ownership Polygon Sha256 must be a 64-character hash.")
	if runtime_binding_seed_path.is_empty() != runtime_binding_seed_sha256.is_empty():
		warnings.append("Runtime Binding Seed Path and Sha256 must be set together.")
	for required in ["Terrain", "Roads", "Rivers", "Bridges", "AuthoredAssets",
			"Gameplay", "GeneratedPreview"]:
		if not has_node(NodePath(required)):
			warnings.append("Missing saved %s container." % required)
	return warnings
