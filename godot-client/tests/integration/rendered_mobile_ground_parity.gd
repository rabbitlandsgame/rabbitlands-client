extends SceneTree
## Rendered proof for the Mobile ground pre-pass (LookGround.mobile_prepass):
## the complete client at the Four Gates plaza the crowd benchmark's market
## cell stands on (server origin, camera 26 m at -60 degrees, no crowd), the
## world viewport saved as `mobile-ground-<renderer>.png` with a JSON beside
## it. Run it once per renderer on the same GPU and compare the two images:
## under Mobile, before the pre-pass, the walk decks drew black seams where
## their edging bands cross each other and the cobble patches sorted after a
## deck painted over it (stage A sign-off, section 8).
##
## Windowed, under the GPU lock, with a fresh isolated APPDATA/LOCALAPPDATA
## whose eloria_hud.cfg holds the Performance preset (quality low, painted
## ground, render scale 0.75) for the iGPU default tier:
##   ELORIA_NO_MAP_CACHE=1 ELORIA_ARTIFACT_DIR=<dir> Godot --log-file <log>
##     --path godot-client --rendering-method mobile|forward_plus
##     --gpu-index 1 --resolution 1280x720 --audio-driver Dummy
##     --script res://tests/integration/rendered_mobile_ground_parity.gd
## Forward+ at render scale 0.75 uses FSR1 and Mobile bilinear, so compare
## Mobile with Forward+ run with ELORIA_FSR=0 to see only the renderer.
## ELORIA_PARITY_PICKS="x,y;x,y" also prints, for each viewport pixel, every
## ground layer under it (height, vertex alpha, shader, sort distance).

const TARGET := Vector3(0.5, 0.0, -0.5)
const SETTLE_FRAMES := 600

var _main: Control
var _failures := 0
var _artifacts := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/mobile-ground")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK, "artifact directory is writable")
	var method := RenderingServer.get_current_rendering_method()
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(_main)
	var ready_by := Time.get_ticks_msec() + 120000
	while (_main.get("map_registry") as Dictionary).is_empty() and Time.get_ticks_msec() < ready_by:
		await process_frame
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	(_main.get("login_panel") as Control).hide()
	(_main.get("creation_panel") as Control).hide()
	(_main.get("game_view") as Control).show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("current_map", "four_gates")
	_main.call("_load_server_map")
	var loader := _main.get("world_loader") as WorldLoader
	var deadline := Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, "Four Gates loads"):
		quit(1)
		return
	var adapter := _main.get("adapter") as CoordinateAdapter
	var tile: Vector2i = adapter.godot_to_server(TARGET)
	state.set("local_actor_id", 1)
	state.set("actors", {1: {"actor_id": 1, "x": tile.x, "y": tile.y, "rotation": 0, "actor_type": 0,
		"kind": 1, "name": "Traveller", "health": 100, "max_health": 100, "alive": true, "appearance": {}}})
	state.call("mark_all_actors_changed")
	_main.call("_sync_world")
	var rig := _main.get("camera_rig") as Node3D
	for pass_index in 2:
		rig.set("distance", 26.0)
		rig.set("pitch_degrees", -60.0)
		rig.call("_update_camera")
		for i in (SETTLE_FRAMES if pass_index == 0 else 120):
			await process_frame
	var prepasses := 0
	var decks := 0
	for node: Node in loader.world_root.find_children("Walk_*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null:
			continue
		for surface: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null or material.shader != LookGround.SHADER_DECK:
				continue
			if not LookGround.reaches_prepass(material):
				continue
			decks += 1
			if material.next_pass != null and material.next_pass.has_meta(LookGround.PREPASS_META):
				prepasses += 1
	_expect(decks > 0, "the plaza's walk decks are painted (%d solid deck surfaces)" % decks)
	if method == "mobile":
		_expect(prepasses == decks, "mobile: every painted deck has its pre-pass (%d of %d)" % [prepasses, decks])
	else:
		_expect(prepasses == 0, "%s: no deck has a pre-pass (%d)" % [method, prepasses])
		_expect(not ResourceLoader.has_cached(LookGround.DECK_PREPASS_PATH)
			and not ResourceLoader.has_cached(LookGround.OVERLAY_PREPASS_PATH),
			"%s: the pre-pass shaders are never loaded" % method)
	var viewport := _main.get("main_viewport") as SubViewport
	var image := viewport.get_texture().get_image()
	var name := "mobile-ground-%s" % method
	_expect(image.save_png(_artifacts.path_join(name + ".png")) == OK, "the frame is saved")
	var camera := _main.get("gameplay_camera") as Camera3D
	# FSR1 below render scale 1 is Forward+ only: Mobile always scales bilinear.
	var report := {"renderer": method, "decks": decks, "prepasses": prepasses,
		"scaling": "fsr1" if method == "forward_plus" and OS.get_environment("ELORIA_FSR") != "0" else "bilinear",
		"size": [image.get_width(), image.get_height()],
		"camera": str(camera.global_transform), "failures": _failures}
	var picks := OS.get_environment("ELORIA_PARITY_PICKS")
	if not picks.is_empty():
		report["picks"] = _pick(loader.world_root, camera, picks)
	var file := FileAccess.open(_artifacts.path_join(name + ".json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, " "))
	file.close()
	print("rendered_mobile_ground_parity: %s renderer=%s decks=%d prepasses=%d" % [
		"PASS" if _failures == 0 else "FAIL", method, decks, prepasses])
	quit(1 if _failures > 0 else 0)

## Every ground layer under each picked viewport pixel, highest first.
func _pick(world_root: Node3D, camera: Camera3D, picks: String) -> Dictionary:
	var layers: Array[MeshInstance3D] = []
	for node: Node in world_root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		var plain := String(mesh.name)
		if mesh.mesh != null and mesh.is_visible_in_tree() and (plain.begins_with("Terrain_")
				or plain.begins_with("AuthoredGround_") or plain.begins_with("Walk_")):
			layers.append(mesh)
	var result := {}
	for pair: String in picks.split(";"):
		var xy := pair.split(",")
		var pixel := Vector2(float(xy[0]), float(xy[1]))
		var origin := camera.project_ray_origin(pixel)
		var direction := camera.project_ray_normal(pixel)
		var hits := []
		for mesh: MeshInstance3D in layers:
			var box := mesh.global_transform * mesh.mesh.get_aabb()
			if not box.grow(0.05).intersects_ray(origin, direction):
				continue
			for surface: int in mesh.mesh.get_surface_count():
				var arrays := mesh.mesh.surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var colours: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] != null \
					else PackedColorArray()
				var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null \
					else PackedInt32Array()
				var count := indices.size() if not indices.is_empty() else vertices.size()
				for t: int in range(0, count, 3):
					var ids := [t, t + 1, t + 2] if indices.is_empty() else [indices[t], indices[t + 1], indices[t + 2]]
					var a: Vector3 = mesh.global_transform * vertices[ids[0]]
					var b: Vector3 = mesh.global_transform * vertices[ids[1]]
					var c: Vector3 = mesh.global_transform * vertices[ids[2]]
					var hit: Variant = Geometry3D.ray_intersects_triangle(origin, direction, a, b, c)
					if hit == null:
						continue
					var alpha := -1.0
					if not colours.is_empty():
						var weights := Geometry3D.get_triangle_barycentric_coords(hit, a, b, c)
						alpha = colours[ids[0]].a * weights.x + colours[ids[1]].a * weights.y \
							+ colours[ids[2]].a * weights.z
					var material := mesh.get_active_material(surface)
					hits.append({"name": String(mesh.name), "y": snappedf((hit as Vector3).y, 0.0001),
						"alpha": snappedf(alpha, 0.001),
						"shader": (material as ShaderMaterial).shader.resource_path.get_file()
							if material is ShaderMaterial and (material as ShaderMaterial).shader != null else "",
						"sortDistance": snappedf(camera.global_position.distance_to(box.get_center()), 0.01)})
		hits.sort_custom(func(l: Dictionary, r: Dictionary) -> bool: return float(l.y) > float(r.y))
		result[pair] = hits
	return result

func _expect(condition: bool, message: String) -> bool:
	if not condition:
		_failures += 1
		push_error("rendered_mobile_ground_parity: " + message)
	else:
		print("PASS " + message)
	return condition
