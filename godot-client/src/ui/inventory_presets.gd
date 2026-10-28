extends RefCounted
## Local presentation only. Inventory positions and item identity stay server-owned.
const SECTION := "inventory_designs"
const VERSION := 1
const DEFAULT := "unified"
const MAX_CUSTOM := 5
const BUILT_INS := {"unified": "Unified compact", "tabbed": "Tabbed satchel",
	"dock": "Edge dock", "popover": "Adaptive inspect", "tray": "Shallow bottom tray"}
const PARTS := {"backpack": "Backpack", "equipment": "Equipment", "pouch": "Pouch", "preview": "Text preview", "inspection": "Inspection", "actions": "Action bar"}
const PLACEMENTS := ["inline", "replace", "side", "popover"]
var active := DEFAULT
var working := preset(DEFAULT)
var custom: Dictionary = {}
var overrides: Dictionary = {}

static func preset(id: String) -> Dictionary:
	if not BUILT_INS.has(id): id = DEFAULT
	var result := {"version": VERSION, "recipe": id, "anchor": "right", "position": Vector2(0.75, 0.25),
		"scale": 1.0, "gap": 3, "font_size": 13, "background": Color("100f0df5"),
		"border": Color("9d8150"), "text": Color("eee3c8"), "border_style": "beveled",
		"equipment_side": "left", "inspection_mode": "inline", "parts": {}}
	for key: String in PARTS:
		result.parts[key] = {"enabled": true, "offset": Vector2.ZERO, "cell": 36, "columns": 6,
			"height": 48, "width": 250, "show_quantity": true, "icon_opacity": 1.0}
	result.parts.equipment.columns = 2
	result.parts.pouch.columns = 4
	result.parts.pouch.cell = 52
	result.parts.inspection.height = 150
	result.parts.inspection.width = 250
	result.parts.actions.columns = 3
	for action: String in ["store", "get", "drop", "mix", "lists"]:
		result.parts.actions["show_" + action] = true
	if id in ["unified", "tabbed", "dock"]:
		for action: String in ["store", "drop", "mix"]:
			result.parts.actions["show_" + action] = false
		result.parts.actions.columns = 2
	result["show_description"] = true
	result["show_stats"] = true
	result["show_comparison"] = true
	match id:
		"tabbed":
			result.inspection_mode = "replace"
			result.parts.backpack.cell = 48
			result.parts.equipment.cell = 48
		"dock":
			result.equipment_side = "top"
			result.parts.equipment.columns = 4
			result.parts.backpack.cell = 60
			result.parts.backpack.columns = 8
			result.parts.equipment.cell = 44
			result.anchor = "right"
		"popover": result.inspection_mode = "popover"
		"tray":
			result.parts.pouch.columns = 8
			result.parts.backpack.columns = 12
			result.parts.backpack.cell = 32
			result.parts.equipment.cell = 32
			result.parts.equipment.columns = 4
			result.inspection_mode = "side"
			result.parts.inspection.width = 226
			result.parts.inspection.height = 190
			result.anchor = "bottom_right"
	return result

static func number(value: Variant, fallback: float, low: float, high: float) -> float:
	return clampf(float(value), low, high) if (value is int or value is float) and is_finite(float(value)) else fallback

static func normalise(raw: Variant) -> Dictionary:
	if not raw is Dictionary: return preset(DEFAULT)
	var result := preset(str(raw.get("recipe", DEFAULT)))
	for key: String in ["anchor", "equipment_side", "inspection_mode", "border_style"]:
		var allowed: Array = {"anchor": ["right", "bottom_right", "bottom_center", "free"],
			"equipment_side": ["left", "right", "top"], "inspection_mode": PLACEMENTS,
			"border_style": ["plain", "beveled", "ornate"]}[key]
		if raw.get(key) in allowed: result[key] = raw[key]
	for key: String in ["background", "border", "text"]:
		var color: Variant = raw.get(key)
		if color is Color and is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a):
			result[key] = Color(clampf(color.r, 0, 1), clampf(color.g, 0, 1), clampf(color.b, 0, 1), clampf(color.a, 0, 1))
	result.scale = number(raw.get("scale"), 1, 0.75, 1.75)
	result.gap = roundi(number(raw.get("gap"), 3, 0, 10))
	result.font_size = roundi(number(raw.get("font_size"), 13, 11, 20))
	var position: Variant = raw.get("position")
	if position is Vector2 and position.is_finite(): result.position = position.clamp(Vector2.ZERO, Vector2.ONE)
	for key: String in ["show_description", "show_stats", "show_comparison"]:
		result[key] = raw.get(key, true) == true
	var parts: Variant = raw.get("parts", {})
	if not parts is Dictionary: return result
	for key: String in PARTS:
		var input: Variant = parts.get(key, {})
		if not input is Dictionary: continue
		var part: Dictionary = result.parts[key]
		part.enabled = true if key == "backpack" else input.get("enabled", part.enabled) == true
		part.cell = roundi(number(input.get("cell"), part.cell, 52 if key == "pouch" else 28, 80 if key == "pouch" else 64))
		part.columns = roundi(number(input.get("columns"), part.columns, 1, 12 if key == "backpack" else 8))
		part.height = roundi(number(input.get("height"), part.height, 140 if key == "inspection" else 32, 400))
		part.width = roundi(number(input.get("width"), part.width, 200, 500))
		part.show_quantity = input.get("show_quantity", true) == true
		part.icon_opacity = number(input.get("icon_opacity"), 1, 0.25, 1)
		if key == "actions":
			part.columns = clampi(part.columns, 1, 5)
			for action: String in ["store", "get", "drop", "mix", "lists"]:
				part["show_" + action] = input.get("show_" + action, part["show_" + action]) == true
		var offset: Variant = input.get("offset")
		if offset is Vector2 and offset.is_finite(): part.offset = offset.clamp(Vector2(-500, -300), Vector2(800, 500))
	return result

func snapshot() -> Dictionary:
	return {"active": active, "working": working.duplicate(true), "custom": custom.duplicate(true), "overrides": overrides.duplicate(true)}

func restore(value: Dictionary) -> void:
	active = value.active
	working = normalise(value.working)
	custom = value.custom.duplicate(true)
	overrides = value.overrides.duplicate(true)

func select(id: String, factory := false) -> void:
	if not BUILT_INS.has(id) and not custom.has(id): return
	if BUILT_INS.has(active): overrides[active] = working.duplicate(true)
	elif custom.has(active): custom[active].layout = working.duplicate(true)
	active = id
	working = normalise(overrides.get(id, preset(id))) if BUILT_INS.has(id) else normalise(custom[id].layout)
	if factory and BUILT_INS.has(id): working = preset(id)

func save_custom(title: String, replace_id := "") -> String:
	if custom.size() >= MAX_CUSTOM and not custom.has(replace_id): return ""
	var id := replace_id if custom.has(replace_id) else "custom_%d" % Time.get_ticks_usec()
	custom[id] = {"name": title.strip_edges().left(48) if not title.strip_edges().is_empty() else "My inventory", "layout": normalise(working)}
	active = id
	return id

func delete_custom(id: String) -> void:
	if not custom.has(id): return
	custom.erase(id)
	if active == id:
		active = DEFAULT
		working = normalise(overrides.get(DEFAULT, preset(DEFAULT)))

func save_file(path: String) -> Error:
	var config := ConfigFile.new()
	config.load(path)
	if BUILT_INS.has(active): overrides[active] = working.duplicate(true)
	elif custom.has(active): custom[active].layout = working.duplicate(true)
	config.set_value(SECTION, "version", VERSION)
	for key: String in ["active", "working", "custom", "overrides"]: config.set_value(SECTION, key, get(key))
	return config.save(path)

func load_file(path: String) -> void:
	var config := ConfigFile.new()
	if config.load(path) != OK or config.get_value(SECTION, "version", 0) != VERSION: return
	working = normalise(config.get_value(SECTION, "working", {}))
	var stored: Variant = config.get_value(SECTION, "custom", {})
	if stored is Dictionary:
		for id: Variant in stored:
			if custom.size() >= MAX_CUSTOM: break
			if id is String and id.begins_with("custom_") and stored[id] is Dictionary and stored[id].get("layout") is Dictionary:
				custom[id] = {"name": str(stored[id].get("name", "My inventory")).left(48), "layout": normalise(stored[id].layout)}
	stored = config.get_value(SECTION, "overrides", {})
	if stored is Dictionary:
		for id: String in BUILT_INS:
			if stored.get(id) is Dictionary: overrides[id] = normalise(stored[id])
	var selected := str(config.get_value(SECTION, "active", DEFAULT))
	active = selected if BUILT_INS.has(selected) or custom.has(selected) else DEFAULT
