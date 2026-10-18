extends RefCounted
## Local preferences only: the server still decides eligibility and cost.
signal changed
const SLOT_COUNT := 12
var catalog: SpellCatalog
var slots: Array[Dictionary] = []
var powers: Dictionary = {}
var wheel_power := 1
var ring_size := 100
var ring_preferences := {"scopes": {}, "powers": {}, "pins": {}}
var book_preferences: Dictionary = {}
var mode := "wheel"
var profile := ""
var path := "user://magic_loadouts.cfg"

func configure(value: SpellCatalog) -> void:
	catalog = value
	_reset()

func _reset() -> void:
	slots.clear()
	powers.clear()
	wheel_power = 1
	ring_size = 100
	ring_preferences = {"scopes": {}, "powers": {}, "pins": {}}
	book_preferences = {}
	for index in range(SLOT_COUNT):
		var id := catalog.default_quick_slots[index] if index < catalog.default_quick_slots.size() else -1
		slots.append({"id": id, "power": 1})

func load_profile(key: String) -> void:
	profile = key.sha256_text()
	_reset()
	var config := ConfigFile.new()
	if config.load(path) == OK:
		var saved_book: Variant = config.get_value(profile, "book_preferences", {})
		if saved_book is Dictionary:
			for tab: String in ["magic", "techniques"]:
				var value: Variant = saved_book.get(tab)
				if value is Dictionary:
					book_preferences[tab] = {"filter": str(value.get("filter", "all")),
						"favorites": value.get("favorites", []).duplicate() if value.get("favorites") is Array else []}
		wheel_power = clampi(int(config.get_value(profile, "wheel_power", 1)), 1, 10)
		ring_size = clampi(int(config.get_value(profile, "ring_size", 100)), 75, 125)
		var saved_ring: Variant = config.get_value(profile, "ring_preferences", {})
		if saved_ring is Dictionary:
			for section in ring_preferences:
				if saved_ring.get(section) is Dictionary:
					ring_preferences[section] = saved_ring[section].duplicate(true)
		var saved: Variant = config.get_value(profile, "slots", [])
		if saved is Array:
			for index in range(mini(saved.size(), SLOT_COUNT)):
				if saved[index] is Dictionary:
					var technique := str(saved[index].get("technique", ""))
					if _technique_key(technique):
						slots[index] = {"id": -1, "power": 1, "technique": technique}
						continue
					var id := int(saved[index].get("id", -1))
					if id == -1 or id in catalog.spell_ids():
						slots[index] = {"id": id, "power": clampi(int(saved[index].get("power", 1)), 1, 10)}
		var saved_powers: Variant = config.get_value(profile, "powers", {})
		if saved_powers is Dictionary:
			for id in catalog.spell_ids():
				powers[id] = clampi(int(saved_powers.get(id, 1)), 1, 10)
	changed.emit()

func assign_slot(index: int, spell_id: int, power: int) -> void:
	if index < 0 or index >= SLOT_COUNT or (spell_id != -1 and spell_id not in catalog.spell_ids()):
		return
	slots[index] = {"id": spell_id, "power": clampi(power, 1, 10)}
	_save()
	changed.emit()

## A quick slot may hold a combat technique instead of a spell (the server's
## technique key). The slot fires it through the Techniques tab, which aims it.
func assign_technique(index: int, key: String) -> void:
	if index < 0 or index >= SLOT_COUNT or not _technique_key(key):
		return
	slots[index] = {"id": -1, "power": 1, "technique": key}
	_save()
	changed.emit()

func technique_at(index: int) -> String:
	if index < 0 or index >= slots.size():
		return ""
	return str(slots[index].get("technique", ""))

## The first slot holding neither a spell nor a technique, or -1.
func first_empty_slot() -> int:
	for index in range(slots.size()):
		if int(slots[index].get("id", -1)) < 0 and technique_at(index).is_empty():
			return index
	return -1

static func _technique_key(key: String) -> bool:
	if key.is_empty() or key.length() > 40:
		return false
	for character in key:
		if not (character == "_" or (character >= "a" and character <= "z")):
			return false
	return true

func power_for(spell_id: int) -> int:
	return int(powers.get(spell_id, 1))

func remember_power(spell_id: int, power: int) -> void:
	powers[spell_id] = clampi(power, 1, 10)
	_save()
	changed.emit()

func remember_cast(spell_id: int, power: int) -> void:
	if spell_id not in catalog.spell_ids(): return
	var family := catalog.effect_for(spell_id)
	var updated := false
	for index in range(slots.size()):
		if int(slots[index].id) < 0 or catalog.effect_for(int(slots[index].id)) != family: continue
		var last_cast := {"id": spell_id, "power": clampi(power, 1, 10)}
		if slots[index] != last_cast:
			slots[index] = last_cast
			updated = true
	if updated:
		_save()
		changed.emit()

func set_wheel_power(power: int) -> void:
	power = clampi(power, 1, 10)
	if wheel_power == power: return
	wheel_power = power
	_save()
	changed.emit()

func set_mode(value: String) -> void:
	# "aimed" was a mode until target spells always waited for a click.
	mode = "prepared" if value == "aimed" else value if value in ["prepared", "wheel"] else "wheel"
	changed.emit()

func set_ring_size(percent: int) -> void:
	percent = clampi(percent, 75, 125)
	if ring_size == percent: return
	ring_size = percent
	_save()
	changed.emit()

func save_ring_preferences() -> void:
	# The ring shares this dictionary. Saving must not rebuild its hovered wedge.
	_save()

func save_book_preferences() -> void:
	# Filtering/favoriting must not rebuild a hovered ring or change quick slots.
	_save()

func targeting_mode() -> String:
	return "aimed" if mode == "aimed" else "prepared"

func _save() -> void:
	if profile.is_empty(): return
	var config := ConfigFile.new()
	config.load(path)
	config.set_value(profile, "slots", slots)
	config.set_value(profile, "powers", powers)
	config.set_value(profile, "wheel_power", wheel_power)
	config.set_value(profile, "ring_size", ring_size)
	config.set_value(profile, "ring_preferences", ring_preferences)
	config.set_value(profile, "book_preferences", book_preferences)
	var error := config.save(path)
	if error != OK:
		push_warning("Could not save spell loadout: " + error_string(error))
