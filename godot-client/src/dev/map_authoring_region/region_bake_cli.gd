extends SceneTree

const REGION_SCRIPT := preload("res://src/dev/map_authoring_region/region_control.gd")


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var options := _options(OS.get_cmdline_user_args())
	var scene_path := String(options.get("scene", ""))
	var output_path := String(options.get("output", ""))
	if scene_path.is_empty() or output_path.is_empty():
		push_error("Usage: --script region_bake_cli.gd -- --scene res://...tscn --output <path>/continent-authoring.json")
		quit(2)
		return
	var packed := ResourceLoader.load(scene_path, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	if packed == null:
		push_error("Could not load authoring scene: %s" % scene_path)
		quit(2)
		return
	var instance := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE) as Node3D
	if instance == null or not instance.has_method("export_snapshot"):
		push_error("Authoring scene root must use MapAuthoringRegion: %s" % scene_path)
		if instance != null:
			instance.free()
		quit(2)
		return
	root.add_child(instance)
	await process_frame
	var document: Dictionary = instance.call("export_snapshot", output_path)
	if document.is_empty():
		push_error(String(instance.get("last_export_status")))
		quit(1)
		return
	print("continent_authoring_bake_ok region=", document.regionId,
		" output=", ProjectSettings.globalize_path(output_path),
		" sha256=", FileAccess.get_sha256(ProjectSettings.globalize_path(output_path)))
	quit(0)


func _options(arguments: PackedStringArray) -> Dictionary:
	var result := {}
	var index := 0
	while index < arguments.size():
		var argument := arguments[index]
		if argument in ["--scene", "--output"] and index + 1 < arguments.size():
			result[argument.trim_prefix("--")] = arguments[index + 1]
			index += 2
		else:
			index += 1
	return result
