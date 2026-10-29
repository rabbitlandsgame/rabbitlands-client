extends SceneTree
## Walkthrough screenshots of the appearance controls (colour model spec 6,
## PC/3 spec 8): character creation at version 1 (develop's dropdowns) and 3
## (skin tone slider, colour wheels, hair finish slider, More face detail),
## the version-2 notices and the dressing room. Needs a display; run it once
## per renderer (Forward+ and --rendering-method gl_compatibility):
##   --path . --audio-driver Dummy --resolution 1280x720 \
##   --script res://tests/integration/rendered_appearance_ui.gd -- --offline-hud-preview --out=<dir>
## Writes <dir>/<renderer>/NN-<state>.png (whole window) and a form-column
## crop of each, plus states.json describing what each frame shows.

const COLOURS = preload("res://src/actors/appearance_colours.gd")
const EDITOR = preload("res://src/ui/appearance_editor.gd")
var main: Control
var network: Node
var out_dir := ""
var states: Array = []
var failures := 0

func _init() -> void:
	call_deferred("run")

func _arg(name: String, fallback: String) -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--%s=" % name):
			return argument.get_slice("=", 1)
	return fallback

func expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	if DisplayServer.get_name() == "headless":
		print("RENDERED_APPEARANCE_UI: needs a display")
		quit(2)
		return
	var renderer := str(ProjectSettings.get_setting("rendering/renderer/rendering_method", "forward_plus"))
	if RenderingServer.get_current_rendering_method() != "":
		renderer = RenderingServer.get_current_rendering_method()
	out_dir = _arg("out", OS.get_environment("ELORIA_ARTIFACT_DIR")).path_join(renderer)
	DirAccess.make_dir_recursive_absolute(out_dir)
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	network = root.get_node("Network")
	main.get_node("%LoginPanel").hide()
	main.get_node("%CreationPanel").show()
	await settle(8)
	var scroll := main.get_node("CreationPanel/Columns/FormPanel/Form/CreationFieldsScroll") as ScrollContainer
	var panel = main.get("creation_colours")
	var form = main.get("portrait_form")
	var grid := scroll.get_node("CreationFields/AppearanceGrid") as Control
	await scroll_to(scroll, grid)
	await shot("01-creation-v1", "Version 1 (offline, older servers): develop's palette dropdowns, unchanged")
	network.call("_set_appearance_protocol", 3)
	await scroll_to(scroll, panel)
	await shot("02-creation-v3", "Version 3, Human: skin tone and undertone sliders with the Eloria tones, hair style, and the five colour choices")
	# Rowan's concept colours: slider position 38, undertone 90, apparent hair.
	for button: Node in form.find_children("*", "Button", true, false):
		if (button as Button).text == "Rowan":
			(button as Button).pressed.emit()
	await settle(6)
	await scroll_to(scroll, panel)
	await shot("03-rowan-preset", "The Rowan preset at version 3: skin 38 with undertone 90, apparent hair (35, 45, 19); the dropdowns show the nearest palette entries")
	panel.choices.hair.set_open(true)
	panel.choices.hair.color_picker.color_changed.emit(Color.from_ok_hsl(0.13, 0.30, 0.90))
	panel.choices.hair.call("_show_decoded")
	main.call("_refresh_creation_preview")
	await settle(6)
	await scroll_to(scroll, panel.choices.hair)
	expect(panel.choices.hair.reach_notice.visible, "a very light hair shows the reach notice")
	await shot("04-hair-wheel", "Hair wheel (apparent colour): a pale blond beyond some hairstyles' reach - the On this hairstyle chip, the lightness bar's reach marks and the notice")
	# Class gear off, so the close-up shows the eyes rather than a helmet.
	(main.get_node("%ShowClassGear") as CheckBox).button_pressed = false
	panel.choices.eyes.set_open(true)
	panel.choices.eyes.color_picker.color_changed.emit(Color.from_ok_hsl(0.52, 0.55, 0.88))
	panel.choices.eyes.call("_show_decoded")
	main.call("_refresh_creation_preview")
	await settle(10)
	await scroll_to(scroll, panel.choices.eyes)
	expect(bool(main.get("creation_face_focus")), "the eye wheel frames the face")
	await shot("05-eye-wheel", "Eye wheel: the preview switches to the face close-up; hatched lightness bands outside 0.20-0.80 and the readability notice")
	panel.choices.eyes.set_open(false)
	var skin: Color = panel.skin_slider.colour()
	panel.choices.shirt.set_open(true)
	panel.choices.shirt.color_picker.color_changed.emit(Color.from_ok_hsl(skin.ok_hsl_h, skin.ok_hsl_s, skin.ok_hsl_l))
	panel.choices.shirt.call("_show_decoded")
	main.call("_refresh_creation_preview")
	await settle(6)
	await scroll_to(scroll, panel.choices.shirt)
	expect(panel.choices.shirt.limit_notice.visible, "a shirt like the skin shows the contrast notice")
	await shot("06-shirt-contrast", "Shirt dye like the skin: drawn lighter or darker to stand out, with the notice")
	panel.choices.shirt.set_open(false)
	form.finish_slider.value = 62
	await settle(4)
	await scroll_to(scroll, form.finish_row)
	await shot("07-finish-slider", "Hair finish: the Sleek-Messy slider with Swept, Classic and Tousled ticks, readout between the names")
	form.detail_toggle.button_pressed = true
	(form.detail_controls.eyelid as HSlider).value = 30
	var freckles: Dictionary = form.detail_controls.freckles
	(freckles.auto as CheckBox).button_pressed = false
	(freckles.slider as HSlider).value = 61
	await settle(4)
	await scroll_to(scroll, form.detail_toggle)
	await shot("08-face-detail", "More face detail opened: grouped shape sliders, Auto details (freckles set to 60%), lip colour and High-detail hair")
	await scroll_to(scroll, form.detail_controls.hair_module)
	await shot("09-face-detail-end", "More face detail, end of the section: skin details, lip colour and the High-detail hair with its At High hint")
	network.call("_set_appearance_protocol", 2)
	await settle(4)
	await scroll_to(scroll, panel)
	expect(panel.notice.visible, "version 2 with custom colours shows the colour notice")
	await shot("10-version2-colours", "Version drops to 2 with custom values: develop's dropdowns show the nearest entries, the notice offers Use nearest palette colours")
	await scroll_to(scroll, form.finish_notice)
	expect(form.finish_notice.visible and form.detail_notice.visible, "version 2 shows the finish and detail notices")
	await shot("11-version2-face", "Version 2: develop's finish dropdown with the Use nearest finish notice, and the High-detail notice with Reset to Auto")
	network.call("_set_appearance_protocol", 3)
	main.get_node("%CreationPanel").hide()
	await dressing_room()
	network.call("_set_appearance_protocol", 1)
	var file := FileAccess.open(out_dir.path_join("states.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(states, "  "))
	file.close()
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("RENDERED_APPEARANCE_UI_DONE %s %d frames, %d failures" % [renderer, states.size(), failures])
	quit(1 if failures else 0)

func dressing_room() -> void:
	var editor = EDITOR.new()
	# In game the dressing room sits under Main and takes its theme.
	main.add_child(editor)
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var look := PortraitCustomization.normalized({"hair_detail": 2, "hair_length": 70, "hair_volume": 72})
	look.merge({"skin": 1, "hair": AppearanceVariants.pack_hair(3, 14), "eyes": 1, "shirt": 0, "pants": 0, "boots": 0,
		"skin_tone": 10, "skin_undertone": 51, "hair_hue": 25, "hair_sat": 86, "hair_light": 39}, true)
	var version := func() -> int: return 3
	editor.open_for({"actor_id": 0, "actor_type": 0, "x": 0, "y": 0, "rotation": 0, "name": "", "kind": 1,
		"appearance": look}, registry.models["luminous_female"], animations, equipment,
		func(_command: String) -> int: return OK, version)
	await settle(10)
	await shot("12-dressing-room", "Dressing room at version 3 (Mira's colours): the same slider and wheels in the 390 px column", editor)
	var colours = editor.get("_colours")
	colours.choices.hair.set_open(true)
	await settle(4)
	var scroll := colours.get_parent().get_parent() as ScrollContainer
	await scroll_to(scroll, colours.choices.hair)
	await shot("13-dressing-room-wheel", "Dressing room hair wheel: palette apparent colours as swatches, the custom value and its reach", editor)
	editor.call("_close")
	editor.queue_free()
	await process_frame

func settle(frames: int) -> void:
	for frame: int in frames:
		await process_frame

func scroll_to(scroll: ScrollContainer, target: Control) -> void:
	await settle(3)
	if scroll == null or target == null:
		return
	var offset := target.get_global_rect().position.y - scroll.get_global_rect().position.y + scroll.scroll_vertical
	scroll.scroll_vertical = maxi(0, int(offset) - 12)
	await settle(3)

func shot(name: String, caption: String, focus: Control = null) -> void:
	# Keep the pointer off the controls so no tooltip or hover shows.
	Input.warp_mouse(Vector2(470, 700))
	await settle(3)
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.save_png(out_dir.path_join(name + ".png"))
	var column := focus if focus != null else main.get_node("%FormPanel") as Control
	var rect := column.get_global_rect().intersection(Rect2(Vector2.ZERO, Vector2(image.get_size())))
	var crop := image.get_region(Rect2i(rect))
	crop.save_png(out_dir.path_join(name + "-form.png"))
	states.append({"name": name, "caption": caption, "size": [image.get_width(), image.get_height()]})
