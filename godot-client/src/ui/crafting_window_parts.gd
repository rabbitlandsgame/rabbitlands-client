extends RefCounted
## Shared presentation only. Recipes, rolls and confirmation tokens come from the server.
const Effects := preload("res://src/ui/item_effect_icons.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const IVORY := Color("eee3c8")
const MUTED := Color("b6aa91")
const BRONZE := Color("806c40")
const CYAN := Color("dcb75e")
const AMBER := Color("ffcb70")
static var _material_images: Dictionary = {}

static func style(edge: Color = BRONZE, fill: Color = Color("1c1a15"), margin: float = 4) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = fill
	box.border_color = edge
	box.set_border_width_all(1)
	box.set_corner_radius_all(3)
	box.set_content_margin_all(margin)
	return box

static func label(parent: Node, text: String, font_size: int = 16) -> Label:
	var result := Label.new()
	result.text = text
	result.add_theme_font_size_override("font_size", clampi(font_size, 11, 13))
	result.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	result.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(result)
	return result

static func button(parent: Node, text: String, action: Callable, primary: bool = false) -> Button:
	var result := Button.new()
	result.text = text
	result.custom_minimum_size.y = 28
	result.add_theme_font_size_override("font_size", 12)
	result.pressed.connect(action)
	for state: String in ["normal", "hover", "pressed", "focus", "disabled"]:
		result.add_theme_stylebox_override(state, style(CYAN if primary else BRONZE, Color("514026") if primary else Color("1c1a15"), 4))
	result.add_theme_color_override("font_color", IVORY)
	parent.add_child(result)
	return result

static func card(parent: Node, title: String = "") -> VBoxContainer:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", style())
	parent.add_child(panel)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 4)
	panel.add_child(body)
	if not title.is_empty(): label(body, title, 18)
	return body

static func icon(parent: Node, texture: Texture2D, pixels: int = 36) -> TextureRect:
	var result := TextureRect.new()
	result.texture = texture
	result.custom_minimum_size = Vector2(pixels, pixels)
	result.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	result.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	result.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	parent.add_child(result)
	return result

static func navigation(parent: Node, active: int, changed: Callable) -> TabBar:
	var tabs := TabBar.new()
	tabs.add_theme_font_size_override("font_size", 12)
	tabs.add_theme_stylebox_override("tab_selected", style(CYAN, Color("514026"), 5))
	tabs.add_theme_stylebox_override("tab_unselected", style(BRONZE, Color("1c1a15"), 5))
	tabs.add_tab("Break Down", Effects.texture("Brutal"))
	tabs.add_tab("Refine", Effects.texture("Attuned"))
	tabs.add_tab("Enchant", Effects.texture("Runebound"))
	tabs.set_tab_icon_max_width(0, 22)
	tabs.set_tab_icon_max_width(1, 22)
	tabs.set_tab_icon_max_width(2, 22)
	tabs.current_tab = active
	parent.add_child(tabs)
	tabs.tab_changed.connect(changed)
	return tabs

static func ledger(parent: Node) -> ItemList:
	var list := preload("res://src/ui/crafting_copy_list.gd").new()
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.fixed_icon_size = Vector2i(28, 48)
	list.add_theme_font_size_override("font_size", 12)
	list.add_theme_constant_override("v_separation", 7)
	list.add_theme_stylebox_override("panel", style())
	list.add_theme_stylebox_override("selected", style(CYAN, Color("514026"), 4))
	list.add_theme_stylebox_override("selected_focus", style(CYAN, Color("514026"), 4))
	parent.add_child(list)
	return list

static func copy_text(row: Dictionary) -> String:
	return str(row.name)

static func copy_note(list: ItemList, row: Dictionary) -> void:
	var notes: Dictionary = list.get_meta("copy_notes", {})
	var count: int = row.get("effects", []).size()
	var location := "Storage · #%d" % int(row.instance_id) if row.get("source") == "storage" else "Slot %d" % (int(row.slot) + 1)
	notes[int(row.instance_id)] = "%s · %d effect%s" % [location, count, "" if count == 1 else "s"]
	list.set_meta("copy_notes", notes)
	list.queue_redraw()

static func hero(parent: Node) -> Dictionary:
	var line := HBoxContainer.new()
	line.custom_minimum_size.y = 46
	line.add_theme_constant_override("separation", 7)
	parent.add_child(line)
	var picture := icon(line, null, 40)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	line.add_child(text)
	var title := label(text, "Select an item", 13)
	var condition := label(text, "", 11)
	var slots := label(text, "", 11)
	for caption: Label in [title, condition, slots]:
		caption.autowrap_mode = TextServer.AUTOWRAP_OFF
		caption.clip_text = true
		caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	return {"icon": picture, "title": title, "condition": condition, "slots": slots}

static func show_hero(hero_parts: Dictionary, owner_main: Node, row: Dictionary) -> void:
	(hero_parts.icon as TextureRect).texture = null if row.is_empty() else owner_main.call("_named_icon", int(row.get("image_id", 0)), str(row.name))
	(hero_parts.title as Label).text = str(row.get("name", "Select an item"))
	(hero_parts.title as Label).add_theme_color_override("font_color", Tiers.color(str(row.get("tier", "normal"))))
	var condition := ""
	if not row.is_empty():
		var location := "Storage copy #%d" % int(row.instance_id) if row.get("source") == "storage" else "Backpack slot %d" % (int(row.slot) + 1)
		condition = "%s · Quality %d%%" % [location, int(row.quality)]
		if row.get("durability") != null and row.get("max_durability") != null:
			condition += " · Durability %d/%d" % [int(row.durability), int(row.max_durability)]
	(hero_parts.condition as Label).text = condition
	(hero_parts.condition as Label).tooltip_text = condition
	(hero_parts.condition as Label).modulate = MUTED
	var count: int = row.get("effects", []).size()
	var capacity := 2 if str(row.get("tier", "normal")) == "magic" else 4
	var pips := ""
	for index: int in capacity: pips += "● " if index < count else "○ "
	(hero_parts.slots as Label).text = "" if row.is_empty() else "%s  %d/%d effects" % [pips.strip_edges(), count, capacity]
	(hero_parts.slots as Label).add_theme_color_override("font_color", Tiers.color(str(row.get("tier", "normal"))))

static func effect(parent: Node, description: String) -> HBoxContainer:
	var presentation := Effects.presentation(description)
	var line := HBoxContainer.new()
	line.custom_minimum_size.y = 32
	line.add_theme_constant_override("separation", 6)
	parent.add_child(line)
	icon(line, Effects.texture(str(presentation.name)), 26)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	line.add_child(text)
	var name_label := label(text, str(presentation.name), 12)
	var value_label := label(text, (str(presentation.roll) + " " + str(presentation.body)).strip_edges(), 11)
	value_label.modulate = MUTED
	for caption: Label in [name_label, value_label]:
		caption.autowrap_mode = TextServer.AUTOWRAP_OFF
		caption.clip_text = true
		caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		caption.tooltip_text = description
	line.tooltip_text = description
	return line

static func material(parent: Node, owner_main: Node, row: Dictionary, owned: int = -1) -> void:
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 5)
	parent.add_child(line)
	icon(line, material_icon(owner_main, row), 22)
	label(line, str(row.name), 15)
	var amount := label(line, str(int(row.quantity)), 17)
	amount.size_flags_horizontal = Control.SIZE_SHRINK_END
	amount.custom_minimum_size.x = 28
	amount.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	if owned >= 0:
		var available := label(line, str(owned), 16)
		available.size_flags_horizontal = Control.SIZE_SHRINK_END
		available.custom_minimum_size.x = 38
		available.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		available.modulate = CYAN if owned >= int(row.quantity) else AMBER

static func cost_heading(parent: Node) -> void:
	var row := HBoxContainer.new()
	parent.add_child(row)
	label(row, "Materials", 14).modulate = MUTED
	for heading: String in ["Need", "Owned"]:
		var text := label(row, heading, 13)
		text.size_flags_horizontal = Control.SIZE_SHRINK_END
		text.custom_minimum_size.x = 55
		text.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

static func material_icon(owner_main: Node, row: Dictionary) -> Texture2D:
	if _material_images.is_empty():
		var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/items/crafting_materials.json"))
		_material_images = config.get("images", {})
	var image_id := int(row.get("image_id", _material_images.get(str(row.name), -1)))
	# Older snapshots used zero for a missing icon; gold is the real zero icon.
	if image_id == 0: image_id = int(_material_images.get(str(row.name), 0))
	return owner_main.call("_named_icon", image_id, str(row.name)) if image_id >= 0 else null

static func summary(rows: Array, gold: int = -1) -> String:
	var values := PackedStringArray()
	for row: Dictionary in rows:
		values.append("%d %s" % [int(row.quantity), str(row.name)])
	if gold > 0: values.append("%d gold" % gold)
	return " · ".join(values)

static func odds_inline(parent: Node, chances: Array) -> void:
	for chance: Dictionary in chances:
		var count := int(chance.count)
		var color := Tiers.color("magic" if count <= 2 else "rare")
		var percent := ("%.2f" % (float(chance.chance) * 100)).trim_suffix("0").trim_suffix("0").trim_suffix(".")
		var caption := label(parent, "%d: %s%%" % [count, percent], 11)
		caption.tooltip_text = "%s%% chance of %d effect%s" % [percent, count, "" if count == 1 else "s"]
		caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		caption.modulate = color
