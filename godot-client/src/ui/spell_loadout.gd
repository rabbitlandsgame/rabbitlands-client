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
	for index in range(SLOT_COUNT):
		var id := catalog.default_quick_slots[index] if index < catalog.default_quick_slots.size() else -1
		slots.append({"id": id, "power": 1})

func load_profile(key: String) -> void:
	profile = key.sha256_text()
	_reset()
	var config := ConfigFile.new()
	if config.load(path) == OK:
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
	mode = value if value in ["prepared", "aimed", "wheel"] else "wheel"
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
	var error := config.save(path)
	if error != OK:
		push_warning("Could not save spell loadout: " + error_string(error))
