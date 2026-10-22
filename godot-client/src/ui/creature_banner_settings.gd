extends RefCounted
## Independent creature banner choices for normal play and instance display.
const SECTION := "creature_banners"
const MODES := ["normal", "instance"]
const OPTION_LABELS := {
	"visible": "Show creature banners",
	"names": "Names",
	"health_bar": "Health bars",
	"health_numbers": "Health values",
	"status_icons": "Status effect icons",
	"background": "Banner background",
}

static func setting_key(mode: String, option: String) -> String:
	return "creature_banner_%s_%s" % [mode, option]

static func defaults() -> Dictionary:
	var result := {}
	for mode: String in MODES:
		result[mode] = {}
		for option: String in OPTION_LABELS:
			# Instance display previously hid every other actor's banner.
			result[mode][option] = mode != "instance" or option != "visible"
	return result

static func read(config: ConfigFile) -> Dictionary:
	var result := defaults()
	for mode: String in MODES:
		for option: String in OPTION_LABELS:
			var value: Variant = config.get_value(SECTION, mode + "_" + option, result[mode][option])
			if value is bool:
				result[mode][option] = value
	return result

static func write(config: ConfigFile, values: Dictionary) -> void:
	for mode: String in MODES:
		for option: String in OPTION_LABELS:
			config.set_value(SECTION, mode + "_" + option, bool(values[mode][option]))
