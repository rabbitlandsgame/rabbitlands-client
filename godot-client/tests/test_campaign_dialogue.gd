extends SceneTree
## Headless layout/identity checks; --render DIR additionally captures real
## approved native NPC faces with the same unchanged live actor API.
const Dialogue := preload("res://src/ui/campaign_dialogue.gd")
var failures := 0
var checks := 0

class HeadActor extends Node3D:
	var skeleton: Skeleton3D
	func _init() -> void:
		skeleton = Skeleton3D.new()
		add_child(skeleton)
		skeleton.add_bone("Head")
		skeleton.set_bone_pose_position(0, Vector3(0, 1.7, 0))
	func get_skeleton() -> Skeleton3D:
		return skeleton

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Campaign dialogue proof timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var host := Control.new()
	host.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(host)
	var widget = Dialogue.new()
	host.add_child(widget)
	widget.size = Vector2(1200, 125)
	var stage := Node3D.new()
	root.add_child(stage)
	var actor := HeadActor.new()
	stage.add_child(actor)
	actor.position = Vector3(5, 3, 8)
	actor.rotation.y = 1.3
	var post := actor.global_transform
	var head_pose := actor.skeleton.get_bone_pose(0)
	widget.set_line("Odo Fenn", "Hold the approach. Tell me where you need me.", actor)
	await process_frame
	expect(widget.portrait_visible(), "a supplied native Head skeleton binds the framed portrait")
	expect(widget.speaker_label.text == "Odo Fenn" and widget.body_label.text.begins_with("Hold"), "speaker and dialogue have separate readable labels")
	expect(widget.speaker_label.get_theme_color("font_color") != widget.body_label.get_theme_color("font_color"), "the emphatic gold speaker differs from the white dialogue")
	expect(widget.subtitle_text() == "Odo Fenn: Hold the approach. Tell me where you need me.", "plain complete subtitles remain available")
	expect(widget._viewport.world_3d == actor.get_world_3d() and not widget._viewport.own_world_3d, "the portrait observes the actor's actual World3D")
	expect(widget._camera.cull_mask == 1, "nameplates, map dots and gameplay overlays are excluded from the head camera")
	var focus: Vector3 = actor.skeleton.global_transform * actor.skeleton.get_bone_global_pose(0).origin
	var offset: Vector3 = widget._camera.global_position - focus
	expect(offset.dot(-actor.global_basis.z) > 0.8, "the head camera follows the actor's own front instead of viewing its back")
	widget._elapsed = 0.012
	widget.set_line("Odo Fenn", "Hold the approach. Tell me where you need me.", actor)
	expect(is_equal_approx(widget._elapsed, 0.012), "unchanged per-frame lines retain the bounded portrait cadence")
	actor.rotation.y += PI
	widget._process(0.04)
	focus = actor.skeleton.global_transform * actor.skeleton.get_bone_global_pose(0).origin
	expect((widget._camera.global_position-focus).dot(-actor.global_basis.z) > 0.8, "a turned actor still has a frontal portrait")
	actor.global_transform = post
	expect(actor.skeleton.get_bone_pose(0) == head_pose, "portrait framing never writes the actor's native bone pose")
	widget.set_line("", "The boat reaches the quay.", actor)
	expect(not widget.portrait_visible() and not widget.speaker_label.visible, "narration has no fabricated headshot or speaker")
	expect(widget.subtitle_text() == "The boat reaches the quay.", "narration retains its full text")
	widget.set_line("Landing clerk", "This cargo was signed in yesterday.")
	expect(not widget.portrait_visible() and widget.speaker_label.visible, "an absent bound actor keeps the speaker without inventing a portrait")
	var departing := HeadActor.new()
	stage.add_child(departing)
	widget.set_line("Worker", "Then yesterday can lend us a hand.", departing)
	expect(widget.portrait_visible(), "a newly bound speaker receives its own portrait")
	departing.free()
	widget.set_line("Worker", "Then yesterday can lend us a hand.")
	expect(not widget.portrait_visible(), "the same line immediately drops a freed actor's stale portrait")
	widget.set_line("Odo Fenn", "Hold the approach, mend the access, or help move the injured. Tell me where you need me.", actor)
	for width: float in [1280.0, 720.0, 480.0]:
		widget.size.x = width-32
		widget.fit_width(width-32)
		await process_frame
		await process_frame
		var row: Rect2 = widget._row.get_global_rect()
		expect(widget.get_combined_minimum_size().x <= width-32, "dialogue fits available width at " + str(width))
		expect(widget.body_label.get_global_rect().end.x <= row.end.x+1, "body stays inside the row at " + str(width))
		expect(widget.get_combined_minimum_size().y <= (128 if width > 900 else 110), "portrait and caption preserve room for scene controls at " + str(width))
	widget.reset()
	expect(not widget.visible and not widget.portrait_visible() and widget.subtitle_text().is_empty(), "reset removes the line and portrait")
	expect(widget._viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED, "a finished scene stops rendering its portrait")
	widget.queue_free()
	stage.queue_free()
	await process_frame
	var args := OS.get_cmdline_user_args()
	var render_index := args.find("--render")
	if render_index >= 0 and render_index+1 < args.size() and DisplayServer.get_name() != "headless":
		await _render_native(host, args[render_index+1])
	host.queue_free()
	await process_frame
	print("campaign dialogue: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func _native_actor(stage: Node3D, actor_type: int, actor_name: String) -> ReplicatedActor3D:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var people: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/npc_characters.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var model: Dictionary = registry.models[registry.actorTypes[str(actor_type)]]
	var dto := {"actor_id":1, "actor_type":actor_type, "name":actor_name, "kind":2,
		"x":0, "y":0, "rotation":0, "health":100, "max_health":100, "appearance":{}}
	var person := NpcCharacterLooks.find(dto, people)
	dto = NpcCharacterLooks.present(dto, person)
	var look: Dictionary = person if not person.is_empty() else registry.get("npcLooks", {}).get(str(actor_type), {})
	dto["equipment_visuals"] = look.get("equipmentVisuals", {})
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight":0}), model,
		JSON.parse_string(FileAccess.get_file_as_string(str(model.animationMap))), equipment)
	expect(errors.is_empty(), actor_name + " uses its actual approved runtime appearance")
	return actor

func _render_native(host: Control, folder: String) -> void:
	DirAccess.make_dir_recursive_absolute(folder)
	Engine.max_fps = 30
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("31434d")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d7dfdf")
	environment.environment.ambient_light_energy = 0.8
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -20, 0)
	light.light_energy = 0.8
	stage.add_child(light)
	var camera := Camera3D.new()
	stage.add_child(camera)
	camera.position = Vector3(3, 2.5, -4)
	camera.look_at(Vector3(0.5, 1.0, -0.5))
	camera.current = true
	var backing := PanelContainer.new()
	backing.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	backing.offset_left = 16
	backing.offset_right = -16
	backing.offset_top = -172
	backing.offset_bottom = -16
	var box := StyleBoxFlat.new()
	box.bg_color = Color(0.025, 0.04, 0.05, 0.86)
	box.border_color = Color("756443")
	box.set_border_width_all(1)
	box.set_content_margin_all(12)
	backing.add_theme_stylebox_override("panel", box)
	host.add_child(backing)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	backing.add_child(column)
	var widget = Dialogue.new()
	column.add_child(widget)
	var actions := HFlowContainer.new()
	actions.add_theme_constant_override("h_separation", 14)
	column.add_child(actions)
	for text: String in ["Return to play · Esc", "Read scene account"]:
		var button := Button.new()
		button.text = text
		actions.add_child(button)
	var reduced := CheckButton.new()
	reduced.text = "Reduced camera motion"
	actions.add_child(reduced)
	for entry: Array in [[1280, 720, 360, "Odo Fenn", 0.0, 1.0],
			[720, 480, 360, "Odo Fenn", PI, 1.0], [1280, 720, 348, "Voss", PI/2, 1.0],
			[720, 480, 360, "Odo Fenn", PI, 1.5]]:
		root.size = Vector2i(entry[0], entry[1])
		root.content_scale_factor = entry[5]
		var actor := _native_actor(stage, entry[2], entry[3])
		actor.set_cinematic_presentation(actor.global_position, entry[4], &"idle", 0.0)
		for _frame: int in range(12):
			await process_frame
		var original := actor.global_transform
		widget.fit_width(float(entry[0])-56)
		widget.set_line(entry[3], "Hold the approach, mend the access, or help move the injured. Tell me where you need me.", actor)
		for _frame: int in range(8):
			await process_frame
		await RenderingServer.frame_post_draw
		expect(widget.portrait_visible(), entry[3] + " has a real native face in the portrait")
		expect(actor.global_transform == original, "native headshot leaves " + entry[3] + " at its world post")
		var key := str(entry[3]).to_lower().replace(" ", "-") + "-" + str(entry[0]) + "-" + str(roundi(float(entry[5])*100))
		root.get_texture().get_image().save_png(folder.path_join(key+"-dialogue.png"))
		widget._viewport.get_texture().get_image().save_png(folder.path_join(key+"-head.png"))
		widget.reset()
		actor.queue_free()
		await process_frame
	widget.queue_free()
	backing.queue_free()
	stage.queue_free()
	await process_frame
