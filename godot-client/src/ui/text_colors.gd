extends RefCounted
## Shared interface and world text colors. Defaults use the EL client values
## wherever an equivalent exists; Rabbit Lands-only roles retain their palette.
## Store only explicit choices, so a future default never replaces a player's
## chosen color. Chat messages and the local banner keep their own preferences.

const SECTION := "text_colors"
const SETTINGS_PATH := "user://eloria_hud.cfg"
const DEFAULTS := {
	"ui_label": Color(0.77, 0.57, 0.39), "ui_button": Color(0.77, 0.57, 0.39),
	"ui_bright": Color(0.95, 0.76, 0.52), "ui_heading": Color(0.77, 0.57, 0.39),
	"ui_hover": Color(0.95, 0.76, 0.52), "ui_pressed": Color(0.77, 0.57, 0.39),
	"ui_disabled": Color(0.5, 0.5, 0.5), "ui_input": Color.WHITE,
	"ui_placeholder": Color(0.5, 0.5, 0.5), "ui_selected": Color.WHITE,
	"ui_tooltip": Color.WHITE,
	"login_label": Color.WHITE, "login_input": Color(0.0, 0.9, 1.0),
	"login_placeholder": Color(0.0, 0.9, 1.0, 0.55),
	"login_error": Color.RED, "login_status": Color.WHITE,
	"npc_text": Color.WHITE, "npc_reply": Color.YELLOW,
	"npc_reply_hover": Color(1.0, 0.5, 0.0), "npc_unavailable": Color("999999"),
	"npc_footer": Color.WHITE,
	"inventory_text": Color(0.77, 0.57, 0.39),
	"inventory_selected": Color(0.95, 0.76, 0.52),
	"inventory_count": Color.WHITE,
	"inventory_equipped": Color("8fdc8f"),
	"quantity": Color(0.3, 0.5, 1.0), "quantity_selected": Color(0.0, 1.0, 0.3),
	"quantity_editing": Color(1.0, 0.0, 0.3), "equipment_heading": Color(0.57, 0.67, 0.49),
	"manufacture_normal": Color(0.77, 0.57, 0.39), "manufacture_error": Color.RED,
	"stats_heading": Color(0.95, 0.76, 0.52), "stats_attribute": Color.YELLOW,
	"stats_nexus": Color.WHITE, "stats_skill": Color(1.0, 0.5, 0.2),
	"stats_watched": Color(1.0, 0.5, 0.5), "stats_resource": Color(0.5, 0.5, 1.0),
	"stats_spend": Color(0.45, 0.85, 0.45), "stats_pending": Color(0.63, 0.91, 0.6),
	"knowledge_read": Color.WHITE, "knowledge_unread": Color("999999"),
	"knowledge_selected": Color(0.4, 0.8, 1.0), "knowledge_hover": Color(0.5, 0.5, 1.0),
	"knowledge_complete": Color("8fdc8f"), "search": Color(1.0, 0.6, 0.0),
	"quest_active": Color.WHITE, "quest_completed": Color("999999"),
	"quest_heading": Color.WHITE, "quest_ready": Color(0.77, 0.57, 0.39),
	"book_text": Color(0.77, 0.57, 0.39), "book_muted": Color("999999"),
	"book_heading": Color(0.77, 0.57, 0.39),
	"book_points": Color("c982ee"),
	"spell_text": Color(0.77, 0.57, 0.39), "spell_muted": Color("999999"),
	"spell_ready": Color.GREEN, "spell_blocked": Color.RED, "spell_cost": Color.WHITE,
	"summon_ready": Color("d9ffd9"), "summon_blocked": Color("ff5c5c"),
	"summon_cost": Color("b8c7e6"),
	"reference_online": Color("9ee09e"), "reference_offline": Color(0.5, 0.55, 0.6),
	"party_text": Color("eee3c8"), "party_muted": Color("b6aa91"),
	"party_health": Color("479947"), "party_health_low": Color("b74935"),
	"party_ether": Color("4287ac"),
	"encyclopedia_text": Color.WHITE, "encyclopedia_link": Color("7fb4ff"),
	"encyclopedia_link_hover": Color(0.3, 0.6, 1.0),
	"encyclopedia_heading": Color("e8b552"), "encyclopedia_note": Color("9fb3c8"),
	"encyclopedia_fact": Color("8fd0c8"),
	"hud_meter": Color(0.8, 0.8, 0.8), "hud_skill": Color.WHITE,
	"hud_detail": Color("eee3c8"),
	"hud_selected": Color(0.77, 0.57, 0.39),
	"hud_timer_running": Color(0.5, 1.0, 0.5), "hud_timer_stopped": Color(1.0, 0.5, 0.5),
	"chat_selector": Color(0.5, 0.75, 1.0), "chat_tab": Color(0.77, 0.57, 0.39),
	"chat_selected": Color(0.57, 1.0, 0.59), "chat_unread": Color.YELLOW,
	"world_player": Color.WHITE, "world_npc": Color(0.3, 0.8, 1.0),
	"world_creature": Color.YELLOW, "world_pk": Color.RED,
	"world_special_map": Color(0.6, 0.9, 0.9), "world_guild": Color.WHITE,
	"world_speech": Color.WHITE, "world_title": Color("d9c773"),
	"world_occupation": Color("c7c2ad"), "world_quest": Color("ffba21"),
	"world_health": Color.GREEN, "world_entrance": Color("58e1ff"),
	"world_storage": Color(214.0 / 255.0 * 0.7 + 0.3, 187.0 / 255.0 * 0.7 + 0.3, 122.0 / 255.0 * 0.7 + 0.3),
	"world_resource": Color(0.42, 0.86, 0.44),
	"float_damage": Color(1.0, 0.1, 0.2), "float_heal": Color(0.3, 1.0, 0.3),
	"float_xp": Color(0.3, 1.0, 0.3), "float_xp_loss": Color(1.0, 0.1, 0.2),
	"float_level": Color(0.3, 0.3, 1.0),
	"map_server": Color(0.33, 0.6, 1.0), "map_personal": Color(0.0, 1.0, 0.0),
	"map_region": Color(1.0, 0.95, 0.8, 0.95), "map_current": Color(0.98, 0.78, 0.22),
	"map_hover": Color(1.0, 0.92, 0.55),
	"map_marker": Color.WHITE, "map_continent": Color(0.96, 0.96, 0.98),
	"map_service": Color("f2e4b7"), "map_minimap": Color.WHITE,
	"market_expiring": Color("e0a14a"), "market_completed": Color("9fd88f"),
	"market_refused": Color("f08a6a"),
	"loot_title": Color("e9bd83"), "loot_text": Color("e9e1cf"),
	"loot_muted": Color("9eaaa6"), "loot_accent": Color("7cc6d4"), "loot_success": Color("94d789"),
	"loot_error": Color("ed9475"), "loot_primary": Color("071316"),
	"ready_title": Color("edc981"), "ready_success": Color("a8d895"), "ready_waiting": Color("e1bb80"),
	"leaderboard_title": Color("e1b862"), "leaderboard_text": Color("f2e8d4"),
	"leaderboard_muted": Color("aaa99f"), "leaderboard_silver": Color("bbc9d7"),
	"leaderboard_bronze": Color("ca9167"),
	"mount_title": Color("efdcb7"), "mount_text": Color("d8d1bf"),
	"mount_muted": Color("b7af9d"), "mount_button": Color("f2e5c9"),
	"invasion_text": Color("efe7d6"), "invasion_freshness": Color("a6b7bc"),
	"invasion_heading": Color("d8ba78"), "invasion_destructive": Color("ff9186"),
	"invasion_muted": Color("8296a3"), "invasion_ally": Color("68e7ff"),
	"invasion_boss": Color("ffc94f"), "invasion_enemy": Color("ff6b63"),
	"invasion_detail": Color("9fc0d4"), "invasion_hint": Color("ffd36a"),
	"guide_heading": Color("f2c978"), "update_progress": Color("ffd58c"),
}

const GROUPS := {
	"Interface": ["ui_label", "ui_button", "ui_bright", "ui_heading", "ui_hover", "ui_pressed", "ui_disabled", "ui_input", "ui_placeholder", "ui_selected", "ui_tooltip"],
	"Login": ["login_label", "login_input", "login_placeholder", "login_error", "login_status"],
	"NPC dialogue": ["npc_text", "npc_reply", "npc_reply_hover", "npc_unavailable", "npc_footer"],
	"Inventory and crafting": ["inventory_text", "inventory_selected", "inventory_count", "inventory_equipped", "quantity", "quantity_selected", "quantity_editing", "equipment_heading", "manufacture_normal", "manufacture_error"],
	"Statistics": ["stats_heading", "stats_attribute", "stats_nexus", "stats_skill", "stats_watched", "stats_resource", "stats_spend", "stats_pending"],
	"Knowledge": ["knowledge_read", "knowledge_unread", "knowledge_selected", "knowledge_hover", "knowledge_complete", "search"],
	"Quests": ["quest_active", "quest_completed", "quest_heading", "quest_ready"],
	"Books and spells": ["book_text", "book_muted", "book_heading", "book_points", "spell_text", "spell_muted", "spell_ready", "spell_blocked", "spell_cost", "summon_ready", "summon_blocked", "summon_cost"],
	"Contacts": ["reference_online", "reference_offline"],
	"Party": ["party_text", "party_muted", "party_health", "party_health_low", "party_ether"],
	"Encyclopedia": ["encyclopedia_text", "encyclopedia_link", "encyclopedia_link_hover", "encyclopedia_heading", "encyclopedia_note", "encyclopedia_fact"],
	"HUD and chat controls": ["hud_meter", "hud_skill", "hud_detail", "hud_selected", "hud_timer_running", "hud_timer_stopped", "chat_selector", "chat_tab", "chat_selected", "chat_unread"],
	"World names and speech": ["world_player", "world_npc", "world_creature", "world_pk", "world_special_map", "world_guild", "world_speech", "world_title", "world_occupation", "world_quest", "world_health", "world_entrance", "world_storage", "world_resource"],
	"Floating feedback": ["float_damage", "float_heal", "float_xp", "float_xp_loss", "float_level"],
	"Maps": ["map_server", "map_personal", "map_region", "map_current", "map_hover", "map_marker", "map_continent", "map_service", "map_minimap"],
	"Rabbit Lands windows": ["market_expiring", "market_completed", "market_refused", "loot_title", "loot_text", "loot_muted", "loot_accent", "loot_success", "loot_error", "loot_primary", "ready_title", "ready_success", "ready_waiting", "leaderboard_title", "leaderboard_text", "leaderboard_muted", "leaderboard_silver", "leaderboard_bronze", "mount_title", "mount_text", "mount_muted", "mount_button", "invasion_text", "invasion_freshness", "invasion_heading", "invasion_destructive", "invasion_muted", "invasion_ally", "invasion_boss", "invasion_enemy", "invasion_detail", "invasion_hint", "guide_heading", "update_progress"],
}

const LABELS := {
	"ui_label": "Labels", "ui_button": "Buttons", "ui_bright": "Bright text", "ui_heading": "Headings",
	"ui_hover": "Hovered controls", "ui_pressed": "Pressed controls", "ui_disabled": "Disabled controls",
	"ui_input": "Input text", "ui_placeholder": "Input hints", "ui_selected": "Selected input text", "ui_tooltip": "Tooltips",
	"login_label": "Labels and help", "login_input": "Input text", "login_placeholder": "Input hints", "login_error": "Errors", "login_status": "Status",
	"npc_text": "Speaker and dialogue", "npc_reply": "Replies", "npc_reply_hover": "Hovered replies", "npc_unavailable": "Unavailable replies", "npc_footer": "Instructions",
	"inventory_text": "Lists and buttons", "inventory_selected": "Selected list entry", "inventory_count": "Stack counts", "quantity": "Quantity presets", "quantity_selected": "Selected quantity", "quantity_editing": "Edited quantity", "equipment_heading": "Equipment heading", "manufacture_normal": "Crafting status", "manufacture_error": "Crafting errors",
	"stats_heading": "Headings", "stats_attribute": "Cross attributes", "stats_nexus": "Nexus", "stats_skill": "Skills", "stats_watched": "Watched skills", "stats_resource": "Resource values", "stats_spend": "Spend pickpoints", "stats_pending": "Pending pickpoints",
	"knowledge_read": "Known entries", "knowledge_unread": "Unread entries", "knowledge_selected": "Selected entries", "knowledge_hover": "Hovered entries", "knowledge_complete": "Reading completion", "search": "Search matches",
	"quest_active": "Active quests and body", "quest_completed": "Completed quests", "quest_heading": "Headings", "quest_ready": "Contextual highlights",
	"reference_online": "Online contacts", "reference_offline": "Offline contacts",
	"hud_meter": "Bottom meter text", "hud_skill": "Side skills", "hud_detail": "Clock, compass and card text", "hud_selected": "Selected side skill", "hud_timer_running": "Running timer", "hud_timer_stopped": "Stopped timer", "chat_selector": "Chat selectors", "chat_tab": "Chat tabs", "chat_selected": "Selected chat tab", "chat_unread": "Unread chat tab",
	"world_player": "Player names", "world_npc": "NPC names", "world_creature": "Creature names", "world_pk": "PKable player names", "world_special_map": "Special map player names", "world_guild": "Guild tags", "world_speech": "Overhead speech", "world_title": "Player titles", "world_occupation": "NPC occupations", "world_quest": "Quest markers",
	"float_damage": "Damage", "float_heal": "Healing", "float_xp": "Experience gains", "float_xp_loss": "Experience losses", "float_level": "Level gains",
	"map_server": "Server marks", "map_personal": "Personal marks", "map_region": "Region names", "map_current": "Current region", "map_hover": "Hovered region",
}

class ChangeEvents:
	extends RefCounted
	signal changed(role: String)

static var _events: ChangeEvents
static var _overrides: Dictionary = {}
static var _bindings: Dictionary = {}
static var _binding_owners: Dictionary = {}
static var preferences_path := SETTINGS_PATH

static func events() -> ChangeEvents:
	if _events == null:
		_events = ChangeEvents.new()
	return _events

static func defaults() -> Dictionary:
	return DEFAULTS.duplicate()

static func overrides() -> Dictionary:
	return _overrides.duplicate()

static func colors() -> Dictionary:
	var result := defaults()
	result.merge(_overrides, true)
	return result

static func color(role: String, fallback: Color = Color.WHITE) -> Color:
	return _overrides.get(role, DEFAULTS.get(role, fallback)) as Color

static func is_overridden(role: String) -> bool:
	return _overrides.has(role)

static func label(role: String) -> String:
	return str(LABELS.get(role, role.replace("_", " ").capitalize()))

static func _valid_color(value: Variant) -> Variant:
	if value is String and Color.html_is_valid(value):
		value = Color.html(value)
	if value is Color:
		var chosen: Color = value
		if is_finite(chosen.r) and is_finite(chosen.g) and is_finite(chosen.b) and is_finite(chosen.a):
			return Color(clampf(chosen.r, 0.0, 1.0), clampf(chosen.g, 0.0, 1.0), clampf(chosen.b, 0.0, 1.0), clampf(chosen.a, 0.0, 1.0))
	return null

static func load_colors(path: String = SETTINGS_PATH) -> Dictionary:
	preferences_path = path
	_overrides.clear()
	var config := ConfigFile.new()
	if config.load(path) == OK:
		for role: String in DEFAULTS:
			if not config.has_section_key(SECTION, role):
				continue
			var value: Variant = _valid_color(config.get_value(SECTION, role))
			if value is Color:
				_overrides[role] = value
	_notify("")
	return colors()

static func set_color(role: String, chosen: Color) -> void:
	if not DEFAULTS.has(role):
		return
	var value: Variant = _valid_color(chosen)
	if not value is Color:
		return
	_overrides[role] = value
	_notify(role)

static func reset(role: String = "") -> void:
	if role.is_empty():
		_overrides.clear()
	else:
		_overrides.erase(role)
	_notify(role)

static func save_colors(path: String = "") -> Error:
	if path.is_empty():
		path = preferences_path
	var config := ConfigFile.new()
	var error := config.load(path)
	if error != OK and FileAccess.file_exists(path):
		return error
	for role: String in DEFAULTS:
		if _overrides.has(role):
			config.set_value(SECTION, role, _overrides[role])
		elif config.has_section_key(SECTION, role):
			config.erase_section_key(SECTION, role)
	return config.save(path)

## Binds a theme color while preserving every unrelated style and size.
## Repeated styling passes replace the same binding rather than adding listeners.
static func bind(control: Control, role: String, property: String = "font_color") -> void:
	_bind(control, role, property, true)

## Label3D and other objects expose a color property rather than a theme slot.
static func bind_property(object: Object, role: String, property: String) -> void:
	_bind(object, role, property, false)

static func unbind(object: Object, property: String = "") -> void:
	for key: String in _bindings.keys():
		var binding: Dictionary = _bindings[key]
		if binding.reference.get_ref() == object and (property.is_empty() or binding.property == property):
			_bindings.erase(key)
	var roles: Dictionary = object.get_meta("text_color_roles", {})
	var kinds: Dictionary = object.get_meta("text_color_binding_kinds", {})
	if property.is_empty():
		roles.clear()
		kinds.clear()
	else:
		roles.erase(property)
		kinds.erase(property)
	object.set_meta("text_color_roles", roles)
	object.set_meta("text_color_binding_kinds", kinds)
	if roles.is_empty():
		object.remove_meta("text_color_role")
	else:
		object.set_meta("text_color_role", roles.values()[0])

static func _bind(object: Object, role: String, property: String, theme: bool) -> void:
	if object == null or not DEFAULTS.has(role):
		return
	var key := "%d:%s" % [object.get_instance_id(), property]
	if object is Node:
		var owner_id := object.get_instance_id()
		if not object.has_meta("text_color_entry_hook"):
			object.set_meta("text_color_entry_hook", true)
			(object as Node).tree_entered.connect(_restore_object_bindings.bind(weakref(object)))
		if not _binding_owners.has(owner_id):
			_binding_owners[owner_id] = []
			(object as Node).tree_exiting.connect(_remove_object_bindings.bind(owner_id), CONNECT_ONE_SHOT)
		if not key in _binding_owners[owner_id]:
			(_binding_owners[owner_id] as Array).append(key)
	object.set_meta("text_color_role", role)
	var roles: Dictionary = object.get_meta("text_color_roles", {})
	roles[property] = role
	object.set_meta("text_color_roles", roles)
	var kinds: Dictionary = object.get_meta("text_color_binding_kinds", {})
	kinds[property] = theme
	object.set_meta("text_color_binding_kinds", kinds)
	_bindings[key] = {"reference": weakref(object), "role": role, "property": property, "theme": theme}
	_apply_binding(_bindings[key])

static func _remove_object_bindings(owner_id: int) -> void:
	for key: String in _binding_owners.get(owner_id, []):
		_bindings.erase(key)
	_binding_owners.erase(owner_id)

static func _restore_object_bindings(reference: WeakRef) -> void:
	var object: Object = reference.get_ref()
	if object == null:
		return
	var roles: Dictionary = object.get_meta("text_color_roles", {})
	var kinds: Dictionary = object.get_meta("text_color_binding_kinds", {})
	for property: String in roles:
		_bind(object, str(roles[property]), property, bool(kinds.get(property, true)))

static func _apply_binding(binding: Dictionary) -> bool:
	var object: Object = binding.reference.get_ref()
	if object == null:
		return false
	var chosen := color(str(binding.role))
	if bool(binding.theme) and str(binding.property) in ["font_color", "default_color"] and object.has_meta("hud_text_color_override"):
		var component_color: Variant = object.get_meta("hud_text_color_override")
		if component_color is Color:
			chosen = component_color
	if bool(binding.theme):
		(object as Control).add_theme_color_override(str(binding.property), chosen)
	else:
		object.set(str(binding.property), chosen)
	return true

static func _notify(role: String) -> void:
	for key: String in _bindings.keys():
		var binding: Dictionary = _bindings[key]
		if binding.reference.get_ref() == null:
			_bindings.erase(key)
		elif role.is_empty() or binding.role == role:
			_apply_binding(binding)
	events().changed.emit(role)
