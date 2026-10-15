extends Control
## This overlay teaches the existing UI. It cannot perform gameplay actions
## or locally advance a quest; its only request is the server's skip prompt.

var main: Control
var card: PanelContainer
var heading: Label
var instruction: Label
var chapter: Label
var collapse: Button
var skip: Button
var help: Button
var state: Dictionary = {}
var highlighted: Control
var compact := false
var docked := false
var manufacturing_rect := Rect2()

func configure(owner_ui: Control) -> void:
	main = owner_ui
	z_index = 90
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	card = PanelContainer.new()
	card.name = "TutorialInstruction"
	card.position = Vector2(maxf(16, get_viewport_rect().size.x-310-96), 62)
	card.custom_minimum_size.x = 310
	var style := StyleBoxFlat.new()
	style.bg_color = Color("13262eee")
	style.border_color = Color("cbaa68")
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)
	style.set_content_margin_all(12)
	card.add_theme_stylebox_override("panel", style)
	add_child(card)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 8)
	card.add_child(body)
	chapter = Label.new()
	chapter.add_theme_color_override("font_color", Color("f2c978"))
	chapter.add_theme_font_size_override("font_size", 12)
	body.add_child(chapter)
	heading = Label.new()
	heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	heading.custom_minimum_size.x = 286
	heading.add_theme_font_size_override("font_size", 19)
	body.add_child(heading)
	instruction = Label.new()
	instruction.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	instruction.custom_minimum_size.x = 286
	instruction.add_theme_font_size_override("font_size", 14)
	body.add_child(instruction)
	var buttons := HFlowContainer.new()
	body.add_child(buttons)
	collapse = Button.new()
	collapse.text = "Less"
	collapse.pressed.connect(func(): compact = not compact; _refresh())
	buttons.add_child(collapse)
	skip = Button.new()
	skip.name = "SkipTutorial"
	skip.text = "Skip tutorial…"
	skip.pressed.connect(func(): Network.tutorial_ui(2))
	buttons.add_child(skip)
	help = Button.new()
	help.text = "Ask Nash"
	help.pressed.connect(func(): Network.tutorial_ui(6))
	buttons.add_child(help)
	hide()

func apply_state(value: Dictionary) -> void:
	state = value.duplicate(true)
	_refresh()

func _refresh() -> void:
	visible = AppState.authenticated and bool(state.get("active", false))
	card.visible = visible
	if not visible: return
	var road := str(state.get("tutorial", "")) == "followup"
	var sky := str(state.get("tutorial", "")) == "borrowed_sky"
	var second_bell := str(state.get("tutorial", "")) == "second_bell"
	# Signed Ashore is guided by Nash, so the card offers "Ask Nash";
	# it runs on the live isle rather than a practice copy, so leaving is a skip.
	var signed_ashore := str(state.get("tutorial", "")) == "signed_ashore"
	var watchpost := str(state.get("tutorial", "")) == "watchpost"
	help.visible = second_bell or sky or road or signed_ashore or watchpost
	help.text = "Quest help" if watchpost else "Ask " + str(state.get("guide", "Guide")) if road else "Ask Sera" if sky else "Ask Nash"
	skip.text = "Leave tutorial…" if second_bell or sky or road else "Skip tutorial…"
	chapter.text = ("HELP FOR THE WATCHPOST" if watchpost else str(state.get("adventure", "PRACTICE")).to_upper() if road else "THE BORROWED SKY" if sky else "THE SECOND BELL" if second_bell else str(state.get("chapter", "SIGNED ASHORE")) if signed_ashore else "THE LAST LANTERN") + "  ·  %d / %d" % [int(state.get("stage", 1)), int(state.get("total", 28))]
	heading.text = str(state.get("title", ""))
	instruction.text = str(state.get("hint", ""))
	if road:
		instruction.text += "\nSeparate practice character · checkpoint saved"
	if sky:
		instruction.text += "\nBorrowed attunement · practice only"
	if second_bell:
		instruction.text += "\nBellwatch: %d invaders%s" % [int(state.get("remaining", 0)), " · another wave pending" if bool(state.get("pending", false)) else ""]
	var needed := int(state.get("required", 1))
	# Signed Ashore counts every fact that needs more than one (5 Olives,
	# 3 Lemons sold, 2 points spent); the Lantern keeps its four counted steps.
	if needed > 1 and (road or watchpost or signed_ashore or str(state.get("key", "")) in ["reed", "quartz", "take_reed", "attribute", "sage"]):
		instruction.text += "\nProgress: %d / %d" % [int(state.get("count", 0)), needed]
	instruction.visible = not compact
	collapse.text = "Instructions" if compact else "Less"
	card.reset_size()

func _node(name: String) -> Control:
	# The native manufacturing builder moves these nodes into its side pane,
	# so their scene-unique owner lookup is no longer available afterwards.
	if name == "ManufacturingMixOne": return main.get("manufacturing_mix_one") as Control
	if name == "ManufacturingDetail": return main.get("manufacturing_detail") as Control
	return main.get_node_or_null("%"+name) as Control

func _visible(node: Control) -> bool:
	return is_instance_valid(node) and node.is_visible_in_tree()

func _item_button() -> Control:
	var wanted := str(state.get("item", ""))
	var buttons: Array = main.get("inventory_slot_buttons")
	for raw: Variant in AppState.inventory_names:
		var slot := int(raw)
		if str(AppState.inventory_names[raw]) == wanted and slot >= 0 and slot < buttons.size():
			return buttons[slot] as Control
	return _node("InventoryGrid")

func _selected_item(list: ItemList) -> String:
	var selected := list.get_selected_items()
	return list.get_item_text(selected[0]) if not selected.is_empty() else ""

func control_for_step() -> Control:
	match str(state.get("control", "world")):
		"summoning": return _node("SummoningButton")
		"perks":
			if not _visible(_node("StatsPanel")): return _node("StatsButton")
			var rows: Control = main.get("perk_rows")
			return rows if _visible(rows) else _node("StatsTabs")
		"spells": return _node("SpellsButton")
		"quickbar":
			var bar: Control = main.get("casting_bar")
			if not is_instance_valid(bar): return null
			return bar.get("panel") as Control if _visible(bar.get("panel")) else bar.get("launcher") as Control
		"spell_ring", "ring_power", "ring_target":
			var ring: Control = main.get("spell_wheel")
			if _visible(ring):
				if state.control == "ring_power": return ring.get("_power_label") as Control
				if state.control == "ring_target": return ring.get("_scope_bar") as Control
				return ring.get("_heading") as Control
			var bar: Control = main.get("casting_bar")
			if not is_instance_valid(bar): return _node("SpellsButton")
			return bar.get("wheel_button") as Control if _visible(bar.get("panel")) else bar.get("launcher") as Control
		"map": return _node("MapButton")
		"chat": return _node("ChatInput")
		"ranging": return _node("RangingButton")
		"counters": return _node("StatsTabs") if _visible(_node("StatsPanel")) else _node("StatsButton")
		"inventory": return _item_button() if _visible(_node("InventoryPanel")) else _node("InventoryButton")
		"stats":
			if not _visible(_node("StatsPanel")): return _node("StatsButton")
			var body := main.get("stats_character") as Control
			if _visible(body) and str(state.get("key", "")) == "cancel":
				for candidate: Node in body.get_children():
					var minus := candidate.get_node_or_null("Remove") as Button
					if _visible(minus) and not minus.disabled: return minus
			var confirm := main.get("stats_pickpoint_confirm") as Button
			if _visible(confirm) and not confirm.disabled: return confirm
			var row := main.find_child("Row" + (str(state.get("item", "matter")) if str(state.get("tutorial", "")) == "followup" else "matter"), true, false)
			var plus := row.get_node_or_null("Spend") as Control if row else null
			if _visible(plus) and _highlight_rect(plus).encloses(plus.get_global_rect()): return plus
			# Highlight another visible attribute when the first has scrolled away.
			if _visible(body):
				for candidate: Node in body.get_children():
					if not str(candidate.get_meta("allocation", "")).begins_with("attribute:"): continue
					var button := candidate.get_node_or_null("Spend") as Control
					if _visible(button) and _highlight_rect(button).encloses(button.get_global_rect()): return button
			return _node("StatsTabs")
		"manufacture":
			if not _visible(_node("ManufacturingPanel")): return _node("ManufacturingButton")
			var list := _node("ManufacturingList") as ItemList
			# The Lantern only ever makes a Torch; the others name the recipe
			# (Signed Ashore mixes a Wood Plank before its Torch).
			var wanted := str(state.get("item", "Torch")) if str(state.get("tutorial", "")) in ["followup", "signed_ashore", "watchpost"] else "Torch"
			return _node("ManufacturingMixOne") if not wanted.is_empty() and _selected_item(list).contains(wanted) else list
		"deposit", "withdraw":
			if not _visible(_node("StoragePanel")): return null
			var deposit := str(state.control) == "deposit"
			var list := _node("StorageInventory" if deposit else "StorageItems") as ItemList
			if not _selected_item(list).contains(str(state.get("item", ""))): return list
			var quantity := _node("StorageQuantity") as SpinBox
			if int(quantity.value) != int(state.get("required", 1)): return quantity
			return _node("StorageDeposit" if deposit else "StorageWithdraw")
		"loot": return _node("InventoryGetAll") if _visible(_node("InventoryGetAll")) else null
		"dialogue": return _node("DialogueOptions")
		"merchant":
			var ext: Control = main.get("extension_windows")
			var panel := ext.find_child("MerchantWindow", true, false) as Control
			if not _visible(panel): return null
			var desired := "sell" if str(state.get("key", "")) == "sell" else "buy"
			if str(ext.get("_merchant_mode")) != desired:
				return ext.find_child("MerchantSellMode" if desired=="sell" else "MerchantBuyMode",true,false) as Control
			var list := ext.find_child("MerchantBackpack" if desired == "sell" else "MerchantList",true,false) as ItemList
			return ext.find_child("MerchantTrade",true,false) as Control if _selected_item(list).contains(str(state.get("item",""))) else list
	return null

func _process(_delta: float) -> void:
	var manufacturing := _node("ManufacturingPanel")
	var should_dock := visible and _visible(manufacturing)
	if should_dock != docked:
		docked = should_dock
		var detail: Control = main.get("manufacturing_detail")
		if docked:
			var side: VBoxContainer = main.get("manufacturing_side")
			manufacturing_rect = manufacturing.get_rect()
			card.reparent(side)
			side.move_child(card, 0)
			detail.custom_minimum_size.y = 120
		else:
			card.reparent(self)
			detail.custom_minimum_size.y = 120
			manufacturing.position = manufacturing_rect.position
			manufacturing.size = manufacturing_rect.size
	if not AppState.authenticated:
		card.hide()
		hide()
		return
	if not visible: return
	highlighted = control_for_step()
	if docked:
		card.custom_minimum_size.x = 350
		heading.custom_minimum_size.x = 326
		instruction.custom_minimum_size.x = 326
		manufacturing.size.y = get_viewport_rect().size.y - WindowDrag.RESERVED_BOTTOM_BAR - 16
		manufacturing.position.y = 8
		queue_redraw()
		return
	# Start at the upper right, clear of chat and the resource rail, and move
	# beside an open gameplay panel if it covers the controls being taught.
	var area := get_viewport_rect().size
	var width := 310.0
	card.position = Vector2(maxf(16, area.x-width-96),
		clampf(62, 8, maxf(8, area.y-card.size.y-110)))
	var panels: Array[Control] = []
	for key in ["InventoryPanel", "StoragePanel", "ManufacturingPanel", "StatsPanel", "DialoguePanel"]:
		panels.append(_node(key))
	var ranging: Control = main.get("ranging_window")
	if is_instance_valid(ranging): panels.append(ranging.panel)
	var book: Control = main.get("spells_window")
	if is_instance_valid(book): panels.append(book.panel)
	var spell_bar: Control = main.get("casting_bar")
	if is_instance_valid(spell_bar):
		panels.append(spell_bar.panel if _visible(spell_bar.panel) else spell_bar.launcher)
	var ext: Control = main.get("extension_windows")
	var summons: Control = main.get("summoning_window")
	panels.append_array([summons.panel, ext.get("detail_panel"), ext.get("party_panel"),
		ext.get("market_panel"), ext.find_child("MerchantWindow",true,false) as Control])
	for panel: Control in panels:
		if not _visible(panel): continue
		var bounds := panel.get_global_rect()
		if not Rect2(card.position, Vector2(width, card.size.y)).intersects(bounds): continue
		var left := bounds.position.x-28
		var right := area.x-96-bounds.end.x-12
		if right >= 190:
			width = minf(width,right)
			card.position.x = area.x-96-width
		elif left >= 190:
			width = minf(width,left)
			card.position.x = bounds.position.x-12-width
	# The ring's Control fills the screen; reserve its actual circle instead.
	var ring: Control = main.get("spell_wheel")
	if _visible(ring):
		var ring_bounds: Rect2 = ring.get_ring_bounds().grow(12)
		if Rect2(card.position, Vector2(width,card.size.y)).intersects(ring_bounds):
			var left_space := ring_bounds.position.x-24
			var right_space := area.x-96-ring_bounds.end.x-12
			if left_space >= right_space:
				width = clampf(left_space,190,310)
				card.position.x = 12
			else:
				width = clampf(right_space,190,310)
				card.position.x = area.x-96-width
	if card.custom_minimum_size.x != width:
		card.custom_minimum_size.x = width
		heading.custom_minimum_size.x = width-24
		instruction.custom_minimum_size.x = width-24
		card.size.x = width
		card.reset_size()
	card.position.y = clampf(62, 8, maxf(8, area.y-card.size.y-110))
	queue_redraw()

func _highlight_rect(control: Control) -> Rect2:
	if not _visible(control): return Rect2()
	var rect := control.get_global_rect().grow(4)
	var parent := control.get_parent()
	while parent != null:
		if parent is Control and (parent as Control).clip_contents:
			rect = rect.intersection((parent as Control).get_global_rect().grow(-1.5))
		parent = parent.get_parent()
	return rect.intersection(get_viewport_rect())

func _draw() -> void:
	var rect := _highlight_rect(highlighted)
	if not rect.has_area(): return
	rect.position -= global_position
	var alpha := .72 + .22*sin(Time.get_ticks_msec()*.005)
	draw_rect(rect, Color(1,.79,.35,alpha), false, 3)
