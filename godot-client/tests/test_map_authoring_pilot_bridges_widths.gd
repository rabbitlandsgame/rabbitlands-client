extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const BRIDGE_SCRIPT := preload("res://src/dev/map_authoring_pilot/bridge_control.gd")
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.bridge-width-reload.tscn"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pilot := PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var bridges := pilot.get_node("AuthoredControls/Bridges") as Node3D
	var first := bridges.get_node("Bridge") as Node3D
	first.width = 2.0
	var second := _make_bridge("WideBridge", Vector3(-4.0, 0.0, 8.0),
		Vector3(4.0, 0.0, 8.0), 5.0)
	bridges.add_child(second)
	_set_owner_tree(second, pilot)
	pilot.refresh_all()
	await process_frame

	var first_deck := pilot.get_node("GeneratedPreview/Bridge/Bridge/BridgeDeck") as MeshInstance3D
	var second_deck := pilot.get_node("GeneratedPreview/Bridge/WideBridge/BridgeDeck") as MeshInstance3D
	_expect(is_equal_approx(first_deck.get_aabb().size.z, 2.0),
		"the first generated deck uses its own two-metre width")
	_expect(is_equal_approx(second_deck.get_aabb().size.z, 5.0),
		"a second generated deck independently uses its five-metre width")
	first.width = 2.5
	pilot.refresh_scope = "Road"
	pilot.refresh_selected()
	await process_frame
	first_deck = pilot.get_node("GeneratedPreview/Bridge/Bridge/BridgeDeck") as MeshInstance3D
	_expect(is_equal_approx(first_deck.get_aabb().size.z, 2.5),
		"a manual Road refresh promotes a pending bridge-width edit")
	first.width = 2.0
	pilot.refresh_all()
	await process_frame
	_expect(pilot.call("_encoded_floor", 0.0, 9.75) > 0 and
		pilot.call("_encoded_floor", 0.0, 10.75) == 0,
		"export collision follows the second bridge's authored span mask")
	var high := _make_bridge("HighBridge", Vector3(-4.0, 2.0, 0.0),
		Vector3(4.0, 2.0, 0.0), 3.0)
	bridges.add_child(high)
	pilot.refresh_all()
	await process_frame
	var overlap: Dictionary = pilot.call("_bridge_at", 0.0, 0.0)
	var overlap_height := float(overlap.height)
	_expect(overlap.bridge.name == "HighBridge" and
		is_equal_approx(pilot.call("_road_height", 0.0, 0.0), overlap_height + 0.035) and
		pilot.call("_encoded_floor", 0.0, 0.0) == pilot.call("_encode_height", overlap_height),
		"overlapping spans use the highest deck for road and exported floor")
	high.free()
	pilot.refresh_all()
	await process_frame

	second.rotation.y = PI * 0.5
	second.position = Vector3(8.0, 0.0, 0.0)
	pilot.refresh_all()
	await process_frame
	second_deck = pilot.get_node("GeneratedPreview/Bridge/WideBridge/BridgeDeck") as MeshInstance3D
	_expect(second_deck.get_aabb().size.x > 4.9 and second_deck.get_aabb().size.z > 7.9,
		"moving and rotating a bridge rebuilds its saved endpoint transform")

	var duplicate := first.duplicate() as Node3D
	duplicate.name = "BridgeCopy"
	duplicate.position.z = -8.0
	duplicate.width = 4.0
	bridges.add_child(duplicate)
	_set_owner_tree(duplicate, pilot)
	_expect(first.width == 2.0 and duplicate.width == 4.0,
		"a duplicated bridge owns an independent width value")
	pilot.refresh_all()
	await process_frame
	_expect(pilot.has_node("GeneratedPreview/Bridge/BridgeCopy/BridgeDeck"),
		"a duplicated bridge participates in generated geometry")

	var packed := PackedScene.new()
	_expect(packed.pack(pilot) == OK, "multiple bridges can be packed")
	_expect(ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"multiple bridge controls can be saved")
	var reopened_scene := ResourceLoader.load(RELOAD_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate()
	var reopened_first := reopened.get_node("AuthoredControls/Bridges/Bridge")
	var reopened_copy := reopened.get_node("AuthoredControls/Bridges/BridgeCopy")
	_expect(reopened_first.width == 2.0 and reopened_copy.width == 4.0,
		"each bridge width survives save and reload independently")
	reopened.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(RELOAD_PATH))

	second.free()
	pilot.refresh_all()
	await process_frame
	_expect(not pilot.has_node("GeneratedPreview/Bridge/WideBridge"),
		"deleting one authored bridge removes only its generated span")

	first.get_node("End").position = first.get_node("Start").position
	pilot.refresh_all()
	await process_frame
	_expect(not pilot.has_node("GeneratedPreview/Bridge/Bridge"),
		"a coincident-endpoint bridge is skipped")
	_expect(_contains_warning(pilot.call("_get_configuration_warnings"), "distinct"),
		"a coincident-endpoint bridge has a clear authoring warning")

	first.free()
	duplicate.free()
	pilot.refresh_all()
	await process_frame
	_expect((pilot.get_node("GeneratedPreview/Bridge") as Node3D).get_child_count() == 0 and
		pilot.call("_encoded_floor", 0.0, 0.0) == 0,
		"an empty Bridges container produces no phantom default bridge")

	var incomplete := Node3D.new()
	incomplete.name = "Incomplete"
	incomplete.set_script(BRIDGE_SCRIPT)
	bridges.add_child(incomplete)
	pilot.refresh_all()
	await process_frame
	_expect((pilot.get_node("GeneratedPreview/Bridge") as Node3D).get_child_count() == 0 and
		_contains_warning(pilot.call("_get_configuration_warnings"), "Start and End"),
		"a bridge missing endpoints is warned about and skipped")

	print("map authoring pilot bridges/widths: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	pilot.queue_free()
	quit(_failures)


func _make_bridge(node_name: String, start_position: Vector3,
		end_position: Vector3, width: float) -> Node3D:
	var bridge := Node3D.new()
	bridge.name = node_name
	bridge.set_script(BRIDGE_SCRIPT)
	bridge.width = width
	var start := Marker3D.new()
	start.name = "Start"
	start.position = start_position
	bridge.add_child(start)
	var end := Marker3D.new()
	end.name = "End"
	end.position = end_position
	bridge.add_child(end)
	return bridge


func _set_owner_tree(node: Node, scene_owner: Node) -> void:
	node.owner = scene_owner
	for child in node.get_children():
		_set_owner_tree(child, scene_owner)


func _contains_warning(warnings: PackedStringArray, fragment: String) -> bool:
	for warning in warnings:
		if fragment in warning:
			return true
	return false


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
