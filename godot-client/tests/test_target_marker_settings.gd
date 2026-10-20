extends SceneTree
## Exercise real settings signals, persistence, existing actors and lazy targets.
const Style := preload("res://src/actors/target_marker_style.gd")
const SETTINGS_PATH := "user://eloria_hud.cfg"
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	root.size = Vector2i(1280, 720)
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var original := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings else PackedByteArray()
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var window: Variant = main.settings_window
	window.open_tab("Banners")
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config: Dictionary = models.dire_wolf
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var actor := ReplicatedActor3D.new()
	main.world_root.add_child(actor)
	expect(actor.configure({"actor_id": 2, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
		"x": 0, "y": 0, "rotation": 0}, CoordinateAdapter.new(), config, mapping).is_empty(), "production creature imports")
	actor.set_process(false)
	actor.set_physics_process(false)
	main.actor_nodes = {2: actor}
	(window.panel.find_child("target_markers_reset", true, false) as Button).pressed.emit()
	actor.set_selected(true)
	actor.set_combat_target(true)
	var marker := actor.get_node("CombatTargetMarker")
	expect(marker.pointer.font_size == 48, "default triangle is 50% larger than the previous 32 px glyph")
	expect(not actor.get_node("SelectionRing").visible, "selected combat target shows one ground shape")
	var authoritative := actor.transform
	var capsule := actor.get_node("SelectionCollision") as CollisionShape3D
	var capsule_radius: float = capsule.shape.radius
	var footprint := actor.footprint
	var initial_ring_size: Vector3 = marker.ring.mesh.get_aabb().size
	var initial_square_size: Vector3 = actor.get_node("SelectionRing").mesh.get_aabb().size
	var values := {"circle_size": 150.0, "circle_thickness": 175.0, "circle_color": Color("32cfe6"),
		"square_size": 125.0, "square_thickness": 200.0, "square_color": Color("6e94ff"),
		"triangle_size": 175.0, "triangle_thickness": 150.0, "triangle_color": Color("ef85ee")}
	for key: String in values:
		var control := window.panel.find_child("target_" + key, true, false) as Control
		expect(control != null and window.tab_index_for(control) == window.tabs.get_current_tab(), "Banners exposes " + key)
		if control is ColorPickerButton:
			(control as ColorPickerButton).color = values[key]
			(control as ColorPickerButton).color_changed.emit(values[key])
		else:
			(control as SpinBox).value = values[key]
		expect(main._target_marker_style[key] == values[key], "correct setting signal applies " + key)
		var saved := ConfigFile.new()
		expect(saved.load(SETTINGS_PATH) == OK and saved.get_value(Style.SECTION, key) == values[key], "immediately persists " + key)
	expect(marker.ring.mesh.get_aabb().size.x > initial_ring_size.x * 1.4, "existing combat circle resizes immediately")
	expect(marker.pointer.font_size == 84 and marker.pointer.outline_size == 16, "triangle size and outline apply independently")
	expect(marker.pointer.modulate == values.triangle_color, "triangle color applies to an existing marker")
	var colors: PackedColorArray = marker.ring.mesh.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
	expect(values.circle_color in colors, "circle uses the selected color")
	var square := actor.get_node("SelectionRing") as MeshInstance3D
	var selection_colors: PackedColorArray = square.mesh.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
	expect(values.square_color in selection_colors and Color.BLACK in selection_colors, "tentative circle retains its color and black border while hidden")
	expect(square.mesh.get_aabb().size.x > initial_square_size.x * 1.2, "tentative circle size updates while hidden")
	actor.set_combat_target(false)
	expect(square.visible, "combat end restores the styled tentative circle")
	expect(actor.transform == authoritative and actor.footprint == footprint and capsule.shape.radius == capsule_radius,
		"marker styling preserves server placement, footprint and picking")
	main._target_marker_style = Style.defaults()
	main._load_hud_settings()
	expect(main._target_marker_style == values, "saved appearance reloads")
	for key: String in values:
		var control: Variant = window.panel.find_child("target_" + key, true, false)
		expect(control.color == values[key] if control is ColorPickerButton else control.value == values[key], "UI restores " + key)
	var late := ReplicatedActor3D.new()
	main.world_root.add_child(late)
	expect(late.configure({"actor_id": 3, "kind": 5, "x": 2, "y": 0, "rotation": 0}, CoordinateAdapter.new(), config, mapping).is_empty(), "later creature imports")
	late.set_target_marker_style(main._target_marker_style)
	late.set_combat_target(true)
	expect(late.get_node("CombatTargetMarker").pointer.font_size == 84, "lazy marker inherits current appearance")
	# Identical appearance values must produce identical geometry for tentative
	# and confirmed targets, including late footprint updates and size extremes.
	for size_percent: float in [50.0, 100.0, 200.0]:
		for thickness_percent: float in [25.0, 100.0, 300.0]:
			late.set_target_marker_style({"circle_size": size_percent, "square_size": size_percent,
				"circle_thickness": thickness_percent, "square_thickness": thickness_percent})
			for span: Vector2i in [Vector2i.ONE, Vector2i(2, 2), Vector2i(2, 3)]:
				late.set_footprint(span)
				var tentative: ArrayMesh = late.get("_selection_ring_flat")
				var active: ArrayMesh = late.get_node("CombatTargetMarker").get("_flat")
				var a: PackedVector3Array = tentative.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
				var b: PackedVector3Array = active.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
				expect(a == b, "both circles share footprint, size and thickness rules")
				var tint: PackedColorArray = tentative.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
				expect(Color.BLACK in tint and Style.DEFAULTS.square_color in tint, "tentative ring has yellow fill and black inner/outer borders")
				expect(a.size() > 100, "tentative marker is a tessellated circle rather than four straight sides")
	expect((late.get_node("SelectionRing").material_override as StandardMaterial3D).albedo_color == Color.WHITE,
		"selection material preserves vertex colors without tinting its border")
	# Invalid file values cannot create inverted geometry or invisible pointers.
	var invalid := Style.normalise({"circle_size": NAN, "square_size": -100, "triangle_size": 1e8,
		"circle_thickness": "bad", "triangle_color": "invalid"})
	expect(invalid.circle_size == 100 and invalid.square_size == 50 and invalid.triangle_size == 300
		and invalid.circle_thickness == 100 and invalid.triangle_color == Style.DEFAULTS.triangle_color, "invalid settings clamp or fall back")
	actor.set_target_marker_style({"circle_size": 50, "circle_thickness": 300, "square_size": 50, "square_thickness": 300})
	actor.set_combat_target(true)
	var vertices: PackedVector3Array = marker.ring.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for vertex: Vector3 in vertices:
		expect(vertex.is_finite() and Vector2(vertex.x, vertex.z).length() > 0.01, "extreme circle stays finite and open")
	(window.panel.find_child("target_markers_reset", true, false) as Button).pressed.emit()
	expect(main._target_marker_style == Style.defaults() and marker.pointer.font_size == 48, "reset restores every default immediately")
	if DisplayServer.get_name() != "headless":
		main.login_panel.hide()
		main.creation_panel.hide()
		main.get_node("LoginBackground").hide()
		main.game_view.show()
		for frame: int in 4: await process_frame
		await RenderingServer.frame_post_draw
		var out := "res://test-artifacts/target-markers"
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out))
		expect(root.get_texture().get_image().save_png(ProjectSettings.globalize_path(out + "/settings.png")) == OK, "settings screenshot saved")
		root.size = Vector2i(900, 600)
		main._on_ui_scale_changed(1.5)
		for frame: int in 4: await process_frame
		var grid := window.panel.find_child("TargetMarkerControls", true, false) as GridContainer
		expect(grid.columns == 1, "narrow settings stack marker controls")
		await RenderingServer.frame_post_draw
		expect(root.get_texture().get_image().save_png(ProjectSettings.globalize_path(out + "/settings-narrow.png")) == OK, "narrow settings screenshot saved")
	late.free()
	main.actor_nodes = {}
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		expect(file != null, "settings backup can be restored")
		if file != null:
			file.store_buffer(original)
			file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("TARGET_MARKER_SETTINGS ", "PASS" if failures == 0 else "FAIL", " checks=", checks, " failures=", failures)
	quit(1 if failures else 0)
