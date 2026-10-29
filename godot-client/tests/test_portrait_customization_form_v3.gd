extends SceneTree
## PC/3 form, dressing room and creation wiring, headless (PC/3 spec 9.3 U1-U6
## and colour model spec 8.3 U15): the More face detail section, the Sleek ↔
## Messy hair finish slider and their gating on the negotiated version.

const FORM = preload("res://src/ui/portrait_customization_form.gd")
const EDITOR = preload("res://src/ui/appearance_editor.gd")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const Custom = preload("res://src/actors/portrait_customization.gd")
const HAIR_FINISH = preload("res://src/actors/hair_finish.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func neutral_v3(look: Dictionary) -> bool:
	for field: String in Custom.V3_FIELDS:
		if int(look.get(field, -1)) != int(Custom.DEFAULTS[field]):
			return false
	return true

func v3_tokens(text: String) -> Array:
	var found: Array = []
	for token: String in text.trim_prefix("#appearance ").split(" ", false):
		var field := token.split("=")[0]
		if field in Custom.V3_FIELDS:
			found.append(field)
	return found

func run() -> void:
	root.size = Vector2i(1280, 720)
	await form_suite()
	await editor_suite()
	await creation_suite()
	print("Portrait customization form v3: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

# ------------------------------------------------------------------ U1-U4, U15

func form_suite() -> void:
	var form = FORM.new()
	root.add_child(form)
	await process_frame
	# U1: hidden by default; 53 values, V3 neutral.
	expect(not form.detail_enabled() and not form.detail_toggle.visible and not form.detail_box.visible,
		"U1 the More face detail section is hidden by default")
	expect(form.values().size() == 53 and neutral_v3(form.values()), "U1 values() has 53 keys and V3 is neutral")
	expect((form.controls.hair_detail as OptionButton).visible and not form.finish_row.visible,
		"U15 develop's finish dropdown shows at version 1-2")
	# U2: enable and edit every V3 widget.
	form.set_detail_enabled(true)
	expect(form.detail_toggle.visible and not form.detail_box.visible, "U2 the section starts collapsed")
	form.detail_toggle.button_pressed = true
	expect(form.detail_box.visible, "U2 the toggle opens the section")
	expect(form.finish_row.visible and not (form.controls.hair_detail as OptionButton).visible,
		"U15 the Sleek-Messy slider replaces the dropdown at version 3")
	var edited := {}
	for field: String in Custom.V3_CONTROLS:
		(form.detail_controls[field] as HSlider).value = 80
		edited[field] = 80
	var amounts := {"brow_style": 7, "brow_thickness": 21, "freckles": 41, "liner": 61, "liner_wing": 11, "stubble": 91}
	for field: String in amounts:
		var entry: Dictionary = form.detail_controls[field]
		(entry.auto as CheckBox).button_pressed = false
		expect((entry.slider as HSlider).editable, "U2 unticking Auto enables %s" % field)
		(entry.slider as HSlider).value = amounts[field]
		edited[field] = amounts[field]
	var lip := form.detail_controls.lip_tint as OptionButton
	lip.select(lip.get_item_index(9))
	lip.item_selected.emit(lip.selected)
	edited["lip_tint"] = 9
	var module := form.detail_controls.hair_module as OptionButton
	module.select(module.get_item_index(1))
	module.item_selected.emit(module.selected)
	edited["hair_module"] = 1
	var values: Dictionary = form.values()
	var all_reached := true
	for field: String in edited:
		all_reached = all_reached and int(values[field]) == int(edited[field])
	expect(all_reached, "U2 every V3 widget's edit reaches values()")
	expect(not form.detail_notice.visible, "U2 no notice while the section is offered")
	form.set_detail_enabled(false)
	values = form.values()
	all_reached = true
	for field: String in edited:
		all_reached = all_reached and int(values[field]) == int(edited[field])
	expect(all_reached and form.detail_notice.visible and not form.detail_toggle.visible,
		"U2 disabling keeps the values and shows the notice")
	expect(not Custom.validate(values, 2).ok and Custom.validate(values, 2).error == "unsupported",
		"U2 the version gate refuses the held values")
	(form.detail_notice.get_meta("button") as Button).pressed.emit()
	expect(neutral_v3(form.values()) and not form.detail_notice.visible, "U2 Reset to Auto gives neutral")
	form.set_detail_enabled(true)
	# Auto knobs sit at the derived value: unticking keeps the look.
	form.set_body(0)
	form.update_derived({"skin": 1})
	var freckles: Dictionary = form.detail_controls.freckles
	var derived := RLHeadPortraitMap.details({"skin": 1}, "female")
	expect(roundi((freckles.slider as HSlider).value) == 1 + roundi(100.0 * float(derived.freckles)),
		"U2 the Auto knob shows the derived freckles")
	(freckles.auto as CheckBox).button_pressed = false
	expect(int(form.values().freckles) == 1 + roundi(100.0 * float(derived.freckles)),
		"U2 unticking Auto starts from the derived value")
	form.reset_detail()
	# U3: presets apply DETAILS only while the section is enabled.
	for preset: String in PRESETS.LOOKS:
		form.set_body(0 if preset == "Mira" else 1)
		form.apply_preset(preset)
		var look: Dictionary = form.values()
		var detail := PRESETS.detail(preset)
		var matches := true
		for field: String in detail:
			matches = matches and int(look[field]) == int(detail[field])
		expect(matches, "U3 %s applies its DETAILS while enabled" % preset)
	expect(PRESETS.detail("Rowan").stubble == 61 and PRESETS.detail("Mira").freckles == 66
		and PRESETS.detail("Tavi").eyelid == 30 and PRESETS.detail("Tavi").chin_width == 58,
		"U3 the preset details are the spec values (Tavi's offsets frozen from RL tavi)")
	# Tavi's frozen offsets reproduce the RL tavi controls.
	var tavi := RLHeadAppearance.from_preset("tavi")
	var tavi_controls := RLHeadPortraitMap.controls(PRESETS.shape("Tavi").merged(PRESETS.detail("Tavi")), "male")
	var tavi_ok := true
	for control: String in Custom.V3_CONTROLS:
		tavi_ok = tavi_ok and absf(float(tavi_controls.get(control, 0.0)) - tavi.control(control)) <= 0.011
	expect(tavi_ok, "U3 Tavi's frozen V3 offsets reproduce RL tavi within one step")
	form.set_detail_enabled(false)
	form.apply_preset("Rowan")
	expect(neutral_v3(form.values()) and form.values().facial_hair == 0 and form.values().hair_detail == 1,
		"U3 a preset sets V3 neutral while the section is disabled")
	form.set_detail_enabled(true)
	form.apply_preset("Tavi")
	form.reset_shape()
	var reset: Dictionary = form.values()
	var shape_neutral := true
	for field: String in Custom.V2_FIELDS + Custom.V3_CONTROLS + Custom.V3_DETAILS:
		if field not in ["hair_detail", "hair_finish"]:
			shape_neutral = shape_neutral and int(reset[field]) == int(Custom.DEFAULTS[field])
	expect(shape_neutral and int(reset.hair_detail) == 1, "U3 Reset shape gives neutral shape and detail; the finish slider keeps its value")
	# U4: body sex.
	form.set_body(0)
	var stubble_row: Array = form.get("_stubble_row")
	expect(not (stubble_row[1] as Control).visible, "U4 a female body hides stubble")
	var ids: Array = []
	for item: int in module.item_count:
		ids.append(module.get_item_id(item))
	expect(ids == [0, 1, 3], "U4 a female body offers Automatic, Classic and Mira bun")
	form.set_body(1)
	ids.clear()
	for item: int in module.item_count:
		ids.append(module.get_item_id(item))
	expect(ids == [0, 1, 2] and (stubble_row[1] as Control).visible, "U4 a male body offers Rowan shag and stubble")
	module.select(module.get_item_index(2))
	module.item_selected.emit(module.selected)
	var stubble: Dictionary = form.detail_controls.stubble
	(stubble.auto as CheckBox).button_pressed = false
	(stubble.slider as HSlider).value = 61
	form.set_body(0)
	expect(int(form.values().hair_module) == 2 and int(form.values().stubble) == 61,
		"U4 the dressing room keeps saved values the body does not show")
	form.set_body(0, true)
	expect(int(form.values().hair_module) == 0 and int(form.values().stubble) == 0,
		"U4 creation's female body resets stubble and an incompatible module")
	form.set_body(1)
	await finish_suite(form)
	form.queue_free()
	await process_frame

func finish_suite(form) -> void:
	form.set_values({})
	form.set_detail_enabled(true)
	var slider: HSlider = form.finish_slider
	expect(roundi(slider.value) == 50 and form.finish_readout.text == "Classic", "U15 the slider opens on Classic")
	# Tick snapping writes the enum.
	for case: Array in [[24, 25, 2], [27, 25, 2], [52, 50, 0], [73, 75, 1], [77, 75, 1]]:
		form.set_values({})
		slider.value = 90
		slider.value = case[0]
		var look: Dictionary = form.values()
		expect(roundi(slider.value) == case[1] and int(look.hair_detail) == case[2] and int(look.hair_finish) == 0,
			"U15 %d snaps to %d and saves the enum" % [case[0], case[1]])
	# Leaving a tick by a key step jumps past its snap zone.
	form.set_values({"hair_detail": 1})
	slider.value = 76
	expect(roundi(slider.value) == 78, "U15 a step off Tousled leaves the snap zone")
	# values(): nearest hair_detail plus hair_finish.
	for case: Array in [[10, 2], [37, 2], [38, 0], [62, 0], [63, 1], [100, 1]]:
		form.set_values({})
		slider.value = 90 if case[0] < 50 else 5
		slider.value = case[0]
		var look: Dictionary = form.values()
		expect(int(look.hair_detail) == case[1] and int(look.hair_finish) == case[0] + 1,
			"U15 slider %d saves hair_detail %d and hair_finish %d" % [case[0], case[1], case[0] + 1])
	slider.value = 60
	expect(form.finish_readout.text == "Between Classic and Tousled (60)", "U15 the readout names the neighbours")
	expect(slider.accessibility_name == "Hair finish" and slider.tooltip_text.begins_with("How sleek"),
		"U15 the slider has its accessible name and tooltip")
	# Opening a saved slider position, and the guard.
	form.set_values({"hair_detail": 1, "hair_finish": 91})
	expect(roundi(slider.value) == 90 and int(form.values().hair_finish) == 91, "U15 a saved position reopens")
	form.set_values({"hair_detail": 2, "hair_finish": 91})
	expect(roundi(slider.value) == 25 and int(form.values().hair_finish) == 0,
		"U15 a stale position (nearest finish not the saved one) shows the saved finish")
	# The version notice and Use nearest finish.
	form.set_values({"hair_detail": 1, "hair_finish": 91})
	form.set_detail_enabled(false)
	expect(form.finish_notice.visible and (form.controls.hair_detail as OptionButton).selected == 1
		and int(form.values().hair_finish) == 91, "U15 a held position shows the notice at version 2 and keeps its value")
	(form.finish_notice.get_meta("button") as Button).pressed.emit()
	expect(not form.finish_notice.visible and int(form.values().hair_finish) == 0 and int(form.values().hair_detail) == 1,
		"U15 Use nearest finish saves the nearest enum")
	form.set_values({"hair_detail": 0, "hair_finish": 41})
	var dropdown := form.controls.hair_detail as OptionButton
	dropdown.select(1)
	dropdown.item_selected.emit(1)
	expect(int(form.values().hair_finish) == 0 and int(form.values().hair_detail) == 1,
		"U15 a dropdown pick replaces a held slider position")
	form.set_detail_enabled(true)
	form.set_hair_style(0)
	expect(not slider.editable and (form.detail_controls.hair_module as OptionButton).disabled,
		"U15 Bald disables the slider and the High-detail hair")
	form.set_hair_style(1)
	expect(slider.editable, "U15 a hairstyle enables the slider")
	for preset: Array in [["Rowan", 75], ["Mira", 25], ["Tavi", 75]]:
		form.apply_preset(preset[0])
		expect(roundi(slider.value) == preset[1] and int(form.values().hair_finish) == 0,
			"U15 %s sets the finish slider to %d (saved as the enum)" % preset)
	# Keyboard: PageUp steps by 5; Home and End reach the ends.
	form.set_values({})
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_PAGEUP
	slider.gui_input.emit(key)
	expect(roundi(slider.value) == 55, "U15 PageUp steps the finish by 5")
	key.keycode = KEY_END
	slider.gui_input.emit(key)
	expect(roundi(slider.value) == 100, "U15 End reaches the messiest finish")
	form.step_finish(-1)
	expect(roundi(slider.value) == 75 and int(form.values().hair_detail) == 1 and int(form.values().hair_finish) == 0,
		"U15 ‹ jumps to the previous named finish (Tousled)")
	form.finish_previous.pressed.emit()
	form.finish_previous.pressed.emit()
	expect(roundi(slider.value) == 25, "U15 ‹ steps Tousled, Classic, Swept")
	form.finish_next.pressed.emit()
	expect(roundi(slider.value) == 50 and form.finish_readout.text == "Classic", "U15 › jumps to the next named finish")
	form.set_values({})

# ------------------------------------------------------------------ U6 editor

func editor_suite() -> void:
	var editor = EDITOR.new()
	root.add_child(editor)
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var model: Dictionary = registry.models["luminous_male"]
	var state := {"command": "", "version": 2, "result": OK, "sent": 0}
	var send := func(command: String) -> int:
		state.command = command
		state.sent += 1
		return state.result
	var version := func() -> int: return state.version
	var look := Custom.normalized({"jaw": 70, "hair_detail": 1})
	look.merge({"skin": 2, "hair": 126, "eyes": 3, "shirt": 0, "pants": 0, "boots": 0}, true)
	editor.open_for({"actor_id": 0, "actor_type": 1, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": look}, model, animations, equipment, send, version)
	await process_frame
	var form = editor.get("_form")
	expect(not form.detail_enabled(), "U6 a version-2 dressing room hides the PC/3 controls")
	editor.call("_apply")
	expect(state.sent == 1 and v3_tokens(state.command).is_empty() and state.command.contains("jaw=70"),
		"U6 at version 2 the sent text has no V3 tokens")
	state.version = 3
	editor.set_protocol_version(3)
	expect(form.detail_enabled(), "U6 the dressing room follows a version change")
	editor.call("_apply")
	var tokens := v3_tokens(state.command)
	expect(tokens.size() == 37, "U6 at version 3 the sent text has all 37 V3 tokens (%d)" % tokens.size())
	expect(state.command.contains("hair_finish=0") and state.command.contains("skin_tone=0")
		and state.command.contains("boots_light=0"), "U10/U15 hair_finish and the colour fields are sent at version 3")
	# open_for with V3 values restores them.
	var saved := look.duplicate()
	saved.merge({"eyelid": 20, "freckles": 31, "lip_tint": 5, "hair_module": 1, "hair_detail": 1, "hair_finish": 91}, true)
	editor.open_for({"actor_id": 0, "actor_type": 1, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": saved}, model, animations, equipment, send, version)
	var restored: Dictionary = editor.call("_values")
	expect(int(restored.eyelid) == 20 and int(restored.freckles) == 31 and int(restored.lip_tint) == 5
		and int(restored.hair_module) == 1 and int(restored.hair_finish) == 91, "U6 open_for restores V3 values")
	editor.call("_apply")
	expect(state.command.contains("hair_finish=91") and state.command.contains("eyelid=20"), "U6 Apply sends the restored values")
	# Version drops while held: refused here with the gate's message, nothing sent.
	state.version = 2
	editor.set_protocol_version(2)
	var sent_before: int = state.sent
	editor.call("_apply")
	var status := (editor.get("_status") as Label).text
	expect(state.sent == sent_before and status.begins_with(Custom.V3_DETAIL_MESSAGE),
		"U6 held V3 values at version 2 are refused with the gate's message")
	state.version = 3
	editor.set_protocol_version(3)
	state.result = ERR_UNAVAILABLE
	editor.call("_apply")
	expect((editor.get("_status") as Label).text.contains("needs an update"), "U6 the status explains ERR_UNAVAILABLE")
	state.result = OK
	# Presets in the dressing room: finish and details at version 3.
	for preset: Array in [["Rowan", 75, 1], ["Tavi", 75, 1]]:
		form.apply_preset(preset[0])
		var preset_look: Dictionary = editor.call("_values")
		expect(int(preset_look.hair_detail) == preset[2] and int(preset_look.hair_finish) == 0
			and roundi(form.finish_slider.value) == preset[1], "U15 dressing room preset %s sets its finish" % preset[0])
	editor.call("_close")
	editor.queue_free()
	await process_frame

# ------------------------------------------------------------------ U5 creation

func creation_suite() -> void:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	var network := root.get_node("Network")
	main.get_node("%LoginPanel").hide()
	main.get_node("%CreationPanel").show()
	await process_frame
	var form = main.get("portrait_form")
	var expected := {"skin": 1, "hair": AppearanceVariants.pack_hair(4, 1),
		"eyes": 2, "head": 0, "shirt": 0, "pants": 0, "boots": 0}
	expected.merge(Custom.DEFAULTS)
	expect(main.call("_creation_appearance") == expected, "U5 creation at version 1 equals develop's look plus neutral V3")
	var seen: Array = []
	for version: int in [1, 2, 3, 1]:
		network.call("_set_appearance_protocol", version)
		seen.append([version, form.detail_enabled(), (main.get("creation_colours") as Control).get("_enabled")])
	expect(seen == [[1, false, false], [2, false, false], [3, true, true], [1, false, false]],
		"U5 creation follows appearance_protocol_changed (1, 2, 3, 1): %s" % [seen])
	expect(main.call("_creation_appearance") == expected, "U5 the look is unchanged after the version round trip")
	network.call("_set_appearance_protocol", 3)
	var sex := main.get_node("%CreateGender") as OptionButton
	sex.select(sex.get_item_index(0))
	sex.item_selected.emit(sex.selected)
	var module := form.detail_controls.hair_module as OptionButton
	var ids: Array = []
	for item: int in module.item_count:
		ids.append(module.get_item_id(item))
	expect(ids == [0, 1, 3], "U5 choosing Female filters the creation hair modules")
	sex.select(sex.get_item_index(1))
	sex.item_selected.emit(sex.selected)
	network.call("_set_appearance_protocol", 1)
	main.get_node("%CreationPanel").hide()
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
