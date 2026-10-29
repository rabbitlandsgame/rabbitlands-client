extends SceneTree
## The colour model's UI, headless (colour model spec 8.3 U7-U14): the skin
## tone slider with undertone and Eloria tones, the five OKHSL colour wheels,
## their gating on the negotiated version, presets, randomise, the dressing
## room's Apply text and accessibility.

const COLOURS = preload("res://src/actors/appearance_colours.gd")
const Custom = preload("res://src/actors/portrait_customization.gd")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const EDITOR = preload("res://src/ui/appearance_editor.gd")
const PANEL = preload("res://src/ui/appearance_colour_panel.gd")
const SLIDER = preload("res://src/ui/skin_tone_slider.gd")
const AMBER_EYES: Array[int] = [3, 9]
var failures := 0
var checks := 0
var main: Control
var network: Node
var panel
var form

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func node(path: String) -> Node:
	return main.get_node(path)

func choose(control: OptionButton, id: int) -> void:
	control.select(control.get_item_index(id))
	control.item_selected.emit(control.selected)

func look() -> Dictionary:
	return main.call("_creation_appearance")

func pick(group: String, colour: Color) -> void:
	var choice = panel.choices[group]
	choice.set_open(true)
	choice.color_picker.color_changed.emit(colour)

func run() -> void:
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	network = root.get_node("Network")
	node("%LoginPanel").hide()
	node("%CreationPanel").show()
	await process_frame
	panel = main.get("creation_colours")
	form = main.get("portrait_form")
	await u7_gating()
	u8_snap()
	u13_undertone()
	await u14_reach_and_focus()
	u9_presets()
	u11_randomise()
	u12_accessibility()
	u15_typed_refusal()
	network.call("_set_appearance_protocol", 1)
	node("%CreationPanel").hide()
	main.queue_free()
	await process_frame
	await u10_dressing_room()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("Appearance colour UI: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

# ------------------------------------------------------------------ U15

## A typed #appearance this version cannot save is refused before sending,
## and chat says why (pc3 spec 4.6; cross-version review rb2).
func u15_typed_refusal() -> void:
	network.call("_set_appearance_protocol", 2)
	var app_state := root.get_node("AppState")
	var before: int = (app_state.get("chat_history") as Array).size()
	main.call("_on_chat_submitted", "#appearance skin_tone=95 jaw=41")
	var history: Array = app_state.get("chat_history")
	var error := str(network.get("appearance_error"))
	expect(not error.is_empty() and history.size() == before + 1 and str((history[-1] as Dictionary).get("text", "")) == error,
		"U15 a refused typed #appearance explains itself in chat (%s)" % error)
	network.call("_set_appearance_protocol", 3)

# ------------------------------------------------------------------ U7

func u7_gating() -> void:
	var grid := node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll/CreationFields/AppearanceGrid") as Control
	var skin := node("%CreateSkin") as OptionButton
	var hair_color := node("%CreateHairColor") as OptionButton
	expect(grid.visible and not panel.content.visible and hair_color.get_parent() == grid,
		"U7 version 1: develop's dropdowns in develop's grid")
	expect(skin.get_item_index(0) == -1 and skin.item_count == 9,
		"U7 the Human skin list is develop's: Soft tan (0) is not a new pick")
	var order_before: Array = []
	for child: Node in grid.get_children():
		order_before.append(child.name)
	network.call("_set_appearance_protocol", 3)
	expect(not grid.visible and panel.content.visible and panel.skin_slider.is_visible_in_tree(),
		"U7 version 3: the skin tone slider and wheels replace the grid")
	expect(hair_color.get_parent() == panel.choices.hair.get_node("Row"), "U7 the hair colour wheel wraps the palette dropdown")
	expect(panel.choices.hair.custom_button.is_visible_in_tree(), "U7 Custom… is offered at version 3")
	# Custom values survive 3 -> 2 -> 3.
	panel.skin_slider.tone_slider.value = 60
	pick("hair", Color.from_ok_hsl(0.10, 0.55, 0.30))
	panel.choices.hair.set_open(false)
	var custom := look()
	expect(int(custom.skin_tone) == 60 and int(custom.hair_hue) >= 1, "U7 custom skin tone and hair are set")
	network.call("_set_appearance_protocol", 2)
	var order_after: Array = []
	for child: Node in grid.get_children():
		order_after.append(child.name)
	expect(grid.visible and not panel.content.visible and order_after == order_before,
		"U7 version 2 restores develop's grid in its order")
	expect(look() == custom and panel.notice.visible, "U7 version 2 keeps the values and shows the notice")
	var validation := Custom.validate(look(), 2)
	expect(not validation.ok and validation.message == Custom.COLOUR_MESSAGE, "U7 the gate refuses held colours at version 2")
	network.call("_set_appearance_protocol", 3)
	expect(look() == custom and not panel.notice.visible and int(panel.skin_slider.tone()) == 60,
		"U7 back at version 3 the values and slider are as left")
	network.call("_set_appearance_protocol", 2)
	(panel.notice.get_meta("button") as Button).pressed.emit()
	var nearest := look()
	expect(int(nearest.skin_tone) == 0 and int(nearest.hair_hue) == 0 and not panel.notice.visible
		and int(nearest.skin) == COLOURS.nearest_skin_index(60) and int(nearest.hair) == int(custom.hair),
		"U7 Use nearest palette colours keeps the nearest palette bytes")
	expect(Custom.validate(nearest, 2).ok, "U7 the nearest palette look saves at version 2")
	network.call("_set_appearance_protocol", 3)
	# Non-Humans keep develop's dropdowns.
	var race := node("%CreateRace") as OptionButton
	var human_index := race.selected
	for index: int in race.item_count:
		if race.get_item_metadata(index) == "orun":
			race.select(index)
			race.item_selected.emit(index)
	expect(grid.visible and not panel.visible, "U7 a non-Human race shows develop's dropdowns")
	race.select(human_index)
	race.item_selected.emit(human_index)
	expect(not grid.visible and panel.visible, "U7 back to Human offers the slider and wheels")
	await process_frame

# ------------------------------------------------------------------ U8

func u8_snap() -> void:
	var sex := node("%CreateGender") as OptionButton
	choose(sex, 1)
	var hair_color := node("%CreateHairColor") as OptionButton
	# A palette entry's own colour snaps to the entry, saved with fields 0.
	for index: int in [0, 5, 14]:
		pick("hair", COLOURS.palette_apparent(index, "male"))
		var snapped := look()
		expect(hair_color.get_selected_id() == index and int(snapped.hair_hue) == 0
			and AppearanceVariants.hair_color_index(int(snapped.hair)) == index, "U8 hair palette %d snaps" % index)
	# A colour off the palette is quantised: the decoded triple, the nearest byte.
	var colour := Color.from_ok_hsl(0.62, 0.40, 0.33)
	pick("hair", colour)
	var wire := COLOURS.quantise(colour)
	var custom := look()
	var nearest := COLOURS.nearest_hair_index(COLOURS.triple_colour(wire), "male")
	expect(Vector3i(custom.hair_hue, custom.hair_sat, custom.hair_light) == wire
		and AppearanceVariants.hair_color_index(int(custom.hair)) == nearest and hair_color.get_selected_id() == nearest,
		"U8 a custom hair colour saves its triple and the nearest palette byte")
	expect(panel.choices.hair.readout() == "Custom, near " + hair_color.get_item_text(hair_color.selected),
		"U8 the readout names the nearest entry")
	# A palette pick replaces the custom colour.
	choose(hair_color, 3)
	expect(int(look().hair_hue) == 0 and AppearanceVariants.hair_color_index(int(look().hair)) == 3,
		"U8 a palette pick replaces a custom hair colour")
	for case: Array in [["eyes", "%CreateEyes"], ["shirt", "%CreateShirt"], ["pants", "%CreatePants"], ["boots", "%CreateBoots"]]:
		var group := str(case[0])
		var picker := node(str(case[1])) as OptionButton
		var index := picker.get_item_id(picker.item_count - 1)
		var palette: Color = panel.choices[group].palette_colour(index)
		pick(group, palette)
		var names: Array = Custom.COLOUR_TRIPLES[group]
		expect(int(look()[names[0]]) == 0 and int(look()[group]) == index, "U8 %s palette %d snaps" % [group, index])
		var off := Color.from_ok_hsl(fposmod(palette.ok_hsl_h + 0.031, 1.0), clampf(palette.ok_hsl_s * 0.8, 0.2, 0.9), 0.45)
		pick(group, off)
		var triple := COLOURS.quantise(off)
		var saved := look()
		expect(Vector3i(saved[names[0]], saved[names[1]], saved[names[2]]) == triple
			and int(saved[group]) == panel.choices[group].nearest_index(COLOURS.triple_colour(triple)),
			"U8 a custom %s saves its triple and nearest byte" % group)
		panel.choices[group].set_open(false)
		choose(picker, picker.get_item_id(0))
	# Decoded value shown on the wheel once the pick settles.
	pick("eyes", Color.from_ok_hsl(0.3, 0.5, 0.5))
	panel.choices.eyes.call("_show_decoded")
	expect(COLOURS.quantise(panel.choices.eyes.color_picker.color) == COLOURS.quantise(Color.from_ok_hsl(0.3, 0.5, 0.5)),
		"U8 the wheel shows the decoded value")
	panel.choices.eyes.set_open(false)
	choose(node("%CreateEyes") as OptionButton, 2)

# ------------------------------------------------------------------ U13

func u13_undertone() -> void:
	var slider = panel.skin_slider
	slider.set_from(1, 0, 0)
	slider.tone_slider.value = 95
	slider.undertone_slider.value = 110
	slider.undertone_slider.value = 103
	expect(roundi(slider.undertone_slider.value) == 101 and int(look().skin_undertone) == 0,
		"U13 the undertone detent snaps to Neutral and writes 0")
	slider.undertone_slider.value = 102
	expect(roundi(slider.undertone_slider.value) == 105 and int(look().skin_undertone) == 105,
		"U13 a step off Neutral leaves the detent")
	slider.undertone_slider.value = 1
	expect(slider.limited() and slider.limit_notice.visible, "U13 Pink on warm brown engages the limits and shows the notice")
	slider.undertone_slider.value = 151
	expect(slider.undertone_readout.text == "Golden", "U13 the readout names the landmark")
	slider.step_undertone(1)
	expect(roundi(slider.undertone_slider.value) == 201, "U13 › jumps to the next landmark (Olive)")
	slider.step_tone(-1)
	expect(slider.tone() == 43 and slider.tone_readout.text == "Golden tan", "U13 ‹ jumps to the previous named tone")
	(slider.eloria_buttons[7] as Button).button_pressed = true
	var eloria := look()
	expect(not slider.undertone_slider.editable and int(eloria.skin) == 7 and int(eloria.skin_tone) == 0
		and int(eloria.skin_undertone) == 0, "U13 an Eloria tone disables the undertone and saves the palette byte")
	slider.tone_slider.value = 60
	expect(slider.eloria() == -1 and slider.undertone_slider.editable and int(look().skin_tone) == 60,
		"U13 moving the natural slider leaves the Eloria tone")
	# Stop positions save as the palette byte; a stop with undertone keeps the
	# tone. Soft tan (no legacy byte of its own) keeps its position on golden tan.
	slider.undertone_slider.value = 101
	slider.tone_slider.value = 43
	expect(int(look().skin) == 2 and int(look().skin_tone) == 0, "U13 the Golden tan stop saves skin 2 with tone 0")
	slider.tone_slider.value = 23
	expect(int(look().skin) == 2 and int(look().skin_tone) == 23 and slider.tone_readout.text == "Soft tan",
		"U13 the Soft tan stop saves its position on golden tan's byte")
	slider.undertone_slider.value = 51
	expect(int(look().skin) == 2 and int(look().skin_tone) == 23 and int(look().skin_undertone) == 51,
		"U13 a stop with an undertone keeps the explicit tone")
	# Mira's concept skin (p 10, Rosy) within the spec's 0.0005.
	slider.set_body("female")
	slider.set_from(1, 10, 51)
	expect(COLOURS.delta_e(slider.colour(), Color8(224, 169, 137)) <= 0.001, "U13 Mira's concept skin is reachable")
	slider.set_body("male")
	slider.set_from(1, 0, 0)
	slider.tone_slider.value = 1
	slider.tone_slider.value = 1

# ------------------------------------------------------------------ U14

func u14_reach_and_focus() -> void:
	var hair := node("%CreateHair") as OptionButton
	choose(hair, 1)
	main.call("_refresh_creation_preview")
	var choice = panel.choices.hair
	pick("hair", Color.from_ok_hsl(0.12, 0.25, 0.97))
	choice.call("_sync")
	var ceilings: Dictionary = choice.light_bar.get_meta("ceilings")
	expect(choice.reach_notice.visible and float(ceilings.every) < 0.97, "U14 a very light hair shows the reach notice")
	expect(not choice.light_bar.marks.is_empty(), "U14 the lightness bar marks the reach ceiling")
	var by_style := {}
	for style: int in [1, 3, 5, 9]:
		choose(hair, style)
		main.call("_refresh_creation_preview")
		choice.call("_sync")
		by_style[style] = float((choice.light_bar.get_meta("ceilings") as Dictionary).style)
	var distinct := {}
	for style: int in by_style:
		distinct[snappedf(float(by_style[style]), 0.001)] = true
	expect(distinct.size() >= 2, "U14 the reach marker follows the hairstyle: %s" % [by_style])
	pick("hair", Color.from_ok_hsl(0.08, 0.4, 0.2))
	choice.call("_sync")
	expect(not choice.reach_notice.visible, "U14 a dark hair colour is in reach on every hairstyle")
	choose(hair, 4)
	choice.set_open(false)
	# Opening the eye wheel inspects the face; closing restores the framing.
	var inspect := main.get("creation_inspect_face") as CheckButton
	inspect.button_pressed = false
	panel.choices.eyes.set_open(true)
	expect(bool(main.get("creation_face_focus")) and inspect.button_pressed, "U14 opening the eye wheel frames the face")
	panel.choices.hair.set_open(true)
	expect(not panel.choices.eyes.is_open() and not bool(main.get("creation_face_focus")),
		"U14 one wheel at a time; leaving the eyes restores the full body")
	panel.choices.hair.set_open(false)
	inspect.button_pressed = true
	panel.choices.eyes.set_open(true)
	panel.choices.eyes.set_open(false)
	expect(bool(main.get("creation_face_focus")), "U14 a face close-up chosen before stays after the eye wheel")
	inspect.button_pressed = false
	# The eye limits: a pale iris is kept readable.
	pick("eyes", Color.from_ok_hsl(0.55, 0.5, 0.93))
	panel.choices.eyes.call("_sync")
	expect(panel.choices.eyes.limit_notice.visible and panel.choices.eyes.light_bar.bands.size() == 2,
		"U14 the eye wheel marks the lightness limits and notes the adjustment")
	panel.choices.eyes.set_open(false)
	choose(node("%CreateEyes") as OptionButton, 2)
	# Garments: a shirt close to the skin is stepped away from it.
	panel.skin_slider.tone_slider.value = 43
	var skin := COLOURS.from_oklab(COLOURS.skin_path(43, "male"))
	pick("shirt", Color.from_ok_hsl(skin.ok_hsl_h, skin.ok_hsl_s, skin.ok_hsl_l))
	main.call("_refresh_creation_preview")
	panel.choices.shirt.call("_sync")
	expect(panel.choices.shirt.limit_notice.visible
		and (panel.choices.shirt.limit_notice.get_meta("label") as Label).text == "Adjusted to stand out from your skin",
		"U14 a shirt like the skin shows the contrast notice")
	panel.choices.shirt.set_open(false)
	choose(node("%CreateShirt") as OptionButton, 0)
	await process_frame

# ------------------------------------------------------------------ U9

func u9_presets() -> void:
	var sex := node("%CreateGender") as OptionButton
	var buttons := {}
	for button: Node in form.find_children("*", "Button", true, false):
		if (button as Button).text in PRESETS.LOOKS:
			buttons[(button as Button).text] = button
	for case: Array in [["Rowan", 1], ["Mira", 0], ["Tavi", 1]]:
		var name := str(case[0])
		choose(sex, int(case[1]))
		(buttons[name] as Button).pressed.emit()
		var picked := look()
		var colours: Dictionary = PRESETS.COLOURS[name]
		var nearest: Dictionary = PRESETS.NEAREST[name]
		expect(int(picked.skin_tone) == int(colours.skin_tone) and int(picked.skin_undertone) == int(colours.skin_undertone)
			and int(picked.hair_hue) == int(colours.hair_hue) and int(picked.hair_sat) == int(colours.hair_sat)
			and int(picked.hair_light) == int(colours.hair_light), "U9 %s sets its concept colours at version 3" % name)
		expect(int(picked.skin) == int(nearest.skin) and AppearanceVariants.hair_color_index(int(picked.hair)) == int(nearest.hair_color)
			and AppearanceVariants.hair_style(int(picked.hair)) == int(nearest.style) and int(picked.eyes) == int(nearest.eyes),
			"U9 %s saves the nearest palette bytes" % name)
		expect(int(picked.eye_hue) == 0 and int(picked.shirt_hue) == 0 and int(picked.hair_finish) == 0,
			"U9 %s keeps palette eyes and clothes and saves its finish as the enum" % name)
	network.call("_set_appearance_protocol", 2)
	for case: Array in [["Rowan", 1], ["Mira", 0], ["Tavi", 1]]:
		var name := str(case[0])
		choose(sex, int(case[1]))
		(buttons[name] as Button).pressed.emit()
		var picked := look()
		var nearest: Dictionary = PRESETS.NEAREST[name]
		var neutral := true
		for field: String in Custom.V3_COLOURS:
			neutral = neutral and int(picked[field]) == 0
		expect(neutral and int(picked.skin) == int(nearest.skin)
			and AppearanceVariants.hair_color_index(int(picked.hair)) == int(nearest.hair_color),
			"U9 %s at version 2 picks the nearest palette entries" % name)
		expect(Custom.validate(picked, 2).ok, "U9 %s at version 2 can be saved" % name)
	expect(PRESETS.pick("Rowan").hair == 111 and PRESETS.pick("Mira").hair == 173 and PRESETS.pick("Tavi").hair == 161,
		"U9 the preset legacy hair bytes are the spec's (111, 173, 161)")
	network.call("_set_appearance_protocol", 3)
	choose(sex, 1)

# ------------------------------------------------------------------ U11

func u11_randomise() -> void:
	var race := node("%CreateRace") as OptionButton
	var sex := node("%CreateGender") as OptionButton
	var selectors: Array = ["%CreateSkin", "%CreateHair", "%CreateHairColor", "%CreateEyes",
		"%CreateShirt", "%CreatePants", "%CreateBoots"]
	var custom_rolls := 0
	var undertones := {}
	for seed_value: int in range(160):
		var rng := RandomNumberGenerator.new()
		rng.seed = 9100 + seed_value
		main.call("_randomize_creation_appearance", rng)
		var rolled := look()
		if sex.get_selected_id() not in [0, 1]:
			continue
		# Replay: develop's draws, then the tone and the undertone draws.
		var replay := RandomNumberGenerator.new()
		replay.seed = 9100 + seed_value
		replay.randi_range(0, race.item_count - 1)
		replay.randi_range(0, sex.item_count - 1)
		for path: String in selectors:
			var selector := node(path) as OptionButton
			if path == "%CreateEyes" and AppearanceVariants.culture_for_actor_type(sex.get_selected_id()) in ["orun", "mycelari"]:
				replay.randi_range(0, AMBER_EYES.size() - 1)
			else:
				replay.randi_range(0, selector.item_count - 1)
		var tone := replay.randi_range(1, 201)
		var undertone := replay.randi_range(76, 126)
		if int(rolled.skin) >= 6:
			expect(int(rolled.skin_tone) == 0 and int(rolled.skin_undertone) == 0, "U11 an Eloria roll keeps the palette tone")
			continue
		custom_rolls += 1
		var expected_undertone := 0 if undertone == 101 else undertone
		var expected_tone := tone
		if tone == COLOURS.skin_position(COLOURS.nearest_skin_index(tone)) and expected_undertone == 0:
			expected_tone = 0
		expect(int(rolled.skin_undertone) == expected_undertone and int(rolled.skin_tone) == expected_tone
			and int(rolled.skin) == COLOURS.nearest_skin_index(tone),
			"U11 seed %d rolls tone %d and undertone %d after develop's draws" % [9100 + seed_value, tone, undertone])
		undertones[int(rolled.skin_undertone)] = true
		for field: String in ["hair_hue", "eye_hue", "shirt_hue", "pants_hue", "boots_hue", "hair_finish"]:
			expect(int(rolled[field]) == 0, "U11 a roll draws palette %s" % field)
	expect(custom_rolls >= 6 and undertones.size() >= 4, "U11 rolls reach many tones and undertones (%d rolls)" % custom_rolls)
	# Version 1: develop's draws only, so develop's seeded sequence is unchanged.
	network.call("_set_appearance_protocol", 1)
	var rng := RandomNumberGenerator.new()
	rng.seed = 1729
	main.call("_randomize_creation_appearance", rng)
	var replay := RandomNumberGenerator.new()
	replay.seed = 1729
	replay.randi_range(0, race.item_count - 1)
	replay.randi_range(0, sex.item_count - 1)
	for path: String in selectors:
		var selector := node(path) as OptionButton
		if path == "%CreateEyes" and AppearanceVariants.culture_for_actor_type(sex.get_selected_id()) in ["orun", "mycelari"]:
			replay.randi_range(0, AMBER_EYES.size() - 1)
		else:
			replay.randi_range(0, selector.item_count - 1)
	expect(rng.state == replay.state, "U11 version 1 randomise draws exactly develop's sequence")
	network.call("_set_appearance_protocol", 3)
	for index: int in race.item_count:
		if race.get_item_metadata(index) == "luminous":
			choose(race, index)
	choose(sex, 1)

# ------------------------------------------------------------------ U12

func u12_accessibility() -> void:
	form.detail_toggle.button_pressed = true
	for group: String in panel.GROUPS:
		panel.choices[group].set_open(group == "hair")
	var unnamed: Array = []
	var small: Array = []
	var unfocusable: Array = []
	for host: Node in [panel, form]:
		for control: Node in (host as Node).find_children("*", "Control", true, false):
			var item := control as Control
			if not item.is_visible_in_tree():
				continue
			if item is Range or item is OptionButton or (item is BaseButton and not (item is Button and not (item as Button).text.is_empty())):
				if item.accessibility_name.is_empty() and not item.get_parent() is ColorPicker \
						and not _inside_picker(item):
					unnamed.append(str(item.get_path()))
			if (item is Range or item is BaseButton) and not _inside_picker(item):
				if item.focus_mode == Control.FOCUS_NONE:
					unfocusable.append(str(item.get_path()))
			if item is BaseButton and not _inside_picker(item) and item.get_combined_minimum_size().y < 24:
				small.append(str(item.get_path()))
	expect(unnamed.is_empty(), "U12 every control has an accessible name: %s" % [unnamed.slice(0, 6)])
	expect(unfocusable.is_empty(), "U12 every control takes keyboard focus: %s" % [unfocusable.slice(0, 6)])
	expect(small.is_empty(), "U12 every button target is at least 24 px: %s" % [small.slice(0, 6)])
	for named: Array in [[panel.skin_slider.tone_slider, "Skin tone"], [panel.skin_slider.undertone_slider, "Skin undertone"],
			[node("%CreateHairColor"), "Hair colour"], [node("%CreateEyes"), "Eye colour"],
			[node("%CreateShirt"), "Shirt dye"], [form.finish_slider, "Hair finish"]]:
		expect((named[0] as Control).accessibility_name == str(named[1]), "U12 %s is named" % named[1])
	expect(not panel.skin_slider.tone_slider.accessibility_description.is_empty()
		and panel.choices.hair.custom_button.accessibility_description == panel.choices.hair.readout(),
		"U12 descriptions carry the readouts")
	# Keyboard on the tone slider: PageUp, End.
	var tone: HSlider = panel.skin_slider.tone_slider
	tone.value = 50
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_PAGEUP
	tone.gui_input.emit(key)
	expect(roundi(tone.value) == 60, "U12 PageUp steps the skin tone by 10")
	key.keycode = KEY_HOME
	tone.gui_input.emit(key)
	expect(roundi(tone.value) == 1, "U12 Home reaches pale beige")
	# Notices pair an icon with text.
	var notice: HBoxContainer = panel.notice
	expect(notice.get_child(0) is Control and not (notice.get_meta("label") as Label).text.is_empty(),
		"U12 notices pair an icon with text")
	panel.close_wheels()
	form.detail_toggle.button_pressed = false

func _inside_picker(item: Node) -> bool:
	var parent := item.get_parent()
	while parent != null:
		if parent is ColorPicker:
			return true
		parent = parent.get_parent()
	return false

# ------------------------------------------------------------------ U10

func u10_dressing_room() -> void:
	var editor = EDITOR.new()
	root.add_child(editor)
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var model: Dictionary = registry.models["luminous_female"]
	var state := {"command": "", "version": 3, "sent": 0}
	var send := func(command: String) -> int:
		state.command = command
		state.sent += 1
		return OK
	var version := func() -> int: return state.version
	var saved := Custom.normalized({"hair_detail": 2})
	saved.merge({"skin": 1, "hair": AppearanceVariants.pack_hair(3, 4), "eyes": 1, "shirt": 0, "pants": 0, "boots": 0}, true)
	editor.open_for({"actor_id": 0, "actor_type": 0, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": saved}, model, animations, equipment, send, version)
	await process_frame
	var colours = editor.get("_colours")
	expect(colours.content.visible and not (editor.get("_grid") as Control).visible, "U10 the dressing room offers the wheels at version 3")
	expect(int(colours.skin_slider.tone()) == 1, "U10 the slider opens on the saved stop")
	colours.skin_slider.tone_slider.value = 30
	var off := Color.from_ok_hsl(0.05, 0.7, 0.45)
	colours.choices.hair.set_open(true)
	colours.choices.hair.color_picker.color_changed.emit(off)
	colours.choices.pants.set_open(true)
	colours.choices.pants.color_picker.color_changed.emit(Color.from_ok_hsl(0.6, 0.5, 0.3))
	var applied: Dictionary = editor.call("_values")
	expect(int(applied.skin) == COLOURS.nearest_skin_index(30) and int(applied.skin_tone) == 30, "U10 the skin's legacy byte is the nearest stop")
	expect(AppearanceVariants.hair_color_index(int(applied.hair)) == COLOURS.nearest_hair_index(COLOURS.triple_colour(COLOURS.quantise(off)), "female")
		and AppearanceVariants.hair_style(int(applied.hair)) == 3, "U10 the hair's legacy byte is the nearest apparent entry, style kept")
	editor.call("_apply")
	var missing: Array = []
	for field: String in Custom.V3_COLOURS + ["hair_finish"]:
		if not state.command.contains(" %s=" % field):
			missing.append(field)
	expect(missing.is_empty(), "U10 the version-3 Apply text has all 17 colour fields and hair_finish: %s" % [missing])
	expect(state.command.contains("skin_tone=30") and state.command.contains("skin=%d" % COLOURS.nearest_skin_index(30)),
		"U10 Apply sends the custom tone with its nearest byte")
	# Version 2: none of them (after Use nearest palette colours).
	state.version = 2
	editor.set_protocol_version(2)
	var sent_before: int = state.sent
	editor.call("_apply")
	expect(state.sent == sent_before and (editor.get("_status") as Label).text.begins_with(Custom.COLOUR_MESSAGE),
		"U10 held colours at version 2 are refused before sending")
	(colours.notice.get_meta("button") as Button).pressed.emit()
	editor.call("_apply")
	var leaked: Array = []
	for field: String in Custom.V3_COLOURS + ["hair_finish"]:
		if state.command.contains(" %s=" % field):
			leaked.append(field)
	expect(state.sent == sent_before + 1 and leaked.is_empty() and state.command.contains("skin=%d" % COLOURS.nearest_skin_index(30)),
		"U10 the version-2 Apply text has none of the colour fields or hair_finish: %s" % [leaked])
	editor.call("_close")
	editor.queue_free()
	await process_frame
	await u10_round_trips(model, animations, equipment)

## Opening the dressing room and applying with nothing changed keeps every
## saved byte and custom value (the cross-version review's pants 11 and Soft
## tan): palette and custom, every listed or merged dye, every skin, at
## versions 3 and 2.
func u10_round_trips(model: Dictionary, animations: Dictionary, equipment: Dictionary) -> void:
	var saves: Array = []
	var base := {"skin": 1, "hair": AppearanceVariants.pack_hair(3, 4), "eyes": 1, "shirt": 0, "pants": 0, "boots": 0}
	for skin: int in 10:
		saves.append(base.merged({"skin": skin}, true))
	for tone: int in [13, 20, 23, 30, 60, 150]:
		saves.append(COLOURS.canonical(base.merged({"skin_tone": tone, "skin_undertone": 0 if tone == 23 else 60}, true), "female"))
	for part: String in COLOURS.PARTS:
		for index: int in 12:
			saves.append(base.merged({part: index}, true))
			var frozen: Vector3i = COLOURS.frozen_dye(part, index)
			var custom := Vector3i(frozen.x, clampi(frozen.y + 3, 1, 101), clampi(frozen.z - 2, 1, 101))
			saves.append(COLOURS.canonical(base.merged({part + "_hue": custom.x, part + "_sat": custom.y,
				part + "_light": custom.z}, true), "female"))
	for index: int in 12:
		var eye: Vector3i = COLOURS.EYE_FROZEN[index]
		saves.append(COLOURS.canonical(base.merged({"eyes": index, "eye_hue": eye.x, "eye_sat": eye.y,
			"eye_light": clampi(eye.z + 2, 1, 101)}, true), "female"))
	for index: int in 20:
		var hair: Vector3i = COLOURS.frozen_hair(index, "female")
		saves.append(COLOURS.canonical(base.merged({"hair": AppearanceVariants.pack_hair(3, index), "hair_hue": hair.x,
			"hair_sat": hair.y, "hair_light": clampi(hair.z + 2, 1, 101)}, true), "female"))
	var bad: Array = []
	var trips := 0
	for version: int in [3, 2]:
		var editor = EDITOR.new()
		root.add_child(editor)
		var state := {"version": version}
		var send := func(_command: String) -> int: return OK
		var source := func() -> int: return state.version
		for look: Dictionary in saves:
			var saved := Custom.normalized(look)
			saved.merge(look, true)
			if not Custom.validate(saved, version).ok:
				continue
			editor.open_for({"actor_id": 0, "actor_type": 0, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
				"appearance": saved}, model, animations, equipment, send, source)
			var applied: Dictionary = editor.call("_values")
			trips += 1
			for field: String in saved:
				if int(applied.get(field, -1)) != int(saved[field]):
					bad.append("v%d %s: %s %s -> %s" % [version, str(look), field, saved[field], applied.get(field)])
					break
		editor.call("_close")
		editor.queue_free()
		await process_frame
	expect(trips >= 150 and bad.is_empty(), "U10 open-and-Apply keeps every saved byte and custom value (%d trips): %s" % [trips, bad.slice(0, 6)])
	# A save with Soft tan shows and keeps it; a new pick never offers it.
	var editor = EDITOR.new()
	root.add_child(editor)
	editor.open_for({"actor_id": 0, "actor_type": 0, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": Custom.normalized({}).merged(base.merged({"skin": 0}, true), true)}, model, animations, equipment,
		func(_command: String) -> int: return OK, func() -> int: return 2)
	var skin_picker := (editor.get("_pickers") as Dictionary).skin as OptionButton
	expect(skin_picker.get_selected_id() == 0 and skin_picker.get_item_text(skin_picker.selected) == "Soft tan",
		"U10 a Soft tan save opens on Soft tan")
	editor.open_for({"actor_id": 0, "actor_type": 0, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": Custom.normalized({}).merged(base, true)}, model, animations, equipment,
		func(_command: String) -> int: return OK, func() -> int: return 2)
	expect(skin_picker.get_item_index(0) == -1, "U10 another save's list has no Soft tan")
	editor.call("_close")
	editor.queue_free()
	await process_frame
