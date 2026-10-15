extends SceneTree

const EXTRAS_PATH := "res://data/world/map_asset_extras.json"
const RELOAD_PATH := "user://map-asset-extraction-reload.tscn"
const Placement := preload("res://addons/map_asset_palette/placement.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var manifest: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(EXTRAS_PATH)) as Dictionary
	var entries := manifest.get("entries", []) as Array
	_expect(manifest.get("version") == 1 and not entries.is_empty(),
		"generated extras manifest declares a versioned continent library")
	var all_load := true
	var all_grounded := true
	for value: Variant in entries:
		var entry := value as Dictionary
		var packed := load(String(entry.scene_path)) as PackedScene
		all_load = all_load and packed != null
		if packed == null:
			continue
		var instance := packed.instantiate() as Node3D
		var bounds_result := Placement.mesh_bounds(instance)
		all_grounded = all_grounded and bool(bounds_result.get("valid", false))
		if bool(bounds_result.get("valid", false)):
			var bounds := bounds_result.bounds as AABB
			var grounded := Placement.ground_transform(instance, entry, Vector3.ZERO)
			var oriented := Transform3D(grounded.basis, Vector3.ZERO) * bounds
			all_grounded = all_grounded and \
				absf(grounded.origin.y + oriented.position.y) < 0.002 and \
				grounded.basis.is_equal_approx(instance.transform.basis)
		instance.free()
	_expect(all_load, "every extracted continent GLB loads through ResourceLoader")
	_expect(all_grounded,
		"every extracted asset keeps its metre scale and grounds its visible imported bounds")

	var lodge := _entry(entries, "continent:woodland-lodge")
	var created := Placement.instantiate_entry(lodge)
	var node := created.get("node") as Node3D
	_expect(node != null and not bool(created.get("starter", true)),
		"multi-part woodland lodge instantiates as a linked library scene")
	if node == null:
		_finish()
		return
	var parent := Node3D.new()
	parent.name = "PlacedAssets"
	root.add_child(parent)
	parent.add_child(node)
	node.owner = parent
	node.transform = Placement.ground_transform(node, lodge, Vector3(4.0, 7.0, -3.0))
	var bounds := Placement.mesh_bounds(node).bounds as AABB
	var material_names := _material_names(node)
	_expect(absf(node.position.y + bounds.position.y - 7.0) < 0.002 and
		node.transform.basis.is_equal_approx(Basis.IDENTITY),
		"height zero preserves the extracted metre scale and grounds the visible bounds")
	_expect(material_names.size() >= 4,
		"multi-part extracted building retains several native materials")
	var packed := PackedScene.new()
	_expect(packed.pack(parent) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"placed extracted scene saves")
	var reopened := (load(RELOAD_PATH) as PackedScene).instantiate()
	root.add_child(reopened)
	var saved := reopened.get_child(0) as Node3D
	_expect(saved != null and saved.scene_file_path == lodge.scene_path and
		_material_names(saved) == material_names,
		"save and reopen keeps linked GLB identity and native material set")
	reopened.queue_free()
	parent.queue_free()
	await process_frame
	_finish()


func _material_names(node: Node) -> PackedStringArray:
	var names := PackedStringArray()
	for mesh_node: Node in node.find_children("*", "MeshInstance3D", true, false):
		var mesh := (mesh_node as MeshInstance3D).mesh
		for surface in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			var label := "" if material == null else String(material.resource_name)
			if not label.is_empty() and label not in names:
				names.append(label)
	names.sort()
	return names


func _entry(entries: Array, id: String) -> Dictionary:
	for value: Variant in entries:
		var entry := value as Dictionary
		if entry.get("id") == id:
			return entry
	return {}


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false


func _finish() -> void:
	for path in [RELOAD_PATH, RELOAD_PATH + ".uid"]:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("map asset extraction: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)
