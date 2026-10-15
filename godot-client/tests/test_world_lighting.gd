extends SceneTree
## Guards the manifest-driven lighting rig.
##
## `LightMarkerBinder` was written, tested in isolation, and never called: the
## binder had no call site in the world-loaded handler, so every brazier, hearth and
## shrine lamp a map declared was silently dropped and `map_light_root` stayed
## null for the whole session. These assertions therefore drive the real
## world-loaded entry point rather than the binder directly.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var scene: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(scene)
	await process_frame

	scene.call("_on_world_loaded", _manifest([
		{"id": "Light_Brazier_a", "position": [1.0, 2.0, 3.0],
			"color": [1.0, 0.69, 0.4], "energyHint": 2.1, "rangeHint": 12.5},
		{"id": "Light_Brazier_b", "position": [-4.0, 0.5, 6.0]}]))
	await process_frame
	var rig: Node3D = scene.get("map_light_root") as Node3D
	_expect(rig != null and rig.get_child_count() == 2,
		"loading a world binds every manifest marker light into the scene")
	if rig != null and rig.get_child_count() == 2:
		_expect(rig.get_parent() == scene.get("world_root"),
			"marker lights are parented to the gameplay world root")
		var first: OmniLight3D = rig.get_child(0) as OmniLight3D
		_expect(first != null and first.name == "Light_Brazier_a"
			and first.position.is_equal_approx(Vector3(1.0, 2.0, 3.0))
			and is_equal_approx(first.light_energy, 2.1)
			and is_equal_approx(first.omni_range, 12.5)
			and first.light_color.is_equal_approx(Color(1.0, 0.69, 0.4)),
			"a bound marker keeps its declared name, position, energy, range, and colour")
		var second: OmniLight3D = rig.get_child(1) as OmniLight3D
		_expect(second != null
			and is_equal_approx(second.light_energy, LightMarkerBinder.DEFAULT_ENERGY)
			and is_equal_approx(second.omni_range, LightMarkerBinder.DEFAULT_RANGE),
			"a marker without hints falls back to the documented brazier defaults")
		_expect(not first.shadow_enabled and not second.shadow_enabled,
			"marker fill lights do not pay for shadow maps")

	# A second load must replace the rig rather than accumulate lights.
	scene.call("_on_world_loaded", _manifest([
		{"id": "Light_Only", "position": [0.0, 1.0, 0.0]}]))
	await process_frame
	var replaced: Node3D = scene.get("map_light_root") as Node3D
	_expect(replaced != null and replaced.get_child_count() == 1,
		"loading a second world replaces the previous marker rig")

	# A map that declares no markers must leave nothing behind.
	scene.call("_on_world_loaded", _manifest([]))
	await process_frame
	_expect(scene.get("map_light_root") == null,
		"a world declaring no markers leaves no marker light rig behind")
	var world_root: Node3D = scene.get("world_root") as Node3D
	var leftover := 0
	for child: Node in world_root.get_children():
		if child.name == "MapLights":
			leftover += 1
	_expect(leftover == 0, "the empty rig node is not left parked in the world")

	print("world lighting tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	scene.queue_free()
	await process_frame
	quit(failures)

func _manifest(markers: Array) -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.data = {
		"schemaVersion": "1.0",
		"asset": {"id": "light_marker_probe", "name": "Light Marker Probe",
			"glb": "world.glb", "units": "meters",
			"coordinateSystem": {"upAxis": "Y"}, "bounds": {}},
		"lighting": {"markers": markers}}
	return manifest

func _expect(value: bool, label: String) -> void:
	if value:
		return
	failures += 1
	push_error("FAIL: " + label)
