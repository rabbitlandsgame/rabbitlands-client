extends RefCounted

## Local design simulation. No network, production character or live rewards.
## The JSON quest and layout are also the inputs to the authoring checks.
signal changed
var layout: Dictionary
var quest: Dictionary
var state: Dictionary
var message := ""

func _init() -> void:
	layout = JSON.parse_string(FileAccess.get_file_as_string("res://package/layout.json"))
	quest = JSON.parse_string(FileAccess.get_file_as_string("res://package/quest.json"))
	reset()

func reset() -> void:
	state = {"version": 1, "step": 0, "tile": layout.spawn.duplicate(),
		"inventory": {}, "storage": {}, "equipment": [], "flags": {},
		"harvest": {}, "food": 22, "health": 20, "max_health": 20,
		"capacity": 100, "points": 0, "xp": 0, "boar_health": 14,
		"auto_gather": true, "history": [], "attribute": "", "gold": 0}
	message = "A ferry is grounded. A second boat is approaching the reef. The beacon is dark."
	changed.emit()

func current() -> Dictionary:
	if int(state.step) >= quest.steps.size():
		return {"id": "complete", "scene": 8, "target": "ferry", "objective": quest.handoff.objective,
			"hint": "Draft complete. In the game, Ilyon welcomes you to Four Gates.", "voice": ""}
	return quest.steps[int(state.step)]

func target(id: String) -> Dictionary:
	for entry: Dictionary in layout.targets:
		if entry.id == id:
			return entry
	return {}

func count(bag: String, item: String) -> int:
	return int(state[bag].get(item, 0))

func has_flag(key: String) -> bool:
	return bool(state.flags.get(key, false))

func near(id: String) -> bool:
	var t: Dictionary = target(id)
	return not t.is_empty() and Vector2(state.tile[0], state.tile[1]).distance_to(Vector2(t.tile[0], t.tile[1])) <= 4.0

func near_cache() -> bool:
	return near("lower_cache") or near("upper_cache") or near("dock_cache")

func weight() -> int:
	var result := 0
	for item: String in state.inventory:
		result += int(state.inventory[item])
	return result

func move_to(tile: Vector2i) -> void:
	state.tile = [tile.x, tile.y]
	if near("nesh"):
		state.flags.arrived = true
	if near("rest") and has_flag("looted"):
		state.flags.rested = true
	if near("dock") and has_flag("lit"):
		state.flags.returned = true
	advance()

func satisfied(condition: Array) -> bool:
	match str(condition[0]):
		"flag": return has_flag(str(condition[1]))
		"harvest", "storage", "inventory": return count(str(condition[0]), str(condition[1])) >= int(condition[2])
		"equipped": return condition[1] in state.equipment
		"food": return int(state.food) >= int(condition[1])
	return false

func advance() -> void:
	while int(state.step) < quest.steps.size() and satisfied(quest.steps[int(state.step)].condition):
		state.history.append(current().id)
		state.step = int(state.step) + 1
	if "attribute" in state.history:
		state.flags.prepared = true
	changed.emit()

func grant(bag: String, item: String, amount: int) -> void:
	state[bag][item] = count(bag, item) + amount
	if int(state[bag][item]) == 0:
		state[bag].erase(item)

func act(action: String, item := "", amount := 1) -> bool:
	message = ""
	var ok := false
	match action:
		"supply":
			if near("caldus") and has_flag("arrived") and not has_flag("supplied"):
				for name: String in quest.starterKit:
					grant("inventory", name, int(quest.starterKit[name]))
				state.storage = quest.cacheStock.duplicate(true)
				state.flags.supplied = true
				message = "Caldus: Take this. I'll hold the shelter. Bring that light back."
				ok = true
		"chart":
			if near("chart") and has_flag("supplied"):
				state.flags.chart_read = true
				message = "The chart: garden → repair shed → causeway → beacon. An old stair leads down to the eastern dock."
				ok = true
		"map":
			state.flags.map_opened = true
			ok = true
		"harvest":
			var id: String = "reed" if item == "Reed" else "quartz"
			var quota: int = 3 if item == "Reed" else 1
			if item not in ["Reed", "Quartz"]:
				return false
			if near(id) and has_flag("chart_read") and count("harvest", item) < quota:
				if item == "Quartz" and count("inventory", "Pickaxe") < 1:
					message = "Quartz needs the Pickaxe in your pack."
				elif weight() >= int(state.capacity):
					message = "Your pack is full. Make room in the keeper's cache."
				else:
					grant("harvest", item, 1)
					grant("inventory", item, 1)
					state.xp = int(state.xp) + 9
					message = "%s gathered: %d/%d" % [item, count("harvest", item), quota]
					ok = true
		"deposit", "withdraw":
			var source := "inventory" if action == "deposit" else "storage"
			var destination := "storage" if action == "deposit" else "inventory"
			var quantity: int = mini(maxi(0, amount), count(source, item))
			if near_cache() and quantity > 0:
				if action == "withdraw" and weight() + quantity > int(state.capacity):
					message = "Your pack is full. Deposit something first."
				else:
					grant(source, item, -quantity)
					grant(destination, item, quantity)
					message = "%s %d × %s." % ["Stored" if action == "deposit" else "Withdrew", quantity, item]
					ok = true
		"craft":
			if has_flag("crafted"):
				message = "Your torch is ready for the beacon."
			elif count("inventory", "Wood Plank") and count("inventory", "Cloth Roll") and count("inventory", "Hatchet"):
				grant("inventory", "Wood Plank", -1)
				grant("inventory", "Cloth Roll", -1)
				grant("inventory", "Torch", 1)
				state.food = maxi(-45, int(state.food)-1)
				state.xp = int(state.xp) + 5
				state.flags.crafted = true
				message = "Torch made. Nesh steadied the work for this first attempt. The causeway opens."
				ok = true
			else:
				message = "You need 1 Wood Plank, 1 Cloth Roll and a Hatchet in your pack."
		"equip":
			if item in ["Sword", "Shield"] and count("inventory", item) and item not in state.equipment:
				grant("inventory", item, -1)
				state.equipment.append(item)
				message = "%s equipped." % item
				ok = true
		"eat":
			if count("inventory", "Bread"):
				grant("inventory", "Bread", -1)
				state.food = mini(45, int(state.food)+20)
				message = "Bread eaten. Food supports recovery; you can continue without waiting for full health."
				ok = true
		"spend":
			if item in ["Matter", "Carry"] and int(state.points) > 0 and not has_flag("spent"):
				state.points = int(state.points)-1
				state.flags.spent = true
				state.attribute = item
				if item == "Matter":
					state.max_health = int(state.max_health)+5
					state.health = mini(int(state.max_health), int(state.health)+5)
				else:
					state.capacity = int(state.capacity)+10
				message = "%s chosen. This is a permanent build choice in the full game." % item
				ok = true
		"loot":
			if near("bag") and has_flag("defeated") and not has_flag("looted"):
				# A bound quest supply cannot be stranded by a full pack in this draft.
				grant("inventory", "Raw Meat", 1)
				state.flags.looted = true
				message = "Raw Meat acquired. " + ("Auto-gather picked it up for you." if state.auto_gather else "The bag is empty.")
				ok = true
		"repair":
			if near("housing") and has_flag("prepared") and not has_flag("repaired"):
				if count("inventory", "Reed") >= 3 and count("inventory", "Quartz") >= 1:
					grant("inventory", "Reed", -3)
					grant("inventory", "Quartz", -1)
					state.flags.repaired = true
					message = "The shutters hold. Quartz sits in its socket. All it needs is your flame."
					ok = true
				else:
					message = "Bring 3 Reed and 1 Quartz from the lantern cache."
		"light":
			if near("housing") and has_flag("repaired") and count("inventory", "Torch") and not has_flag("lit"):
				state.flags.lit = true
				message = "Your flame reaches across the water. The boat turns clear of the reef. Nesh: There. They see us."
				ok = true
		"sell":
			if near("dock") and has_flag("lit") and not has_flag("sold"):
				if count("inventory", "Raw Meat") >= 1:
					grant("inventory", "Raw Meat", -1)
					state.gold = int(state.gold)+10
					state.flags.sold = true
					message = "Sold 1 Raw Meat for 10 gold. The galley has its meal."
					ok = true
				else:
					message = "Your meat may be in storage. The dock cache shares the keeper's seal."
		"buy":
			if near("dock") and has_flag("sold") and not has_flag("bought") and int(state.gold) >= 8:
				state.gold = int(state.gold)-8
				grant("inventory", "Bread", 1)
				state.flags.bought = true
				message = "Bought Bread for 8 gold. You have 2 gold for the road."
				ok = true
		"depart":
			if near("ferry") and has_flag("bought") and not has_flag("departed"):
				state.flags.departed = true
				state.flags.rewarded = true
				message = "Keeper of the First Light · Next: Talk to Gate Warden Ilyon."
				ok = true
	if not ok and message.is_empty():
		message = "Get closer to the marked target, or finish the current instruction first."
	advance()
	return ok

func can_attack() -> bool:
	return near("boar") and not has_flag("defeated") and "Sword" in state.equipment and "Shield" in state.equipment

func combat_round() -> bool:
	if not can_attack():
		return false
	if int(state.health) <= 4:
		state.health = int(state.max_health)
		state.boar_health = 14
		message = "Nesh pulls you clear. Breathe, then try again. Your equipment and supplies are safe."
		state.tile = [63, 52]
		changed.emit()
		return false
	state.boar_health = maxi(0, int(state.boar_health)-4)
	if int(state.boar_health) == 0:
		state.flags.defeated = true
		state.points = int(state.points)+1
		state.xp = int(state.xp)+75
		message = "The path is clear. You earned a pickpoint."
		if state.auto_gather:
			act("loot")
		advance()
		return false
	state.health = maxi(1, int(state.health)-3)
	message = "You hit the boar. It strikes back. Click the ground to attempt a retreat."
	changed.emit()
	return true

func save(path := "user://lantern-draft.json") -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(state))

func restore(path := "user://lantern-draft.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary or int(parsed.get("version", 0)) != 1:
		return false
	for key: String in state:
		if not parsed.has(key) or typeof(parsed[key]) != typeof(state[key]) and not (typeof(parsed[key]) in [TYPE_FLOAT, TYPE_INT] and typeof(state[key]) in [TYPE_FLOAT, TYPE_INT]):
			return false
	if int(parsed.step) < 0 or int(parsed.step) > quest.steps.size() or parsed.tile.size() != 2:
		return false
	var x := int(parsed.tile[0])
	var y := int(parsed.tile[1])
	if x < 0 or y < 0 or x >= 120 or y >= 120 or int(layout.walkGrid[y*120+x]) == 0:
		return false
	state = parsed
	message = "Welcome back. Your island and current objective are restored."
	advance()
	return true
