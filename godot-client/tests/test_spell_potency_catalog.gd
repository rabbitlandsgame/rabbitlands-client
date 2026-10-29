extends SceneTree
## The spell encyclopedia distinguishes unlocking from recommendation.
var failures := 0

func _init() -> void: call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func run() -> void:
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var view = load("res://src/ui/encyclopedia_view.gd").new()
	view.set("_catalogues", {"spells": catalog})
	var entries: Array = view._spell_entries("spells")
	var immunity: Dictionary = {}
	for entry: Dictionary in entries:
		if entry.title == "Magic Immunity": immunity = entry
	check(not immunity.is_empty(), "advanced spell has an encyclopedia entry")
	check(immunity.get("facts", []).has(["Unlock Magic level", "40"]), "advanced unlock is 40")
	check(immunity.get("facts", []).has(["Recommended Magic level", "80"]), "advanced recommendation is 80")
	check(catalog.spell(11).get("power_level") == 68, "the catalog preserves the old higher-power baseline")
	view.free()
	print("spell potency catalog: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
