extends RefCounted
## Versioned local presentation settings. Slot assignments, chat history and
## server state deliberately belong to their existing owners.
const SECTION := "hud_presets"
const VERSION := 1
const BUILT_INS := {"current": "Current HUD", "heritage": "Heritage Polish · option 1",
	"classic": "Refined Classic · option 2", "modular": "Modular MMO · option 3",
	"adventure": "Painterly Adventure · option 4", "minimal": "Minimal Modern · option 5"}
const PARTS := {"rail_panel": "Blank HUD panel", "utilities": "Menu icons", "resources": "Resource meters",
	"spells": "Quick spells / techniques", "items": "Quick items",
	"medallion": "Resource circle", "chat": "Conversation window",
	"system_chat": "System window", "party": "Party roster", "minimap": "Minimap",
	"skills": "Skill statistics", "clock": "Game clock", "compass": "Compass",
	"status": "Status indicators", "timer": "Countdown / stopwatch",
	"research": "Research progress", "logo": "Rabbit Lands logo", "fps": "FPS",
	"objectives": "Tracked objectives", "target": "Selected target", "nameplate": "Character banner",
	"player_card": "Player card", "food_meter": "Food meter", "load_meter": "Load meter", "xp_meter": "Experience meter"}
const ANCHORS := ["original", "top_left", "top_center", "top_right", "left",
	"right", "bottom_left", "bottom_center", "bottom_right", "free"]
const STYLES := ["current", "heritage", "classic", "modular", "adventure", "minimal"]
const RESOURCES := ["health", "mana", "food", "action", "mount_stamina", "load"]
const RESOURCE_COLORS := {"health": Color("65b873"), "mana": Color("5ba6ed"),
	"food": Color("e6b85b"), "action": Color("b69ae5"), "mount_stamina": Color("67c8bf"), "load": Color("c49c72"), "experience": Color("c5b989")}
const BORDERS := ["plain", "laurel", "runic", "crystal"]
const HUD_BORDERS := ["plain", "beveled", "ornate"]
const BANNER_FIELDS := ["show_names", "health_bar", "health_numbers", "ether_bar", "ether_numbers", "food_bar", "food_numbers", "action_bar", "action_numbers", "banner_background"]
var editor_position := Vector2(-1, -1)
var active := "current"
var working: Dictionary = preset("current")
var custom: Dictionary = {}
var builtin_overrides: Dictionary = {}
var loaded := false

static func preset(id: String) -> Dictionary:
	# Option 2 carries the player-refined Heritage layout. Option 1 keeps the
	# original concept's narrow right rail and full-width lower toolbar.
	var value := _preset_recipe("heritage" if id == "classic" else id)
	if id == "classic":
		for key: String in PARTS: value.parts[key].style = "classic"
		value.parts.skills.enabled = false
		value.parts.minimap.enabled = true
		value.parts.minimap.map_shape = "round"
		value.parts.minimap.frame_shape = "circle"
		value.parts.minimap.scale = 0.72
		value.parts.minimap.dimensions = Vector2.ONE * 240 / 0.72
		value.parts.minimap.map_title = true
		value.parts.minimap.map_directions = "north"
		value.parts.minimap.north_marker = "arrow"
		value.parts.minimap.direction_offset = 12.0
		_place(value, "minimap", "top_right", Vector2(-30, 56))
	elif id == "heritage":
		for key: String in PARTS:
			value.parts[key].dock_target = "none"
			value.parts[key].dock_offset = Vector2.ZERO
			value.parts[key].edge_dock = "none"
			value.parts[key].extend_to_edge = false
		value.parts.party.enabled = false
		value.parts.skills.enabled = true
		value.parts.minimap.enabled = false
		value.parts.rail_panel.enabled = true
		value.parts.rail_panel.full_height = true
		value.parts.rail_panel.hide_with_stats = false
		value.parts.rail_panel.dimensions = Vector2(92, 400)
		value.parts.rail_panel.edge_dock = "top_right"
		value.parts.rail_panel.hud_border_style = "beveled"
		# Match the player's saved Heritage arrangement with responsive docks.
		value.parts.compass.enabled = true
		value.parts.compass.scale = 0.5
		value.parts.compass.dimensions = Vector2(184, 129)
		value.parts.compass.edge_dock = "bottom_right"
		value.parts.compass.show_labels = false
		_place(value, "compass", "bottom_right", Vector2.ZERO)
		value.parts.clock.clock_mode = "both"
		value.parts.clock.dimensions = Vector2(92, 96)
		value.parts.clock.scale = 1.0
		_dock(value, "clock", "compass", "top", "stretch")
		value.parts.research.enabled = true
		value.parts.research.dimensions = Vector2(92, 28)
		_dock(value, "research", "clock", "top", "stretch")
		value.parts.skills.scale = 0.7
		value.parts.skills.axis_scale = Vector2(1.964945, 1.873677)
		_dock(value, "skills", "research", "top", "stretch")
		for key: String in ["spells", "items"]:
			value.parts[key].orientation = "vertical"
			value.parts[key].rows = 6
			value.parts[key].columns = 1
			value.parts[key].scale = 1.0
			value.parts[key].flush_slots = true
			value.parts[key].slot_gap = 0.0
			value.parts[key].dimensions = Vector2(46, 276)
			value.parts[key].slot_border_style = "beveled"
		_dock(value, "items", "logo", "bottom", "end")
		_dock(value, "spells", "items", "left", "end")
		value.parts.logo.scale = 1.0
		value.parts.logo.axis_scale = Vector2.ONE
		value.parts.logo.dimensions = Vector2(92, 88)
		value.parts.logo.edge_dock = "top_right"
		value.parts.status.enabled = true
		value.parts.status.scale = 0.8
		value.parts.status.axis_scale = Vector2(1.90535, 1.833333)
		_dock(value, "status", "rail_panel", "left", "end")
		value.parts.utilities.scale = 1.0
		value.parts.utilities.dimensions = Vector2(1011.111, 44)
		_dock(value, "utilities", "status", "left", "end")
		value.parts.utilities.extend_to_edge = true
		value.parts.resources.dimensions = Vector2(1175, 40)
		_dock(value, "resources", "rail_panel", "left", "end")
		value.parts.resources.dock_offset.y = -44
		value.parts.resources.extend_to_edge = true
		value.parts.chat.dimensions = Vector2(490, 220)
		_place(value, "chat", "top_left", Vector2(12, 48))
		value.parts.chat.frame_style = "floating"
		value.parts.chat.show_background = false
		value.parts.chat.show_border = false
		value.parts.chat.compact = true
		value.parts.resources.show_icons = true
		value.parts.resources.show_labels = true
	elif id == "adventure":
		# Preserve the player's completed option-4 arrangement as its factory layout.
		_dock(value, "medallion", "resources", "top")
		value.parts.spells.dock_align = "end"
		value.parts.items.dock_align = "end"
		value.parts.utilities.dock_gap = -1.0
		value.meter_order = ["health", "mana", "action", "food", "load", "experience"]
		value.parts.resources.anchor = "free"
		value.parts.resources.position = Vector2(0.23252, 0.942408)
		value.parts.resources.scale = 0.95
		value.parts.resources.dimensions = Vector2(686.3817, 40)
		value.parts.resources.extend_to_edge = true
		value.parts.resources.frame_style = "panel"
		value.parts.resources.show_background = true
		value.parts.resources.show_border = true
		value.parts.resources.background_color = Color("241e15ed")
		value.parts.resources.border_color = Color("aa8d50")
		value.parts.resources.show_icons = true
		value.parts.resources.show_labels = true
		value.parts.resources.show_values = true
		for index: int in [0, 1]:
			value.parts.medallion.arcs[index].enabled = true
			value.parts.medallion.arcs[index].sweep_angle = 100.0
		value.parts.medallion.arcs[5].enabled = true
		value.parts.medallion.arcs[5].sweep_angle = 68.0
		value.parts.minimap.anchor = "free"
		value.parts.minimap.position = Vector2(0.821694, 0.546395)
		value.parts.minimap.dock_target = "none"
		value.parts.minimap.edge_dock = "right"
		value.parts.minimap.map_shape = "round"
		value.parts.minimap.map_palette = "natural"
		value.parts.minimap.hud_border_style = "beveled"
		value.parts.minimap.map_title = true
		value.parts.minimap.map_directions = "north"
		value.parts.minimap.direction_offset = 21.0
		value.parts.minimap.north_marker = "arrow"
		value.parts.load_meter.anchor = "free"
		value.parts.load_meter.offset = Vector2.ZERO
		value.parts.load_meter.position = Vector2(0.823438, 0.931937)
	elif id == "minimal":
		# Adopt the player's saved option-5 presentation without runtime state.
		for key: String in ["resources", "food_meter", "load_meter", "xp_meter"]: value.parts[key].enabled = false
		value.parts.spells.anchor = "free"
		value.parts.spells.offset = Vector2.ZERO
		value.parts.spells.position = Vector2(0.274471, 0.851833)
		value.parts.spells.grid_mode = "aspect"
		value.parts.spells.slots = 8
		value.parts.spells.dimensions = Vector2(366.798, 52)
		value.parts.spells.background_color = Color.TRANSPARENT
		_dock(value, "spells", "items", "top")
		value.parts.spells.dock_offset.x = 0.772278
		value.parts.items.anchor = "free"
		value.parts.items.offset = Vector2.ZERO
		value.parts.items.position = Vector2(0.355391, 0.91825)
		value.parts.items.slots = 8
		value.parts.items.dock_target = "none"
		value.parts.items.edge_dock = "bottom"
		value.parts.items.slot_border_style = "beveled"
		value.parts.party.dimensions = Vector2(244, 239)
		value.parts.party.show_player_details = true
		value.parts.minimap.anchor = "free"
		value.parts.minimap.offset = Vector2.ZERO
		value.parts.minimap.position = Vector2(0.815278, 0.051667)
		value.parts.minimap.edge_dock = "right"
		value.parts.minimap.map_shape = "round"
		value.parts.minimap.map_palette = "natural"
		value.parts.minimap.map_directions = "north"
		value.parts.minimap.direction_offset = 18.0
		value.parts.minimap.north_marker = "arrow"
		value.parts.compass.anchor = "free"
		value.parts.compass.offset = Vector2.ZERO
		value.parts.compass.position = Vector2(0.351563, 0.02)
		value.parts.compass.dimensions = Vector2(380, 25.33334)
		value.parts.logo.scale = 0.5
		value.parts.objectives.background_color = Color(0.18636246, 0.24665597, 0.29187614, 0.69803923)
		value.parts.objectives.border_color = Color(0.33680552, 0.28724948, 0.28724948)
		value.parts.objectives.frame_style = "panel"
		value.parts.objectives.show_background = true
		value.parts.objectives.show_border = true
		value.parts.objectives.hud_border_style = "beveled"
		value.parts.food_meter.anchor = "free"
		value.parts.food_meter.position = Vector2(0.690972, 0.892778)
		value.parts.food_meter.dock_target = "none"
		value.parts.load_meter.anchor = "free"
		value.parts.load_meter.position = Vector2(0.004688, 0.9275)
		value.parts.load_meter.dock_target = "none"
		value.parts.load_meter.edge_dock = "bottom_left"
	return value

static func _preset_recipe(id: String) -> Dictionary:
	var value := {"version": VERSION, "frame_alpha_version": 1, "legacy": id == "current", "parts": {},
		"icons": {}, "meters": {}, "meter_order": [], "resource_colors": RESOURCE_COLORS.duplicate(), "chat_windows": {}, "native_spell_bar": {}, "banner_options": {}}
	for field: String in BANNER_FIELDS:
		value.banner_options[field] = field != "banner_background" and (id != "minimal" or field == "show_names")
	for key: String in PARTS:
		value.parts[key] = {"enabled": key != "medallion", "anchor": "original",
			"offset": Vector2.ZERO, "position": Vector2(0.5, 0.5), "scale": 1.0, "axis_scale":Vector2.ONE,
			"orientation": "horizontal", "rows": 1, "columns": 0, "grid_mode": "fixed", "style": id, "slots": 6, "dimensions": Vector2.ZERO,
			"background_color": Color("241e15ed"), "border_color": Color("aa8d50"), "text_color": Color("eee3c8"),
			"dock_target": "none", "dock_side": "right", "dock_gap": 0.0, "dock_align":"center", "dock_offset":Vector2.ZERO, "extend_to_edge":false, "edge_dock":"none",
			"compass_mode": "round", "map_shape": "square", "map_palette": "natural", "load_display": "free", "center_resource": "health",
			"center_color": RESOURCE_COLORS.health, "border_design": "plain", "arcs": default_arcs(),
			"show_values": true, "show_labels": true, "show_icons":false, "compact": id == "minimal",
			"frame_style": "panel", "show_background": true, "show_border": true, "clock_mode": "both",
			"hud_border_style": "plain", "frame_shape": "match_map", "compass_corners": "fill_when_docked",
			"slot_border_style": "match_hud", "slot_border_color": Color("aa8d50"), "icon_opacity": 1.0, "unavailable_icon_opacity": 1.0,
			"flush_slots": false, "slot_gap": 2.0,
			"map_title": false, "map_directions": "all", "direction_offset": -9.0, "north_marker": "letter", "map_label_frame": false,
			"full_height": false, "hide_with_stats": false,
			"meter_keys": [], "show_secondary": true, "show_self": true, "show_player_details": false, "show_badges": true}
	for key: String in ["rail_panel", "player_card", "food_meter", "load_meter", "xp_meter"]:
		value.parts[key].enabled = false
		if key in ["food_meter", "load_meter", "xp_meter"]: value.parts[key].meter_keys = [{"food_meter":"food", "load_meter":"load", "xp_meter":"experience"}[key]]
	value.parts.objectives.enabled = true
	value.parts.target.enabled = true
	value.parts.items.slots = 8
	value.parts.spells.orientation = "vertical"
	value.parts.items.orientation = "vertical"
	if id == "current": return value
	value.meters = {"health":true, "mana":true, "food":true, "load":true, "action":true, "experience":true}
	if id == "heritage":
		_place(value, "spells", "top_right", Vector2(-80, 210))
		_place(value, "items", "top_right", Vector2(-8, 210))
		value.parts.spells.scale = 0.75
		value.parts.items.scale = 0.75
		_place(value, "utilities", "bottom_left", Vector2(4, -4))
		value.parts.utilities.scale = 0.75
		_place(value, "resources", "bottom_center", Vector2(0, -62))
		_place(value, "chat", "bottom_left", Vector2(4, -120))
		_place(value, "system_chat", "left", Vector2(4, -70))
		_place(value, "minimap", "top_right", Vector2(-8, 8))
		value.parts.minimap.scale = 0.62
		_place(value, "party", "top_left", Vector2(8, 8))
		_place(value, "compass", "top_right", Vector2(-82, 530))
		value.parts.compass.scale = 0.65
		_place(value, "clock", "top_right", Vector2(-82, 616))
		value.parts.clock.scale = 0.8
		_place(value, "skills", "top_right", Vector2(-8, 530))
		value.parts.skills.scale = 0.8
		_place(value, "status", "bottom_left", Vector2(4, -40))
		value.parts.status.scale = 0.8
		_place(value, "objectives", "top_right", Vector2(-200, 8))
		for key: String in ["timer", "research", "logo", "fps"]: value.parts[key].enabled = false
		return _art_directed(value, id)
	for key: String in ["skills", "clock", "compass", "status", "timer", "research", "logo", "fps"]:
		value.parts[key].enabled = false
	_place(value, "utilities", "bottom_center", Vector2(0, -8))
	_place(value, "resources", "bottom_center", Vector2(0, -166))
	_place(value, "chat", "top_left", Vector2(12, 290))
	value.parts.chat.dimensions = Vector2(350, 180)
	value.parts.system_chat.dimensions = Vector2(350, 100)
	value.parts.party.dimensions = Vector2(244, 236)
	_place(value, "system_chat", "top_left", Vector2(12, 240))
	_place(value, "chat", "bottom_left", Vector2(12, -200))
	_place(value, "party", "top_left", Vector2(12, 12))
	_place(value, "minimap", "top_right", Vector2(-12, 12))
	value.parts.spells.orientation = "horizontal"
	value.parts.items.orientation = "horizontal"
	value.parts.target.enabled = id in ["modular", "minimal"]
	_place(value, "target", "top_center", Vector2(0, 12))
	value.parts.objectives.enabled = id in ["modular", "adventure", "minimal"]
	_place(value, "objectives", "top_right", Vector2(-12, 270))
	value.parts.minimap.map_shape = "round" if id in ["classic", "modular"] else "square"
	for key: String in PARTS:
		if id in ["modular", "minimal"]:
			value.parts[key].background_color = Color("191e22d0") if id == "modular" else Color("121a2060")
			value.parts[key].border_color = Color("727b86") if id == "modular" else Color("858f9c66")
	if id == "classic":
		value.parts.compass.enabled = true
		_place(value, "compass", "bottom_right", Vector2(-12, -250))
		_place(value, "spells", "bottom_right", Vector2(-12, -152))
		_place(value, "items", "bottom_right", Vector2(-12, -94))
		_place(value, "resources", "bottom_left", Vector2(12, -56))
		_place(value, "utilities", "bottom_left", Vector2(12, -8))
		value.parts.utilities.scale = 0.8
	elif id == "modular":
		value.meter_order = ["health", "mana", "food", "load", "action", "experience"]
		value.parts.resources.orientation = "vertical"
		value.parts.resources.dimensions = Vector2(410, 150)
		value.meters = {"health":true, "mana":true, "food":true, "load":false, "action":false, "experience":false}
		_place(value, "spells", "bottom_center", Vector2(0, -102))
		_place(value, "items", "bottom_center", Vector2(0, -44))
		_place(value, "utilities", "bottom_right", Vector2(-10, -8))
		value.parts.utilities.rows = 2
		value.parts.utilities.scale = 0.7
	elif id == "adventure":
		value.parts.medallion.enabled = true
		value.parts.medallion.border_design = "laurel"
		_place(value, "medallion", "bottom_center", Vector2(0, -62))
		_place(value, "spells", "bottom_center", Vector2(-250, -72))
		_place(value, "items", "bottom_center", Vector2(235, -72))
		_place(value, "resources", "bottom_center", Vector2(0, -200))
		_place(value, "minimap", "bottom_right", Vector2(-12, -58))
		value.parts.minimap.scale = 0.7
		value.parts.spells.scale = 0.9
		value.parts.items.scale = 0.9
		value.parts.spells.slots = 5
		value.parts.items.slots = 5
		value.parts.spells.dock_target = "medallion"
		value.parts.spells.dock_side = "left"
		value.parts.items.dock_target = "medallion"
		value.parts.items.dock_side = "right"
		value.meters = {"health":false, "mana":false, "food":false, "load":false, "action":false, "experience":true}
		value.parts.resources.dimensions = Vector2(700, 22)
		value.parts.resources.show_labels = false
		value.parts.resources.show_values = false
		value.parts.resources.background_color.a = 0
		value.parts.resources.border_color.a = 0.35
		_place(value, "resources", "bottom_center", Vector2.ZERO)
		_place(value, "medallion", "bottom_center", Vector2(0, -78))
		value.parts.utilities.offset.y = -24
		value.parts.utilities.rows = 2
		value.parts.utilities.scale = 0.7
	elif id == "minimal":
		_place(value, "spells", "bottom_center", Vector2(-130, -30))
		_place(value, "items", "bottom_center", Vector2(240, -30))
		value.parts.spells.scale = 0.85
		value.parts.items.scale = 0.85
		value.parts.items.dock_target = "spells"
		value.parts.items.dock_side = "right"
		_place(value, "utilities", "bottom_right", Vector2(-8, -8))
		value.parts.utilities.scale = 0.7
		value.parts.utilities.rows = 2
		_place(value, "resources", "bottom_center", Vector2(0, -140))
		value.parts.resources.show_labels = false
		value.parts.resources.show_values = false
		value.parts.resources.dimensions = Vector2(540, 32)
		value.parts.resources.offset.y = -102
		value.parts.minimap.scale = 0.7
		value.parts.compass.enabled = true
		value.parts.compass.compass_mode = "ribbon"
		_place(value, "compass", "top_center", Vector2(0, 8))
		_place(value, "target", "top_center", Vector2(0, 74))
	return _art_directed(value, id)

static func _art_directed(value: Dictionary, id: String) -> Dictionary:
	# These are real control configurations, not screenshots or mock HUD copies.
	if id == "current": return value
	value.parts.chat.dimensions = Vector2(350, 200)
	value.parts.system_chat.dimensions = Vector2(350, 95)
	value.parts.party.dimensions = Vector2(244, 170)
	value.parts.party.compact = true
	value.parts.party.frame_style = "floating"
	value.parts.objectives.compact = true
	for key: String in ["resources", "food_meter", "load_meter"]: value.parts[key].load_display = "carried"
	value.chat_windows = {"chat":{"options":{"combined":id in ["adventure", "minimal"], "background_opacity":0.12 if id == "minimal" else 0.36}},
		"system_chat":{"options":{"background_opacity":0.2}}}
	_place(value, "chat", "bottom_left", Vector2(12, -112))
	_place(value, "system_chat", "bottom_left", Vector2(12, -8))
	value.parts.chat.compact = id in ["modular", "adventure", "minimal"]
	value.parts.system_chat.compact = true
	for key: String in ["food_meter", "load_meter", "xp_meter"]:
		value.parts[key].meter_keys = [{"food_meter":"food", "load_meter":"load", "xp_meter":"experience"}[key]]
		value.parts[key].dimensions = Vector2(220, 46)
		value.parts[key].frame_style = "floating" if id == "minimal" else "panel"
	value.parts.xp_meter.show_labels = false
	value.parts.xp_meter.show_values = false
	value.parts.xp_meter.frame_style = "floating"
	value.parts.xp_meter.dimensions = Vector2(500, 22)
	_place(value, "xp_meter", "bottom_center", Vector2.ZERO)
	if id == "heritage":
		value.parts.party.enabled = false
		value.parts.minimap.enabled = false
		value.parts.objectives.enabled = false
		value.parts.target.enabled = false
		value.parts.chat.dimensions = Vector2(490, 220)
		value.parts.system_chat.dimensions = Vector2(440, 100)
		_place(value, "chat", "top_left", Vector2(12, 48))
		_place(value, "system_chat", "bottom_left", Vector2(12, -112))
		_place(value, "spells", "top_right", Vector2(-46, 70))
		_place(value, "items", "top_right", Vector2(-4, 70))
		value.parts.spells.scale = 0.65
		value.parts.items.scale = 0.65
		value.parts.items.slots = 6
		_place(value, "skills", "top_right", Vector2(-4, 320))
		value.parts.skills.scale = 0.7
		_place(value, "clock", "bottom_right", Vector2(-4, -60))
		value.parts.clock.scale = 0.6
		_place(value, "compass", "bottom_right", Vector2(-4, -4))
		value.parts.compass.scale = 0.5
		value.parts.logo.enabled = true
		_place(value, "logo", "top_right", Vector2(-4, 4))
		value.parts.logo.scale = 0.6
		value.parts.fps.enabled = true
		_place(value, "fps", "top_right", Vector2(-100, 4))
		value.parts.resources.dimensions = Vector2(1080, 34)
		value.parts.resources.frame_style = "floating"
		_place(value, "resources", "bottom_left", Vector2(4, -40))
		value.parts.utilities.scale = 1.0
		value.parts.status.enabled = false
	elif id == "classic":
		_place(value, "system_chat", "bottom_left", Vector2(12, -322))
		value.parts.player_card.enabled = true
		_place(value, "player_card", "top_left", Vector2(12, 12))
		_place(value, "party", "top_left", Vector2(12, 130))
		value.parts.party.show_self = false
		value.parts.minimap.scale = 0.72
		value.parts.objectives.enabled = true
		_place(value, "objectives", "top_right", Vector2(-12, 220))
		value.parts.objectives.dimensions = Vector2(260, 100)
		_place(value, "spells", "bottom_right", Vector2(-12, -142))
		_place(value, "items", "bottom_right", Vector2(-12, -80))
		value.parts.spells.scale = 0.85
		value.parts.items.scale = 0.85
		value.parts.compass.scale = 0.7
		_place(value, "compass", "bottom_right", Vector2(-12, -220))
		value.parts.resources.dimensions = Vector2(1080, 34)
		_place(value, "resources", "bottom_left", Vector2(12, -46))
		value.parts.utilities.scale = 0.85
	elif id == "modular":
		for field: String in BANNER_FIELDS: value.banner_options[field] = field == "show_names"
		value.parts.chat.frame_style = "panel"
		value.parts.resources.dimensions = Vector2(510, 76)
		value.parts.resources.orientation = "horizontal"
		value.parts.resources.rows = 2
		value.parts.resources.frame_style = "floating"
		value.meters = {"health":true, "mana":true, "food":true, "load":true, "action":true, "experience":false}
		value.meter_order = ["health", "mana", "action", "food", "load", "experience"]
		_place(value, "resources", "bottom_center", Vector2(0, -154))
		value.parts.spells.slots = 8
		value.parts.spells.scale = 0.95
		value.parts.items.scale = 0.95
		_place(value, "spells", "bottom_center", Vector2(0, -94))
		_place(value, "items", "bottom_center", Vector2(0, -34))
		value.parts.xp_meter.enabled = true
		value.parts.minimap.scale = 0.72
		_place(value, "objectives", "top_right", Vector2(-12, 220))
		value.parts.objectives.dimensions = Vector2(260, 100)
		_show_icons(value, ["InventoryButton", "StatsButton", "AttackButton", "ManufacturingButton", "QuestButton", "EncyclopediaButton", "OptionsButton"])
		value.parts.utilities.rows = 1
		value.parts.utilities.scale = 1
	elif id == "adventure":
		value.parts.minimap.map_palette = "parchment"
		value.parts.chat.dimensions = Vector2(330, 200)
		value.parts.chat.offset.y = -150
		value.parts.spells.scale = 1.1
		value.parts.items.scale = 1.1
		value.parts.medallion.show_labels = false
		_place(value, "system_chat", "bottom_left", Vector2(12, -330))
		_place(value, "medallion", "bottom_center", Vector2(0, -40))
		value.parts.resources.frame_style = "floating"
		_place(value, "food_meter", "bottom_left", Vector2(12, -8))
		_place(value, "load_meter", "bottom_right", Vector2(-12, -8))
		value.parts.food_meter.enabled = true
		value.parts.load_meter.enabled = true
		_place(value, "minimap", "bottom_right", Vector2(-12, -100))
		_place(value, "objectives", "top_right", Vector2(-12, 12))
		value.parts.objectives.dimensions = Vector2(270, 110)
		_place(value, "utilities", "bottom_right", Vector2(-12, -62))
		value.parts.utilities.rows = 1
		value.parts.utilities.scale = 0.9
		_show_icons(value, ["InventoryButton", "MapButton", "BuddyButton", "OptionsButton"])
	elif id == "minimal":
		value.parts.minimap.map_palette = "muted"
		value.parts.spells.show_badges = false
		value.parts.spells.frame_style = "floating"
		value.parts.items.frame_style = "floating"
		value.parts.target.enabled = false
		value.parts.logo.enabled = true
		value.parts.logo.scale = 0.35
		_place(value, "logo", "top_left", Vector2(12, 4))
		_place(value, "party", "top_left", Vector2(12, 42))
		value.parts.chat.frame_style = "floating"
		value.parts.chat.dimensions = Vector2(350, 190)
		_place(value, "chat", "bottom_left", Vector2(12, -16))
		value.parts.resources.dimensions = Vector2(470, 58)
		value.parts.resources.rows = 2
		value.parts.resources.show_values = true
		value.parts.resources.frame_style = "floating"
		value.meters = {"health":true, "mana":true, "action":true, "food":false, "load":false, "experience":false}
		value.meter_order = ["health", "mana", "action", "food", "load", "experience"]
		_place(value, "resources", "bottom_center", Vector2(0, -112))
		value.parts.spells.slots = 4
		value.parts.items.slots = 4
		value.parts.spells.scale = 1.1
		value.parts.items.scale = 1.1
		_place(value, "spells", "bottom_center", Vector2(-100, -30))
		value.parts.xp_meter.enabled = true
		for key: String in ["food_meter", "load_meter"]:
			value.parts[key].enabled = true
			value.parts[key].dimensions = Vector2(130, 46)
		_place(value, "food_meter", "bottom_center", Vector2(-310, -112))
		_place(value, "load_meter", "bottom_center", Vector2(310, -112))
		_place(value, "objectives", "top_right", Vector2(-12, 220))
		value.parts.objectives.frame_style = "floating"
		value.parts.objectives.dimensions = Vector2(260, 100)
		value.parts.utilities.frame_style = "floating"
		value.parts.utilities.rows = 1
		value.parts.utilities.scale = 0.9
		_show_icons(value, ["InventoryButton", "StatsButton", "ManufacturingButton", "QuestButton", "MapButton", "OptionsButton"])
	return _connected_defaults(value, id)

static func _show_icons(value: Dictionary, visible: Array) -> void:
	value.icons["__default"] = false
	for key: String in ["WalkButton", "SitButton", "MountsButton", "LookButton", "TradeButton", "AttackButton", "InventoryButton", "SpellsButton", "ManufacturingButton", "EmotesButton", "QuestButton", "MapButton", "InfoButton", "BuddyButton", "StatsButton", "KnowledgeButton", "ConsoleButton", "HelpButton", "EncyclopediaButton", "RangingButton", "MinimapButton", "OptionsButton", "ChatButton", "DisconnectButton"]:
		value.icons[key] = key in visible

static func _dock(value: Dictionary, key: String, target: String, side: String, alignment := "center", gap := 0.0) -> void:
	value.parts[key].dock_target = target
	value.parts[key].dock_side = side
	value.parts[key].dock_align = alignment
	value.parts[key].dock_gap = gap
	value.parts[key].offset = Vector2.ZERO
	value.parts[key].dock_offset = Vector2.ZERO

static func _connected_defaults(value: Dictionary, id: String) -> Dictionary:
	for key: String in ["resources", "food_meter", "load_meter"]: value.parts[key].show_icons = true
	if id == "heritage":
		# A digital clock and one separate compass form the final column.
		value.parts.compass.enabled = true
		for key: String in ["items", "spells"]:
			value.parts[key].orientation = "horizontal"
			value.parts[key].rows = 2
			value.parts[key].columns = 3
			value.parts[key].slots = 6
			value.parts[key].scale = 0.9
			value.parts[key].dimensions = Vector2(144, 100) # 90px tall: resource strip + menu.
		_place(value, "clock", "bottom_right", Vector2.ZERO)
		value.parts.clock.edge_dock = "bottom_right"
		value.parts.clock.clock_mode = "digital"
		value.parts.clock.scale = 0.85
		value.parts.clock.dimensions = Vector2(80, 25.5) / 0.85
		value.parts.compass.scale = 0.5
		value.parts.compass.dimensions = Vector2(80, 64.5) / 0.5
		_dock(value, "compass", "clock", "top", "stretch")
		_dock(value, "items", "clock", "left", "end")
		_dock(value, "spells", "items", "left", "end")
		_dock(value, "skills", "compass", "top", "end", 8)
		value.parts.utilities.dimensions = Vector2(1100, 44)
		_dock(value, "utilities", "spells", "left", "end")
		value.parts.utilities.extend_to_edge = true
		value.parts.resources.dimensions = Vector2(1100, 46)
		_dock(value, "resources", "utilities", "top", "stretch")
		value.parts.resources.frame_style = "panel"
		value.parts.party.show_player_details = true
		value.parts.party.enabled = true
		value.parts.party.frame_style = "floating"
		value.parts.party.dimensions = Vector2(220, 271)
		_place(value, "party", "top_left", Vector2(6, 6))
		value.parts.chat.dimensions = Vector2(490, 190)
		_dock(value, "chat", "party", "bottom", "start", 12)
		for key: String in PARTS: value.parts[key].hud_border_style = "beveled"
		value.parts.compass.hud_border_style = "ornate"
		value.parts.minimap.hud_border_style = "ornate"
		value.meter_order = ["health", "mana", "food", "action", "load", "experience"]
		value.banner_options.banner_background = true
	elif id == "classic":
		value.parts.items.edge_dock = "bottom_right"
		value.parts.utilities.scale = 1
		value.parts.utilities.dimensions = Vector2(900, 42)
		_dock(value, "utilities", "items", "left", "end")
		value.parts.utilities.extend_to_edge = true
		value.parts.resources.dimensions = Vector2(900, 46)
		_dock(value, "resources", "utilities", "top", "stretch")
		_dock(value, "spells", "items", "top", "end", 8)
		_dock(value, "compass", "spells", "top", "end", 12)
		_dock(value, "party", "player_card", "bottom", "start", 10)
	elif id == "modular":
		value.parts.xp_meter.edge_dock = "bottom"
		_dock(value, "items", "xp_meter", "top", "center", 8)
		_dock(value, "spells", "items", "top", "stretch", 4)
		_dock(value, "resources", "spells", "top", "center", 12)
		value.parts.utilities.edge_dock = "bottom_right"
	elif id == "adventure":
		value.parts.resources.edge_dock = "bottom"
		value.parts.food_meter.edge_dock = "bottom_left"
		value.parts.load_meter.edge_dock = "bottom_right"
		value.parts.utilities.dimensions = Vector2(220, 42)
		value.parts.minimap.dimensions = Vector2.ONE * 220 / float(value.parts.minimap.scale)
		_dock(value, "utilities", "load_meter", "top", "stretch", 8)
		_dock(value, "minimap", "utilities", "top", "stretch", 6)
	elif id == "minimal":
		value.parts.xp_meter.edge_dock = "bottom"
		value.parts.utilities.edge_dock = "bottom_right"
		_dock(value, "resources", "spells", "top", "start", 12)
		value.parts.resources.dock_offset.x = -20
		_dock(value, "food_meter", "resources", "left", "center", 12)
		_dock(value, "load_meter", "resources", "right", "center", 12)
	if id in ["classic", "modular", "minimal"]:
		_dock(value, "objectives", "minimap", "bottom", "end", 12)
	for key: String in PARTS:
		value.parts[key].show_background = value.parts[key].frame_style != "floating"
		value.parts[key].show_border = value.parts[key].frame_style != "floating"
	return value

static func default_arcs() -> Array:
	var result: Array = []
	for index: int in 8:
		var resource: String = ["mana", "action", "mount_stamina", "health", "food", "load", "action", "mount_stamina"][index]
		result.append({"enabled": index in [0, 4], "resource": resource, "color": RESOURCE_COLORS[resource],
			"radius_offset": 0.0, "thickness": 5.0, "start_angle": 100.0 if index < 4 else 15.0, "sweep_angle": 65.0})
	return result

static func _place(value: Dictionary, part: String, anchor: String, offset: Vector2) -> void:
	value.parts[part].anchor = anchor
	value.parts[part].offset = offset

static func _number(value: Variant, fallback: float, low: float, high: float) -> float:
	if not (value is float or value is int): return fallback
	return clampf(float(value), low, high) if is_finite(float(value)) else fallback

static func normalise(raw: Variant) -> Dictionary:
	var result := preset("current")
	if not raw is Dictionary or int(raw.get("version", 0)) != VERSION: return result
	result.legacy = raw.get("legacy", false) == true
	if not raw.has("banner_options"): result.banner_options = {}
	var parts: Variant = raw.get("parts", {})
	if parts is Dictionary:
		for key: String in PARTS:
			var input: Variant = parts.get(key, {})
			if not input is Dictionary: continue
			var part: Dictionary = result.parts[key]
			part.enabled = input.get("enabled", part.enabled) == true
			part.anchor = input.get("anchor", "original") if input.get("anchor", "original") in ANCHORS else "original"
			part.style = input.get("style", "current") if input.get("style", "current") in STYLES else "current"
			part.orientation = "vertical" if input.get("orientation") == "vertical" else "horizontal"
			part.rows = int(_number(input.get("rows"), 1, 1, 32 if key == "utilities" else (12 if key == "spells" else 8)))
			part.columns = int(_number(input.get("columns"), 0, 0, 32 if key == "utilities" else (12 if key == "spells" else 8)))
			part.grid_mode = "aspect" if input.get("grid_mode") == "aspect" else "fixed"
			part.slots = int(_number(input.get("slots"), 8 if key == "items" else 6, 1, 12 if key == "spells" else 8))
			part.scale = _number(input.get("scale"), 1, 0.5, 2.0)
			var axes: Variant = input.get("axis_scale", Vector2.ONE)
			if axes is Vector2 and axes.is_finite() and key != "medallion": part.axis_scale = axes.clamp(Vector2.ONE * 0.25, Vector2.ONE * 4)
			for field: String in ["background_color", "border_color", "text_color", "center_color", "slot_border_color"]:
				if input.get(field) is Color:
					var color: Color = input[field]
					if is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a): part[field] = color.clamp()
			for field: String in ["show_values", "show_labels"]: part[field] = input.get(field, true) == true
			part.show_icons = input.get("show_icons", false) == true
			part.compact = input.get("compact", false) == true
			part.full_height = input.get("full_height", false) == true
			part.hide_with_stats = input.get("hide_with_stats", false) == true
			part.frame_style = "floating" if input.get("frame_style") == "floating" else "panel"
			part.show_background = input.get("show_background", part.frame_style != "floating") == true
			part.show_border = input.get("show_border", part.frame_style != "floating") == true
			# Earlier XP-strip defaults baked transparency into the colors even
			# after the player enabled its HUD frame. Repair that one-time case;
			# current layouts retain explicitly chosen zero opacity on reload.
			if int(raw.get("frame_alpha_version", 0)) == 0 and part.frame_style == "panel":
				if part.show_background and part.background_color.a == 0: part.background_color.a = 0.93
				if part.show_border and part.border_color.a == 0: part.border_color.a = 1.0
			part.clock_mode = input.get("clock_mode", "both") if input.get("clock_mode", "both") in ["dial", "digital", "both"] else "both"
			part.hud_border_style = input.get("hud_border_style", "plain") if input.get("hud_border_style") in HUD_BORDERS else "plain"
			part.slot_border_style = input.get("slot_border_style", "match_hud") if input.get("slot_border_style") in ["match_hud", "none", "beveled", "ornate"] else "match_hud"
			part.icon_opacity = _number(input.get("icon_opacity"), 1.0, 0, 1)
			part.unavailable_icon_opacity = _number(input.get("unavailable_icon_opacity"), 1.0, 0, 1)
			part.flush_slots = input.get("flush_slots", false) == true
			part.slot_gap = _number(input.get("slot_gap"), 2.0, 0, 12)
			part.frame_shape = input.get("frame_shape", "match_map") if input.get("frame_shape") in ["match_map", "circle", "rectangle"] else "match_map"
			part.compass_corners = input.get("compass_corners", "fill_when_docked") if input.get("compass_corners", "fill_when_docked") in ["transparent", "fill_when_docked", "filled"] else "fill_when_docked"
			part.show_secondary = input.get("show_secondary", true) == true
			part.show_self = input.get("show_self", true) == true
			part.show_player_details = input.get("show_player_details", false) == true
			part.show_badges = input.get("show_badges", true) == true
			var meter_keys: Variant = input.get("meter_keys", [])
			if meter_keys is Array:
				for meter: Variant in meter_keys:
					if meter in ["health", "mana", "food", "load", "action", "experience"] and meter not in part.meter_keys: part.meter_keys.append(meter)
			part.dock_target = input.get("dock_target", "none") if input.get("dock_target") in PARTS and input.get("dock_target") != key else "none"
			if key == "nameplate" or part.dock_target == "nameplate": part.dock_target = "none"
			part.dock_side = input.get("dock_side", "right") if input.get("dock_side", "right") in ["left", "right", "top", "bottom"] else "right"
			part.dock_gap = _number(input.get("dock_gap"), 0, -16, 100)
			part.dock_align = input.get("dock_align", "center") if input.get("dock_align") in ["start", "center", "end", "stretch"] else "center"
			part.extend_to_edge = input.get("extend_to_edge", false) == true
			part.edge_dock = input.get("edge_dock", "none") if input.get("edge_dock") in ["left", "right", "top", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"] else "none"
			part.compass_mode = "ribbon" if input.get("compass_mode") == "ribbon" else "round"
			part.map_shape = "round" if input.get("map_shape") == "round" else "square"
			part.map_title = input.get("map_title", false) == true
			part.map_directions = input.get("map_directions", "all") if input.get("map_directions", "all") in ["all", "north", "none"] else "all"
			part.direction_offset = _number(input.get("direction_offset"), -9, -48, 120)
			part.north_marker = "arrow" if input.get("north_marker") == "arrow" else "letter"
			part.map_label_frame = input.get("map_label_frame", false) == true
			part.map_palette = input.get("map_palette", "natural") if input.get("map_palette") in ["natural", "parchment", "muted"] else "natural"
			part.load_display = "carried" if input.get("load_display") == "carried" else "free"
			part.center_resource = input.get("center_resource", "health") if input.get("center_resource", "health") in RESOURCES else "health"
			part.border_design = input.get("border_design", "plain") if input.get("border_design", "plain") in BORDERS else "plain"
			var arcs: Variant = input.get("arcs", [])
			if arcs is Array:
				for index: int in mini(8, arcs.size()):
					if not arcs[index] is Dictionary: continue
					var arc: Dictionary = arcs[index]
					part.arcs[index].enabled = arc.get("enabled", false) == true
					part.arcs[index].resource = arc.get("resource") if arc.get("resource") in RESOURCES else "mana"
					part.arcs[index].radius_offset = _number(arc.get("radius_offset"), 0, -30, 96)
					part.arcs[index].thickness = _number(arc.get("thickness"), 5, 2, 16)
					part.arcs[index].start_angle = _number(arc.get("start_angle"), 100 if index < 4 else 15, -360, 360)
					part.arcs[index].sweep_angle = _number(arc.get("sweep_angle"), 65, 10, 180)
					if arc.get("color") is Color:
						var color: Color = arc.color
						if is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a): part.arcs[index].color = color.clamp()
			for field: String in ["offset", "dock_offset", "position", "dimensions"]:
				var vector: Variant = input.get(field)
				if vector is Vector2 and vector.is_finite():
					part[field] = vector.clamp(Vector2.ONE * (-4096 if field in ["offset", "dock_offset"] else (-1 if field == "position" else 0)), Vector2.ONE * (2 if field == "position" else 4096))
	# Reject cycles, including indirect ones, before any recursive docking pass.
	for key: String in PARTS:
		var seen: Array = [key]
		var target: String = result.parts[key].dock_target
		while target != "none":
			if target in seen:
				result.parts[key].dock_target = "none"
				break
			seen.append(target)
			target = result.parts[target].dock_target
	for field: String in ["icons", "meters", "banner_options"]:
		var flags: Variant = raw.get(field, {})
		if flags is Dictionary:
			for key: Variant in flags:
				if key is String and key.length() < 80 and flags[key] is bool:
					result[field][key] = flags[key]
	var colors: Variant = raw.get("resource_colors", {})
	if colors is Dictionary:
		for key: String in RESOURCE_COLORS:
			if colors.get(key) is Color:
				var color: Color = colors[key]
				if is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a): result.resource_colors[key] = color.clamp()
	var order: Variant = raw.get("meter_order", [])
	if order is Array:
		for key: Variant in order:
			if key in ["mana", "food", "health", "load", "action", "experience"] and key not in result.meter_order:
				result.meter_order.append(key)
	var windows: Variant = raw.get("chat_windows", {})
	var native_bar: Variant = raw.get("native_spell_bar", {})
	if native_bar is Dictionary and not native_bar.is_empty():
		result.native_spell_bar = {"docked": native_bar.get("docked", true) == true,
			"horizontal": native_bar.get("horizontal", false) == true,
			"expanded": native_bar.get("expanded", true) == true,
			"slot_count": int(_number(native_bar.get("slot_count"), 6, 1, 12))}
		if native_bar.get("position") is Vector2 and native_bar.position.is_finite():
			result.native_spell_bar.position = native_bar.position.clamp(Vector2.ZERO, Vector2(4096, 4096))
	if windows is Dictionary:
		for key: String in ["chat", "system_chat"]:
			var window: Variant = windows.get(key, {})
			if not window is Dictionary: continue
			var saved := {}
			var dimensions: Variant = window.get("size")
			if dimensions is Vector2 and dimensions.is_finite():
				saved.size = dimensions.clamp(Vector2(280, 95), Vector2(1600, 1000))
			var options: Variant = window.get("options", {})
			if options is Dictionary:
				saved.options = {}
				for field: String in ["visible", "combined", "locked"]:
					if options.get(field) is bool: saved.options[field] = options[field]
				for field: String in ["font_size", "background_opacity", "line_spacing", "idle_fade"]:
					if options.get(field) is float or options.get(field) is int:
						saved.options[field] = _number(options[field], 0, 0, 120)
			result.chat_windows[key] = saved
	return result

func load_file(path: String) -> void:
	var config := ConfigFile.new()
	if config.load(path) != OK or not config.has_section_key(SECTION, "working"): return
	var raw: Variant = config.get_value(SECTION, "working")
	if not raw is Dictionary or raw.get("version") != VERSION: return
	working = normalise(raw)
	var entries: Variant = config.get_value(SECTION, "custom", {})
	if entries is Dictionary:
		for key: Variant in entries:
			if custom.size() >= 24: break
			if not key is String or not key.begins_with("custom_") or not entries[key] is Dictionary: continue
			var entry: Dictionary = entries[key]
			if not entry.get("layout") is Dictionary or entry.layout.get("version") != VERSION: continue
			custom[key] = {"name": str(entry.get("name", "My HUD")).strip_edges().left(48), "layout": normalise(entry.layout)}
	active = str(config.get_value(SECTION, "active", "current"))
	if not BUILT_INS.has(active) and not custom.has(active): active = "current"
	var saved: Variant = config.get_value(SECTION, "builtin_overrides", {})
	if saved is Dictionary:
		for id: String in BUILT_INS:
			if saved.get(id) is Dictionary and saved[id].get("version") == VERSION: builtin_overrides[id] = normalise(saved[id])
	if BUILT_INS.has(active): builtin_overrides[active] = working.duplicate(true)
	loaded = true
	var editor: Variant = config.get_value(SECTION, "editor_position", Vector2(-1, -1))
	if editor is Vector2 and editor.is_finite(): editor_position = editor

func save_file(path: String) -> Error:
	var config := ConfigFile.new()
	config.load(path)
	config.set_value(SECTION, "working", normalise(working))
	config.set_value(SECTION, "custom", custom)
	config.set_value(SECTION, "active", active)
	if BUILT_INS.has(active): builtin_overrides[active] = normalise(working)
	config.set_value(SECTION, "builtin_overrides", builtin_overrides)
	config.set_value(SECTION, "editor_position", editor_position)
	return config.save(path)

func select(id: String, factory_default := false) -> void:
	if BUILT_INS.has(id): working = preset(id) if factory_default or not builtin_overrides.has(id) else normalise(builtin_overrides[id])
	elif custom.has(id): working = normalise(custom[id].layout)
	else: return
	active = id

func save_custom(label: String, replace_id := "") -> String:
	if custom.size() >= 24 and not custom.has(replace_id): return ""
	var id := replace_id if custom.has(replace_id) else "custom_%d_%d" % [Time.get_unix_time_from_system(), Time.get_ticks_usec()]
	var title := label.strip_edges().left(48)
	custom[id] = {"name": title if not title.is_empty() else "My HUD", "layout": normalise(working)}
	active = id
	return id
