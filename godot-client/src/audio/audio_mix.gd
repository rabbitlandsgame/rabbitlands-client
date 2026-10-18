extends RefCounted
## Shared buses let settings scale both event sounds and map ambience live.

const MASTER_BUS := &"RL Audio"
const MASTER_DEFAULT := 0.6
const CATEGORIES := {
	"music": {"bus": &"RL Music", "label": "Music", "volume": 0.55},
	"interface": {"bus": &"RL Interface", "label": "HUD & menus", "volume": 0.2},
	"footsteps": {"bus": &"RL Footsteps", "label": "Footsteps", "volume": 0.6},
	"combat": {"bus": &"RL Combat", "label": "Combat & spells", "volume": 0.55},
	"activity": {"bus": &"RL Activity", "label": "Gathering & items", "volume": 0.5},
	"ambience": {"bus": &"RL Ambience", "label": "World ambience", "volume": 0.45},
}

static func ensure_buses() -> void:
	_add_bus(MASTER_BUS, &"Master", MASTER_DEFAULT)
	for category: String in CATEGORIES:
		var info: Dictionary = CATEGORIES[category]
		_add_bus(info.bus, MASTER_BUS, float(info.volume))

static func _add_bus(bus: StringName, send: StringName, volume: float) -> void:
	if AudioServer.get_bus_index(bus) >= 0:
		return
	AudioServer.add_bus()
	var index := AudioServer.bus_count - 1
	AudioServer.set_bus_name(index, bus)
	AudioServer.set_bus_send(index, send)
	set_volume(bus, volume)

static func set_volume(bus: StringName, volume: float) -> void:
	var index := AudioServer.get_bus_index(bus)
	var gain := clampf(volume, 0.0, 1.0)
	AudioServer.set_bus_volume_db(index, linear_to_db(maxf(gain, 0.0001)))
	# Zero is a true mute, including positional ambience and looping music.
	AudioServer.set_bus_mute(index, is_zero_approx(gain))

static func bus_for_sound(sound: String) -> StringName:
	if sound.begins_with("ui_"):
		return CATEGORIES.interface.bus
	if sound.begins_with("footstep"):
		return CATEGORIES.footsteps.bus
	if sound.begins_with("combat_") or sound in ["spell_cast", "world_effect"]:
		return CATEGORIES.combat.bus
	if sound in ["civic_crowd", "waterfall", "rain"]:
		return CATEGORIES.ambience.bus
	return CATEGORIES.activity.bus
