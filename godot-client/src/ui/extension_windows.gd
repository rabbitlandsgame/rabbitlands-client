extends Control
## The nine Eloria extension windows, built here rather than in main.gd.
##
## Each is driven by one server-push state packet and renders that snapshot and
## nothing else: the server states the whole window, the client draws it. None
## of these windows holds state of its own, so none of them can disagree with
## the server about what it is showing.
##
## The script deliberately declares no `class_name`: a global class is parsed
## before the autoload singletons are registered, and this window reads
## `AppState` directly, so naming it globally makes it fail to compile.
##
## They live in one script because they share one seam - the fork's extension
## protocol - and because main.gd is already long enough that nine more windows
## would make it unreadable. The quest surfaces use retained shared textures
## and style resources: their fantasy chrome is built once and has no
## actor-count cost.

const RESERVED_RIGHT_RAIL := 96.0
const PANEL_SIZE := Vector2(560.0, 380.0)
const PARTY_WIDTH := 244.0
const PARTY_MINIMUM := Vector2(144, 108)
const PARTY_NAMES_WIDTH := 216.0
const PARTY_HEALTH := Color("479947")
const PARTY_LOW_HEALTH := Color("b74935")
const PARTY_ETHER := Color("4287ac")
const HUD_STYLE = preload("res://src/ui/compact_hud_style.gd")
const PARTY_MEDALLION = preload("res://src/ui/party_medallion.gd")
const QUEST_JOURNAL_SIZE := Vector2(540.0, 650.0)
const QUEST_TRACKER_SIZE := Vector2(292.0, 124.0)
const QUEST_TRACKER_MAX_HEIGHT := 320.0
const QUEST_STONE := Color(0.135, 0.125, 0.12, 0.98)
const QUEST_STONE_RAISED := Color(0.205, 0.18, 0.145, 1.0)
const QUEST_BRASS := Color(0.72, 0.54, 0.23, 1.0)
const QUEST_BRASS_BRIGHT := Color(0.96, 0.77, 0.26, 1.0)
const QUEST_PARCHMENT_DARK := Color(0.34, 0.20, 0.08, 1.0)
const QUEST_INK := Color(0.17, 0.105, 0.055, 1.0)
const QUEST_WARM_TEXT := Color(0.96, 0.93, 0.84, 1.0)
const QUEST_MUTED_TEXT := Color(0.68, 0.62, 0.52, 1.0)
const QUEST_BURGUNDY := Color(0.45, 0.075, 0.045, 1.0)
const QUEST_BURGUNDY_HOVER := Color(0.62, 0.12, 0.065, 1.0)
const QUEST_PARCHMENT_TEXTURE: Texture2D = preload(
	"res://assets/ui/oldcraft_inspired/eloria_parchment.png")
const QUEST_CARVED_FRAME_TEXTURE: Texture2D = preload(
	"res://assets/ui/oldcraft_inspired/eloria_carved_frame.png")
## The combat box. It reports one fight and then has nothing to say, so it
## holds for this long after the last thing that happened and fades out - it
## used to sit there after the target was already dead.
const COMBAT_HOLD_MSEC := 5000
const COMBAT_FADE_MSEC := 700
const COMBAT_PANEL_SIZE := Vector2(240.0, 76.0)
const COMBAT_FONT_SIZE := 13
const MARKET_SIZE := Vector2(840.0, 600.0)
## The pack, not the worn slots the inventory packet also carries.
const MARKET_PACK_SLOTS := 36
## The server's own ceiling on a unit price.
const MARKET_PRICE_LIMIT := 2000000000
## A refused request is answered too; this only frees the buttons if neither
## answer ever arrives.
const MARKET_REQUEST_MSEC := 4000
## A week, out of the 365 days a listing runs.
const MARKET_EXPIRING_SECONDS := 7 * 86400
const MARKET_EXPIRING_COLOUR := Color("e0a14a")
const MARKET_DONE_COLOUR := Color("9fd88f")
const MARKET_REFUSED_COLOUR := Color("f08a6a")

signal combat_hud_preference_changed()

var item_atlas: ItemAtlas

# Always-on HUD readouts.
var navigation_label: Label
var combat_panel: PanelContainer
var combat_target: Label
var combat_player_bar: ProgressBar
var combat_target_bar: ProgressBar
var combat_event: Label
var combat_menu: PopupMenu
## Off entirely: the player dismissed it from its own menu and gets it back
## from the settings panel.
var combat_hud_enabled := true
## Pinned boxes never fade; they stay put until combat says otherwise.
var combat_hud_pinned := false
var _combat_expiry_msec := 0
var _combat_dragging := false
var _combat_drag_offset := Vector2.ZERO
var events_panel: PanelContainer
var events_text: RichTextLabel

# Toggled or server-opened windows, in cancel-cascade order.
var quest_panel: PanelContainer
var quest_list: ItemList
var quest_detail: RichTextLabel
var quest_track_button: Button
var quest_guide: Control
var quest_active_button: Button
var quest_done_button: Button
var quest_count: Label
## Which half of the journal is showing. The player's choice about their own
## window, so it is kept here; both lists are the server's own state.
var _quest_showing_archive := false
var tracked_quest: PanelContainer
var tracked_quest_text: RichTextLabel
var quest_untrack_button: Button
var mail_panel: PanelContainer
var mail_list: ItemList
var mail_body: RichTextLabel
var detail_panel: PanelContainer
var detail_text: RichTextLabel
var merchant_panel: PanelContainer
var merchant_header: Label
var merchant_list: ItemList
## merchant_list remains the active list for tutorial and integration callers.
var merchant_buy_list: ItemList
var merchant_sell_list: ItemList
var merchant_buy_mode: Button
var merchant_sell_mode: Button
var merchant_selection: Label
var merchant_description: RichTextLabel
var merchant_totals: Label
var merchant_trade: Button
var merchant_selected_icon: TextureRect
var merchant_empty_pack: Label
var _merchant_actor := -1
var _merchant_request_pending := false
var merchant_quantity: LineEdit
var merchant_status: Label
var market_panel: PanelContainer
var market_header: Label
var market_list: ItemList
var market_history: Tree
var market_status: Label
var market_tabs: Dictionary = {}
var market_collect: Button
var market_search_row: HBoxContainer
var market_search: LineEdit
var market_filters_box: VBoxContainer
var market_category: OptionButton
var market_type: OptionButton
var market_sort: OptionButton
var market_seller: LineEdit
var market_min_price: LineEdit
var market_max_price: LineEdit
const MARKET_SORTS := ["name", "name_desc", "price", "price_desc", "total", "total_desc",
	"newest", "oldest", "quantity", "expiry"]
const MARKET_SORT_LABELS := ["Name: A–Z", "Name: Z–A", "Unit price: low to high",
	"Unit price: high to low", "Total price: low to high", "Total price: high to low",
	"Newest first", "Oldest first", "Largest stacks first", "Ending soon"]
var market_empty: Label
var market_page_row: HBoxContainer
var market_page_label: Label
var market_previous: Button
var market_next: Button
var market_returns_box: VBoxContainer
var market_returns: ItemList
var market_selected_icon: TextureRect
var market_selection: Label
var market_quantity_box: VBoxContainer
var market_quantity: LineEdit
var market_price_box: VBoxContainer
var market_price: LineEdit
var market_totals: Label
var market_buy: Button
var market_renew: Button
var market_cancel: Button
var market_sell: Button
## Browse, mine, and history are server pages; sell is the player's pack.
var _market_tab := "browse"
## When the last request went out, or -1 once the server has answered it.
var _market_request_msec := -1
var party_panel: PanelContainer
var gauntlet_ready_window: Control
var gauntlet_loot_window: Control
var party_header: Label
var party_rows: VBoxContainer
var party_invite_row: HBoxContainer
var party_invite_label: Label
var party_status: Label
var party_leave_button: Button
var party_add_bot: MenuButton
var _party_was_joined := false
var _party_last_inviter := ""
var party_collapse: Button
var party_scroll: ScrollContainer
var _party_collapsed := false
var party_options: MenuButton
var party_resize_grip: Label
var _party_numbers := false
var _party_custom_size := false
var _party_expanded_size := Vector2(PARTY_WIDTH, 0)
var _party_resizing := false
var _party_resize_mouse := Vector2.ZERO
var _party_resize_size := Vector2.ZERO
var preferences_path := WindowPreferences.SETTINGS_PATH
var achievements_panel: PanelContainer
var achievements_header: Label
var achievements_tabs: HBoxContainer
var achievements_rows: VBoxContainer
var achievements_title_picker: OptionButton
var achievements_status: Label
## Which category is showing. The player's choice about their own window; the
## pages themselves are the server's, one per category in the catalogue.
var _achievements_page := ""

var _merchant_mode := "buy"
## The quest the player asked to keep on screen, by its title. Which quest to
## watch is the player's choice about their own screen, so it is kept here;
## everything shown about it is the server's own journal entry, restated on
## every 224, and a tracked quest the server stops sending simply stops being
## tracked.
var _tracked_quest_title := ""
var _field_tracking_title := ""
var _tracked_quest_layout_revision := 0

func _ready() -> void:
	name = "ExtensionWindows"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Anchors alone keep the current (zero) rect; the offsets have to be reset
	# too, or every centre-anchored readout lands 640 pixels off screen.
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	gauntlet_ready_window = preload("res://src/ui/gauntlet_ready_window.gd").new()
	add_child(gauntlet_ready_window)
	gauntlet_loot_window = preload("res://src/ui/gauntlet_loot_window.gd").new()
	add_child(gauntlet_loot_window)
	AppState.state_changed.connect(_on_state_changed)
	sync_all()

func configure(atlas: ItemAtlas, guide: Control = null) -> void:
	item_atlas = atlas
	gauntlet_loot_window.configure(atlas)
	quest_guide = guide
	if quest_guide != null:
		quest_guide.tracking_changed.connect(_on_quest_guide_tracking_changed)
	_sync_quests()

func _on_quest_guide_tracking_changed() -> void:
	if not quest_guide.is_quest_tracked() and quest_guide.quest_title() == _tracked_quest_title:
		_tracked_quest_title = ""
	_sync_quests()

## True when a window that owns the pointer or the keyboard is open, so the
## rest of the HUD can treat the screen as busy.
func has_open_window() -> bool:
	for panel: PanelContainer in _cascade():
		if panel != party_panel and panel.visible:
			return true
	return false

## Closes the topmost open window. Returns true when something closed, so the
## cancel cascade in main.gd can stop there.
func close_top(include_party := false) -> bool:
	for panel: PanelContainer in _cascade():
		# The roster is persistent HUD; its close button and toggle still work.
		if panel == party_panel and not include_party or not panel.visible:
			continue
		if panel == gauntlet_loot_window.panel:
			gauntlet_loot_window.close()
		elif panel == gauntlet_ready_window.panel:
			gauntlet_ready_window.cancel()
			panel.hide()
		elif panel == merchant_panel:
			AppState.close_merchant()
		elif panel == market_panel:
			AppState.close_marketplace()
		elif panel == detail_panel:
			AppState.close_item_detail()
		else:
			panel.hide()
		return true
	return false

func close_all() -> void:
	while close_top(true):
		pass

func toggle_quest_journal() -> void:
	_toggle(quest_panel)

func toggle_mail() -> void:
	_toggle(mail_panel)

func toggle_achievements() -> void:
	_sync_achievements()
	_toggle(achievements_panel)

## Cancel order: the windows the server opened come first, because they are the
## ones the player did not choose to have on screen.
func _cascade() -> Array[PanelContainer]:
	# The tracked-quest readout is deliberately absent: it is a HUD element the
	# player pinned, not a window covering the screen, so cancel leaves it be.
	return [gauntlet_loot_window.panel, gauntlet_ready_window.panel, merchant_panel, market_panel, detail_panel, mail_panel,
		quest_panel, party_panel, achievements_panel]

func _toggle(panel: PanelContainer) -> void:
	if panel.visible:
		panel.hide()
		return
	for other: PanelContainer in _cascade():
		if other != panel and other != party_panel and other != gauntlet_ready_window.panel:
			other.hide()
	panel.show()
	panel.move_to_front()

func _on_state_changed(path: StringName) -> void:
	match path:
		&"navigation":
			_sync_navigation()
		&"combat_state":
			_sync_combat()
		&"special_events":
			_sync_events()
		&"quest_journal", &"quest_archive":
			_sync_quests()
		&"lantern_tutorial":
			var guide: Dictionary = AppState.lantern_tutorial
			if str(guide.get("tutorial", "")) == "field_dispatch" or not _field_tracking_title.is_empty():
				if bool(guide.get("active", false)) and str(guide.get("tutorial", "")) == "field_dispatch":
					_field_tracking_title = str(guide.get("adventure", guide.get("title", "")))
					_tracked_quest_title = _field_tracking_title
				else:
					if _tracked_quest_title == _field_tracking_title:
						_tracked_quest_title = ""
					_field_tracking_title = ""
				_sync_quests()
		&"mail":
			_sync_mail()
		&"item_detail":
			_sync_detail()
		&"merchant":
			_sync_merchant()
		&"marketplace":
			_sync_marketplace()
		&"inventory":
			# The Sell tab lists the pack; it changes under the window.
			if market_panel.visible and _market_tab == "sell":
				_render_market()
		&"party":
			_sync_party()
		&"achievements_catalog":
			_sync_achievements()
		&"connection":
			if AppState.connection_state == "disconnected":
				_field_tracking_title = ""
				_tracked_quest_title = ""
				# A dropped session is not a fight that just ended: nothing
				# from it should linger, pinned or not.
				combat_panel.hide()
				combat_panel.modulate.a = 1.0
				sync_all()

func sync_all() -> void:
	_sync_navigation()
	_sync_combat()
	_sync_events()
	_sync_quests()
	_sync_mail()
	_sync_detail()
	_sync_merchant()
	_sync_marketplace()
	_sync_party()
	_sync_achievements()

# --- navigation --------------------------------------------------------------

func _sync_navigation() -> void:
	if not bool(AppState.navigation.get("active", false)):
		navigation_label.hide()
		return
	navigation_label.text = "%s  %d, %d  (%d tiles)" % [
		str(AppState.navigation.get("label", "Waypoint")),
		int(AppState.navigation.get("x", 0)), int(AppState.navigation.get("y", 0)),
		int(AppState.navigation.get("distance", 0))]
	navigation_label.show()

# --- combat ------------------------------------------------------------------

func _sync_combat() -> void:
	if not combat_hud_enabled:
		combat_panel.hide()
		return
	if not bool(AppState.combat_state.get("active", false)):
		return
	var target_name: String = str(AppState.combat_state.get("target_name", ""))
	combat_target.text = target_name if not target_name.is_empty() else "Target"
	combat_player_bar.max_value = maxi(1, int(
		AppState.combat_state.get("player_max_health", 1)))
	combat_player_bar.value = int(AppState.combat_state.get("player_health", 0))
	combat_target_bar.max_value = maxi(1, int(
		AppState.combat_state.get("target_max_health", 1)))
	combat_target_bar.value = int(AppState.combat_state.get("target_health", 0))
	combat_event.text = _combat_event_text()
	combat_panel.modulate.a = 1.0
	combat_panel.show()
	_combat_expiry_msec = Time.get_ticks_msec() + COMBAT_HOLD_MSEC

## The box holds for five seconds after the last thing combat said and then
## fades. A pinned one is left alone, and a dismissed one is already hidden.
func _process(_delta: float) -> void:
	if not combat_panel.visible or combat_hud_pinned or _combat_dragging:
		return
	var past: int = Time.get_ticks_msec() - _combat_expiry_msec
	if past < 0:
		return
	if past >= COMBAT_FADE_MSEC:
		combat_panel.hide()
		combat_panel.modulate.a = 1.0
		return
	combat_panel.modulate.a = 1.0 - float(past) / float(COMBAT_FADE_MSEC)

## Left drag moves the box; right click offers to pin or dismiss it.
func _on_combat_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var button: InputEventMouseButton = event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_RIGHT and button.pressed:
			combat_menu.set_item_checked(0, combat_hud_pinned)
			combat_menu.position = Vector2i(get_viewport().get_mouse_position())
			combat_menu.popup()
			combat_panel.accept_event()
			return
		if button.button_index != MOUSE_BUTTON_LEFT:
			return
		_combat_dragging = button.pressed
		if button.pressed:
			_combat_drag_offset = (get_viewport().get_mouse_position()
				- combat_panel.position)
			combat_panel.modulate.a = 1.0
		else:
			_combat_expiry_msec = Time.get_ticks_msec() + COMBAT_HOLD_MSEC
			combat_hud_preference_changed.emit()
		combat_panel.accept_event()
	elif event is InputEventMouseMotion and _combat_dragging:
		var wanted: Vector2 = get_viewport().get_mouse_position() - _combat_drag_offset
		# The panel is anchored to the top centre, so its position is an offset
		# from there rather than a screen coordinate; keeping it on screen is a
		# clamp against half the width either side.
		var half: float = size.x * 0.5
		combat_panel.position = Vector2(
			clampf(wanted.x, -half, maxf(-half, half - combat_panel.size.x)),
			clampf(wanted.y, 0.0, maxf(0.0, size.y - combat_panel.size.y)))
		combat_panel.accept_event()

func _on_combat_menu_pressed(id: int) -> void:
	if id == 0:
		set_combat_hud_pinned(not combat_hud_pinned)
	else:
		set_combat_hud_enabled(false)
	combat_hud_preference_changed.emit()

func set_combat_hud_enabled(enabled: bool) -> void:
	combat_hud_enabled = enabled
	if not enabled:
		combat_panel.hide()
		return
	combat_panel.modulate.a = 1.0
	_sync_combat()

func set_combat_hud_pinned(pinned: bool) -> void:
	combat_hud_pinned = pinned
	if pinned and combat_hud_enabled:
		combat_panel.modulate.a = 1.0
		combat_panel.show()

func combat_hud_position() -> Vector2:
	return combat_panel.position

func set_combat_hud_position(where: Vector2) -> void:
	combat_panel.position = where

func _combat_event_text() -> String:
	var damage: int = int(AppState.combat_state.get("recent_damage", 0))
	match int(AppState.combat_state.get("event", 0)):
		EloriaProtocol.COMBAT_EVENT_HIT:
			return "Hit for %d" % damage
		EloriaProtocol.COMBAT_EVENT_INCOMING:
			return "Took %d damage" % damage
		EloriaProtocol.COMBAT_EVENT_MISS:
			return "Missed"
		EloriaProtocol.COMBAT_EVENT_DODGE:
			return "Dodged"
		EloriaProtocol.COMBAT_EVENT_DEFEAT:
			return "Fight ended"
		_:
			return "In combat"

# --- special events ----------------------------------------------------------

func _sync_events() -> void:
	if AppState.special_events.is_empty():
		events_panel.hide()
		return
	events_text.text = "\n".join(AppState.special_events)
	events_panel.show()

# --- quest journal -----------------------------------------------------------

func _sync_quests() -> void:
	if not _field_tracking_title.is_empty():
		_tracked_quest_title = _field_tracking_title
	quest_active_button.button_pressed = not _quest_showing_archive
	quest_done_button.button_pressed = _quest_showing_archive
	quest_done_button.text = "Completed (%d)" % AppState.quest_archive.size()
	quest_count.text = ("%d COMPLETE" % AppState.quest_archive.size()
		if _quest_showing_archive else "%d ACTIVE" % AppState.quest_journal.size())
	if _quest_showing_archive:
		_sync_quest_archive()
		_sync_tracked_quest()
		return
	var selected: int = _selected_index(quest_list)
	quest_list.clear()
	for entry: Dictionary in AppState.quest_journal:
		var target: int = int(entry.get("target", 0))
		var current: int = int(entry.get("current", 0))
		var status: String = ("ready" if bool(entry.get("ready", false))
			else ("%d/%d" % [current, target] if target > 0 else "in progress"))
		quest_list.add_item("◆  %s  [%s]" % [str(entry.get("title", "")), status])
		var row: int = quest_list.item_count - 1
		quest_list.set_item_custom_fg_color(row, QUEST_BRASS_BRIGHT
			if bool(entry.get("ready", false)) else QUEST_WARM_TEXT)
	if AppState.quest_journal.is_empty():
		quest_detail.text = ("[center][color=#7c5a34][font_size=16]"
			+ "%s[/font_size][/color][/center]" % tr("ELORIA_QUEST_NONE"))
		quest_track_button.disabled = true
		quest_track_button.text = "Track"
		_sync_tracked_quest()
		return
	quest_track_button.disabled = false
	var index: int = clampi(selected, 0, AppState.quest_journal.size() - 1)
	quest_list.select(index)
	_sync_tracked_quest()
	_show_quest(index)

func _quest_is_tracked(title: String) -> bool:
	if quest_guide != null and quest_guide.quest_title() == title:
		return quest_guide.is_quest_tracked()
	return not title.is_empty() and title == _tracked_quest_title

## The finished half of the same window. Tracking is meaningless here - there
## is nothing left to do - so the button is disabled rather than removed, which
## would move everything else when the view changes.
func _sync_quest_archive() -> void:
	var selected: int = _selected_index(quest_list)
	quest_list.clear()
	for entry: Dictionary in AppState.quest_archive:
		quest_list.add_item("✓  %s  [%s]" % [str(entry.get("title", "")),
			str(entry.get("location", ""))])
		quest_list.set_item_custom_fg_color(quest_list.item_count - 1,
			QUEST_MUTED_TEXT)
	quest_track_button.disabled = true
	if AppState.quest_archive.is_empty():
		quest_detail.text = ("[center][color=#7c5a34][font_size=16]"
			+ "You have not finished any quests yet.[/font_size][/color][/center]")
		return
	var index: int = clampi(selected, 0, AppState.quest_archive.size() - 1)
	quest_list.select(index)
	_show_archived_quest(index)

func _on_quest_view(archive: bool) -> void:
	if _quest_showing_archive == archive:
		# Both are toggle buttons, so pressing the one already down would
		# otherwise un-press it and leave the window showing neither view.
		quest_active_button.button_pressed = not archive
		quest_done_button.button_pressed = archive
		return
	_quest_showing_archive = archive
	quest_list.deselect_all()
	_sync_quests()

## Pins the selected quest to the screen, or unpins it when it is already the
## tracked one.
func _on_quest_track_pressed() -> void:
	if _quest_showing_archive:
		return
	var index: int = _selected_index(quest_list)
	if index < 0 or index >= AppState.quest_journal.size():
		return
	var title: String = str(
		(AppState.quest_journal[index] as Dictionary).get("title", ""))
	var entry: Dictionary = AppState.quest_journal[index]
	if quest_guide != null and quest_guide.quest_title() == title:
		quest_guide.set_quest_tracked(not quest_guide.is_quest_tracked())
		return
	if str(entry.get("location", "")) == "Main world":
		var error := Network.send_chat("#quests untrack" if title == _tracked_quest_title else "#quests track " + title)
		if error != OK:
			AppState.append_local_message("Could not update quest tracking. Reconnect and try again.")
		return
	if not _field_tracking_title.is_empty():
		Network.send_chat("#quests untrack")
		_field_tracking_title = ""
	_tracked_quest_title = "" if title == _tracked_quest_title else title
	_sync_quests()

func _on_quest_untrack_pressed() -> void:
	_tracked_quest_title = ""
	_sync_quests()

## The tracked quest as the server last stated it. Nothing is remembered from
## an earlier journal: if the server stops listing the quest, the readout goes.
func _sync_tracked_quest() -> void:
	var tracked: Dictionary = {}
	for entry: Dictionary in AppState.quest_journal:
		if str(entry.get("title", "")) == _tracked_quest_title:
			tracked = entry
			break
	if tracked.is_empty():
		_tracked_quest_title = ""
		_tracked_quest_layout_revision += 1
		tracked_quest.hide()
		return
	if str(tracked.get("location", "")) == "Main world" or (
			quest_guide != null and quest_guide.quest_title() == _tracked_quest_title):
		# The guide owns this quest's window, including its tracking choice.
		tracked_quest.hide()
		return
	var target: int = int(tracked.get("target", 0))
	var lines: Array[String] = [
		"[center][font_size=20][color=#8f6425][b]QUEST TRACKER[/b][/color][/font_size][/center]",
		"[font_size=17][color=#592b18]◆  [b]%s[/b][/color][/font_size]"
			% str(tracked.get("title", "")),
		"[indent][font_size=15][color=#2b1a0e]%s[/color][/font_size][/indent]"
			% str(tracked.get("objective", ""))]
	if bool(tracked.get("ready", false)):
		lines.append("[indent][font_size=15][color=#946c1d][b]Ready to turn in[/b][/color]"
			+ "[color=#5e4b35] at %s[/color][/font_size][/indent]"
			% str(tracked.get("location", "unknown")))
	elif target > 0:
		lines.append(("[indent][font_size=15][color=#70491d]%d of %d[/color]"
			+ "[color=#5e4b35]  ·  %s[/color][/font_size][/indent]") % [
				int(tracked.get("current", 0)), target,
				str(tracked.get("location", "unknown"))])
	else:
		lines.append("[indent][font_size=15][color=#5e4b35]%s[/color][/font_size][/indent]"
			% str(tracked.get("location", "unknown")))
	# Let the label report its natural wrapped height for this one update. The
	# event-driven fitter turns this back off after applying the bounded size.
	tracked_quest.custom_minimum_size.y = QUEST_TRACKER_SIZE.y
	tracked_quest.size.y = QUEST_TRACKER_SIZE.y
	tracked_quest_text.fit_content = true
	tracked_quest_text.text = "\n".join(lines)
	tracked_quest.show()
	# RichTextLabel resolves wrapped line height after its container settles.
	# Fit only when the server changes the quest, never from `_process()`.
	_tracked_quest_layout_revision += 1
	_fit_tracked_quest_to_content(_tracked_quest_layout_revision)

func _fit_tracked_quest_to_content(revision: int) -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	if revision != _tracked_quest_layout_revision or not tracked_quest.visible:
		return
	var content_height := tracked_quest_text.get_content_height()
	tracked_quest_text.fit_content = false
	var desired_height := clampf(content_height + 32.0,
		QUEST_TRACKER_SIZE.y, QUEST_TRACKER_MAX_HEIGHT)
	tracked_quest.custom_minimum_size.y = desired_height
	tracked_quest.size.y = desired_height
	tracked_quest_text.scroll_active = content_height + 32.0 > QUEST_TRACKER_MAX_HEIGHT

## One list serves both halves of the window, so a selection has to be read
## against whichever half is showing - against the other one it would either
## describe the wrong quest or silently describe nothing.
func _on_quest_selected(index: int) -> void:
	if _quest_showing_archive:
		_show_archived_quest(index)
	else:
		_show_quest(index)

func _show_archived_quest(index: int) -> void:
	if index < 0 or index >= AppState.quest_archive.size():
		return
	var entry: Dictionary = AppState.quest_archive[index]
	quest_detail.text = ("[font_size=22][color=#592b18][b]%s[/b][/color][/font_size]"
		+ "\n[color=#9b682d][font_size=11][b]COMPLETED IN[/b][/font_size][/color]"
		+ "\n[color=#2b1a0e]%s[/color]\n\n"
		+ "[color=#9b682d][font_size=11][b]CHRONICLE[/b][/font_size][/color]"
		+ "\n[color=#2b1a0e]%s[/color]") % [str(entry.get("title", "")),
			str(entry.get("location", "")), str(entry.get("detail", ""))]

func _show_quest(index: int) -> void:
	if index < 0 or index >= AppState.quest_journal.size():
		return
	var entry: Dictionary = AppState.quest_journal[index]
	quest_track_button.text = "Untrack" if _quest_is_tracked(str(entry.get("title", ""))) else "Track"
	var target: int = int(entry.get("target", 0))
	var lines: Array[String] = [
		"[font_size=22][color=#592b18][b]%s[/b][/color][/font_size]"
			% str(entry.get("title", "")),
		"[color=#9b682d][font_size=11][b]QUEST OBJECTIVES[/b][/font_size][/color]",
		"[color=#2b1a0e]◆  %s[/color]" % str(entry.get("objective", "")),
		"",
		"[color=#9b682d][font_size=11][b]LOCATION[/b][/font_size][/color]",
		"[color=#2b1a0e]%s[/color]" % str(entry.get("location", "unknown"))]
	if bool(entry.get("ready", false)):
		lines.append("\n[color=#946c1d][b]%s[/b][/color]"
			% tr("ELORIA_QUEST_READY"))
	elif target > 0:
		lines.append("\n[color=#9b682d][font_size=11][b]PROGRESS[/b][/font_size][/color]")
		lines.append("[color=#2b1a0e]%d of %d complete[/color]"
			% [int(entry.get("current", 0)), target])
	quest_detail.text = "\n".join(lines)

# --- mail --------------------------------------------------------------------

func _sync_mail() -> void:
	var selected: int = _selected_index(mail_list)
	mail_list.clear()
	for message: Dictionary in AppState.mail:
		mail_list.add_item("%s%s  -  %s" % [
			"" if bool(message.get("read", false)) else "* ",
			str(message.get("sender", "")), str(message.get("subject", ""))])
	if AppState.mail.is_empty():
		mail_body.text = "[center]No mail.[/center]"
		return
	var index: int = clampi(selected, 0, AppState.mail.size() - 1)
	mail_list.select(index)
	_show_mail(index)

func _show_mail(index: int) -> void:
	if index < 0 or index >= AppState.mail.size():
		return
	var message: Dictionary = AppState.mail[index]
	mail_body.text = "[b]%s[/b]\nfrom %s\n\n%s" % [
		str(message.get("subject", "")), str(message.get("sender", "")),
		str(message.get("body", ""))]

func _on_mail_selected(index: int) -> void:
	_show_mail(index)
	if index < 0 or index >= AppState.mail.size():
		return
	var message: Dictionary = AppState.mail[index]
	if bool(message.get("read", false)):
		return
	# The read flag is the server's. Asking it to mark the message read is the
	# only way to change it; the list redraws when the new inbox arrives.
	Network.send_chat("#mail read %d" % int(message.get("mail_id", 0)))

# --- item detail -------------------------------------------------------------

## Whether an item description may open this window. The inventory sets it
## before each request: a plain click wants only the line along the bottom of
## the inventory, and Inspect wants the whole card. The state that arrives is
## the same either way - what changes is whether it is shown here.
var detail_popup_allowed := true

func _sync_detail() -> void:
	if not bool(AppState.item_detail.get("open", false)) or not detail_popup_allowed:
		detail_panel.hide()
		return
	var lines: Array[String] = ["[b]%s[/b]" % str(AppState.item_detail.get("name", ""))]
	var category: String = str(AppState.item_detail.get("category", ""))
	if not category.is_empty():
		lines.append(category)
	if bool(AppState.item_detail.get("equipped", false)):
		lines.append("[color=#8fdc8f]Equipped.[/color]")
	var quantity: int = int(AppState.item_detail.get("quantity", 0))
	if quantity > 1:
		lines.append("Quantity: %d" % quantity)
	for field: String in ["description", "stats"]:
		var value: String = str(AppState.item_detail.get(field, ""))
		if not value.is_empty():
			lines.append("")
			lines.append(value)
	var comparison_name: String = str(AppState.item_detail.get("comparison_name", ""))
	if not comparison_name.is_empty():
		lines.append("")
		lines.append("[b]Compared with %s[/b]" % comparison_name)
		lines.append(str(AppState.item_detail.get("comparison", "")))
	detail_text.text = "\n".join(lines)
	detail_panel.show()
	detail_panel.move_to_front()

# --- merchant ----------------------------------------------------------------

func _sync_merchant() -> void:
	_merchant_request_pending = false
	if not bool(AppState.merchant.get("open", false)):
		merchant_panel.hide()
		_merchant_actor = -1
		return
	var actor_id := int(AppState.merchant.get("actor_id", -1))
	var opening := _merchant_actor != actor_id
	var selected_id := -1
	if not opening and merchant_list != null and not merchant_list.get_selected_items().is_empty():
		selected_id = int(merchant_list.get_item_metadata(merchant_list.get_selected_items()[0]))
	elif opening:
		_merchant_mode = "buy"
		merchant_quantity.text = "1"
	_merchant_actor = actor_id
	merchant_header.text = "%s    ·    Gold: %d gc    ·    Carry: %d/%d" % [
		str(AppState.merchant.get("npc_name", "Merchant")),
		int(AppState.merchant.get("gold", 0)), int(AppState.merchant.get("carried", 0)),
		int(AppState.merchant.get("capacity", 0))]
	merchant_buy_list.clear()
	merchant_sell_list.clear()
	for entry: Dictionary in AppState.merchant.get("items", []) as Array:
		if int(entry.get("buy_price", 0)) > 0:
			_add_merchant_row(merchant_buy_list, entry, false)
		if int(entry.get("owned", 0)) > 0 and int(entry.get("sell_price", 0)) > 0:
			_add_merchant_row(merchant_sell_list, entry, true)
	merchant_empty_pack.visible = merchant_sell_list.item_count == 0
	merchant_list = merchant_buy_list if _merchant_mode == "buy" else merchant_sell_list
	for index: int in range(merchant_list.item_count):
		if int(merchant_list.get_item_metadata(index)) == selected_id:
			merchant_list.select(index)
			break
	if opening and merchant_list.item_count > 0:
		merchant_list.select(0)
	if merchant_list.get_selected_items().is_empty():
		merchant_quantity.text = "1"
	else:
		merchant_quantity.text = str(clampi(int(merchant_quantity.text), 1,
			maxi(1, _merchant_maximum(_merchant_entry()))))
		merchant_list.ensure_current_is_visible()
	merchant_status.text = ""
	_sync_merchant_summary()
	merchant_panel.show()
	merchant_panel.move_to_front()

func _add_merchant_row(list: ItemList, entry: Dictionary, selling: bool) -> void:
	var name := str(entry.get("name", ""))
	var price := _merchant_price_label(entry, selling)
	var label := "%s  ×%d     ·     %s" % [name, int(entry.get("owned", 0)), price] if selling else "%s     ·     %s" % [name, price]
	var row := list.item_count
	list.add_item(label, _named_icon(int(entry.get("image_id", 0)), name))
	list.set_item_metadata(row, int(entry.get("index", row)))
	list.set_item_tooltip(row, "%s\n%s: %s\nIn your pack: %d" % [name, "Sell price" if selling else "Buy price", price, int(entry.get("owned", 0))])

func _merchant_price_label(entry: Dictionary, selling: bool) -> String:
	var price := int(entry.get("sell_price" if selling else "buy_price", 0))
	var lot := maxi(1, int(entry.get("sell_quantity", 1))) if selling else 1
	return "%d gc each" % price if lot == 1 else "%s gc each (%d for %d gc)" % [str(float(price) / lot), lot, price]

func _on_merchant_selected(_index: int, mode: String) -> void:
	merchant_quantity.text = "1"
	_merchant_mode = mode
	merchant_list = merchant_buy_list if mode == "buy" else merchant_sell_list
	merchant_quantity.text = str(maxi(1, int(_merchant_entry().get("sell_quantity", 1)))) if mode == "sell" else "1"
	(merchant_sell_list if mode == "buy" else merchant_buy_list).deselect_all()
	merchant_list.ensure_current_is_visible()
	_sync_merchant_summary()

func _on_merchant_mode(mode: String) -> void:
	merchant_quantity.text = "1"
	_merchant_mode = mode
	merchant_list = merchant_buy_list if mode == "buy" else merchant_sell_list
	(merchant_sell_list if mode == "buy" else merchant_buy_list).deselect_all()
	if merchant_list.get_selected_items().is_empty() and merchant_list.item_count > 0:
		merchant_list.select(0)
	merchant_quantity.text = str(maxi(1, int(_merchant_entry().get("sell_quantity", 1)))) if mode == "sell" else "1"
	merchant_list.ensure_current_is_visible()
	_sync_merchant_summary()

func _merchant_entry() -> Dictionary:
	var selected := merchant_list.get_selected_items()
	if selected.is_empty():
		return {}
	var item_index := int(merchant_list.get_item_metadata(selected[0]))
	for entry: Dictionary in AppState.merchant.get("items", []) as Array:
		if int(entry.get("index", -1)) == item_index:
			return entry
	return {}

func _merchant_maximum(entry: Dictionary) -> int:
	if entry.is_empty():
		return 0
	if _merchant_mode == "sell":
		var lot := maxi(1, int(entry.get("sell_quantity", 1)))
		var owned := mini(1000000, int(entry.get("owned", 0)))
		return owned - owned % lot
	var price := int(entry.get("buy_price", 0))
	var maximum := mini(1000000, int(AppState.merchant.get("gold", 0)) / price) if price > 0 else 1000000
	var weight := int(entry.get("emu", 0))
	if weight > 0:
		var free := maxi(0, int(AppState.merchant.get("capacity", 0)) - int(AppState.merchant.get("carried", 0)))
		maximum = mini(maximum, free / weight)
	return maximum

func _merchant_change_quantity(delta: int) -> void:
	var lot := maxi(1, int(_merchant_entry().get("sell_quantity", 1))) if _merchant_mode == "sell" else 1
	merchant_quantity.text = str(clampi(int(merchant_quantity.text) + delta * lot, lot, 1000000))
	_sync_merchant_summary()

func _merchant_set_maximum() -> void:
	merchant_quantity.text = str(maxi(1, _merchant_maximum(_merchant_entry())))
	_sync_merchant_summary()

func _sync_merchant_summary(_text: String = "") -> void:
	merchant_buy_mode.set_pressed_no_signal(_merchant_mode == "buy")
	merchant_sell_mode.set_pressed_no_signal(_merchant_mode == "sell")
	var entry := _merchant_entry()
	merchant_trade.disabled = true
	if entry.is_empty():
		merchant_selection.text = "Select an item to buy or sell."
		merchant_description.text = "Select an item to read its description."
		merchant_totals.text = ""
		merchant_selected_icon.texture = null
		merchant_trade.text = "Buy" if _merchant_mode == "buy" else "Sell"
		return
	var buying := _merchant_mode == "buy"
	var price := int(entry.get("buy_price" if buying else "sell_price", 0))
	merchant_selection.text = "%s\n%s · %s" % ["BUYING" if buying else "SELLING", str(entry.get("name", "")), _merchant_price_label(entry, not buying)]
	merchant_selected_icon.texture = _named_icon(int(entry.get("image_id", 0)), str(entry.get("name", "")))
	var description := str(entry.get("description", "")).strip_edges()
	merchant_description.text = description if not description.is_empty() else "No description available."
	var quantity_text := merchant_quantity.text.strip_edges()
	var valid := quantity_text.is_valid_int() and int(quantity_text) >= 1 and int(quantity_text) <= 1000000
	if not valid:
		merchant_totals.text = "Enter a whole quantity\nbetween 1 and 1,000,000."
		return
	var quantity := int(quantity_text)
	var lot := 1 if buying else maxi(1, int(entry.get("sell_quantity", 1)))
	if quantity % lot != 0:
		merchant_totals.text = "Sell in multiples of %d.\n%d items = %d gc." % [lot, lot, price]
		return
	var maximum := _merchant_maximum(entry)
	merchant_trade.text = "%s %d" % ["Buy" if buying else "Sell", quantity]
	if not buying and maximum == 0 and lot > 1:
		merchant_totals.text = "Need %d items to sell\nfor %d gc." % [lot, price]
		return
	if quantity > maximum:
		merchant_totals.text = "Maximum available: %d\n%s" % [maximum,
			"Not enough gold or free carry space." if buying else "You do not own that many."]
		merchant_trade.tooltip_text = merchant_totals.text
		return
	var total := quantity / lot * price
	var gold_after := int(AppState.merchant.get("gold", 0)) + (-total if buying else total)
	merchant_totals.text = "%s: %d gc\nGold after: %d gc" % ["Cost" if buying else "Receive", total, gold_after]
	if entry.has("emu"):
		var carry_after := int(AppState.merchant.get("carried", 0)) + int(entry.emu) * quantity * (1 if buying else -1)
		merchant_totals.text += "\nCarry after: %d/%d" % [maxi(0, carry_after), int(AppState.merchant.get("capacity", 0))]
	merchant_trade.text = "%s %d" % ["Buy" if buying else "Sell", quantity]
	merchant_trade.disabled = _merchant_request_pending
	merchant_trade.tooltip_text = "Waiting for the merchant's response." if _merchant_request_pending else ""

## The dedicated shop command accepts an exact quantity in one request. The
## server validates stock, gold, carrying capacity and ownership as before.
func _merchant_trade_command() -> String:
	var quantity_text := merchant_quantity.text.strip_edges()
	if not quantity_text.is_valid_int() or int(quantity_text) < 1 or int(quantity_text) > 1000000:
		merchant_status.text = "Enter a whole quantity between 1 and 1,000,000."
		return ""
	var actor_id: int = int(AppState.merchant.get("actor_id", -1))
	var selected: PackedInt32Array = merchant_list.get_selected_items()
	if actor_id < 0 or selected.is_empty():
		merchant_status.text = "Select an item first."
		return ""
	var item_index: int = int(merchant_list.get_item_metadata(int(selected[0])))
	return "#shop %s %d %d %d" % [_merchant_mode, actor_id, item_index, int(quantity_text)]


func _on_merchant_trade() -> void:
	_sync_merchant_summary()
	if merchant_trade.disabled:
		return
	var command := _merchant_trade_command()
	if command.is_empty():
		return
	var trade_error: Error = Network.send_chat(command)
	if trade_error != OK:
		merchant_status.text = "Merchant request failed: " + error_string(trade_error)
		return
	_merchant_request_pending = true
	_sync_merchant_summary()
	merchant_status.text = "Buying…" if _merchant_mode == "buy" else "Selling…"

# --- marketplace -------------------------------------------------------------

## The Nymara Exchange. Browse and My listings are pages the server states;
## Sell is the player's own pack, read from the inventory the client already
## holds, so listing something never asks for a slot number. Every request is
## the `#auction` command a player could type in chat, and the window redraws
## from the state the server answers with. A server that heard
## `market_window_v2` answers refusals that way too, and pages and searches
## the whole market; v3 adds filters, sorting, and private sales history.
## An older one shows its first twenty rows unpaged.

func _sync_marketplace() -> void:
	if not bool(AppState.marketplace.get("open", false)):
		market_panel.hide()
		_market_tab = "browse"
		_market_request_msec = -1
		return
	var tab: String = str(AppState.marketplace.get("market_view",
		"mine" if int(AppState.marketplace.get("view", 0)) == 1 else "browse"))
	if tab != _market_tab or not market_panel.visible:
		market_list.deselect_all()
	_market_tab = tab
	_market_request_msec = -1
	var notice: String = str(AppState.marketplace.get("notice", ""))
	match int(AppState.marketplace.get("notice_kind", EloriaProtocol.MARKET_NOTICE_NONE)):
		EloriaProtocol.MARKET_NOTICE_DONE:
			_market_status(notice, MARKET_DONE_COLOUR)
		EloriaProtocol.MARKET_NOTICE_REFUSED:
			_market_status(notice, MARKET_REFUSED_COLOUR)
		_:
			_market_status("", QUEST_MUTED_TEXT)
	if not market_search.has_focus():
		market_search.text = str(AppState.marketplace.get("query", ""))
	_sync_market_filters()
	_render_market()
	market_panel.show()
	market_panel.move_to_front()

func _render_market() -> void:
	var state: Dictionary = AppState.marketplace
	var paged: bool = int(state.get("version", 1)) >= 2
	var selling: bool = _market_tab == "sell"
	var history: bool = _market_tab == "history"
	var advanced: bool = int(state.get("version", 1)) >= 3
	market_list.visible = not history
	market_history.visible = history
	(market_tabs["history"] as Button).visible = advanced
	market_filters_box.visible = advanced and not selling
	for tab: String in market_tabs:
		(market_tabs[tab] as Button).set_pressed_no_signal(tab == _market_tab)
	var gold: int = int(state.get("gold", 0))
	var returned: int = int(state.get("returned_items", 0))
	market_header.text = "Proceeds: %s gc    ·    Return escrow: %s item%s" % [
		_market_number(gold), _market_number(returned), "" if returned == 1 else "s"]
	market_collect.disabled = gold <= 0 and returned <= 0
	market_collect.tooltip_text = ("Nothing is waiting for you." if market_collect.disabled
		else "Take your sale proceeds and returned items into your pack.")
	market_search_row.visible = paged and not selling
	market_page_row.visible = paged and not selling
	var selected_items: PackedInt32Array = market_list.get_selected_items()
	var previous_key: int = (int(market_list.get_item_metadata(selected_items[0]))
		if not selected_items.is_empty() else -1)
	var previous_index: int = int(selected_items[0]) if not selected_items.is_empty() else 0
	market_list.clear()
	if selling:
		for entry: Dictionary in _market_sell_entries():
			var row: int = market_list.item_count
			market_list.add_item("%s  ×%d" % [str(entry.name), int(entry.quantity)],
				_named_icon(int(entry.image_id), str(entry.name)))
			market_list.set_item_metadata(row, int(entry.slot))
			market_list.set_item_tooltip(row, "%s\nIn your pack: %d" % [
				str(entry.name), int(entry.quantity)])
	elif history:
		_render_market_sales(state.get("history", []) as Array)
	else:
		for listing: Dictionary in state.get("listings", []) as Array:
			_add_market_row(listing)
	var restored := false
	for row: int in range(market_list.item_count):
		if int(market_list.get_item_metadata(row)) == previous_key:
			market_list.select(row)
			restored = true
			break
	if not restored and market_list.item_count > 0:
		market_list.select(clampi(previous_index, 0, market_list.item_count - 1))
		_reset_market_amounts()
	if not market_list.get_selected_items().is_empty():
		market_list.ensure_current_is_visible()
	market_empty.visible = ((state.get("history", []) as Array).is_empty()
		if history else market_list.item_count == 0)
	market_empty.text = _market_empty_text()
	if paged:
		_render_market_page(state)
	var returns: Array = state.get("returns", []) as Array
	market_returns_box.visible = _market_tab == "mine" and not returns.is_empty()
	market_returns.clear()
	for entry: Dictionary in returns:
		var row: int = market_returns.item_count
		market_returns.add_item("%s  ×%d    ·    %s" % [str(entry.get("item_name", "")),
			int(entry.get("quantity", 0)), _market_return_reason(str(entry.get("reason", "")))],
			_named_icon(int(entry.get("image_id", 0)), str(entry.get("item_name", ""))))
		market_returns.set_item_selectable(row, false)
		if str(entry.get("reason", "")) == "expired":
			market_returns.set_item_custom_fg_color(row, MARKET_EXPIRING_COLOUR)
	_sync_market_footer()
	# A container grows to fit and never shrinks back; the window is a fixed size.
	market_panel.size = MARKET_SIZE

func _add_market_row(listing: Dictionary) -> void:
	var item_name: String = str(listing.get("item_name", ""))
	var quantity: int = int(listing.get("quantity", 0))
	var price: int = int(listing.get("unit_price", 0))
	var seconds: int = int(listing.get("seconds_left", 0))
	var own: bool = bool(listing.get("own", false))
	var parts: Array[String] = ["%s  ×%d" % [item_name, quantity], "%s gc each" % _market_number(price)]
	if _market_tab == "browse":
		parts.append("your listing" if own else str(listing.get("seller", "")))
	parts.append(_market_time_left(seconds))
	var row: int = market_list.item_count
	market_list.add_item("    ·    ".join(PackedStringArray(parts)), _named_icon(int(listing.get("image_id", 0)), item_name))
	market_list.set_item_metadata(row, int(listing.get("listing_id", -1)))
	market_list.set_item_tooltip(row, "Listing #%d\n%s ×%d at %s gc each (%s gc for all)\nSeller: %s\nExpires: %s" % [
		int(listing.get("listing_id", -1)), item_name, quantity, _market_number(price),
		_market_number(price * quantity), str(listing.get("seller", "")), _market_time_left(seconds)])
	if seconds < MARKET_EXPIRING_SECONDS:
		market_list.set_item_custom_fg_color(row, MARKET_EXPIRING_COLOUR)
	elif own and _market_tab == "browse":
		market_list.set_item_custom_fg_color(row, QUEST_MUTED_TEXT)

func _render_market_sales(sales: Array) -> void:
	var selected: TreeItem = market_history.get_selected()
	var previous: int = int((selected.get_metadata(0) as Dictionary).get("transaction_id", -1)) if selected else -1
	market_history.clear()
	var tree_root: TreeItem = market_history.create_item()
	var first: TreeItem
	var restored := false
	for sale: Dictionary in sales:
		var row: TreeItem = market_history.create_item(tree_root)
		if first == null:
			first = row
		var item_name: String = str(sale.get("item_name", ""))
		row.set_text(0, item_name)
		row.set_icon(0, _named_icon(int(sale.get("image_id", 0)), item_name))
		row.set_icon_max_width(0, 28)
		row.set_text(1, _market_number(int(sale.get("quantity", 0))))
		row.set_text(2, str(sale.get("buyer", "")))
		row.set_text(3, _market_number(int(sale.get("total", 0))))
		row.set_text(4, _market_sale_time(int(sale.get("created_at", 0))).trim_suffix(" UTC"))
		row.set_text_alignment(1, HORIZONTAL_ALIGNMENT_CENTER)
		row.set_text_alignment(3, HORIZONTAL_ALIGNMENT_RIGHT)
		row.set_text_alignment(4, HORIZONTAL_ALIGNMENT_CENTER)
		row.set_metadata(0, sale)
		var tooltip: String = "Listing #%d · Sale #%d\n%s ×%s at %s gc each\nBought by %s · %s" % [
			int(sale.get("listing_id", 0)), int(sale.get("transaction_id", 0)), item_name,
			_market_number(int(sale.get("quantity", 0))), _market_number(int(sale.get("unit_price", 0))),
			str(sale.get("buyer", "")), _market_sale_time(int(sale.get("created_at", 0)))]
		for column: int in range(5):
			row.set_tooltip_text(column, tooltip)
		if int(sale.get("transaction_id", -1)) == previous:
			row.select(0)
			restored = true
	if not restored and first != null:
		first.select(0)

func _market_sale_time(timestamp: int) -> String:
	return Time.get_datetime_string_from_unix_time(timestamp, true).left(16) + " UTC"

func _render_market_page(state: Dictionary) -> void:
	var total: int = int(state.get("total", 0))
	var offset: int = int(state.get("offset", 0))
	var page_size: int = maxi(1, int(state.get("page_size", 20)))
	var history: bool = _market_tab == "history"
	var shown: int = (state.get("history" if history else "listings", []) as Array).size()
	var noun: String = "sale" if history else "listing"
	var query: String = str(state.get("query", ""))
	var matching: String = "  matching “%s”" % query if not query.is_empty() else ""
	if total == 0:
		market_page_label.text = "No %ss" % noun + matching
	else:
		market_page_label.text = "%s–%s of %s %s%s%s" % [_market_number(offset + 1),
			_market_number(offset + maxi(1, shown)), _market_number(total),
			noun, "" if total == 1 else "s", matching]
	market_previous.disabled = offset <= 0
	market_next.disabled = offset + page_size >= total

func _market_empty_text() -> String:
	var query: String = str(AppState.marketplace.get("query", ""))
	if _market_tab == "history":
		return ("No sales match these filters. Clear filters to see all recorded sales."
			if _market_has_filters() else "No sales yet. Purchases of your listings will appear here.")
	if int(AppState.marketplace.get("version", 1)) >= 3 and _market_has_filters():
		return "No listings match these filters. Try a wider price range or Clear filters."
	match _market_tab:
		"sell":
			return "Your pack holds nothing to list. Gold Coins are the Exchange's currency."
		"mine":
			return ("None of your listings match “%s”." % query if not query.is_empty()
				else "You have no active listings. Sell lists something from your pack.")
	return ("No listings match “%s”." % query if not query.is_empty()
		else "Nothing is listed on the Exchange right now.")

func _market_return_reason(reason: String) -> String:
	match reason:
		"expired":
			return "expired - waiting in return escrow"
		"cancelled":
			return "cancelled - waiting in return escrow"
	return "waiting in return escrow"

## What the player can list: their pack, not what they wear, and not the
## currency the Exchange trades in.
func _market_sell_entries() -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var slots: Array = AppState.inventory.keys()
	slots.sort()
	for raw_slot: Variant in slots:
		var slot: int = int(raw_slot)
		if slot < 0 or slot >= MARKET_PACK_SLOTS:
			continue
		var item: Dictionary = AppState.inventory[raw_slot] as Dictionary
		var quantity: int = int(item.get("quantity", 0))
		var item_name: String = str(AppState.inventory_names.get(slot, ""))
		if quantity <= 0 or item_name == "Gold Coins":
			continue
		var image_id: int = int(item.get("image_id", 0))
		entries.append({"slot": slot, "quantity": quantity, "image_id": image_id,
			"name": item_name if not item_name.is_empty() else "Item #%d" % image_id})
	return entries

func _market_entry() -> Dictionary:
	if _market_tab == "history":
		var row: TreeItem = market_history.get_selected()
		return row.get_metadata(0) as Dictionary if row else {}
	var selected: PackedInt32Array = market_list.get_selected_items()
	if selected.is_empty():
		return {}
	var key: int = int(market_list.get_item_metadata(selected[0]))
	if _market_tab == "sell":
		for entry: Dictionary in _market_sell_entries():
			if int(entry.slot) == key:
				return entry
		return {}
	for listing: Dictionary in AppState.marketplace.get("listings", []) as Array:
		if int(listing.get("listing_id", -1)) == key:
			return listing
	return {}

## Gold the player is carrying, or -1 when the client cannot name its slots.
func _market_carried_gold() -> int:
	if AppState.inventory_names.is_empty():
		return -1
	var total := 0
	for raw_slot: Variant in AppState.inventory:
		if str(AppState.inventory_names.get(int(raw_slot), "")) == "Gold Coins":
			total += int((AppState.inventory[raw_slot] as Dictionary).get("quantity", 0))
	return total

## A whole quantity from 1 to `maximum`, or -1.
func _market_quantity(maximum: int) -> int:
	var text: String = market_quantity.text.strip_edges()
	if not text.is_valid_int():
		return -1
	var quantity: int = int(text)
	return quantity if quantity >= 1 and quantity <= maximum else -1

## A whole unit price the server accepts, or -1.
func _market_price() -> int:
	var text: String = market_price.text.strip_edges().replace(",", "")
	if not text.is_valid_int():
		return -1
	var price: int = int(text)
	return price if price >= 1 and price <= MARKET_PRICE_LIMIT else -1

func _reset_market_amounts() -> void:
	var entry: Dictionary = _market_entry()
	# A whole stack is what is usually listed; one is the cautious purchase.
	market_quantity.text = (str(int(entry.get("quantity", 1)))
		if _market_tab == "sell" and not entry.is_empty() else "1")
	if _market_tab == "sell":
		market_price.text = ""

func _on_market_selected(_index: int) -> void:
	_reset_market_amounts()
	_sync_market_footer()

func _market_change_quantity(delta: int) -> void:
	var text: String = market_quantity.text.strip_edges()
	var current: int = int(text) if text.is_valid_int() else 0
	market_quantity.text = str(clampi(current + delta, 1, maxi(1, _market_maximum())))
	_sync_market_footer()

func _market_set_all() -> void:
	market_quantity.text = str(maxi(1, _market_maximum()))
	_sync_market_footer()

func _market_maximum() -> int:
	return int(_market_entry().get("quantity", 1))

func _market_waiting() -> bool:
	return (_market_request_msec >= 0
		and Time.get_ticks_msec() - _market_request_msec < MARKET_REQUEST_MSEC)

func _sync_market_footer(_text: String = "") -> void:
	var buying: bool = _market_tab == "browse"
	var managing: bool = _market_tab == "mine"
	var selling: bool = _market_tab == "sell"
	market_quantity_box.visible = buying or selling
	market_price_box.visible = selling
	market_buy.visible = buying
	market_renew.visible = managing
	market_cancel.visible = managing
	market_sell.visible = selling
	for button: Button in [market_buy, market_renew, market_cancel, market_sell]:
		button.disabled = true
		button.tooltip_text = ""
	market_buy.text = "Buy"
	market_sell.text = "List for sale"
	market_totals.text = ""
	var waiting: bool = _market_waiting()
	var entry: Dictionary = _market_entry()
	if _market_tab == "history":
		market_selected_icon.texture = null
		market_selection.text = "Your completed sales · times shown in UTC"
		if not entry.is_empty():
			market_selected_icon.texture = _named_icon(int(entry.get("image_id", 0)), str(entry.get("item_name", "")))
			market_selection.text = "Listing #%d · %s gc each · %s gc received" % [
				int(entry.get("listing_id", 0)), _market_number(int(entry.get("unit_price", 0))),
				_market_number(int(entry.get("total", 0)))]
		return
	if entry.is_empty():
		market_selected_icon.texture = null
		market_selection.text = ("Select an item from your pack to list it." if selling
			else "Select one of your listings to renew or cancel it." if managing
			else "Select a listing to buy from it.")
		return
	var item_name: String = str(entry.get("name" if selling else "item_name", ""))
	market_selected_icon.texture = _named_icon(int(entry.get("image_id", 0)), item_name)
	var quantity_limit: int = int(entry.get("quantity", 0))
	if managing:
		market_selection.text = "%s  ×%d    ·    %s gc each\nExpires in %s." % [item_name,
			quantity_limit, _market_number(int(entry.get("unit_price", 0))),
			_market_time_left(int(entry.get("seconds_left", 0))).trim_suffix(" left")]
		market_totals.text = "Renew: 365 days from now.\nCancel or expiry: back to you\nthrough return escrow."
		market_renew.disabled = waiting
		market_cancel.disabled = waiting
		return
	if buying:
		var price: int = int(entry.get("unit_price", 0))
		if bool(entry.get("own", false)):
			market_selection.text = "%s  ×%d    ·    %s gc each\nYour own listing: see My listings." % [
				item_name, quantity_limit, _market_number(price)]
			market_buy.tooltip_text = "The Exchange will not sell you your own listing."
			return
		market_selection.text = "%s\n%s gc each    ·    %d on offer" % [
			item_name, _market_number(price), quantity_limit]
		var quantity: int = _market_quantity(quantity_limit)
		if quantity < 0:
			market_totals.text = "Enter a whole quantity\nfrom 1 to %d." % quantity_limit
			return
		var cost: int = quantity * price
		var carried: int = _market_carried_gold()
		market_totals.text = "Cost: %s gc" % _market_number(cost)
		market_buy.text = "Buy %d" % quantity
		if carried >= 0:
			market_totals.text += "\nYou carry: %s gc" % _market_number(carried)
			if cost > carried:
				market_totals.text += "\nNot enough gold."
				market_buy.tooltip_text = "You need %s gc." % _market_number(cost)
				return
		market_buy.disabled = waiting
		return
	market_selection.text = "%s\n%d in your pack" % [item_name, quantity_limit]
	var amount: int = _market_quantity(quantity_limit)
	if amount < 0:
		market_totals.text = "Enter a whole quantity\nfrom 1 to %d." % quantity_limit
		return
	market_sell.text = "List %d" % amount
	var unit_price: int = _market_price()
	if unit_price < 0:
		market_totals.text = "Enter a price per item\nin whole gold coins."
		return
	market_totals.text = "%s gc if all sell\nListed for 365 days." % _market_number(amount * unit_price)
	market_sell.disabled = waiting

func _market_status(text: String, colour: Color) -> void:
	market_status.text = text
	market_status.add_theme_color_override("font_color", colour)

## Sends one `#auction` command. The window redraws from the state the server
## answers with; until then the action buttons hold off a second click.
func _market_send(command: String, waiting_text: String) -> void:
	if command.is_empty():
		return
	var error: Error = Network.send_chat(command)
	if error != OK:
		_market_status("The request was not sent: " + error_string(error), MARKET_REFUSED_COLOUR)
		return
	_market_status(waiting_text, QUEST_MUTED_TEXT)
	# Only a version-2 server answers a refusal with a state; an older one
	# answers in chat alone, so holding the buttons would strand them.
	if int(AppState.marketplace.get("version", 1)) >= 2:
		_market_request_msec = Time.get_ticks_msec()
		get_tree().create_timer(MARKET_REQUEST_MSEC / 1000.0).timeout.connect(
			_sync_market_footer.bind(""))
	_sync_market_footer()

func _market_filter_values() -> Dictionary:
	return {"category": market_category.get_item_metadata(market_category.selected),
		"item_type": market_type.get_item_metadata(market_type.selected),
		"sort": MARKET_SORTS[market_sort.selected], "seller": market_seller.text.strip_edges(),
		"min_price": market_min_price.text.strip_edges().replace(",", ""),
		"max_price": market_max_price.text.strip_edges().replace(",", "")}

func _market_has_filters() -> bool:
	var filters: Dictionary = AppState.marketplace.get("filters", {}) as Dictionary
	for key: String in ["category", "item_type", "seller", "min_price", "max_price"]:
		if str(filters.get(key, "")) != "":
			return true
	return not str(AppState.marketplace.get("query", "")).is_empty()

func _market_fill_choice(picker: OptionButton, values: Array, all_text: String, selected: String) -> void:
	picker.clear()
	picker.add_item(all_text)
	picker.set_item_metadata(0, "")
	picker.select(0)
	for value: Variant in values:
		picker.add_item(str(value))
		var index: int = picker.item_count - 1
		picker.set_item_metadata(index, str(value))
		if str(value) == selected:
			picker.select(index)

func _sync_market_filters() -> void:
	var state: Dictionary = AppState.marketplace
	var filters: Dictionary = state.get("filters", {}) as Dictionary
	_market_fill_choice(market_category, state.get("categories", []) as Array,
		"All categories", str(filters.get("category", "")))
	_market_fill_choice(market_type, state.get("types", []) as Array,
		"All item types", str(filters.get("item_type", "")))
	var order_index: int = MARKET_SORTS.find(str(filters.get("sort", "name" if _market_tab == "browse" else "newest")))
	market_sort.select(maxi(0, order_index))
	market_sort.set_item_disabled(MARKET_SORTS.find("expiry"), _market_tab == "history")
	for pair: Array in [[market_seller, "seller"], [market_min_price, "min_price"], [market_max_price, "max_price"]]:
		var field: LineEdit = pair[0] as LineEdit
		if not field.has_focus():
			field.text = str(filters.get(str(pair[1]), ""))
	market_seller.placeholder_text = "Buyer name" if _market_tab == "history" else "Seller name"

func _market_view_command(view: String, offset: int, query: String, filters: Dictionary = {}) -> String:
	if int(AppState.marketplace.get("version", 1)) >= 3:
		return "#auction ui3 " + JSON.stringify({"view": view, "offset": maxi(0, offset),
			"query": query.strip_edges(), "filters": _market_filter_values() if filters.is_empty() else filters})
	var command: String = "#auction ui %s %d" % [view, maxi(0, offset)]
	var words: String = " ".join(query.strip_edges().split(" ", false))
	return command if words.is_empty() else command + " " + words

func _market_buy_command() -> String:
	var entry: Dictionary = _market_entry()
	if _market_tab != "browse" or entry.is_empty() or bool(entry.get("own", false)):
		return ""
	var quantity: int = _market_quantity(int(entry.get("quantity", 0)))
	if quantity < 0:
		return ""
	return "#auction buy %d %d" % [int(entry.listing_id), quantity]

func _market_listing_command(action: String) -> String:
	var entry: Dictionary = _market_entry()
	if _market_tab != "mine" or entry.is_empty():
		return ""
	return "#auction %s %d" % [action, int(entry.listing_id)]

func _market_sell_command() -> String:
	var entry: Dictionary = _market_entry()
	if _market_tab != "sell" or entry.is_empty():
		return ""
	var quantity: int = _market_quantity(int(entry.quantity))
	var price: int = _market_price()
	if quantity < 0 or price < 0:
		return ""
	return "#auction sell %d %d %d" % [int(entry.slot), quantity, price]

func _on_market_tab(tab: String) -> void:
	market_search.text = ""
	if tab == "sell":
		_market_tab = "sell"
		market_list.deselect_all()
		_market_status("", QUEST_MUTED_TEXT)
		_render_market()
		return
	for tab_name: String in market_tabs:
		(market_tabs[tab_name] as Button).set_pressed_no_signal(tab_name == tab)
	var defaults: Dictionary = {"sort": "name" if tab == "browse" else "newest"}
	_market_send(_market_view_command(tab, 0, "", defaults), "Opening " + (
		"your sales history…" if tab == "history" else "your listings…" if tab == "mine" else "the Exchange…"))

func _on_market_search(_text: String = "") -> void:
	if int(AppState.marketplace.get("version", 1)) >= 3:
		var filters: Dictionary = _market_filter_values()
		for key: String in ["min_price", "max_price"]:
			var value: String = str(filters[key])
			if not value.is_empty() and (not value.is_valid_int() or int(value) < 0 or int(value) > MARKET_PRICE_LIMIT):
				_market_status("Enter whole, non-negative prices up to 2,000,000,000 gc.", MARKET_REFUSED_COLOUR)
				return
		if str(filters.min_price) != "" and str(filters.max_price) != "" and int(filters.min_price) > int(filters.max_price):
			_market_status("Minimum price cannot exceed maximum price.", MARKET_REFUSED_COLOUR)
			return
	var view: String = _market_tab if _market_tab in ["mine", "history"] else "browse"
	_market_send(_market_view_command(view, 0, market_search.text), "Searching…")

func _on_market_filter_changed(_index: int) -> void:
	_on_market_search()

func _on_market_clear_search() -> void:
	market_search.text = ""
	market_category.select(0)
	market_type.select(0)
	market_sort.select(0 if _market_tab == "browse" else MARKET_SORTS.find("newest"))
	market_seller.text = ""
	market_min_price.text = ""
	market_max_price.text = ""
	_on_market_search()

func _on_market_page(direction: int) -> void:
	var state: Dictionary = AppState.marketplace
	var page_size: int = maxi(1, int(state.get("page_size", 20)))
	var view: String = str(state.get("market_view", "mine" if int(state.get("view", 0)) == 1 else "browse"))
	_market_send(_market_view_command(view,
		int(state.get("offset", 0)) + direction * page_size, str(state.get("query", "")),
		state.get("filters", {}) as Dictionary),
		"Turning the page…")

func _on_market_buy() -> void:
	_market_send(_market_buy_command(), "Buying…")

func _on_market_renew() -> void:
	_market_send(_market_listing_command("renew"), "Renewing…")

func _on_market_cancel() -> void:
	_market_send(_market_listing_command("cancel"), "Cancelling…")

func _on_market_sell() -> void:
	_market_send(_market_sell_command(), "Listing…")

func _on_market_collect() -> void:
	_market_send("#auction collect", "Collecting…")

## How long a listing has left, in the largest unit that is not zero.
func _market_time_left(seconds: int) -> String:
	if seconds >= 2 * 86400:
		return "%d days left" % (seconds / 86400)
	if seconds >= 86400:
		return "1 day left"
	if seconds >= 2 * 3600:
		return "%d hours left" % (seconds / 3600)
	if seconds >= 3600:
		return "1 hour left"
	if seconds >= 120:
		return "%d minutes left" % (seconds / 60)
	return "under 2 minutes left"

func _market_number(value: int) -> String:
	var digits: String = str(absi(value))
	var grouped := ""
	while digits.length() > 3:
		grouped = "," + digits.right(3) + grouped
		digits = digits.left(digits.length() - 3)
	return ("-" if value < 0 else "") + digits + grouped

# --- party -------------------------------------------------------------------

## The window exists to answer one question the world view cannot: how is
## somebody doing who is not on your screen. So every row carries health and
## ether as bars or numbers and states where that person is standing, and a member the
## server reports offline keeps their row and says so.
func _sync_party(open_requested: bool = false) -> void:
	var state: Dictionary = AppState.party
	var members: Array = state.get("members", []) as Array
	var invited_by: String = str(state.get("invited_by", ""))
	var in_party: bool = bool(state.get("in_party", false))
	var can_manage := not in_party
	for raw: Variant in members:
		if bool(raw.get("is_self", false)) and bool(raw.get("leader", false)):
			can_manage = true
	party_add_bot.visible = can_manage
	party_add_bot.disabled = members.size() >= 8
	# Health and location packets refresh the roster without reopening a
	# window the player dismissed. Joining or a new invitation can open it.
	var open_for_change: bool = ((in_party and not _party_was_joined)
		or (not invited_by.is_empty() and invited_by != _party_last_inviter))
	_party_was_joined = in_party
	_party_last_inviter = invited_by

	party_invite_label.text = "%s invited you. Accept?" % invited_by
	party_invite_row.visible = not invited_by.is_empty()
	for child: Node in party_rows.get_children():
		party_rows.remove_child(child)
		child.queue_free()

	if not in_party and invited_by.is_empty():
		party_header.tooltip_text = "No party"
		_layout_party()
		party_panel.hide()
		return

	var online_count := 0
	for raw: Variant in members:
		var member: Dictionary = raw as Dictionary
		if bool(member.get("online", false)):
			online_count += 1
		party_rows.add_child(_party_row(member))
	party_header.tooltip_text = ("Party - %d of %d online" % [online_count, members.size()]
		if not members.is_empty() else "No party")
	party_leave_button.disabled = members.is_empty()
	_layout_party()
	if open_requested or open_for_change:
		party_panel.show()
		party_panel.move_to_front()

func _party_row(member: Dictionary) -> Control:
	var row := HBoxContainer.new()
	row.name = "Member" + str(member.get("name", ""))
	row.custom_minimum_size.y = 36
	row.add_theme_constant_override("separation", 7)
	row.set_meta("leader", bool(member.get("leader", false)))
	var online: bool = bool(member.get("online", false))
	# A row that has stopped updating should look like it has stopped, rather
	# than showing the last health the player had before they vanished.
	var tint: Color = Color(1, 1, 1, 1) if online else Color(1, 1, 1, 0.45)

	row.modulate = tint
	row.tooltip_text = "%s%s\nHealth: %d/%d · Ether: %d/%d\n%s (%d, %d)" % [
		str(member.get("name", "")), (" (leader)" if bool(member.get("leader", false)) else "") + (" (offline)" if not online else ""),
		int(member.get("health", 0)), int(member.get("max_health", 0)),
		int(member.get("ether", 0)), int(member.get("max_ether", 0)),
		str(member.get("map_id", "")), int(member.get("x", 0)), int(member.get("y", 0))]
	var portrait: Control = PARTY_MEDALLION.new()
	portrait.name = "Portrait"
	portrait.configure(member)
	row.add_child(portrait)
	var vitals := VBoxContainer.new()
	vitals.name = "Vitals"
	vitals.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vitals.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	vitals.add_theme_constant_override("separation", 2)
	row.add_child(vitals)
	var header := HBoxContainer.new()
	header.name = "Identity"
	vitals.add_child(header)
	var title := Label.new()
	title.name = "Name"
	title.text = str(member.get("name", "")) + (" · you" if bool(member.get("is_self", false)) else "")
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title.add_theme_font_size_override("font_size", 12)
	title.add_theme_color_override("font_color", HUD_STYLE.TEXT)
	header.add_child(title)
	var where := Label.new()
	where.name = "Standing"
	where.text = "" if online else "offline"
	if bool(member.get("is_bot", false)) and str(member.get("map_id", "")).is_empty():
		where.text = "standby"
	where.add_theme_font_size_override("font_size", 10)
	where.add_theme_color_override("font_color", HUD_STYLE.MUTED)
	header.add_child(where)

	var low_health := float(member.get("health", 0)) / maxf(1, float(member.get("max_health", 1))) < 0.25
	var health_colour := PARTY_LOW_HEALTH if low_health else PARTY_HEALTH
	var health := _bar("Health", health_colour)
	health.custom_minimum_size = Vector2(0.0, 6.0)
	health.max_value = maxf(1.0, float(member.get("max_health", 1)))
	health.value = float(member.get("health", 0)) if online else 0.0
	vitals.add_child(health)
	health.visible = not _party_numbers
	vitals.add_child(_party_number("HealthNumber", int(member.get("health", 0)), int(member.get("max_health", 0)), health_colour, online))

	var ether := _bar("Ether", PARTY_ETHER)
	ether.custom_minimum_size = Vector2(0.0, 3.0)
	ether.max_value = maxf(1.0, float(member.get("max_ether", 1)))
	ether.value = float(member.get("ether", 0)) if online else 0.0
	vitals.add_child(ether)
	ether.visible = not _party_numbers
	vitals.add_child(_party_number("EtherNumber", int(member.get("ether", 0)), int(member.get("max_ether", 0)), PARTY_ETHER, online))
	if bool(member.get("is_bot", false)) and party_add_bot.visible:
		var remove := Button.new()
		remove.name = "RemoveBot"
		remove.text = "×"
		remove.tooltip_text = "Remove " + str(member.name)
		HUD_STYLE.button(remove)
		remove.pressed.connect(func() -> void: _send_party_command("#party bot remove " + str(member.name)))
		row.add_child(remove)
	return row

func _party_number(node_name: String, current: int, maximum: int, colour: Color, online: bool) -> Label:
	var number := Label.new()
	number.name = node_name
	number.text = "%d/%d" % [current, maximum] if online else "—/—"
	number.add_theme_font_size_override("font_size", 11)
	number.add_theme_color_override("font_color", colour)
	number.visible = _party_numbers
	return number

func _layout_party() -> void:
	var count := (AppState.party.get("members", []) as Array).size()
	var bounds := get_viewport_rect().size
	var dragger := party_panel.get_node("WindowDrag") as WindowDrag
	var bottom := bounds.y - WindowDrag.RESERVED_BOTTOM_BAR
	if is_instance_valid(dragger.bottom_hud):
		bottom = minf(bottom, dragger.bottom_hud.global_position.y)
	var maximum := Vector2(maxf(PARTY_MINIMUM.x, bounds.x - 108), maxf(PARTY_MINIMUM.y, bottom - 12))
	_party_expanded_size.x = clampf(_party_expanded_size.x, PARTY_MINIMUM.x, maximum.x)
	var compact := _party_expanded_size.x < PARTY_NAMES_WIDTH
	party_header.text = "Party" if compact and count > 0 else party_header.tooltip_text
	var row_height := 36.0
	for row: Node in party_rows.get_children():
		(row.get_node("Vitals/Identity") as Control).visible = not compact
		row_height = maxf(row_height, (row as Control).get_combined_minimum_size().y)
	party_scroll.visible = not _party_collapsed and count > 0
	party_scroll.custom_minimum_size.y = row_height
	var body := _window_body(party_panel)
	(body.get_node("PartyActions") as Control).visible = not _party_collapsed
	party_leave_button.visible = count > 0
	party_leave_button.text = "Leave" if compact else "Leave party"
	(body.get_node("PartyActions/PartyHint") as Control).visible = not compact
	party_status.visible = not _party_collapsed and not party_status.text.is_empty()
	party_collapse.text = "▸" if _party_collapsed else "▾"
	party_collapse.tooltip_text = "Expand party" if _party_collapsed else "Collapse party"
	party_panel.custom_minimum_size = Vector2(PARTY_MINIMUM.x, 0)
	var minimum := party_panel.get_combined_minimum_size()
	if _party_collapsed:
		_party_expanded_size.y = maxf(_party_expanded_size.y, PARTY_MINIMUM.y)
		party_panel.size = Vector2(_party_expanded_size.x, minimum.y)
	else:
		if not _party_custom_size:
			_party_expanded_size.y = minimum.y + (maxf(0, minf(288, party_rows.get_combined_minimum_size().y) - row_height) if count > 0 else 0)
		party_panel.size = _party_expanded_size.clamp(minimum.max(PARTY_MINIMUM), maximum)
		_party_expanded_size = party_panel.size
	dragger.clamp_into_view()

func resize_party_window(requested: Vector2) -> void:
	_party_custom_size = true
	_party_expanded_size = requested.max(PARTY_MINIMUM)
	_layout_party()

func _on_party_resize_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		var click := event as InputEventMouseButton
		_party_resizing = click.pressed
		if click.pressed:
			_party_resize_mouse = click.global_position
			_party_resize_size = party_panel.size
		else:
			_save_party_layout()
		party_resize_grip.accept_event()
	elif event is InputEventMouseMotion and _party_resizing:
		resize_party_window(_party_resize_size + (event as InputEventMouseMotion).global_position - _party_resize_mouse)
		party_resize_grip.accept_event()

func _on_party_option(id: int) -> void:
	if id == 0:
		var was_visible := party_panel.visible
		_party_numbers = not _party_numbers
		party_options.get_popup().set_item_checked(0, _party_numbers)
		_sync_party()
		party_panel.visible = was_visible
		_layout_party()
	elif id == 1:
		_party_custom_size = false
		_party_expanded_size = Vector2(PARTY_WIDTH, 0)
		_layout_party()
	_save_party_layout()

func _queue_party_layout() -> void:
	_layout_party.call_deferred()

func _toggle_party_collapsed() -> void:
	_party_collapsed = not _party_collapsed
	_layout_party()
	_save_party_layout()

func _save_party_layout() -> void:
	WindowPreferences.store_layout("party_hud", Rect2(party_panel.position, _party_expanded_size), _party_collapsed, preferences_path,
		{"numbers": _party_numbers, "custom_size": _party_custom_size})

## The catalogue, one category at a time, with a bar on every line.
##
## Everything drawn came off the wire, including which pages exist: a category
## the server's catalogue gains appears here without this file changing.
func _sync_achievements() -> void:
	var entries: Array = AppState.achievements_catalog.get("entries", []) as Array
	var done := 0
	var pages: Array[String] = []
	for raw: Variant in entries:
		var entry: Dictionary = raw as Dictionary
		if bool(entry.get("done", false)):
			done += 1
		var page: String = str(entry.get("category", ""))
		if not pages.has(page):
			pages.append(page)
	achievements_header.text = ("%d of %d earned" % [done, entries.size()]
		if not entries.is_empty() else "No achievements yet")
	if not pages.has(_achievements_page):
		_achievements_page = pages[0] if not pages.is_empty() else ""
	_sync_achievement_tabs(pages)
	_sync_achievement_titles(entries)
	for child: Node in achievements_rows.get_children():
		achievements_rows.remove_child(child)
		child.queue_free()
	for raw: Variant in entries:
		var entry: Dictionary = raw as Dictionary
		if str(entry.get("category", "")) == _achievements_page:
			achievements_rows.add_child(_achievement_row(entry))

func _sync_achievement_tabs(pages: Array[String]) -> void:
	for child: Node in achievements_tabs.get_children():
		achievements_tabs.remove_child(child)
		child.queue_free()
	for page: String in pages:
		var button := Button.new()
		button.name = "Page" + page
		button.text = page
		button.toggle_mode = true
		button.button_pressed = page == _achievements_page
		button.pressed.connect(_on_achievements_page_chosen.bind(page))
		achievements_tabs.add_child(button)

func _on_achievements_page_chosen(page: String) -> void:
	_achievements_page = page
	_sync_achievements()

## The picker offers exactly the titles this character has earned, because the
## server refuses any other and a menu of things it would refuse is worse than
## a short menu.
func _sync_achievement_titles(entries: Array) -> void:
	var worn: String = str(AppState.achievements_catalog.get("worn_title", ""))
	achievements_title_picker.clear()
	achievements_title_picker.add_item("(none)")
	achievements_title_picker.set_item_metadata(0, "none")
	var chosen := 0
	for raw: Variant in entries:
		var entry: Dictionary = raw as Dictionary
		var title: String = str(entry.get("title", ""))
		if title.is_empty() or not bool(entry.get("done", false)):
			continue
		achievements_title_picker.add_item(title)
		var index: int = achievements_title_picker.item_count - 1
		achievements_title_picker.set_item_metadata(index, title)
		if title == worn:
			chosen = index
	achievements_title_picker.select(chosen)
	achievements_title_picker.disabled = achievements_title_picker.item_count <= 1

func _on_achievement_title_chosen(index: int) -> void:
	var wanted: String = str(achievements_title_picker.get_item_metadata(index))
	var error: Error = Network.send_chat("#title " + wanted)
	achievements_status.text = ("Sent to the server; the window updates when it answers."
		if error == OK else "Title request failed: " + error_string(error))

func _achievement_row(entry: Dictionary) -> Control:
	var row := VBoxContainer.new()
	row.name = "Achievement" + str(entry.get("key", ""))
	var header := HBoxContainer.new()
	header.name = "Header"
	row.add_child(header)
	var name_label := Label.new()
	name_label.name = "Name"
	name_label.text = str(entry.get("name", ""))
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(name_label)
	var progress: int = int(entry.get("progress", 0))
	var target: int = maxi(1, int(entry.get("target", 1)))
	var count := Label.new()
	count.name = "Count"
	count.text = "%d / %d" % [progress, target]
	header.add_child(count)
	var tick := Label.new()
	tick.name = "Done"
	tick.custom_minimum_size = Vector2(24, 0)
	tick.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	tick.text = "*" if bool(entry.get("done", false)) else ""
	header.add_child(tick)
	var bar := _bar("Progress", Color(0.42, 0.62, 0.35))
	bar.custom_minimum_size = Vector2(0.0, 9.0)
	bar.max_value = float(target)
	bar.value = float(mini(progress, target))
	row.add_child(bar)
	var blurb := Label.new()
	blurb.name = "Description"
	blurb.text = str(entry.get("description", ""))
	blurb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	# An unearned row is the catalogue a player browses rather than a failure,
	# so it stays legible; the tick and the full bar mark the earned ones.
	blurb.modulate = Color(1.0, 1.0, 1.0, 0.7)
	row.add_child(blurb)
	var granted: String = str(entry.get("title", ""))
	if not granted.is_empty():
		var reward := Label.new()
		reward.name = "Grants"
		reward.text = "   grants the title \"%s\"" % granted
		reward.modulate = Color(0.85, 0.78, 0.45, 1.0)
		row.add_child(reward)
	return row

func _on_party_accept() -> void:
	_send_party_command("#party accept")

func _on_party_decline() -> void:
	_send_party_command("#party decline")

func _on_party_leave() -> void:
	_send_party_command("#party leave")

func _send_party_command(command: String) -> void:
	var error: Error = Network.send_chat(command)
	party_status.text = ("Sent to the server; the window updates when it answers."
		if error == OK else "Party request failed: " + error_string(error))
	_layout_party()

func toggle_party() -> void:
	if party_panel.visible:
		party_panel.hide()
		return
	_sync_party(true)
	# Nothing to show is worth saying, rather than a button that does nothing.
	if not party_panel.visible:
		party_status.text = ""
		party_header.text = "No party"
		for child: Node in party_rows.get_children():
			child.queue_free()
		party_panel.show()
		party_panel.move_to_front()

# --- construction ------------------------------------------------------------

## Worn goods look worn here too: a merchant's stock and the exchange both name
## what they are selling, so the name is enough to decide without the server
## restating it per row.
func _named_icon(image_id: int, name: String) -> Texture2D:
	if item_atlas == null:
		return null
	if AppState.is_degraded_item(name):
		var worn: Texture2D = item_atlas.worn_icon_for(image_id)
		if worn != null:
			return worn
	return item_atlas.icon_for(image_id)

func _selected_index(list: ItemList) -> int:
	var selected: PackedInt32Array = list.get_selected_items()
	return int(selected[0]) if not selected.is_empty() else 0

func _build() -> void:
	navigation_label = Label.new()
	navigation_label.name = "NavigationHud"
	navigation_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	navigation_label.set_anchors_preset(Control.PRESET_CENTER_TOP)
	navigation_label.position = Vector2(-180.0, 34.0)
	navigation_label.custom_minimum_size = Vector2(360.0, 24.0)
	navigation_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	navigation_label.hide()
	add_child(navigation_label)

	combat_panel = _panel("CombatHud",
		Vector2(-COMBAT_PANEL_SIZE.x * 0.5, 64.0), COMBAT_PANEL_SIZE,
		Control.PRESET_CENTER_TOP)
	combat_panel.gui_input.connect(_on_combat_gui_input)
	var combat_box := VBoxContainer.new()
	combat_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	combat_box.add_theme_constant_override("separation", 1)
	combat_panel.add_child(combat_box)
	combat_target = Label.new()
	combat_target.name = "CombatTarget"
	combat_target.mouse_filter = Control.MOUSE_FILTER_IGNORE
	combat_target.add_theme_font_size_override("font_size", COMBAT_FONT_SIZE)
	combat_target.add_theme_color_override("font_outline_color", Color.BLACK)
	combat_target.add_theme_constant_override("outline_size", 3)
	combat_target.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	combat_box.add_child(combat_target)
	combat_target_bar = _bar("CombatTargetBar", Color(0.82, 0.32, 0.28))
	combat_target_bar.custom_minimum_size = Vector2(0.0, 9.0)
	combat_target_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	combat_box.add_child(combat_target_bar)
	combat_player_bar = _bar("CombatPlayerBar", Color(0.36, 0.72, 0.42))
	combat_player_bar.custom_minimum_size = Vector2(0.0, 9.0)
	combat_player_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	combat_box.add_child(combat_player_bar)
	combat_event = Label.new()
	combat_event.name = "CombatEvent"
	combat_event.mouse_filter = Control.MOUSE_FILTER_IGNORE
	combat_event.add_theme_font_size_override("font_size", COMBAT_FONT_SIZE)
	combat_event.add_theme_color_override("font_outline_color", Color.BLACK)
	combat_event.add_theme_constant_override("outline_size", 3)
	combat_event.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	combat_box.add_child(combat_event)
	combat_menu = PopupMenu.new()
	combat_menu.name = "CombatHudMenu"
	combat_menu.add_check_item(tr("ELORIA_COMBAT_HUD_PIN"), 0)
	combat_menu.add_item(tr("ELORIA_COMBAT_HUD_HIDE"), 1)
	combat_menu.id_pressed.connect(_on_combat_menu_pressed)
	combat_panel.add_child(combat_menu)

	events_panel = _panel("SpecialEvents", Vector2(12.0, 120.0),
		Vector2(300.0, 120.0), Control.PRESET_TOP_LEFT)
	events_text = RichTextLabel.new()
	events_text.name = "SpecialEventsText"
	events_text.fit_content = true
	events_panel.add_child(events_text)

	quest_panel = _window("QuestJournal", "QUEST JOURNAL")
	quest_panel.custom_minimum_size = QUEST_JOURNAL_SIZE
	quest_panel.size = QUEST_JOURNAL_SIZE
	quest_panel.position = Vector2(24.0,
		(720.0 - QUEST_JOURNAL_SIZE.y) * 0.5)
	quest_panel.set_meta(&"visual_style", "eloria_field_journal")
	var quest_backdrop := ColorRect.new()
	quest_backdrop.name = "JournalBackdrop"
	quest_backdrop.color = Color(0.035, 0.03, 0.027, 0.985)
	quest_backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	quest_panel.add_child(quest_backdrop)
	quest_panel.move_child(quest_backdrop, 0)
	var quest_header := _window_body(quest_panel).get_node("Header") as HBoxContainer
	var quest_close := quest_header.get_node("Close") as Button
	quest_count = Label.new()
	quest_count.name = "QuestCount"
	quest_count.text = "0 ACTIVE"
	quest_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	quest_count.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	quest_header.add_child(quest_count)
	quest_header.move_child(quest_count, quest_close.get_index())
	var quest_views := HBoxContainer.new()
	quest_views.name = "QuestViews"
	quest_views.alignment = BoxContainer.ALIGNMENT_CENTER
	quest_views.add_theme_constant_override("separation", 8)
	_window_body(quest_panel).add_child(quest_views)
	quest_active_button = Button.new()
	quest_active_button.name = "QuestActive"
	quest_active_button.text = "Active"
	quest_active_button.toggle_mode = true
	quest_active_button.button_pressed = true
	quest_active_button.pressed.connect(_on_quest_view.bind(false))
	quest_views.add_child(quest_active_button)
	quest_done_button = Button.new()
	quest_done_button.name = "QuestDone"
	quest_done_button.text = "Completed (0)"
	quest_done_button.toggle_mode = true
	quest_done_button.pressed.connect(_on_quest_view.bind(true))
	quest_views.add_child(quest_done_button)
	var quest_columns := VBoxContainer.new()
	quest_columns.name = "QuestColumns"
	quest_columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quest_columns.add_theme_constant_override("separation", 10)
	_window_body(quest_panel).add_child(quest_columns)
	quest_list = ItemList.new()
	quest_list.name = "QuestList"
	quest_list.custom_minimum_size = Vector2(0.0, 170.0)
	quest_list.item_selected.connect(_on_quest_selected)
	quest_columns.add_child(quest_list)
	var quest_side := VBoxContainer.new()
	quest_side.name = "QuestDetailSide"
	quest_side.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quest_side.add_theme_constant_override("separation", 8)
	quest_columns.add_child(quest_side)
	var quest_record_heading := Label.new()
	quest_record_heading.name = "QuestRecordHeading"
	quest_record_heading.text = "ADVENTURER'S RECORD"
	quest_side.add_child(quest_record_heading)
	var quest_parchment := PanelContainer.new()
	quest_parchment.name = "QuestParchment"
	quest_parchment.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	quest_parchment.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quest_side.add_child(quest_parchment)
	var quest_parchment_surface := PanelContainer.new()
	quest_parchment_surface.name = "ParchmentTexture"
	quest_parchment_surface.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	quest_parchment_surface.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quest_parchment.add_child(quest_parchment_surface)
	quest_detail = RichTextLabel.new()
	quest_detail.name = "QuestDetail"
	quest_detail.bbcode_enabled = true
	quest_detail.scroll_active = true
	quest_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	quest_detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	quest_detail.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quest_parchment_surface.add_child(quest_detail)
	quest_track_button = Button.new()
	quest_track_button.name = "QuestTrack"
	quest_track_button.text = "Track"
	quest_track_button.pressed.connect(_on_quest_track_pressed)
	quest_side.add_child(quest_track_button)
	_style_quest_journal(quest_views, quest_parchment,
		quest_parchment_surface, quest_record_heading)

	# This is a pinned HUD note, not another modal window. It sits immediately
	# left of the fixed 96-pixel resource rail and leaves the centre view clear.
	tracked_quest = _panel("TrackedQuest",
		Vector2(-RESERVED_RIGHT_RAIL - QUEST_TRACKER_SIZE.x - 12.0, 18.0),
		QUEST_TRACKER_SIZE, Control.PRESET_TOP_RIGHT)
	tracked_quest.z_index = 20
	tracked_quest.clip_contents = true
	tracked_quest.set_meta(&"visual_style", "eloria_quest_tracker")
	var tracker_parchment := PanelContainer.new()
	tracker_parchment.name = "TrackerParchment"
	tracker_parchment.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tracker_parchment.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tracked_quest.add_child(tracker_parchment)
	var tracker_parchment_surface := PanelContainer.new()
	tracker_parchment_surface.name = "ParchmentTexture"
	tracker_parchment_surface.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tracker_parchment_surface.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tracker_parchment.add_child(tracker_parchment_surface)
	tracked_quest_text = RichTextLabel.new()
	tracked_quest_text.name = "TrackedQuestText"
	tracked_quest_text.bbcode_enabled = true
	tracked_quest_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tracked_quest_text.scroll_active = false
	tracked_quest_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tracked_quest_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tracker_parchment_surface.add_child(tracked_quest_text)
	_style_quest_tracker(tracker_parchment, tracker_parchment_surface)
	var tracker_actions := Control.new()
	tracker_actions.name = "TrackerActions"
	tracker_actions.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tracked_quest.add_child(tracker_actions)
	quest_untrack_button = Button.new()
	quest_untrack_button.name = "UntrackQuest"
	quest_untrack_button.text = "×"
	quest_untrack_button.tooltip_text = "Untrack quest. Choose Track in Quests to show it again."
	quest_untrack_button.flat = true
	quest_untrack_button.add_theme_color_override("font_color", QUEST_INK)
	quest_untrack_button.add_theme_font_size_override("font_size", 18)
	tracker_actions.add_child(quest_untrack_button)
	quest_untrack_button.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	quest_untrack_button.position = Vector2(-30, 4)
	quest_untrack_button.size = Vector2(26, 26)
	quest_untrack_button.pressed.connect(_on_quest_untrack_pressed)

	mail_panel = _window("MailWindow", "Mail")
	var mail_columns := HSplitContainer.new()
	mail_columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_window_body(mail_panel).add_child(mail_columns)
	mail_list = ItemList.new()
	mail_list.name = "MailList"
	mail_list.custom_minimum_size = Vector2(240.0, 0.0)
	mail_list.item_selected.connect(_on_mail_selected)
	mail_columns.add_child(mail_list)
	mail_body = RichTextLabel.new()
	mail_body.name = "MailBody"
	mail_body.bbcode_enabled = true
	mail_columns.add_child(mail_body)

	detail_panel = _window("ItemDetail", "Item")
	detail_text = RichTextLabel.new()
	detail_text.name = "ItemDetailText"
	detail_text.bbcode_enabled = true
	detail_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_window_body(detail_panel).add_child(detail_text)

	_build_merchant_window()

	_build_market_window()

	party_panel = _window("PartyWindow", "Party")
	party_panel.z_index = 20
	party_panel.add_theme_stylebox_override("panel", HUD_STYLE.box())
	# Leave the upper-left conversation feed clear on a fresh layout. Explicit
	# player positions still restore unchanged.
	var party_default := Vector2(maxf(12, get_viewport_rect().size.x - WindowDrag.RESERVED_RIGHT_RAIL - PARTY_WIDTH - 18), 56)
	var party_saved := WindowPreferences.stored_rect("party_hud", Rect2(party_default, Vector2(PARTY_WIDTH, 100)), preferences_path)
	party_panel.position = party_saved.position
	_party_collapsed = WindowPreferences.stored_collapsed("party_hud", false, preferences_path)
	var party_saved_options := WindowPreferences.stored_options("party_hud", {}, preferences_path)
	_party_numbers = bool(party_saved_options.get("numbers", false))
	_party_custom_size = bool(party_saved_options.get("custom_size", false))
	_party_expanded_size = party_saved.size if _party_custom_size else Vector2(PARTY_WIDTH, 0)
	var party_dragger := party_panel.get_node("WindowDrag") as WindowDrag
	party_dragger.bottom_hud = get_parent().get_node_or_null("Quickbar") as Control
	party_dragger.moved.connect(func(_to: Vector2) -> void: _save_party_layout())
	var party_body: VBoxContainer = _window_body(party_panel)
	party_body.add_theme_constant_override("separation", 5)
	party_header = party_panel.get_node("Body/Header/Title") as Label
	party_header.add_theme_font_size_override("font_size", 12)
	party_header.add_theme_color_override("font_color", HUD_STYLE.TEXT)
	party_header.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var party_close := party_panel.get_node("Body/Header/Close") as Button
	party_close.text = "×"
	HUD_STYLE.button(party_close)
	party_collapse = Button.new()
	party_collapse.name = "Collapse"
	HUD_STYLE.button(party_collapse)
	party_collapse.pressed.connect(_toggle_party_collapsed)
	var party_title_row := party_panel.get_node("Body/Header") as HBoxContainer
	party_options = MenuButton.new()
	party_options.name = "Options"
	party_options.text = "…"
	party_options.tooltip_text = "Party display options"
	HUD_STYLE.button(party_options)
	party_options.get_popup().add_check_item("Show health/ether numbers", 0)
	party_options.get_popup().set_item_checked(0, _party_numbers)
	party_options.get_popup().add_item("Reset window size", 1)
	party_options.get_popup().id_pressed.connect(_on_party_option)
	party_title_row.add_child(party_options)
	party_title_row.move_child(party_options, 1)
	party_title_row.add_child(party_collapse)
	party_title_row.move_child(party_collapse, 2)
	party_invite_row = HBoxContainer.new()
	party_invite_row.name = "PartyInvite"
	party_invite_row.hide()
	party_body.add_child(party_invite_row)
	party_invite_label = Label.new()
	party_invite_label.name = "PartyInviteLabel"
	party_invite_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	party_invite_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	party_invite_label.add_theme_font_size_override("font_size", 11)
	party_invite_row.add_child(party_invite_label)
	var accept := Button.new()
	accept.name = "PartyAccept"
	accept.text = "Accept"
	accept.pressed.connect(_on_party_accept)
	HUD_STYLE.button(accept)
	party_invite_row.add_child(accept)
	var decline := Button.new()
	decline.name = "PartyDecline"
	decline.text = "Decline"
	decline.pressed.connect(_on_party_decline)
	HUD_STYLE.button(decline)
	party_invite_row.add_child(decline)
	party_scroll = ScrollContainer.new()
	party_scroll.name = "PartyScroll"
	party_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	party_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	party_body.add_child(party_scroll)
	party_rows = VBoxContainer.new()
	party_rows.name = "PartyMembers"
	party_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	party_rows.add_theme_constant_override("separation", 4)
	party_scroll.add_child(party_rows)
	var party_actions := HBoxContainer.new()
	party_actions.name = "PartyActions"
	party_body.add_child(party_actions)
	party_leave_button = Button.new()
	party_leave_button.name = "PartyLeave"
	party_leave_button.text = "Leave party"
	HUD_STYLE.button(party_leave_button)
	party_leave_button.pressed.connect(_on_party_leave)
	party_actions.add_child(party_leave_button)
	party_add_bot = preload("res://src/ui/bot_class_picker.gd").new()
	party_add_bot.name = "AddBot"
	HUD_STYLE.button(party_add_bot)
	party_add_bot.class_chosen.connect(func(class_id: int) -> void: _send_party_command("#party bot add %d" % class_id))
	party_actions.add_child(party_add_bot)
	# Inviting needs a name, and a name needs typing; the chat command already
	# reads well, so the window points at it rather than growing a text field
	# that would duplicate it.
	var party_hint := Label.new()
	party_hint.name = "PartyHint"
	party_hint.text = "?"
	party_hint.add_theme_font_size_override("font_size", 10)
	party_hint.tooltip_text = "#party invite <name> invites a teammate. #p <message> speaks to the party."
	party_actions.add_child(party_hint)
	var party_spacer := Control.new()
	party_spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	party_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	party_actions.add_child(party_spacer)
	party_resize_grip = Label.new()
	party_resize_grip.name = "ResizeGrip"
	party_resize_grip.text = "◢"
	party_resize_grip.custom_minimum_size = Vector2(18, 18)
	party_resize_grip.mouse_filter = Control.MOUSE_FILTER_STOP
	party_resize_grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	party_resize_grip.tooltip_text = "Drag to resize party"
	party_resize_grip.gui_input.connect(_on_party_resize_input)
	party_actions.add_child(party_resize_grip)
	party_status = Label.new()
	party_status.name = "PartyStatus"
	party_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	party_status.add_theme_font_size_override("font_size", 11)
	party_body.add_child(party_status)
	party_body.move_child(party_actions, party_body.get_child_count() - 1)
	get_viewport().size_changed.connect(_queue_party_layout)
	if is_instance_valid(party_dragger.bottom_hud):
		party_dragger.bottom_hud.resized.connect(_queue_party_layout)
	_layout_party()
	party_panel.hide()

	# The achievement catalogue. Server-stated end to end: the pages are
	# whatever categories the catalogue file has in it, and so are the names,
	# the descriptions, the thresholds and the titles. Nothing here is a table
	# of this client's own, so nothing here can go stale when one moves.
	achievements_panel = _window("Achievements", "Achievements")
	var achievements_body: VBoxContainer = _window_body(achievements_panel)
	achievements_header = Label.new()
	achievements_header.name = "AchievementsHeader"
	achievements_body.add_child(achievements_header)
	var achievements_title_row := HBoxContainer.new()
	achievements_title_row.name = "TitleRow"
	achievements_body.add_child(achievements_title_row)
	var achievements_title_label := Label.new()
	achievements_title_label.name = "TitleLabel"
	achievements_title_label.text = "Title:"
	achievements_title_row.add_child(achievements_title_label)
	achievements_title_picker = OptionButton.new()
	achievements_title_picker.name = "TitlePicker"
	achievements_title_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	achievements_title_picker.item_selected.connect(_on_achievement_title_chosen)
	achievements_title_row.add_child(achievements_title_picker)
	achievements_tabs = HBoxContainer.new()
	achievements_tabs.name = "AchievementsTabs"
	achievements_tabs.alignment = BoxContainer.ALIGNMENT_CENTER
	achievements_body.add_child(achievements_tabs)
	var achievements_scroll := ScrollContainer.new()
	achievements_scroll.name = "AchievementsScroll"
	achievements_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	achievements_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	achievements_body.add_child(achievements_scroll)
	achievements_rows = VBoxContainer.new()
	achievements_rows.name = "AchievementsBody"
	achievements_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	achievements_scroll.add_child(achievements_rows)
	achievements_status = Label.new()
	achievements_status.name = "AchievementsStatus"
	achievements_body.add_child(achievements_status)
	achievements_panel.hide()

## Low-cost, retained quest chrome. The two source textures are preloaded once,
## and these StyleBoxes are built once with the windows; tracking a quest only
## changes label text and visibility, so a busy scene pays no repeating
## decoration cost.
func _quest_box(background: Color, border: Color, width: int,
		corner: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = background
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(corner)
	box.set_content_margin_all(margin)
	return box

func _quest_texture_box(texture: Texture2D, margin: float,
		modulation := Color.WHITE) -> StyleBoxTexture:
	var box := StyleBoxTexture.new()
	box.texture = texture
	box.modulate_color = modulation
	box.set_content_margin_all(margin)
	return box

func _style_quest_button(button: Button, primary: bool) -> void:
	var normal_background := QUEST_BURGUNDY if primary else QUEST_STONE
	var hover_background := QUEST_BURGUNDY_HOVER if primary else QUEST_STONE_RAISED
	var normal := _quest_box(normal_background, QUEST_BRASS, 2, 9, 7.0)
	var hover := _quest_box(hover_background, QUEST_BRASS_BRIGHT, 3, 10, 7.0)
	var pressed := _quest_box(QUEST_BURGUNDY, QUEST_BRASS_BRIGHT, 3, 8, 7.0)
	var disabled := _quest_box(Color(0.09, 0.08, 0.07, 0.92),
		Color(0.3, 0.27, 0.22, 0.9), 1, 9, 7.0)
	for raised: StyleBoxFlat in [normal, hover, disabled]:
		raised.border_blend = true
		raised.shadow_color = Color(0.015, 0.01, 0.008, 0.88)
		raised.shadow_size = 3
		raised.shadow_offset = Vector2(0.0, 2.0)
	pressed.border_blend = true
	pressed.shadow_color = Color(0.015, 0.01, 0.008, 0.82)
	pressed.shadow_size = 1
	pressed.shadow_offset = Vector2(0.0, 1.0)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("hover_pressed", pressed)
	button.add_theme_stylebox_override("focus", hover)
	button.add_theme_stylebox_override("disabled", disabled)
	button.add_theme_color_override("font_color", QUEST_WARM_TEXT)
	button.add_theme_color_override("font_hover_color", QUEST_BRASS_BRIGHT)
	button.add_theme_color_override("font_pressed_color", QUEST_BRASS_BRIGHT)
	button.add_theme_color_override("font_disabled_color", QUEST_MUTED_TEXT)
	button.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
	button.add_theme_constant_override("outline_size", 2)
	button.custom_minimum_size.y = maxf(button.custom_minimum_size.y, 38.0)

func _style_quest_journal(quest_views: HBoxContainer,
		parchment: PanelContainer, parchment_surface: PanelContainer,
		record_heading: Label) -> void:
	# The transparent centre of the carved frame reveals JournalBackdrop while
	# its opaque perimeter supplies all of the tactile stone and aged brass.
	var frame := _quest_texture_box(QUEST_CARVED_FRAME_TEXTURE, 56.0)
	quest_panel.add_theme_stylebox_override("panel", frame)
	var body := _window_body(quest_panel)
	body.add_theme_constant_override("separation", 10)
	var header := body.get_node("Header") as HBoxContainer
	header.add_theme_constant_override("separation", 10)
	var title := header.get_node("Title") as Label
	title.add_theme_color_override("font_color", QUEST_BRASS_BRIGHT)
	title.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.95))
	title.add_theme_constant_override("outline_size", 3)
	title.add_theme_font_size_override("font_size", 22)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	quest_count.add_theme_color_override("font_color", QUEST_BRASS_BRIGHT)
	quest_count.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.95))
	quest_count.add_theme_constant_override("outline_size", 2)
	quest_count.add_theme_font_size_override("font_size", 12)
	quest_count.custom_minimum_size.x = 92.0
	_style_quest_button(header.get_node("Close") as Button, true)
	for child: Node in quest_views.get_children():
		if child is Button:
			var tab := child as Button
			tab.custom_minimum_size.x = 142.0
			tab.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			_style_quest_button(tab, false)
	var list_panel := _quest_box(Color(0.055, 0.05, 0.048, 0.98),
		QUEST_BRASS, 2, 3, 8.0)
	quest_list.add_theme_stylebox_override("panel", list_panel)
	var selected := _quest_box(QUEST_BURGUNDY, QUEST_BRASS_BRIGHT, 2, 2, 4.0)
	for state: String in ["cursor", "cursor_unfocused", "selected",
			"selected_focus", "hovered_selected"]:
		quest_list.add_theme_stylebox_override(state, selected)
	quest_list.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	quest_list.add_theme_color_override("font_color", QUEST_WARM_TEXT)
	quest_list.add_theme_color_override("font_selected_color", QUEST_BRASS_BRIGHT)
	quest_list.add_theme_color_override("font_hovered_selected_color",
		QUEST_BRASS_BRIGHT)
	quest_list.add_theme_color_override("guide_color", Color(QUEST_BRASS, 0.22))
	quest_list.add_theme_font_size_override("font_size", 14)
	quest_list.add_theme_constant_override("line_separation", 8)
	record_heading.add_theme_color_override("font_color", QUEST_BRASS_BRIGHT)
	record_heading.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.9))
	record_heading.add_theme_constant_override("outline_size", 2)
	record_heading.add_theme_font_size_override("font_size", 12)
	var page := _quest_box(Color(0.14, 0.075, 0.025, 1.0),
		QUEST_PARCHMENT_DARK, 2, 5, 4.0)
	page.shadow_color = Color(0.0, 0.0, 0.0, 0.38)
	page.shadow_size = 5
	page.shadow_offset = Vector2(0.0, 3.0)
	parchment.add_theme_stylebox_override("panel", page)
	parchment_surface.add_theme_stylebox_override("panel",
		_quest_texture_box(QUEST_PARCHMENT_TEXTURE, 14.0,
			Color(0.94, 0.88, 0.76, 1.0)))
	quest_detail.add_theme_color_override("default_color", QUEST_INK)
	quest_detail.add_theme_color_override("font_selected_color", QUEST_INK)
	quest_detail.add_theme_color_override("selection_color", Color(0.55, 0.35, 0.12, 0.28))
	quest_detail.add_theme_font_size_override("normal_font_size", 15)
	_style_quest_button(quest_track_button, true)
	quest_track_button.custom_minimum_size.x = 154.0
	quest_track_button.size_flags_horizontal = Control.SIZE_SHRINK_END

func _style_quest_tracker(parchment: PanelContainer,
		parchment_surface: PanelContainer) -> void:
	# The pinned tracker is the torn page from the larger journal, not another
	# heavy window. The parchment itself supplies the edge and small shadow.
	tracked_quest.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	var page := _quest_box(Color(0.14, 0.075, 0.025, 0.98),
		QUEST_PARCHMENT_DARK, 2, 5, 3.0)
	page.shadow_color = Color(0.0, 0.0, 0.0, 0.62)
	page.shadow_size = 6
	page.shadow_offset = Vector2(0.0, 3.0)
	parchment.add_theme_stylebox_override("panel", page)
	parchment_surface.add_theme_stylebox_override("panel",
		_quest_texture_box(QUEST_PARCHMENT_TEXTURE, 9.0,
			Color(0.96, 0.90, 0.78, 0.985)))
	tracked_quest_text.add_theme_color_override("default_color", QUEST_INK)
	tracked_quest_text.add_theme_font_size_override("normal_font_size", 13)

## Two inventories share one explicit transaction, matching the selected concept.
func _build_merchant_window() -> void:
	merchant_panel = _window("MerchantWindow", "Merchant")
	merchant_panel.custom_minimum_size = Vector2(1040.0, 550.0)
	merchant_panel.size = merchant_panel.custom_minimum_size
	merchant_panel.position = Vector2(72.0, 65.0)
	merchant_panel.add_theme_stylebox_override("panel", _quest_box(Color("15120f"), Color("9a7843"), 1, 3, 12.0))
	var body := _window_body(merchant_panel)
	body.add_theme_constant_override("separation", 10)
	var header := body.get_node("Header") as HBoxContainer
	(header.get_node("Title") as Label).hide()
	merchant_header = Label.new()
	merchant_header.name = "MerchantHeader"
	merchant_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	merchant_header.add_theme_font_size_override("font_size", 18)
	header.add_child(merchant_header)
	header.move_child(merchant_header, 0)
	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 12)
	body.add_child(columns)
	for selling: bool in [false, true]:
		var panel := PanelContainer.new()
		panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		panel.size_flags_stretch_ratio = 1.0
		panel.add_theme_stylebox_override("panel", _quest_box(Color("1c1813"), Color("76603b"), 1, 2, 10.0))
		columns.add_child(panel)
		var column := VBoxContainer.new()
		panel.add_child(column)
		var mode := Button.new()
		mode.name = "MerchantSellMode" if selling else "MerchantBuyMode"
		mode.text = "Your backpack" if selling else "Shop goods"
		mode.toggle_mode = true
		mode.alignment = HORIZONTAL_ALIGNMENT_LEFT
		mode.add_theme_font_size_override("font_size", 19)
		mode.pressed.connect(_on_merchant_mode.bind("sell" if selling else "buy"))
		column.add_child(mode)
		var hint := Label.new()
		hint.text = "Select an item to sell · sell price" if selling else "Select an item to buy · buy price"
		hint.add_theme_font_size_override("font_size", 13)
		column.add_child(hint)
		var list := ItemList.new()
		list.name = "MerchantBackpack" if selling else "MerchantList"
		list.size_flags_vertical = Control.SIZE_EXPAND_FILL
		list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		list.fixed_icon_size = Vector2i(40, 40)
		list.icon_scale = 1.0
		list.add_theme_constant_override("icon_margin", 12)
		list.add_theme_font_size_override("font_size", 15)
		list.add_theme_color_override("font_color", QUEST_WARM_TEXT)
		list.add_theme_color_override("font_selected_color", QUEST_WARM_TEXT)
		list.add_theme_constant_override("v_separation", 7)
		list.add_theme_stylebox_override("panel", _quest_box(Color("151310"), Color("76603b"), 0, 0, 4.0))
		list.add_theme_stylebox_override("selected", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
		list.add_theme_stylebox_override("selected_focus", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
		list.item_selected.connect(_on_merchant_selected.bind("sell" if selling else "buy"))
		column.add_child(list)
		if selling:
			merchant_sell_mode = mode
			merchant_sell_list = list
			merchant_empty_pack = Label.new()
			merchant_empty_pack.text = "No items this merchant buys in your backpack."
			merchant_empty_pack.add_theme_font_size_override("font_size", 13)
			column.add_child(merchant_empty_pack)
		else:
			merchant_buy_mode = mode
			merchant_buy_list = list
	merchant_list = merchant_buy_list
	var description_panel := PanelContainer.new()
	description_panel.name = "MerchantDescriptionPanel"
	description_panel.add_theme_stylebox_override("panel", _quest_box(Color("1c1813"), Color("76603b"), 1, 2, 10.0))
	body.add_child(description_panel)
	merchant_description = RichTextLabel.new()
	merchant_description.name = "MerchantDescription"
	merchant_description.custom_minimum_size.y = 76
	merchant_description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	merchant_description.bbcode_enabled = false
	merchant_description.add_theme_font_size_override("normal_font_size", 14)
	merchant_description.add_theme_color_override("default_color", QUEST_WARM_TEXT)
	description_panel.add_child(merchant_description)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 14)
	body.add_child(footer)
	merchant_selected_icon = TextureRect.new()
	merchant_selected_icon.custom_minimum_size = Vector2(48, 48)
	merchant_selected_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	merchant_selected_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	footer.add_child(merchant_selected_icon)
	merchant_selection = Label.new()
	merchant_selection.name = "MerchantSelection"
	merchant_selection.custom_minimum_size.x = 250
	merchant_selection.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	merchant_selection.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	footer.add_child(merchant_selection)
	var quantities := VBoxContainer.new()
	footer.add_child(quantities)
	var quantity_label := Label.new()
	quantity_label.text = "Quantity"
	quantities.add_child(quantity_label)
	var stepper := HBoxContainer.new()
	quantities.add_child(stepper)
	var minus := Button.new()
	minus.text = "−"
	minus.pressed.connect(_merchant_change_quantity.bind(-1))
	stepper.add_child(minus)
	merchant_quantity = LineEdit.new()
	merchant_quantity.name = "MerchantQuantity"
	merchant_quantity.text = "1"
	merchant_quantity.custom_minimum_size.x = 80
	merchant_quantity.alignment = HORIZONTAL_ALIGNMENT_CENTER
	merchant_quantity.text_changed.connect(_sync_merchant_summary)
	stepper.add_child(merchant_quantity)
	var plus := Button.new()
	plus.text = "+"
	plus.pressed.connect(_merchant_change_quantity.bind(1))
	stepper.add_child(plus)
	var maximum := Button.new()
	maximum.name = "MerchantMaximum"
	maximum.text = "Max"
	maximum.pressed.connect(_merchant_set_maximum)
	stepper.add_child(maximum)
	merchant_totals = Label.new()
	merchant_totals.name = "MerchantTotals"
	merchant_totals.custom_minimum_size.x = 170
	footer.add_child(merchant_totals)
	merchant_trade = Button.new()
	merchant_trade.name = "MerchantTrade"
	merchant_trade.text = "Buy"
	merchant_trade.custom_minimum_size = Vector2(112, 44)
	merchant_trade.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	merchant_trade.add_theme_stylebox_override("normal", _quest_box(Color("5d4320"), Color("d5aa60"), 1, 3, 9.0))
	merchant_trade.add_theme_stylebox_override("hover", _quest_box(Color("77552a"), Color("ebc982"), 1, 3, 9.0))
	merchant_trade.pressed.connect(_on_merchant_trade)
	footer.add_child(merchant_trade)
	merchant_status = Label.new()
	merchant_status.name = "MerchantStatus"
	merchant_status.add_theme_font_size_override("font_size", 13)
	body.add_child(merchant_status)

func _build_market_window() -> void:
	market_panel = _window("MarketplaceWindow", "Nymara Exchange")
	market_panel.custom_minimum_size = MARKET_SIZE
	market_panel.size = MARKET_SIZE
	# Left of centre, so the tutorial guide's card still has room beside it.
	market_panel.position = Vector2(72.0, 52.0)
	market_panel.add_theme_stylebox_override("panel", _quest_box(Color("15120f"), Color("9a7843"), 1, 3, 12.0))
	var body := _window_body(market_panel)
	body.add_theme_constant_override("separation", 8)
	(body.get_node("Header/Title") as Label).add_theme_font_size_override("font_size", 18)
	var bar := HBoxContainer.new()
	bar.name = "MarketplaceBar"
	bar.add_theme_constant_override("separation", 6)
	body.add_child(bar)
	for tab: Array in [["browse", "Browse"], ["mine", "My listings"], ["history", "Sales history"], ["sell", "Sell"]]:
		var button := Button.new()
		button.name = "Marketplace" + str(tab[0]).capitalize()
		button.text = str(tab[1])
		button.toggle_mode = true
		button.custom_minimum_size.x = 96
		button.pressed.connect(_on_market_tab.bind(str(tab[0])))
		bar.add_child(button)
		market_tabs[str(tab[0])] = button
	market_header = Label.new()
	market_header.name = "MarketplaceHeader"
	market_header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	market_header.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	body.add_child(market_header)
	var bar_spacer := Control.new()
	bar_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(bar_spacer)
	market_collect = Button.new()
	market_collect.name = "MarketplaceCollect"
	market_collect.text = "Collect"
	market_collect.pressed.connect(_on_market_collect)
	bar.add_child(market_collect)
	market_search_row = HBoxContainer.new()
	market_search_row.name = "MarketplaceSearchRow"
	body.add_child(market_search_row)
	market_search = LineEdit.new()
	market_search.name = "MarketplaceSearch"
	market_search.placeholder_text = "Search item names"
	market_search.max_length = 40
	market_search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	market_search.text_submitted.connect(_on_market_search)
	market_search_row.add_child(market_search)
	var search := Button.new()
	search.name = "MarketplaceSearchButton"
	search.text = "Search / Apply"
	search.pressed.connect(_on_market_search)
	market_search_row.add_child(search)
	var clear := Button.new()
	clear.name = "MarketplaceClearSearch"
	clear.text = "Clear filters"
	clear.pressed.connect(_on_market_clear_search)
	market_search_row.add_child(clear)
	var refresh := Button.new()
	refresh.text = "Refresh"
	refresh.tooltip_text = "Reload listings or sales with the current filters."
	refresh.pressed.connect(_on_market_search)
	market_search_row.add_child(refresh)
	market_filters_box = VBoxContainer.new()
	market_filters_box.name = "MarketplaceFilters"
	body.add_child(market_filters_box)
	var choices_row := HBoxContainer.new()
	market_filters_box.add_child(choices_row)
	market_category = OptionButton.new()
	market_category.name = "MarketplaceCategory"
	market_category.tooltip_text = "Filter by item category, such as weapons, armor, or resources."
	market_type = OptionButton.new()
	market_type.name = "MarketplaceType"
	market_type.tooltip_text = "Filter by item class or equipment type, such as torso, shield, ranged, or reagent."
	market_sort = OptionButton.new()
	market_sort.name = "MarketplaceSort"
	market_sort.tooltip_text = "Sort all matching results, across every page. Prices are in gold coins."
	for picker: OptionButton in [market_category, market_type, market_sort]:
		picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		picker.fit_to_longest_item = false
		picker.item_selected.connect(_on_market_filter_changed)
		choices_row.add_child(picker)
	market_category.add_item("All categories")
	market_category.set_item_metadata(0, "")
	market_type.add_item("All item types")
	market_type.set_item_metadata(0, "")
	for label: String in MARKET_SORT_LABELS:
		market_sort.add_item(label)
	var price_row := HBoxContainer.new()
	market_filters_box.add_child(price_row)
	market_seller = LineEdit.new()
	market_seller.name = "MarketplaceSeller"
	market_seller.placeholder_text = "Seller name"
	market_seller.max_length = 40
	market_seller.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	market_seller.text_submitted.connect(_on_market_search)
	price_row.add_child(market_seller)
	var price_filter_label := Label.new()
	price_filter_label.text = "Unit price (gc)"
	price_row.add_child(price_filter_label)
	market_min_price = LineEdit.new()
	market_min_price.name = "MarketplaceMinPrice"
	market_min_price.placeholder_text = "Min"
	market_max_price = LineEdit.new()
	market_max_price.name = "MarketplaceMaxPrice"
	market_max_price.placeholder_text = "Max"
	for field: LineEdit in [market_min_price, market_max_price]:
		field.custom_minimum_size.x = 116
		field.max_length = 13
		field.tooltip_text = "Optional price per item, in gold coins. Leave blank for no limit."
		field.text_submitted.connect(_on_market_search)
		price_row.add_child(field)
	market_list = ItemList.new()
	market_list.name = "MarketplaceList"
	market_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	market_list.fixed_icon_size = Vector2i(32, 32)
	market_list.add_theme_constant_override("icon_margin", 10)
	market_list.add_theme_font_size_override("font_size", 15)
	market_list.add_theme_color_override("font_color", QUEST_WARM_TEXT)
	market_list.add_theme_color_override("font_selected_color", QUEST_WARM_TEXT)
	market_list.add_theme_constant_override("v_separation", 5)
	market_list.add_theme_stylebox_override("panel", _quest_box(Color("151310"), Color("76603b"), 1, 2, 4.0))
	market_list.add_theme_stylebox_override("selected", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
	market_list.add_theme_stylebox_override("selected_focus", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
	market_list.item_selected.connect(_on_market_selected)
	body.add_child(market_list)
	market_history = Tree.new()
	market_history.name = "MarketplaceHistory"
	market_history.columns = 5
	market_history.hide_root = true
	market_history.column_titles_visible = true
	market_history.select_mode = Tree.SELECT_ROW
	market_history.size_flags_vertical = Control.SIZE_EXPAND_FILL
	market_history.add_theme_font_size_override("font_size", 14)
	market_history.add_theme_constant_override("v_separation", 8)
	market_history.add_theme_color_override("font_color", QUEST_WARM_TEXT)
	market_history.add_theme_stylebox_override("panel", _quest_box(Color("151310"), Color("76603b"), 1, 2, 4.0))
	market_history.add_theme_stylebox_override("selected", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
	market_history.add_theme_stylebox_override("selected_focus", _quest_box(Color("40331e"), Color("c59a53"), 1, 2, 3.0))
	for column: int in range(5):
		market_history.set_column_title(column, ["Item", "Qty", "Buyer", "Received (gc)", "Sold at (UTC)"][column])
		market_history.set_column_custom_minimum_width(column, [220, 50, 110, 120, 164][column])
		market_history.set_column_expand(column, column == 0 or column == 2)
	market_history.item_selected.connect(_sync_market_footer)
	body.add_child(market_history)
	market_empty = Label.new()
	market_empty.name = "MarketplaceEmpty"
	market_empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	market_empty.add_theme_color_override("font_color", QUEST_MUTED_TEXT)
	body.add_child(market_empty)
	market_page_row = HBoxContainer.new()
	market_page_row.name = "MarketplacePages"
	body.add_child(market_page_row)
	market_previous = Button.new()
	market_previous.name = "MarketplacePrevious"
	market_previous.text = "◀ Previous"
	market_previous.pressed.connect(_on_market_page.bind(-1))
	market_page_row.add_child(market_previous)
	market_page_label = Label.new()
	market_page_label.name = "MarketplacePage"
	market_page_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	market_page_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	market_page_row.add_child(market_page_label)
	market_next = Button.new()
	market_next.name = "MarketplaceNext"
	market_next.text = "Next ▶"
	market_next.pressed.connect(_on_market_page.bind(1))
	market_page_row.add_child(market_next)
	market_returns_box = VBoxContainer.new()
	market_returns_box.name = "MarketplaceReturnsBox"
	body.add_child(market_returns_box)
	var returns_heading := Label.new()
	returns_heading.text = "Waiting in return escrow - Collect puts these back in your pack"
	returns_heading.add_theme_font_size_override("font_size", 13)
	returns_heading.add_theme_color_override("font_color", QUEST_BRASS_BRIGHT)
	market_returns_box.add_child(returns_heading)
	market_returns = ItemList.new()
	market_returns.name = "MarketplaceReturns"
	market_returns.custom_minimum_size = Vector2(0.0, 64.0)
	market_returns.fixed_icon_size = Vector2i(24, 24)
	market_returns.add_theme_font_size_override("font_size", 13)
	market_returns.add_theme_color_override("font_color", QUEST_WARM_TEXT)
	market_returns.add_theme_stylebox_override("panel", _quest_box(Color("151310"), Color("76603b"), 1, 2, 4.0))
	market_returns_box.add_child(market_returns)
	var footer := HBoxContainer.new()
	footer.name = "MarketplaceFooter"
	footer.add_theme_constant_override("separation", 12)
	body.add_child(footer)
	market_selected_icon = TextureRect.new()
	market_selected_icon.custom_minimum_size = Vector2(44, 44)
	market_selected_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	market_selected_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	footer.add_child(market_selected_icon)
	market_selection = Label.new()
	market_selection.name = "MarketplaceSelection"
	market_selection.custom_minimum_size.x = 170
	market_selection.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	market_selection.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	footer.add_child(market_selection)
	market_quantity_box = VBoxContainer.new()
	market_quantity_box.name = "MarketplaceQuantityBox"
	footer.add_child(market_quantity_box)
	var quantity_label := Label.new()
	quantity_label.text = "Quantity"
	market_quantity_box.add_child(quantity_label)
	var stepper := HBoxContainer.new()
	market_quantity_box.add_child(stepper)
	var minus := Button.new()
	minus.text = "−"
	minus.pressed.connect(_market_change_quantity.bind(-1))
	stepper.add_child(minus)
	market_quantity = LineEdit.new()
	market_quantity.name = "MarketplaceQuantity"
	market_quantity.text = "1"
	market_quantity.custom_minimum_size.x = 64
	market_quantity.alignment = HORIZONTAL_ALIGNMENT_CENTER
	market_quantity.text_changed.connect(_sync_market_footer)
	stepper.add_child(market_quantity)
	var plus := Button.new()
	plus.text = "+"
	plus.pressed.connect(_market_change_quantity.bind(1))
	stepper.add_child(plus)
	var all := Button.new()
	all.name = "MarketplaceAll"
	all.text = "All"
	all.pressed.connect(_market_set_all)
	stepper.add_child(all)
	market_price_box = VBoxContainer.new()
	market_price_box.name = "MarketplacePriceBox"
	footer.add_child(market_price_box)
	var price_label := Label.new()
	price_label.text = "Price each (gc)"
	market_price_box.add_child(price_label)
	market_price = LineEdit.new()
	market_price.name = "MarketplacePrice"
	market_price.placeholder_text = "gold coins"
	market_price.custom_minimum_size.x = 104
	market_price.alignment = HORIZONTAL_ALIGNMENT_CENTER
	market_price.text_changed.connect(_sync_market_footer)
	market_price.text_submitted.connect(func(_text: String) -> void: _on_market_sell())
	market_price_box.add_child(market_price)
	market_totals = Label.new()
	market_totals.name = "MarketplaceTotals"
	market_totals.custom_minimum_size.x = 140
	market_totals.add_theme_font_size_override("font_size", 13)
	footer.add_child(market_totals)
	market_buy = _market_action_button("MarketplaceBuy", "Buy", _on_market_buy)
	footer.add_child(market_buy)
	market_renew = _market_action_button("MarketplaceRenew", "Renew", _on_market_renew)
	footer.add_child(market_renew)
	market_cancel = _market_action_button("MarketplaceCancel", "Cancel listing", _on_market_cancel)
	footer.add_child(market_cancel)
	market_sell = _market_action_button("MarketplaceSell", "List for sale", _on_market_sell)
	footer.add_child(market_sell)
	market_status = Label.new()
	market_status.name = "MarketplaceStatus"
	# One line, trimmed: a wrapping label measured before its first layout
	# asks for a column of single words and stretches the window off screen.
	market_status.clip_text = true
	market_status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	market_status.add_theme_font_size_override("font_size", 13)
	body.add_child(market_status)

func _market_action_button(button_name: String, text: String, action: Callable) -> Button:
	var button := Button.new()
	button.name = button_name
	button.text = text
	button.custom_minimum_size = Vector2(108, 40)
	button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	button.add_theme_stylebox_override("normal", _quest_box(Color("5d4320"), Color("d5aa60"), 1, 3, 8.0))
	button.add_theme_stylebox_override("hover", _quest_box(Color("77552a"), Color("ebc982"), 1, 3, 8.0))
	button.pressed.connect(action)
	return button

func _bar(bar_name: String, colour: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.name = bar_name
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0.0, 14.0)
	var fill := StyleBoxFlat.new()
	fill.bg_color = colour
	bar.add_theme_stylebox_override("fill", fill)
	return bar

func _panel(panel_name: String, offset: Vector2, size: Vector2,
		preset: int) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.name = panel_name
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.set_anchors_preset(preset)
	panel.position = offset
	panel.custom_minimum_size = size
	panel.size = size
	panel.hide()
	add_child(panel)
	return panel

## A centred window with a title row and a close button. Kept clear of the
## fixed right-hand resource rail, which nothing may cover.
func _window(window_name: String, title: String) -> PanelContainer:
	var available: float = 1280.0 - RESERVED_RIGHT_RAIL
	var panel := _panel(window_name,
		Vector2((available - PANEL_SIZE.x) * 0.5, (720.0 - PANEL_SIZE.y) * 0.5),
		PANEL_SIZE, Control.PRESET_TOP_LEFT)
	panel.z_index = 26
	var body := VBoxContainer.new()
	body.name = "Body"
	panel.add_child(body)
	var header := HBoxContainer.new()
	header.name = "Header"
	body.add_child(header)
	WindowDrag.attach(panel, header)
	var title_label := Label.new()
	title_label.name = "Title"
	title_label.text = title
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title_label)
	var close := Button.new()
	close.name = "Close"
	close.text = "Close"
	close.pressed.connect(func() -> void:
		if panel == merchant_panel:
			AppState.close_merchant()
		elif panel == market_panel:
			AppState.close_marketplace()
		elif panel == detail_panel:
			AppState.close_item_detail()
		else:
			panel.hide())
	header.add_child(close)
	return panel

func _window_body(panel: PanelContainer) -> VBoxContainer:
	return panel.get_node("Body") as VBoxContainer
