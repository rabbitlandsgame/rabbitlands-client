extends RefCounted
## Deterministic local examples for the HUD sandbox and visual checks.
const NAMES := ["Kellan", "Mira", "Rowan", "Tavi", "Selene", "Bram", "Nia", "Fen", "Ari", "Orin", "Luca", "Vale"]
const MAP_ID := "landfall"
const SPAWN := Vector2i(130, 214) # Landfall's published arrival point.

static func member(index: int) -> Dictionary:
	return {"name":NAMES[index] if index < NAMES.size() else "Guest %d" % index,
		"leader":index == 0, "is_self":index == 0, "online":true,
		"health":maxi(20, 150 - index * 17), "max_health":150,
		"ether":maxi(10, 60 - index * 5), "max_ether":60,
		"map_id":MAP_ID, "x":SPAWN.x + index, "y":SPAWN.y}

static func set_party(app: Node, members: Array) -> void:
	app.set("party", {"in_party":not members.is_empty(), "members":members.duplicate(true), "invited_by":"", "invite_seconds":0})
	app.emit_signal("state_changed", &"party")

static func populate(main: Control, app: Node) -> void:
	app.set("authenticated", true)
	app.set("local_actor_id", 99)
	app.set("current_map", MAP_ID)
	app.set("actors", {99:{"actor_id":99,"x":SPAWN.x,"y":SPAWN.y,"rotation":0,"actor_type":1,"kind":1,"name":"Kellan","health":120,"max_health":150,"alive":true,"sitting":false,"map":MAP_ID}})
	app.set("stats", {"health":120,"max_health":150,"ether":45,"max_ether":60,"food":42,
		"action_points":28,"max_action_points":30,"carried":115,"capacity":320})
	app.set("inventory", {0:{"image_id":3,"quantity":9,"slot":0,"inventory_usable":true},
		1:{"image_id":31,"quantity":2,"slot":1,"inventory_usable":true},
		2:{"image_id":35,"quantity":1,"slot":2,"inventory_usable":true}})
	var level_floor: int = main._experience_floor_for_level(12)
	var next_floor: int = main._experience_floor_for_level(13)
	app.stats.harvesting_base = 12
	app.stats.harvesting_exp = level_floor + int((next_floor - level_floor) * 0.28)
	app.stats.harvesting_exp_next = next_floor
	main._sync_stats()
	main._sync_inventory()
	main.spell_loadout.path = "user://hud-preview-spells.cfg"
	for index: int in 12: main.spell_loadout.assign_slot(index, index, 1)
	set_party(app, [member(0), member(1), member(2)])
	app.chat_lines.clear()
	for row: Array in [[0,"Entered Landfall."], [0,"Torch crafted x3."], [0,"Tavi: Meet at the bridge."], [0,"[Party] Rowan: Ready when you are."], [1,"[PM from Mira: Save a place for me.]"]]:
		var payload := PackedByteArray([int(row[0])])
		payload.append_array(str(row[1]).to_utf8_buffer())
		payload.append(0)
		app.call("_on_packet", 0, payload)
	app.quest_journal.clear()
	app.quest_journal.append({"title":"The Watchtower Road", "objective":"Find the messenger near the landing.", "location":"Landfall", "current":2, "target":4})
	main.extension_windows._tracked_quest_title = "The Watchtower Road"
	main.extension_windows._sync_tracked_quest()
