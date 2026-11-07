extends RefCounted
## Player-wide shop shortcuts, independent of merchant and inventory quantities.
const DEFAULTS: Array[int] = [1, 5, 10, 100, 1000]
const MAXIMUM := 1000000
var values: Array[int] = DEFAULTS.duplicate()

func load_file(path: String) -> void:
	values = DEFAULTS.duplicate()
	var config := ConfigFile.new()
	if config.load(path) != OK: return
	var stored: Variant = config.get_value("merchant", "quantity_presets", [])
	if not stored is Array: return
	for index: int in range(mini(stored.size(), values.size())):
		var value: Variant = stored[index]
		if value is int and value >= 1 and value <= MAXIMUM:
			values[index] = value

func save_value(index: int, value: int, path: String) -> Error:
	if index < 0 or index >= values.size() or value < 1 or value > MAXIMUM:
		return ERR_INVALID_PARAMETER
	var config := ConfigFile.new()
	var error := config.load(path)
	if error != OK and error != ERR_FILE_NOT_FOUND: return error
	var updated := values.duplicate()
	updated[index] = value
	config.set_value("merchant", "quantity_presets", updated)
	error = config.save(path)
	if error == OK: values = updated
	return error
