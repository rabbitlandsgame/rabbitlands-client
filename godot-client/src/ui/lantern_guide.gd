extends Control
const TextColors := preload("res://src/ui/text_colors.gd")
## This overlay teaches the existing UI. It cannot perform gameplay actions
## or locally advance a quest. Tracking changes only its presentation; skipping
## or leaving still requires the server's existing prompt.

signal tracking_changed()

var main: Control
var card: PanelContainer
var heading: Label
var instruction: Label
var chapter: Label
var collapse: Button
var skip: Button
var help: Button
var untrack: Button
var state: Dictionary = {}
var _untracked_quests: Dictionary = {}
var highlighted: Control
var compact := false
var docked := false
var manufacturing_rect := Rect2()
var campaign_content: Control
var _campaign: Dictionary = {}
var _campaign_choices: Dictionary = {}
var _prefer_campaign := false
var _campaign_signature := ""
var _body: VBoxContainer
var _buttons: HFlowContainer
var _pending_campaign_kind := ""
var _pending_campaign_msec := 0
var _rescue_return_tracking: Dictionary = {}

func attach_campaign(content: Control) -> void:
	campaign_content = content
	content.reparent(_body)
	_body.move_child(content, _buttons.get_index())
	content.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	content.call("embed")
	_refresh()

func apply_campaign(snapshot: Dictionary) -> void:
	var previous_identity := campaign_identity()
	var previous_kind := str(_campaign.get("kind", "opening"))
	var incoming_kind := str(snapshot.get("kind", "opening"))
	if incoming_kind == "rescue" and previous_kind != "rescue" and has_campaign():
		_rescue_return_tracking = {"identity":previous_identity, "prefer":_prefer_campaign}
	if not _pending_campaign_kind.is_empty() and not str(snapshot.get("run_id", "")).is_empty() \
			and str(snapshot.get("kind", "opening")) == _pending_campaign_kind \
			and Time.get_ticks_msec() - _pending_campaign_msec <= 30000:
		_campaign_choices[str(snapshot.get("kind", "opening")) + ":" + str(snapshot.run_id)] = true
		_prefer_campaign = true
		_pending_campaign_kind = ""
	_campaign = snapshot
	if bool(snapshot.get("active", false)) and not _campaign_choices.has(campaign_identity()):
		_campaign_choices[campaign_identity()] = true
		_prefer_campaign = true
	if incoming_kind != "rescue" and campaign_identity() == str(_rescue_return_tracking.get("identity", "")):
		_prefer_campaign = bool(_rescue_return_tracking.get("prefer", false))
		_rescue_return_tracking.clear()
	var entry := campaign_entry()
	var signature := JSON.stringify(entry)
	_refresh()
	if signature != _campaign_signature:
		_campaign_signature = signature
		tracking_changed.emit()

func campaign_identity() -> String:
	return str(_campaign.get("kind", "opening")) + ":" + str(_campaign.get("run_id", "lead"))

func has_campaign() -> bool:
	var party: Dictionary = _campaign.get("party", {})
	return not _campaign.is_empty() and (bool(_campaign.get("active", false)) \
		or bool(_campaign.get("available", false)) \
		or not (_campaign.get("travel", {}) as Dictionary).is_empty() \
		or bool(party.get("can_join", false)) or bool(party.get("can_start_own", false)))

func campaign_entry() -> Dictionary:
	if not has_campaign():
		return {}
	var travel: Dictionary = _campaign.get("travel", {})
	var adoption: Dictionary = _campaign.get("adoption", {})
	var objective := str(_campaign.get("hint", "Explore with the field crew."))
	if not travel.is_empty():
		objective = str(travel.get("route", objective)) + "\nSpeak with " + str(travel.get("npc", "the local crew")) + " to continue."
	if str(adoption.get("state", "")) == "pending":
		objective += "\n\nYour account: " + str(adoption.get("summary", "Choose whether to record this shared outcome."))
		if not bool(adoption.get("can_adopt", false)):
			objective += "\n" + str(adoption.get("reason", "Complete your own field practice first."))
	var map := EloriaProtocol.map_id_from_reference(str(travel.get("map", _campaign.get("map", ""))))
	var location := map.replace("_", " ").capitalize() if not map.is_empty() else "Field expedition"
	if str(_campaign.get("kind", "")) == "rescue" and map == "landfall_insides":
		location = "Lantern Mine"
	return {"title":str(_campaign.get("title", "The Missing Measure")), "objective":objective,
		"location":location,
		"_campaign":true, "_campaign_identity":campaign_identity(),
		"_exact_title":str(_campaign.get("kind", "opening")) in ["opening", "rescue"]}

func is_campaign_tracked() -> bool:
	return has_campaign() and bool(_campaign_choices.get(campaign_identity(), false))

func using_campaign() -> bool:
	return _prefer_campaign and is_campaign_tracked()

func set_campaign_tracked(tracked: bool) -> void:
	if not has_campaign():
		return
	_campaign_choices[campaign_identity()] = tracked
	_prefer_campaign = tracked
	_refresh()
	tracking_changed.emit()

func prefer_standard_quest() -> void:
	_prefer_campaign = false
	if str(_campaign.get("kind", "")) == "rescue" and not _rescue_return_tracking.is_empty():
		_rescue_return_tracking.prefer = false
	_refresh()

func follow_campaign_request(action: String) -> void:
	# Explicitly beginning/joining from a pinned contact card follows that new
	# run; mere availability at a contact never pins a card by itself.
	if using_campaign() and str(_campaign.get("run_id", "")).is_empty() \
			and action in ["start", "resume", "join", "bank", "road", "lamps", "rescue"]:
		_pending_campaign_kind = str(_campaign.get("kind", "opening"))
		_pending_campaign_msec = Time.get_ticks_msec()

func request_campaign_replay() -> void:
	if is_instance_valid(campaign_content):
		campaign_content.call("request_replay")

func configure(owner_ui: Control) -> void:
	main = owner_ui
	# The highlight is decorative; only the card participates in hit testing.
	z_index = 240
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	card = PanelContainer.new()
	card.name = "TutorialInstruction"
	card.z_as_relative = false
	card.z_index = 8
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
	_body = body
	body.add_theme_constant_override("separation", 8)
	card.add_child(body)
	chapter = Label.new()
	TextColors.bind(chapter, "guide_heading")
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
	_buttons = buttons
	body.add_child(buttons)
	collapse = Button.new()
	collapse.text = "Less"
	collapse.pressed.connect(func(): compact = not compact; _refresh())
	buttons.add_child(collapse)
	untrack = Button.new()
	untrack.name = "UntrackQuest"
	untrack.text = "Untrack"
	untrack.tooltip_text = "Hide this quest window. Keep your progress and choose Track in Quests to show it again."
	untrack.pressed.connect(func(): set_campaign_tracked(false) if using_campaign() else set_quest_tracked(false))
	buttons.add_child(untrack)
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
	tracking_changed.emit()

## Guide payload titles describe the current step; the journal uses the quest's
## stable title. Keep the player's choice across objective and chapter updates.
func quest_title() -> String:
	if using_campaign():
		return str(campaign_entry().get("title", "The Missing Measure"))
	if not bool(state.get("active", false)):
		return ""
	match str(state.get("tutorial", "")):
		"signed_ashore": return "Signed Ashore"
		"watchpost": return "Help for the Watchpost"
		"borrowed_sky": return "The Borrowed Sky"
		"second_bell": return "The Second Bell"
		"followup", "field_dispatch": return str(state.get("adventure", state.get("title", "")))
	return "The Last Lantern"

func is_quest_tracked() -> bool:
	if using_campaign():
		return true
	var title := quest_title()
	if str(state.get("tutorial", "")) == "field_dispatch":
		return not title.is_empty()
	return not title.is_empty() and not _untracked_quests.has(title)

func set_quest_tracked(tracked: bool) -> void:
	# The ordinary journal selects its own guide without changing the saved
	# local choice for an expedition or a server-owned field dispatch.
	_prefer_campaign = false
	var title := quest_title()
	if title.is_empty():
		return
	if str(state.get("tutorial", "")) == "field_dispatch":
		# Dispatch tracking is saved by the server and also controls its marker.
		var error := Network.send_chat("#quests track " + title if tracked else "#quests untrack")
		if error != OK:
			AppState.append_local_message("Could not update quest tracking. Reconnect and try again.")
		return
	if tracked:
		_untracked_quests.erase(title)
	else:
		_untracked_quests[title] = true
	_refresh()
	tracking_changed.emit()

func _refresh() -> void:
	if card == null:
		return
	var campaign := using_campaign()
	if is_instance_valid(campaign_content):
		campaign_content.visible = campaign and not compact and bool(campaign_content.call("presentation_available"))
	if campaign:
		visible = AppState.authenticated and is_instance_valid(campaign_content) \
			and bool(campaign_content.call("presentation_available"))
		card.visible = visible
		chapter.text = "CURRENT EXPEDITION"
		heading.text = str(campaign_entry().get("title", "The Missing Measure"))
		campaign_content.call("embed_instruction", instruction)
		instruction.text = str(campaign_entry().get("objective", ""))
		instruction.visible = not compact
		skip.hide()
		help.hide()
		collapse.text = "Instructions" if compact else "Less"
		card.reset_size()
		return
	if instruction.get_parent() != _body:
		instruction.reparent(_body)
		_body.move_child(instruction, heading.get_index() + 1)
		instruction.custom_minimum_size.x = heading.custom_minimum_size.x
	visible = AppState.authenticated and is_quest_tracked()
	card.visible = visible
	if not visible: return
	var road := str(state.get("tutorial", "")) == "followup"
	var field := str(state.get("tutorial", "")) == "field_dispatch"
	skip.visible = not field
	var sky := str(state.get("tutorial", "")) == "borrowed_sky"
	var second_bell := str(state.get("tutorial", "")) == "second_bell"
	# Signed Ashore is guided by Nash, so the card offers "Ask Nash";
	# it runs on the live isle rather than a practice copy, so leaving is a skip.
	var signed_ashore := str(state.get("tutorial", "")) == "signed_ashore"
	var watchpost := str(state.get("tutorial", "")) == "watchpost"
	help.visible = second_bell or sky or road or signed_ashore or watchpost or field
	help.text = "Quest help" if watchpost else "Ask " + str(state.get("guide", "Guide")) if road else "Ask Sera" if sky else "Ask Nash"
	skip.text = "Leave tutorial…" if second_bell or sky or road else "Skip tutorial…"
	if field:
		help.text = "Quest help"
	chapter.text = ("HELP FOR THE WATCHPOST" if watchpost else str(state.get("adventure", "PRACTICE")).to_upper() if road else "THE BORROWED SKY" if sky else "THE SECOND BELL" if second_bell else str(state.get("chapter", "SIGNED ASHORE")) if signed_ashore else "THE LAST LANTERN") + "  ·  %d / %d" % [int(state.get("stage", 1)), int(state.get("total", 28))]
	heading.text = str(state.get("title", ""))
	if field:
		chapter.text = "MAIN WORLD DISPATCH  ·  %d / %d" % [int(state.get("stage",1)),int(state.get("total",1))]
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
	if needed > 1 and (road or field or watchpost or signed_ashore or str(state.get("key", "")) in ["reed", "quartz", "take_reed", "attribute", "sage"]):
		instruction.text += "\nProgress: %d / %d" % [int(state.get("count", 0)), needed]
	instruction.visible = not compact
	collapse.text = "Instructions" if compact else "Less"
	card.reset_size()

func _node(name: String) -> Control:
	# The native manufacturing builder moves these nodes into its side pane,
	# so their scene-unique owner lookup is no longer available afterwards.
	if name == "ManufacturingMixOne": return main.get("manufacturing_mix_one") as Control
	if name == "ManufacturingDetail":
		var workspace: Control = main.get("mixing_workspace")
		if workspace != null and workspace.ready_to_layout: return workspace.groups.details
		return main.get("manufacturing_detail") as Control
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
			var wanted := str(state.get("item", "Torch")) if str(state.get("tutorial", "")) in ["followup", "signed_ashore", "watchpost", "field_dispatch"] else "Torch"
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
			var panel := ext.get("merchant_panel") as Control
			if not _visible(panel): return null
			var desired := "sell" if str(state.get("key", "")) == "sell" else "buy"
			if str(ext.get("_merchant_mode")) != desired:
				return panel.find_child("MerchantSellMode" if desired=="sell" else "MerchantBuyMode",true,false) as Control
			var list := panel.find_child("MerchantBackpack" if desired == "sell" else "MerchantList",true,false) as ItemList
			return panel.find_child("MerchantTrade",true,false) as Control if _selected_item(list).contains(str(state.get("item",""))) else list
	return null

func _process(_delta: float) -> void:
	if using_campaign():
		if docked:
			card.reparent(self)
			card.z_as_relative = false
			card.z_index = 8
			docked = false
		highlighted = null
		if not AppState.authenticated:
			card.hide()
			hide()
			return
		if visible:
			var area := get_viewport_rect().size
			var width := minf(310, maxf(190, area.x - 24))
			card.custom_minimum_size.x = width
			heading.custom_minimum_size.x = width - 24
			card.position = Vector2(maxf(12, area.x-width-96), clampf(62, 8, maxf(8, area.y-card.size.y-12)))
		queue_redraw()
		return
	var manufacturing := _node("ManufacturingPanel")
	var workspace: Control = main.get("mixing_workspace")
	var custom_mixing: bool = workspace != null and workspace.ready_to_layout
	var should_dock := visible and _visible(manufacturing) and not custom_mixing
	if should_dock != docked:
		docked = should_dock
		var detail: Control = main.get("manufacturing_detail")
		if docked:
			var side: VBoxContainer = main.get("manufacturing_side")
			manufacturing_rect = manufacturing.get_rect()
			card.reparent(side)
			card.z_as_relative = true
			card.z_index = 0
			side.move_child(card, 0)
			detail.custom_minimum_size.y = 120
		else:
			card.reparent(self)
			card.z_as_relative = false
			card.z_index = 8
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
		ext.get("market_panel"), ext.get("merchant_panel")])
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
