extends SceneTree

const FORM = preload("res://src/ui/portrait_customization_form.gd")
const EDITOR = preload("res://src/ui/appearance_editor.gd")
const Protocol = preload("res://src/network/protocol.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	root.size = Vector2i(1280, 720)
	var defaults := PortraitCustomization.DEFAULTS
	expect(PortraitCustomization.decode(PortraitCustomization.encode({}), 0) == defaults, "legacy default shape remains neutral")
	var look := {"facial_hair": 5, "jaw": 80, "cheekbones": 65, "nose": 73, "height": 100, "build": 0, "hair_detail": 2}
	var encoded := PortraitCustomization.encode(look)
	expect(encoded.size() == 10 and PortraitCustomization.decode(encoded, 0) == look, "all seven selections survive compact wire encoding")
	for index: int in range(3, 10):
		var malformed := encoded.duplicate()
		malformed[index] = 255
		expect(PortraitCustomization.decode(malformed, 0).is_empty(), "out-of-range extension rejected %d" % index)
	expect(PortraitCustomization.decode(encoded.slice(0, 9), 0).is_empty(), "truncated extension rejected")
	var created := Protocol.create_character("Human", "test-only", look.merged({"actor_type": 0, "hair": 299}), 2)
	var delimiter := created.find(0, 3)
	expect(created[delimiter + 9] == 2, "starter class remains ninth creation byte")
	expect(PortraitCustomization.decode(created, delimiter + 10) == look, "creation appends shape after class")
	for wardrobe: bool in [false, true]:
		var payload := PackedByteArray()
		payload.resize(28)
		payload[10] = 0
		payload.append_array("Human".to_ascii_buffer())
		payload.append(0)
		payload.append_array(PackedByteArray([0, 0, 255, 3, 0]))
		if wardrobe:
			payload.append_array(PackedByteArray([87, 65, 1, 7, 8, 9, 0]))
		payload.append_array(encoded)
		var dto := Protocol.decode_actor(payload, true)
		for field: String in PortraitCustomization.FIELDS:
			expect(dto.appearance.get(field) == look[field], "spawn parses %s with wardrobe=%s" % [field, wardrobe])
	var form := FORM.new()
	root.add_child(form)
	form.set_values(look)
	expect(form.values() == look, "all controls reopen saved choices")
	form.set_values({})
	expect(form.values() == defaults, "shape reset returns exact neutral state")
	var editor := EDITOR.new()
	root.add_child(editor)
	expect(not editor.visible, "dressing room starts hidden with no rendering")
	expect(editor.get("_viewport").render_target_update_mode == SubViewport.UPDATE_DISABLED, "hidden preview has no rendering cost")
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for actor_type: int in [0, 1]:
		var model: Dictionary = registry.models["luminous_female" if actor_type == 0 else "luminous_male"]
		var state := {"command": ""}
		editor.open_for({"actor_id": 0, "actor_type": actor_type, "x": 0, "y": 0, "rotation": 0,
			"name": "", "kind": 1, "appearance": look.merged({"skin": 2, "hair": 126, "eyes": 3}),
			"equipment_visuals": CreationArchetypes.loadout_at(0)}, model, animations, equipment,
			func(command: String) -> int:
				state.command = command
				return OK)
		expect(editor.visible and is_instance_valid(editor.get("_actor")), "Human editor builds a real preview %d" % actor_type)
		await process_frame
		await process_frame
		expect(editor.size.y <= root.size.y - 24 and editor.position.y >= 0, "dressing room stays inside the screen after text wraps")
		expect(editor.get("_camera").cull_mask == 3, "portrait camera excludes minimap overlays")
		var actor := editor.get("_actor") as ReplicatedActor3D
		expect(actor.get("_portrait_scale").is_equal_approx(Vector3(0.85, 1.1, 0.85)), "saved proportions match live editor")
		var forced_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
		var previous_quality := LookProfile.player_quality()
		OS.set_environment(LookProfile.QUALITY_VARIABLE, "")
		LookProfile.set_player_quality(2)
		editor.refresh_render_quality()
		expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 1, "open dressing room follows global High quality")
		LookProfile.set_player_quality(1)
		editor.refresh_render_quality()
		expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 0, "open dressing room releases High resources after global downgrade")
		editor.set_preview_quality(2)
		LookProfile.set_player_quality(0)
		editor.refresh_render_quality()
		expect(actor._render_quality == 2, "explicit workshop tier stays independent of global quality")
		editor.quality_level = -1
		LookProfile.set_player_quality(previous_quality)
		OS.set_environment(LookProfile.QUALITY_VARIABLE, forced_quality)
		editor.refresh_render_quality()
		editor.call("_apply")
		expect(state.command.begins_with("#appearance ") and state.command.contains("facial_hair=5") and state.command.contains("height=100"), "Apply sends complete validated values atomically")
		editor.call("_close")
		expect(not is_instance_valid(editor.get("_actor")) and editor.get("_viewport").render_target_update_mode == SubViewport.UPDATE_DISABLED, "closing releases preview and stops rendering")
		await process_frame
	form.queue_free()
	editor.queue_free()
	await process_frame
	print("Portrait customization: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
