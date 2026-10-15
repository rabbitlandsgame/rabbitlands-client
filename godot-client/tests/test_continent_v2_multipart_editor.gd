extends SceneTree
## Load the real authoring entries without rendering or publishing a bake.
const CATALOG := preload("res://addons/map_authoring_workspace/territory_catalog.gd")
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const TOPDOWN := preload("res://addons/map_authoring_usability/top_down_capture.gd")
const PREVIEW := preload("res://addons/map_authoring_workspace/reference_preview.gd")
var failures := 0
var assertions := 0
func _initialize() -> void:
	call_deferred("_run")
func _run() -> void:
	var catalog := CATALOG.new()
	var entries: Array[Dictionary] = catalog.entries("", CATALOG.configured_path())
	_expect(catalog.errors.is_empty(), "real continent-v2 catalog validates: " + "; ".join(catalog.errors))
	_expect(entries.size() == 15, "all fifteen scenes are registered")
	for entry in entries:
		var packed := load(String(entry.scene_path)) as PackedScene
		_expect(packed != null and entry.editable, String(entry.id) + " saved authored scene loads")
		if packed == null:
			continue
		var scene := packed.instantiate() as Node3D
		var terrain := scene.get_node("Terrain")
		terrain.preview_enabled = false
		for patch in terrain.get_node("Patches").get_children():
			_expect(patch is Marker3D and patch.get_script() != null, String(entry.id) + " retained patch has valid native/script type")
		root.add_child(scene)
		_expect(catalog.active_scene_error(scene, entry).is_empty(), String(entry.id) + " active editor ownership/frame binding accepted")
		var rings := GEOMETRY.from_entry(entry)
		_expect(GEOMETRY.hash(rings) == scene.get("ownership_polygon_sha256"), String(entry.id) + " catalog SHA equals scene binding")
		var host := PREVIEW.new()
		host.configure(scene, entry)
		scene.add_child(host)
		var local_rings := TOPDOWN.ownership_polygons_local(scene)
		_expect(local_rings.size() == rings.size(), String(entry.id) + " editor tools receive all ownership components")
		if entry.id == "ravenhead":
			_expect(rings.size() == 2 and terrain.preview_clip_polygons == rings, "Ravenhead retains both exact viewer components")
			var framing: Dictionary = TOPDOWN.plan(scene, 0.1, local_rings)
			var owned: Rect2 = GEOMETRY.bounds(local_rings)
			_expect(not framing.has("error") and framing.rect.encloses(owned), "Ravenhead capture frames both disjoint components")
			var mask: PackedByteArray = terrain.preview_clip_mask()
			var all_match := true
			var boundary_cells := 0
			var max_distance := 0.0
			var counts := [0,0]
			var outside := 0
			var columns: int = terrain.grid_size.x - 1
			var rows: int = terrain.grid_size.y - 1
			var cell: float = terrain.cell_metres
			var origin: Vector2 = terrain.origin
			var translation: Vector3 = entry.translation
			for z in rows:
				for x in columns:
					var point := origin + Vector2(translation.x,translation.z) + Vector2(x+0.5,z+0.5)*cell
					var inside := GEOMETRY.contains(point,rings)
					if mask[z*columns+x] != (1 if inside else 0):
						var distance := GEOMETRY.edge_distance(point,rings)
						max_distance = maxf(max_distance,distance)
						boundary_cells += 1 if distance < 0.001 else 0
						all_match = all_match and distance < 0.001
					outside += 0 if inside else 1
					for index in 2:
						counts[index] += 1 if Geometry2D.is_point_in_polygon(point,rings[index]) else 0
			_expect(all_match and counts[0] > 0 and counts[1] > 0 and outside > 0, "Ravenhead viewer agrees with union off borders (%s, outside %d; %d half-open border cells, max discrepancy distance %.6f)" % [counts,outside,boundary_cells,max_distance])
		scene.queue_free()
		await process_frame
	print("continent-v2 multipart editor: %d assertions, %d failures" % [assertions,failures])
	quit(1 if failures else 0)
func _expect(condition: bool,message: String) -> void:
	assertions += 1
	failures += 0 if condition else 1
	print("PASS: " if condition else "FAIL: ", message)
