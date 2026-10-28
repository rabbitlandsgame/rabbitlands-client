extends SceneTree
## Two actual client actors, sharing playback time and an orbit camera.

var clips := ["Idle_A", "Fighting_Idle", "Walk", "Jog", "Gallop", "Sword_Attack", "Hit_Chest", "Death_A"]
class InputRelay extends Node:
	var callback: Callable
	func _input(event: InputEvent) -> void: callback.call(event)
var actors: Array[ReplicatedActor3D] = []
var players: Array[AnimationPlayer] = []
var cameras: Array[Camera3D] = []
var viewports: Array[SubViewport] = []
var panes: Array[SubViewportContainer] = []
var clip_picker: OptionButton
var timeline: HSlider
var time_label: Label
var pause_button: Button
var repeat_actions: CheckBox
var blend: CheckBox
var running := true
var speed := 1.0
var yaw := 2.2
var pitch := 0.18
var distance := 3.0
var focus := Vector3(0, 0.6, 0)
var default_focus := Vector3(0, 0.6, 0)
var default_distance := 3.0
var dragging := false
var ready_to_play := false
var closing := false
var job: Dictionary
var clip := "Walk"
var clock := 0.0

func _initialize() -> void:
	call_deferred("run")

func label_for(text: String, size := 18) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	return label

func button_for(text: String, parent: Node, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("Launch with eloria-assets/tools/preview_creature_sampling.py so the comparison inputs are hash checked.")
		quit(1)
		return
	job = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	clips.assign(job.clips)
	if not clips.has(clip): clip = clips[0]
	root.title = job.get("title", "Rabbit Lands | %s comparison | %d FPS draft" % [job.display_name, int(job.fps)])
	set_auto_accept_quit(false)
	root.close_requested.connect(close_preview)
	root.size = Vector2i(1440, 920)
	Engine.max_fps = 240
	var input_relay := InputRelay.new()
	input_relay.callback = handle_input
	root.add_child(input_relay)
	var background := ColorRect.new()
	background.color = Color("141d28")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	root.add_child(margin)
	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 12)
	margin.add_child(layout)
	layout.add_child(label_for(job.get("heading", "%s  /  %d FPS animation draft" % [job.display_name, int(job.fps)]), 25))
	layout.add_child(label_for(job.get("description", "Same model, materials and corrective shapes. Both actors share time, speed and camera. Draft awaits your review."), 16))
	var row := HBoxContainer.new()
	layout.add_child(row)
	row.add_child(label_for("Animation  "))
	clip_picker = OptionButton.new()
	for name in clips: clip_picker.add_item(name.replace("_", " "))
	clip_picker.select(clips.find(clip))
	clip_picker.item_selected.connect(func(index: int): select_clip(clips[index]))
	row.add_child(clip_picker)
	pause_button = button_for("Pause", row, toggle_pause)
	button_for("Restart", row, func(): seek_both(0.0))
	row.add_child(label_for("   Speed  "))
	var speed_picker := OptionButton.new()
	for value in [0.1, 0.25, 0.5, 1.0, 2.0]: speed_picker.add_item(str(value) + "x")
	speed_picker.select(3)
	speed_picker.item_selected.connect(func(index: int): speed = [0.1, 0.25, 0.5, 1.0, 2.0][index])
	row.add_child(speed_picker)
	blend = CheckBox.new()
	blend.text = "Blend switches (0.15 s)"
	blend.button_pressed = true
	row.add_child(blend)
	repeat_actions = CheckBox.new()
	repeat_actions.text = "Repeat one-shots"
	row.add_child(repeat_actions)
	var panels := HBoxContainer.new()
	panels.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_theme_constant_override("separation", 12)
	layout.add_child(panels)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config: Dictionary = models[str(job.actor)]
	var animation_map: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	# Inspection also exposes retained clips not used by the current gameplay map.
	for index in clips.size(): animation_map.actions["__preview_native_" + str(index)] = clips[index]
	for index in 2:
		var fixture: Dictionary = job.models[index]
		if FileAccess.get_sha256(str(fixture.path)) != str(fixture.sha256):
			push_error("Comparison input changed: " + str(fixture.path)); quit(1); return
		var column := VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		panels.add_child(column)
		column.add_child(label_for(str(fixture.label), 22))
		var container := SubViewportContainer.new()
		container.size_flags_vertical = Control.SIZE_EXPAND_FILL
		container.stretch = true
		container.custom_minimum_size = Vector2(300, 350)
		container.gui_input.connect(orbit_input)
		column.add_child(container)
		panes.append(container)
		var viewport := SubViewport.new()
		viewport.own_world_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		container.add_child(viewport)
		viewports.append(viewport)
		var stage := make_stage(viewport)
		var path := str(fixture.path)
		# Force the production native actor path for both files, including the
		# asset-declared bake cadence. Do not depend on an existing editor cache.
		var packed := GlbSceneCache._build_raw(path)
		if packed == null: push_error("Could not load " + path); quit(1); return
		GlbSceneCache.install_prepared({path: packed})
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var local_config := config.duplicate(true)
		local_config.scene = path
		local_config.animationLibrary = path
		var errors := actor.configure({"actor_id": index + 1, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
			"name": "", "x": 0, "y": 0, "rotation": 0, "health": 100, "max_health": 100,
			"appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"metresPerTile": 1.0}), local_config, animation_map)
		if not errors.is_empty(): push_error(str(errors)); quit(1); return
		actor.position = Vector3.ZERO
		actor.rotation = Vector3.ZERO
		if index == 0:
			var model := actor.get_node("NativeModel") as Node3D
			var bounds: AABB = model.global_transform * actor._native_body_bounds
			default_focus = bounds.get_center(); focus = default_focus
			default_distance = maxf(3.0, bounds.size.length() * 1.3); distance = default_distance
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.set_health_visible(false)
		# The preview owns end holds; gameplay's automatic finished->idle
		# callback would prevent inspecting the one-shot endpoint.
		var player := actor.animation_player
		if player.animation_finished.is_connected(actor._on_animation_finished):
			player.animation_finished.disconnect(actor._on_animation_finished)
		for node in actor.find_children("*", "AnimationPlayer", true, false):
			(node as AnimationPlayer).callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		actors.append(actor)
		players.append(player)
	column_footer(layout)
	var scrub := HBoxContainer.new()
	layout.add_child(scrub)
	timeline = HSlider.new()
	timeline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	timeline.step = 0.0001
	timeline.value_changed.connect(func(value: float): seek_both(value))
	scrub.add_child(timeline)
	time_label = label_for("", 17)
	time_label.custom_minimum_size.x = 190
	scrub.add_child(time_label)
	var views := HBoxContainer.new()
	layout.add_child(views)
	button_for("Front", views, func(): yaw = PI; pitch = 0.18; update_cameras())
	button_for("Side", views, func(): yaw = PI / 2; pitch = 0.12; update_cameras())
	button_for("Rear", views, func(): yaw = 0.0; pitch = 0.18; update_cameras())
	button_for("Above", views, func(): pitch = 1.0; update_cameras())
	button_for("Reset camera", views, func(): yaw = 2.2; pitch = 0.18; distance = default_distance; focus = default_focus; update_cameras())
	views.add_child(label_for("   Drag either model to orbit  |  Wheel: zoom  |  Space: pause  |  Arrows: animation", 16))
	if job.has("review_points"):
		var review_row := HBoxContainer.new()
		layout.add_child(review_row)
		review_row.add_child(label_for("Inspect measured differences:  ", 16))
		for point: Dictionary in job.review_points:
			button_for(str(point.caption), review_row, inspect_point.bind(point))
	ready_to_play = true
	select_clip(clip)
	update_cameras()
	print("CREATURE_COMPARISON_READY; actual ReplicatedActor3D + native importer")
	if "--smoke" in args: await smoke_test()

func column_footer(layout: VBoxContainer) -> void:
	layout.add_child(label_for(str(job.get("summary", "")), 16))
	if job.has("runtime_summary"): layout.add_child(label_for(str(job.runtime_summary), 14))

func make_stage(viewport: SubViewport) -> Node3D:
	var stage := Node3D.new()
	viewport.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("263443")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("c2d0e1")
	world.environment.ambient_light_energy = 0.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-50, -35, 0)
	light.light_energy = 1.4
	stage.add_child(light)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("45535c")
	plane.material = material
	floor_mesh.mesh = plane
	stage.add_child(floor_mesh)
	var camera := Camera3D.new()
	camera.fov = 38
	camera.near = 0.02
	stage.add_child(camera)
	camera.current = true
	cameras.append(camera)
	return stage

func select_clip(name: String) -> void:
	clip = name
	clip_picker.select(clips.find(name))
	clock = 0.0
	for player in players:
		assert(player.has_animation(clip))
		var restarting := player.assigned_animation == clip
		if restarting: player.stop()
		player.play(clip, 0.15 if blend.button_pressed and running and not restarting else 0.0)
		player.advance(0.0)
	timeline.max_value = players[0].get_animation(clip).length
	refresh_time()

func seek_both(value: float) -> void:
	clock = value
	# Scrubbing selects an absolute pose; clear an unfinished crossfade first.
	for player in players:
		player.play("RESET", 0.0)
		player.seek(0.0, true)
		player.play(clip, 0.0)
		player.seek(clock, true)
	for actor in actors: actor.get_skeleton().force_update_all_bone_transforms()
	refresh_time()

func refresh_time() -> void:
	if timeline == null: return
	timeline.set_value_no_signal(clock)
	time_label.text = " %.4f / %.4f s" % [clock, timeline.max_value]

func toggle_pause() -> void:
	running = not running
	pause_button.text = "Pause" if running else "Play"

func update_cameras() -> void:
	var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	for camera in cameras: camera.look_at_from_position(focus + offset, focus)

func inspect_point(point: Dictionary) -> void:
	running = false
	pause_button.text = "Play"
	select_clip(str(point.clip))
	seek_both(float(point.time))
	var target: Array = point.get("focus", [default_focus.x, default_focus.y, default_focus.z])
	focus = Vector3(float(target[0]), float(target[1]), float(target[2]))
	yaw = 2.2; pitch = 0.15; distance = maxf(1.0, default_distance * 0.6)
	update_cameras()

func orbit_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT or event.button_index == MOUSE_BUTTON_RIGHT: dragging = event.pressed
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP: distance = maxf(0.8, distance * 0.9)
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN: distance = minf(12, distance / 0.9)
	if event is InputEventMouseMotion and dragging:
		yaw -= event.relative.x * 0.008
		pitch = clampf(pitch + event.relative.y * 0.006, -0.2, 1.45)
	update_cameras()

func handle_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and not event.pressed: dragging = false
	if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_SPACE:
		toggle_pause()
		root.set_input_as_handled()
	if event.keycode in [KEY_LEFT, KEY_RIGHT]:
		var index := posmod(clips.find(clip) + (1 if event.keycode == KEY_RIGHT else -1), clips.size())
		clip_picker.select(index)
		select_clip(clips[index])
		root.set_input_as_handled()

func _process(delta: float) -> bool:
	if ready_to_play and running:
		var length := players[0].get_animation(clip).length
		if clock >= length and repeat_actions.button_pressed: select_clip(clip)
		var step := delta * speed
		for player in players: player.advance(step)
		for actor in actors: actor.get_skeleton().force_update_all_bone_transforms()
		if players[0].get_animation(clip).loop_mode != Animation.LOOP_NONE:
			clock = fmod(clock + step, length)
		else: clock = minf(clock + step, length)
		refresh_time()
	return false

func close_preview() -> void:
	if closing: return
	closing = true
	ready_to_play = false
	for actor in actors: actor.queue_free()
	actors.clear()
	players.clear()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	quit()

func smoke_test() -> void:
	running = false
	pause_button.text = "Play"
	var output := str(job.output)
	DirAccess.make_dir_recursive_absolute(output)
	var records := []
	for name in clips:
		select_clip(name)
		seek_both(timeline.max_value * 0.47)
		for player in players: assert(player.current_animation == name)
		for frame in 3: await process_frame
		if DisplayServer.get_name() != "headless":
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(output.path_join(name + ".png"))
		records.append({"clip": name, "length": timeline.max_value, "synchronized_time": clock})
	if DisplayServer.get_name() != "headless":
		for point: Dictionary in job.get("review_points", []):
			inspect_point(point)
			for view in ["close", "side"]:
				if view == "side": yaw = PI / 2; update_cameras()
				for frame in 3: await process_frame
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png(output.path_join(str(point.id) + "-" + view + ".png"))
				for index in 2:
					viewports[index].get_texture().get_image().save_png(output.path_join(str(point.id) + "-" + view + "-" + str(index) + ".png"))
	# Exercise end hold, restoration, all directed switches and controls.
	for previous in clips:
		for following in clips:
			select_clip(previous); seek_both(timeline.max_value * 0.9)
			select_clip(following)
			for player in players: player.advance(0.075)
	select_clip("Death_A"); seek_both(timeline.max_value)
	for player in players: player.advance(0.1); assert(player.current_animation_position >= timeline.max_value - 0.001)
	repeat_actions.button_pressed = true
	running = true
	_process(1.0 / 240.0)
	for player in players: assert(player.current_animation_position < 0.005, "One-shot repeat did not restart")
	running = false
	repeat_actions.button_pressed = false
	select_clip("Idle_A"); seek_both(0.0)
	yaw = PI / 2; pitch = 0.3; distance = 2.8; update_cameras()
	var key := InputEventKey.new()
	key.keycode = KEY_RIGHT; key.pressed = true
	Input.parse_input_event(key)
	await process_frame
	assert(clip == clips[posmod(clips.find("Idle_A") + 1, clips.size())], "Keyboard animation input was not delivered")
	key = InputEventKey.new(); key.keycode = KEY_SPACE; key.pressed = true
	Input.parse_input_event(key)
	await process_frame
	assert(running, "Keyboard play/pause input was not delivered")
	Input.parse_input_event(key)
	await process_frame
	assert(not running)
	var old_yaw := yaw
	var center := panes[0].get_global_rect().get_center()
	var mouse := InputEventMouseButton.new()
	mouse.position = center; mouse.global_position = center
	mouse.button_index = MOUSE_BUTTON_LEFT; mouse.pressed = true
	Input.parse_input_event(mouse)
	await process_frame
	var motion := InputEventMouseMotion.new()
	motion.position = center + Vector2(50, 10); motion.global_position = motion.position
	motion.relative = Vector2(50, 10); motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(motion)
	await process_frame
	assert(yaw != old_yaw, "Dragging the pane did not orbit the cameras")
	mouse.pressed = false; Input.parse_input_event(mouse)
	var old_distance := distance
	mouse = InputEventMouseButton.new(); mouse.position = center; mouse.global_position = center
	mouse.button_index = MOUSE_BUTTON_WHEEL_UP; mouse.pressed = true
	Input.parse_input_event(mouse)
	await process_frame
	assert(distance < old_distance, "Mouse wheel did not zoom")
	FileAccess.open(output.path_join("preview-smoke.json"), FileAccess.WRITE).store_string(JSON.stringify({"clips": records, "directed_switches_exercised": clips.size() * clips.size(), "terminal_hold_and_idle_reset": true, "keyboard_mouse_orbit_zoom_input_delivered": true, "models": job.models, "renderer": RenderingServer.get_current_rendering_method()}, "  "))
	print("CREATURE_COMPARISON_SMOKE_PASS")
	await close_preview()
