extends Node
## Real production controls in the offline Landfall fixture. Presentation
## captions and pointer are the only overlays; no HUD artwork is substituted.
const FOLDER := "res://test-artifacts/hud-public-guide"
var main: Control
var workspace: Control
var overlay: CanvasLayer
var caption: Label
var pointer: Label
var frame := 0
var recording := false
var times: Array[int] = []
var started := 0
var preset_switches := 0
var dry_run := false
var last_capture := 0

func capture(source: Control) -> void:
	main = source
	workspace = main.hud_workspace
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER.path_join("frames")))
	# Hold the world still while demonstrating live UI interactions. This is a
	# prepared local UI demonstration, not footage of combat or server activity.
	main.camera_rig.set_process(false)
	main.main_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	for id: String in workspace.Presets.BUILT_INS:
		workspace.choose_preset(id, true)
		await _hold(0.5)
		await _still(id + ".png")
	workspace.choose_preset("heritage", true)
	get_tree().root.gui_embed_subwindows = true
	workspace.preset_picker.item_selected.connect(func(_index: int) -> void:
		if recording: preset_switches += 1)
	overlay = CanvasLayer.new()
	overlay.layer = 1001
	add_child(overlay)
	var box := PanelContainer.new()
	box.position = Vector2(425, 18)
	box.size = Vector2(590, 70)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = Color("111915ee")
	style.border_color = Color("bea66cff")
	style.set_border_width_all(1)
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	box.add_theme_stylebox_override("panel", style)
	overlay.add_child(box)
	caption = Label.new()
	caption.add_theme_font_size_override("font_size", 19)
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(caption)
	var note := Label.new()
	note.text = "Manual editing · 2× playback · offline sample state"
	note.position = Vector2(480,90)
	note.add_theme_font_size_override("font_size",13)
	overlay.add_child(note)
	pointer = Label.new()
	pointer.text = "➤"
	pointer.add_theme_font_size_override("font_size", 26)
	pointer.add_theme_color_override("font_color", Color("fff0b0"))
	pointer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pointer.position = Vector2(700, 450)
	overlay.add_child(pointer)
	started = Time.get_ticks_msec()
	recording = true
	caption.text = "Classic → Adventure · built by hand\nReal editor controls · local Landfall demonstration"
	await _hold(2.0)
	main.settings_window.open_tab("HUD")
	caption.text = "1  Open Settings → HUD → Edit HUD"
	await _hold(1.2)
	var editor_button: Button = main.settings_window.page_body("HUD").get_node("HudPresets/HudEditorButton")
	assert(editor_button != null)
	await _click(editor_button)
	assert(workspace.is_open())
	await _hold(1.0)
	caption.text = "2  Move the editor aside to reach the HUD"
	await _click(_button("Move aside"))
	await _hold(1.2)
	caption.text = "3  Hide the right rail and its individual components"
	for key: String in ["rail_panel","skills","clock","compass","research","status","logo","fps"]:
		await _select(key)
		await _toggle("Show " + workspace.Presets.PARTS[key], false)
	caption.text = "4  Keep XP in a smaller, centered bottom strip"
	await _select("resources")
	await _click(_button("Detach"))
	await _choice("Position","Bottom Center")
	await _number("Scale",0.95)
	await _number("Window width",686)
	await _number("Window height",40)
	await _choice("Dock to screen","Bottom")
	await _choice("Position","Bottom Center")
	await _look()
	for meter: String in ["health","mana","food","action","load"]:
		await _reveal(_row("Resource " + meter))
		await _click(_row("Resource " + meter).get_child(0))
	caption.text = "5  Enable the health circle and choose a laurel border"
	await _select("medallion")
	await _toggle("Show Resource circle",true)
	await _look()
	await _choice("Circle border","Laurel")
	await _toggle("Show center label",false)
	await _choice("Dock to","Resource meters")
	await _choice("Dock edge","Top")
	await _choice("Dock alignment","Center")
	caption.text = "6  Choose and shape the circle's curved resource meters"
	for index: int in [0,1,5]:
		await _select("arc_%d"%index)
		await _toggle("Show curve",true)
		await _number("Curve length (degrees)",68 if index==5 else 100)
	caption.text = "7  Rotate the quick bars and set five slots per row"
	for key: String in ["spells","items"]:
		await _select(key)
		await _choice("Orientation","Horizontal")
		await _number("Quick spell count" if key=="spells" else "Quick item count",5)
		await _number("Rows",1)
		await _number("Scale",1.1)
		await _toggle("Flush slot edges",false)
		await _number("Slot spacing",2)
		await _choice("Slot border","Match Hud")
		await _look()
		caption.text = "Dock " + ("spells on the left" if key=="spells" else "items on the right") + " of the circle"
		await _choice("Dock to","Resource circle")
		await _choice("Dock edge","Left" if key=="spells" else "Right")
		await _choice("Dock alignment","End")
		await _number("Horizontal offset",0)
		await _number("Vertical offset",0)
	caption.text = "8  Add separate food and load meters at the lower corners"
	for key: String in ["food_meter","load_meter"]:
		await _select(key)
		await _toggle("Show " + workspace.Presets.PARTS[key],true)
		await _look()
		await _choice("Dock to screen","Bottom Left" if key=="food_meter" else "Bottom Right")
	caption.text = "9  Choose the menu icons and dock them above Load"
	await _select("utilities")
	await _click(_button("Detach"))
	await _toggle("Dock extend to screen edge",false)
	await _look()
	for button: Button in workspace.icon_buttons:
		var text: String = button.tooltip_text.split("\n")[0]
		if text.is_empty(): text = str(button.name).trim_suffix("Button")
		await _toggle(text,str(button.name) in ["InventoryButton","MapButton","BuddyButton","OptionsButton"])
	await _number("Scale",0.9)
	await _number("Window width",220)
	await _number("Window height",42)
	await _choice("Dock to","Load meter")
	await _choice("Dock edge","Top")
	await _choice("Dock alignment","Stretch")
	await _number("Dock spacing",-1)
	caption.text = "10  Show a round brass minimap, map name and north arrow"
	await _select("minimap")
	await _toggle("Show Minimap",true)
	await _choice("Appearance","Adventure")
	await _choice("HUD border design","Beveled")
	await _choice("Map shape","Round")
	await _choice("Minimap frame","Match Map")
	await _toggle("Map name above minimap",true)
	await _choice("Map directions","North")
	await _choice("North marker","Arrow")
	await _number("Direction distance from radius",21)
	await _number("Scale",0.7)
	await _number("Window width",314)
	await _number("Window height",314)
	# A real rim drag positions the map; the right-edge dock retains that height.
	var map: Control = workspace._root("minimap")
	var grab: Vector2 = map.get_global_transform() * (map.size*0.5+Vector2(1,-1).normalized()*(map.size.x*0.5-6))
	var desired: Vector2 = main.game_view.get_global_transform() * Vector2(main.game_view.size.x-map.size.x*map.scale.x,main.game_view.size.y*0.5464)
	await _drag(grab,grab+desired-map.global_position)
	await _choice("Dock to screen","Right")
	caption.text = "11  Add the party roster and tracked objectives"
	await _select("party")
	await _toggle("Show Party roster",true)
	await _toggle("Detailed player summary",false)
	await _look()
	await _number("Window width",244)
	await _number("Window height",170)
	await _choice("Position","Top Left")
	await _number("Horizontal offset",12)
	await _number("Vertical offset",12)
	await _select("objectives")
	await _toggle("Show Tracked objectives",true)
	await _look()
	caption.text = "12  Move chat; combine feeds or keep both windows"
	await _select("chat")
	await _look()
	await _toggle("HUD background",true)
	await _toggle("HUD border",true)
	await _choice("Position","Bottom Left")
	await _number("Window width",330)
	await _number("Window height",200)
	await _number("Horizontal offset",12)
	await _number("Vertical offset",-150)
	await _toggle("Combine system and conversation feeds",true)
	await _select("nameplate")
	await _look()
	await _toggle("Banner Background",false)
	var circle_center: Vector2=workspace.parts.medallion.position+workspace.parts.medallion.center_point()*workspace.parts.medallion.scale
	assert(absf(circle_center.x-main.game_view.size.x/2)<1.1,"The manually assembled circle must be centered")
	for key: String in ["spells","items"]:
		assert(workspace.model.working.parts[key].slots==5 and workspace.model.working.parts[key].rows==1
			and workspace.model.working.parts[key].dock_target=="medallion","The manual quick bars must be horizontal and docked")
	assert(workspace._visual_rect("utilities").size.y<90 and not workspace.model.working.parts.utilities.extend_to_edge,
		"The rebuilt menu must remain a compact horizontal toolbar")
	caption.text = "13  Save your own Adventure layout · five custom slots"
	await _click(workspace.preset_name)
	workspace.preset_name.clear()
	for character: String in "My Adventure":
		workspace.preset_name.insert_text_at_caret(character)
		await _hold(0.125)
	await _click(workspace.save_new_button)
	assert(workspace.model.custom.size() == 1)
	assert(preset_switches==0,"The manual walkthrough must never switch built-in presets")
	await _hold(1.4)
	caption.text = "7  Done & save keeps your layout"
	await _click(_button("Done & save"))
	assert(not workspace.is_open())
	await _hold(2.0)
	caption.text = "Your Adventure HUD\nChat, shortcuts and gameplay controls stay available"
	pointer.hide()
	await _hold(2.5)
	recording = false
	var file := FileAccess.open(FOLDER.path_join("frame-times.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(times))
	file.close()
	overlay.hide()
	await _still("custom-adventure.png")
	print("HUD PUBLIC GUIDE: ", frame, " real client frames; ", Time.get_ticks_msec() - started, " ms")

func _button(text: String, parent: Node = null) -> Button:
	var scope: Node = workspace.panel if parent == null else parent
	for node: Node in scope.find_children("*", "Button", true, false):
		if node is Button and node.text == text and node.is_visible_in_tree(): return node
	assert(false, "Missing button " + text)
	return null

func _row(text: String) -> Control:
	for child: Control in workspace.details.get_children():
		if child.get_meta("option_caption", "") == text: return child
	assert(false, "Missing row " + text)
	return null

func _select(key: String) -> void:
	for index: int in workspace.component_picker.item_count:
		if workspace.component_picker.get_item_metadata(index)==key:
			await _choose_index(workspace.component_picker,index)
			return
	assert(false,"Missing component "+key)

func _choose_index(control: OptionButton,index: int) -> void:
	if control.selected==index: return
	await _click(control)
	control.get_popup().set_focused_item(index)
	await _hold(0.08)
	# Activate the visible menu item's control signal. This keeps the capture
	# deterministic across native and embedded popup-window input routing.
	control.get_popup().hide()
	control.select(index)
	control.item_selected.emit(index)
	await _hold(0.08)

func _choice(text: String,value: String) -> void:
	var row := _row(text)
	await _reveal(row)
	var control: OptionButton = row.get_child(1)
	for index: int in control.item_count:
		if control.get_item_text(index)==value:
			await _choose_index(control,index)
			return
	assert(false,"Missing option "+text+": "+value)

func _toggle(text: String,value: bool) -> void:
	var control: CheckBox = _row(text)
	if control.button_pressed==value: return
	await _reveal(control)
	await _click(control)
	assert((_row(text) as CheckBox).button_pressed==value,"Toggle failed: "+text)

func _number(text: String,value: float) -> void:
	var row := _row(text)
	await _reveal(row)
	var control: SpinBox = row.get_child(1)
	if is_equal_approx(control.value,value): return
	var entry := control.get_line_edit()
	await _click(entry)
	entry.select_all()
	entry.insert_text_at_caret(str(value))
	control.value=value
	await _hold(0.08)

func _look() -> void:
	await _choice("Appearance","Adventure")
	for row: Control in workspace.details.get_children():
		if row.get_meta("option_caption","")=="HUD border design":
			await _choice("HUD border design","Plain")
			break

func _reveal(control: Control) -> void:
	var tabs: TabBar = workspace._detail_tabs
	if not control.is_visible_in_tree():
		var original := tabs.current_tab
		var target := original
		for index: int in tabs.tab_count:
			tabs.current_tab=index
			if control.is_visible_in_tree():
				target=index
				break
		tabs.current_tab=original
		await _click_point(tabs.get_global_transform()*tabs.get_tab_rect(target).get_center())
	var scroll: ScrollContainer = workspace.panel.find_child("ComponentOptionsScroll",true,false)
	scroll.ensure_control_visible(control)
	await _hold(0.08)

func _click(control: Control) -> void:
	if workspace.details.is_ancestor_of(control): await _reveal(control)
	await _click_point(control.get_global_rect().get_center())

func _click_point(point: Vector2) -> void:
	await _move(point)
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.pressed = pressed
		get_tree().root.push_input(event, true)
		await _hold(0.08)

func _move(point: Vector2) -> void:
	var from := pointer.position
	for index: int in 2:
		pointer.position = from.lerp(point, float(index + 1) / 2)
		var event := InputEventMouseMotion.new()
		event.position = pointer.position
		get_tree().root.push_input(event, true)
		await _hold(0.08)

func _drag(from: Vector2, to: Vector2) -> void:
	await _move(from)
	var press := InputEventMouseButton.new()
	press.position = from
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	get_tree().root.push_input(press, true)
	for index: int in 8:
		var event := InputEventMouseMotion.new()
		event.position = from.lerp(to, float(index + 1) / 8)
		event.button_mask = MOUSE_BUTTON_MASK_LEFT
		pointer.position = event.position
		get_tree().root.push_input(event, true)
		await _hold(0.125)
	press.position = to
	press.pressed = false
	get_tree().root.push_input(press, true)
	await _hold(0.08)

func _key(code: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = code
		event.pressed = pressed
		get_tree().root.push_input(event, true)
	await _hold(0.125)

func _hold(seconds: float) -> void:
	if dry_run:
		await get_tree().process_frame
		await get_tree().process_frame
		return
	var until := Time.get_ticks_msec() + roundi(seconds * 1000)
	while Time.get_ticks_msec() < until:
		await get_tree().create_timer(0.04).timeout
		if recording and Time.get_ticks_msec()-last_capture>=160:
			await RenderingServer.frame_post_draw
			get_tree().root.get_texture().get_image().save_png(FOLDER.path_join("frames/%04d.png" % frame))
			times.append(Time.get_ticks_msec() - started)
			last_capture=Time.get_ticks_msec()
			frame += 1

func _still(filename: String) -> void:
	if dry_run: return
	await RenderingServer.frame_post_draw
	get_tree().root.get_texture().get_image().save_png(FOLDER.path_join(filename))
