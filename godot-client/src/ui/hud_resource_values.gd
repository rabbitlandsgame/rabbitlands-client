extends RefCounted
## Read the same authoritative values as the original HUD.
const LABELS := {"health":"Health", "mana":"Ether", "food":"Food", "action":"Action", "mount_stamina":"Mount stamina", "load":"Load"}

static func read(resource: String) -> Dictionary:
	var stats: Dictionary = AppState.stats
	var value := 0.0
	var maximum := 1.0
	var available := true
	match resource:
		"health":
			value = float(stats.get("health", 0))
			maximum = float(stats.get("max_health", 1))
		"mana":
			value = float(stats.get("ether", 0))
			maximum = float(stats.get("max_ether", 1))
		"food":
			value = float(stats.get("food", 0))
			maximum = maxf(45, value)
		"action":
			var pool: Dictionary = AppState.techniques if AppState.techniques.has("action_points") else stats
			value = float(pool.get("action_points", 0))
			maximum = float(pool.get("max_action_points", 1))
		"load":
			value = float(stats.get("carried", 0))
			maximum = float(stats.get("capacity", 1))
		"mount_stamina":
			var mount: Dictionary = AppState.mount_state_for_actor(AppState.local_actor_id)
			available = mount.get("mode", "on_foot") == "mounted"
			value = float(mount.get("endurance_ms", 0)) / 1000.0
			maximum = 8.0 # Full gallop endurance, as in the existing mount control.
	return {"value":value, "maximum":maxf(1, maximum), "available":available,
		"ratio":clampf(value / maxf(1, maximum), 0, 1) if available else 0.0, "label":LABELS.get(resource, "Resource")}

static func value_text(data: Dictionary) -> String:
	if not data.available: return "—"
	return ("%.1f / %.1f" if data.label == "Mount stamina" else "%d / %d") % [data.value, data.maximum]
