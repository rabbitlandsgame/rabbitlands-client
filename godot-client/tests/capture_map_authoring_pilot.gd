extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")


func _init() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var pilot: Node = PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var arguments := OS.get_cmdline_user_args()
	if arguments.is_empty():
		var command_line := OS.get_cmdline_args()
		var mode_index := command_line.find("visual-controls")
		if mode_index >= 0:
			arguments = command_line.slice(mode_index)
	if arguments.is_empty() and OS.get_environment("ELORIA_CAPTURE_MODE") == "visual-controls":
		arguments.append("visual-controls")
		arguments.append(OS.get_environment("ELORIA_CAPTURE_PATH"))
	var controls_example := not arguments.is_empty() and arguments[0] == "visual-controls"
	if controls_example:
		var river := pilot.get_node("AuthoredControls/River") as Path3D
		var bent_river := Curve3D.new()
		bent_river.add_point(Vector3(0.0, 0.0, -24.0))
		bent_river.add_point(Vector3(0.0, 0.0, 0.0))
		bent_river.add_point(Vector3(10.0, 0.0, 12.0))
		bent_river.add_point(Vector3(10.0, 0.0, 24.0))
		river.curve = bent_river
		var handle := pilot.get_node("AuthoredControls/TerrainHeights").get_child(0) as Marker3D
		handle.position.y = float(handle.get("neutral_y")) + 2.5
		handle.set("influence_radius", 7.0)
		pilot.call("_detect_authored_changes")
	for unused in 12:
		await process_frame
	var destination := "res://docs/images/map-authoring-pilot.png"
	if controls_example:
		destination = "res://docs/images/map-authoring-controls.png"
		if arguments.size() > 1 and not arguments[1].is_empty():
			destination = arguments[1]
	var absolute_destination := ProjectSettings.globalize_path(destination)
	DirAccess.make_dir_recursive_absolute(absolute_destination.get_base_dir())
	var image := root.get_texture().get_image()
	var error := image.save_png(absolute_destination)
	if error != OK:
		push_error("map authoring pilot capture failed: %s" % error_string(error))
		quit(1)
		return
	print("map authoring pilot capture: ", absolute_destination)
	quit(0)
