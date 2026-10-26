extends RefCounted
## Local layout preferences. Recipe identity and manufacture actions stay server-owned.
const SECTION := "mixing_designs"
const VERSION := 1
const DEFAULT := "workbench"
const MAX_CUSTOM := 5
const BUILT_INS := {"workbench": "Compact workbench", "tabbed": "Tabbed fieldbook", "dock": "Narrow edge dock", "popover": "Quick-mix popover", "tray": "Shallow mixing tray"}
const PARTS := {"recipes": "Recipe browser", "details": "Recipe and requirements", "controls": "Source and quantity", "actions": "Mix actions", "queue": "Production queue", "status": "Result preview"}
var active := DEFAULT
var working := preset(DEFAULT)
var custom: Dictionary = {}
var overrides: Dictionary = {}

static func preset(id: String) -> Dictionary:
	if not BUILT_INS.has(id): id = DEFAULT
	var result := {"version": VERSION, "recipe": id, "anchor": "right", "position": Vector2(0.77, 0.3), "scale": 1.0,
		"font_size": 12, "background": Color("12120ff5"), "border": Color("806c40"), "text": Color("eee3c8"), "border_style": "beveled",
		"queue_expanded": id in ["dock", "tray"], "show_requirements": false, "parts": {}}
	var geometry := {"recipes": Rect2(8, 36, 104, 176), "details": Rect2(120, 36, 204, 176), "controls": Rect2(8, 220, 316, 26),
		"actions": Rect2(8, 270, 316, 28), "queue": Rect2(8, 306, 316, 28), "status": Rect2(8, 249, 316, 18)}
	match id:
		"tabbed":
			geometry = {"recipes": Rect2(8, 65, 248, 168), "details": Rect2(8, 65, 248, 168), "controls": Rect2(8, 254, 248, 52),
				"actions": Rect2(8, 312, 248, 27), "queue": Rect2(8, 346, 248, 28), "status": Rect2(8, 236, 248, 16)}
		"dock":
			geometry = {"recipes": Rect2(8, 36, 224, 110), "details": Rect2(8, 151, 224, 145), "controls": Rect2(8, 302, 224, 52),
				"actions": Rect2(8, 361, 224, 27), "status": Rect2(8, 392, 224, 18), "queue": Rect2(8, 416, 224, 105)}
		"popover":
			result.anchor = "bottom_right"
			geometry = {"recipes": Rect2(8, 36, 264, 158), "details": Rect2(8, 36, 264, 158), "controls": Rect2(8, 218, 264, 26),
				"actions": Rect2(8, 250, 264, 27), "queue": Rect2(8, 284, 264, 28), "status": Rect2(8, 198, 264, 17)}
		"tray":
			result.anchor = "bottom_right"
			geometry = {"recipes": Rect2(8, 33, 186, 178), "details": Rect2(202, 33, 318, 122), "controls": Rect2(202, 158, 318, 26),
				"actions": Rect2(202, 185, 318, 28), "queue": Rect2(528, 33, 204, 178), "status": Rect2(202, 218, 318, 18)}
	for key: String in PARTS:
		result.parts[key] = {"enabled": true, "offset": Vector2.ZERO, "dimensions": geometry[key].size, "position": geometry[key].position}
	if id == "tray": result.parts.status.enabled = false
	return result

static func normalise(raw: Variant) -> Dictionary:
	if not raw is Dictionary: return preset(DEFAULT)
	var result := preset(str(raw.get("recipe", DEFAULT)))
	for key: String in ["anchor", "border_style"]:
		var allowed: Array = ["right", "bottom_right", "bottom_center", "free"] if key == "anchor" else ["plain", "beveled", "ornate"]
		if raw.get(key) in allowed: result[key] = raw[key]
	for key: String in ["background", "border", "text"]:
		var color: Variant = raw.get(key)
		if color is Color and is_finite(color.r) and is_finite(color.g) and is_finite(color.b) and is_finite(color.a):
			result[key] = Color(clampf(color.r, 0, 1), clampf(color.g, 0, 1), clampf(color.b, 0, 1), clampf(color.a, 0, 1))
	result.scale = _number(raw.get("scale"), 1, 0.75, 1.75)
	result.font_size = roundi(_number(raw.get("font_size"), 12, 11, 20))
	var point: Variant = raw.get("position")
	if point is Vector2 and point.is_finite(): result.position = point.clamp(Vector2.ZERO, Vector2.ONE)
	for key: String in ["queue_expanded", "show_requirements"]: result[key] = raw.get(key, result[key]) == true
	var parts: Variant = raw.get("parts", {})
	if parts is Dictionary:
		for key: String in PARTS:
			var part: Variant = parts.get(key, {})
			if not part is Dictionary: continue
			result.parts[key].enabled = true if key in ["controls", "actions"] else part.get("enabled", true) == true
			for field: String in ["offset", "dimensions"]:
				point = part.get(field)
				if point is Vector2 and point.is_finite():
					result.parts[key][field] = point.clamp(Vector2(-600, -400), Vector2(1000, 800)) if field == "offset" else point.clamp(Vector2(100, 12 if key == "status" else 18), Vector2(1000, 650))
	return result

static func _number(value: Variant, fallback: float, low: float, high: float) -> float:
	return clampf(float(value), low, high) if (value is int or value is float) and is_finite(float(value)) else fallback

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
	custom[id] = {"name": title.strip_edges().left(48) if not title.strip_edges().is_empty() else "My mixing design", "layout": normalise(working)}
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
	var stored: Variant = config.get_value(SECTION, "custom", {})
	if stored is Dictionary:
		for id: Variant in stored:
			if custom.size() >= MAX_CUSTOM: break
			if id is String and id.begins_with("custom_") and stored[id] is Dictionary and stored[id].get("layout") is Dictionary:
				custom[id] = {"name": str(stored[id].get("name", "My mixing design")).left(48), "layout": normalise(stored[id].layout)}
	stored = config.get_value(SECTION, "overrides", {})
	if stored is Dictionary:
		for id: String in BUILT_INS:
			if stored.get(id) is Dictionary: overrides[id] = normalise(stored[id])
	var selected := str(config.get_value(SECTION, "active", DEFAULT))
	active = selected if BUILT_INS.has(selected) or custom.has(selected) else DEFAULT
	working = normalise(config.get_value(SECTION, "working", preset(DEFAULT))) if active == selected else preset(DEFAULT)
