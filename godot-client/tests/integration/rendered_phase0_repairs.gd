extends SceneTree
## Rendered before/after evidence for the Phase 0 repairs whose only meaningful
## proof is a capture.
##
## 0.1 marker lights: an interior's whole light rig is its manifest markers, so
## the pair is the same chamber with the binder skipped and with it applied -
## which is exactly the difference between the shipped client and the fixed one.
##
## 0.8 diagnostics panel: the console panel with its message history and with
## the protocol diagnostics view, after feeding the reducer one undecoded
## opcode and one packet that fails to decode.
##
## Every frame is checked for real colour variation, so a dummy or black frame
## cannot pass as evidence.

const INTERIOR := "res://../eloria-assets/maps/nymara-regions/interiors/sunmane_wind_caves/world.json"
const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase0")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	await _render_marker_lights()
	await _render_diagnostics_panel()
	await _render_server_popup()
	await _render_harvest_targets()
	await _render_reading_window()
	print("rendered phase 0 repairs: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _render_marker_lights() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var camera := Camera3D.new()
	camera.far = 400.0
	camera.fov = 62.0
	camera.current = true
	stage.add_child(camera)
	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	stage.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(INTERIOR))
	var deadline: int = Time.get_ticks_msec() + 120000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, "the interior package imports"):
		stage.queue_free()
		return
	_expect(WorldEnvironmentBinder.apply(loader.manifest, world_environment, sun),
		"the manifest environment binds")

	# Frame the chamber that holds the most declared markers, so the pair is
	# taken where the difference is the whole point.
	var markers: Array = (loader.manifest.data.get("lighting", {}) as Dictionary).get(
		"markers", []) as Array
	_expect(markers.size() > 0, "the interior declares marker lights at all")
	var centre := Vector3.ZERO
	for raw: Variant in markers:
		var position: Array = (raw as Dictionary).get("position", []) as Array
		if position.size() >= 3:
			centre += Vector3(float(position[0]), float(position[1]), float(position[2]))
	centre /= maxf(1.0, float(markers.size()))
	camera.global_position = centre + Vector3(0.0, 1.65, 9.0)
	camera.look_at(centre + Vector3(0.0, 1.0, 0.0), Vector3.UP)

	for _settle: int in range(8):
		await process_frame
	await _capture("marker-lights-before.png",
		"the interior with the marker binder skipped, as the client shipped")

	var rig := Node3D.new()
	rig.name = "MapLights"
	stage.add_child(rig)
	var bound: int = LightMarkerBinder.apply(loader.manifest, rig)
	_expect(bound == markers.size(),
		"every declared marker becomes a light: %d of %d" % [bound, markers.size()])
	for _settle: int in range(8):
		await process_frame
	await _capture("marker-lights-after.png",
		"the same chamber with the manifest markers bound")
	stage.queue_free()
	await process_frame

func _render_diagnostics_panel() -> void:
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	var game_view: Control = main.get_node("GameView") as Control
	game_view.show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.call("append_local_message",
		"Console history: the message log this panel has always shown.", 3)
	app_state.call("append_local_message",
		"Protocol diagnostics are one click away in the header.", 3)
	main.call("_toggle_console")
	for _settle: int in range(4):
		await process_frame
	await _capture("console-history.png",
		"the console panel showing its session message history")

	# One opcode this client does not decode, twice, and one packet that fails
	# to decode: a pre-0.6 single-byte trade acceptance.
	app_state.call("_on_packet", 199, PackedByteArray([1, 2, 3]))
	app_state.call("_on_packet", 199, PackedByteArray([4]))
	app_state.call("_on_packet", 36, PackedByteArray([0]))
	var diagnostics_button: Button = main.get_node(
		"GameView/ConsolePanel/Content/Header/ConsoleDiagnostics") as Button
	diagnostics_button.button_pressed = true
	for _settle: int in range(4):
		await process_frame
	var diagnostics_output: RichTextLabel = main.get_node(
		"GameView/ConsolePanel/Content/DiagnosticsOutput") as RichTextLabel
	_expect(diagnostics_output.visible
		and diagnostics_output.text.contains("199")
		and diagnostics_output.text.contains("trade_accept_length"),
		"the rendered diagnostics view names the undecoded opcode and the decode error")
	await _capture("console-diagnostics.png",
		"the same panel showing undecoded opcodes and recent decode errors")
	main.queue_free()
	await process_frame

## The server had no way to ask the player a question at all, so the "before"
## half of this pair is the world with nothing on it: there is no earlier
## rendering of a popup to compare against.
func _render_server_popup() -> void:
	var main: Node = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	# The bytes protocol.summon_behavior_popup() actually builds.
	app_state.call("_on_packet", 83, _hex_bytes(
		"0000000f53756d6d6f6e204265686176696f7268013943686f6f736520686f7720796f7572"
		+ "2073756d6d6f6e6564206372656174757265732073686f756c642073656c6563742074617267"
		+ "6574732e09010d446f206e6f742061747461636b0109011241747461636b206d79206f70706f"
		+ "6e656e7400090119446f206e6f742061747461636b206d79206f70706f6e656e740209011e41"
		+ "747461636b206f6e6c792073756d6d6f6e65642063726561747572657303090120446f206e6f"
		+ "742061747461636b2073756d6d6f6e6564206372656174757265730409010e41747461636b20"
		+ "61742077696c6c05"))
	for _settle: int in range(4):
		await process_frame
	var panel: Control = main.get_node("GameView/PopupPanel") as Control
	_expect(panel.visible, "the popup window is on screen")
	var options: Control = main.get_node(
		"GameView/PopupPanel/PopupContent/PopupOptions") as Control
	_expect(options.get_child_count() == 6,
		"all six behaviour options are presented")
	await _capture("server-popup.png",
		"the server's summon-behaviour popup, decoded from its real bytes")
	app_state.call("close_popup")
	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame

## The world-object pick layer. Before this the client had no pick path for
## rendered props at all, so the "before" half is the same view with the layer
## suppressed: no ring, nothing clickable, no indicator.
func _render_harvest_targets() -> void:
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)

	var stage: Node3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot") as Node3D
	var ground := MeshInstance3D.new()
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(30.0, 30.0)
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.29, 0.35, 0.24)
	ground_mesh.material = ground_material
	ground.mesh = ground_mesh
	stage.add_child(ground)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, 38.0, 0.0)
	stage.add_child(sun)
	var camera: Camera3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera") as Camera3D

	# Two harvest nodes and one interactive, on the tiles the server named.
	var payload := PackedByteArray([1, 3, 0])
	payload.append_array(PackedByteArray([0xf0, 0x01, 1, 0x02, 0x03, 0xe1, 0x01]))
	payload.append_array(_nul("Sunleaf"))
	payload.append_array(_nul("Harvesting level 0"))
	payload.append_array(PackedByteArray([0xf1, 0x01, 1, 0x05, 0x03, 0xe4, 0x01]))
	payload.append_array(_nul("Reed"))
	payload.append_array(_nul("Harvesting level 4"))
	payload.append_array(PackedByteArray([0x0e, 0x00, 2, 0x00, 0x03, 0xdf, 0x01]))
	payload.append_array(_nul("Storage"))
	payload.append_array(_nul("A wayfarer's cache."))
	app_state.call("_on_packet", 236, payload)
	for _settle: int in range(6):
		await process_frame

	var nodes: Dictionary = main.get("map_object_nodes") as Dictionary
	_expect(nodes.size() == 3, "three world objects became pick targets")
	var centre := Vector3.ZERO
	for raw: Variant in nodes.values():
		centre += (raw as Node3D).global_position
	centre /= maxf(1.0, float(nodes.size()))
	camera.global_position = centre + Vector3(0.0, 4.4, 6.4)
	camera.look_at(centre, Vector3.UP)
	for _settle: int in range(4):
		await process_frame
	await _capture("harvest-targets-idle.png",
		"the server's world objects as pick targets: harvest nodes and an interactive")

	var started := PackedByteArray([1, 0xf0, 0x01])
	started.append_array(_nul("Sunleaf"))
	app_state.call("_on_packet", 237, started)
	for _settle: int in range(4):
		await process_frame
	var banner: Label = main.get_node("GameView/HarvestBanner") as Label
	_expect(banner.visible and banner.text.contains("Sunleaf"),
		"the harvesting indicator names the resource")
	await _capture("harvest-targets-active.png",
		"the same view while the server reports harvesting the first node")
	app_state.call("_on_packet", 237, PackedByteArray([0, 0, 0, 0]))
	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame

## The reading window. Reading a book had no presentation at all: the three
## research statistics arrived and nothing read them, so a player researching a
## book could not see that they were.
func _render_reading_window() -> void:
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	# Partial statistics 47/65/66: the book, pages done, pages total.
	app_state.call("_on_packet", 49, PackedByteArray([
		47, 0, 0, 0, 0, 65, 150, 0, 0, 0, 66, 88, 2, 0, 0]))
	for _settle: int in range(4):
		await process_frame
	var panel: Control = main.get_node("GameView/ReadingPanel") as Control
	_expect(panel.visible, "the reading window is on screen")
	await _capture("reading-progress.png",
		"reading a book, driven by the authoritative research statistics")
	app_state.call("_on_packet", 56, PackedByteArray([0, 0]))
	app_state.call("_on_packet", 49, PackedByteArray([
		47, 0, 4, 0, 0, 65, 0, 0, 0, 0, 66, 0, 0, 0, 0]))
	for _settle: int in range(4):
		await process_frame
	_expect(panel.visible, "the completed window is on screen")
	await _capture("reading-complete.png",
		"the same window once the server grants the knowledge")
	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame

func _nul(value: String) -> PackedByteArray:
	var bytes: PackedByteArray = value.to_utf8_buffer()
	bytes.append(0)
	return bytes

func _hex_bytes(value: String) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index: int in range(0, value.length(), 2):
		bytes.append(value.substr(index, 2).hex_to_int())
	return bytes

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description,
		"  mean_luminance=", "%.4f" % _mean_luminance(image))

func _mean_luminance(image: Image) -> float:
	var total := 0.0
	var samples := 0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			total += image.get_pixel(x, y).get_luminance()
			samples += 1
	return total / maxf(1.0, float(samples))

func _has_colour_variation(image: Image) -> bool:
	var first: Color = image.get_pixel(0, 0)
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			if not image.get_pixel(x, y).is_equal_approx(first):
				return true
	return false

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
