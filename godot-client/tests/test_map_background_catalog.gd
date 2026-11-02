extends SceneTree
const Catalog := preload("res://src/world/map_background_catalog.gd")
var failures := 0
func _init() -> void:
	_run.call_deferred()
func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
func _run() -> void:
	var index := {"aliases": {"old_room": "rooms", "old_town": "town"}, "maps": {
		"town": {"path": "town.webp"},
		"rooms": {"sectioned": true, "path": "must-not-reveal-all.webp", "sections": {
			"west": {"path": "west.webp", "worldMin": [10, 20], "worldMax": [30, 40]},
			"east": {"path": "east.webp", "worldMin": [50, 20], "worldMax": [70, 40]}}}}}
	expect(Catalog.select_entry(index, "old_town").path == "town.webp", "ordinary alias selects its baked image")
	expect(Catalog.select_entry(index, "missing").is_empty(), "unknown map has no world-render fallback")
	expect(Catalog.select_entry(index, "rooms").is_empty(), "unknown secret room cannot select aggregate image")
	expect(Catalog.select_entry(index, "old_room", "unknown").is_empty(), "unknown aliased section remains hidden")
	expect(Catalog.select_entry(index, "old_room", "west").path == "west.webp", "alias preserves secret section choice")
	expect(Catalog.select_entry(index, "rooms", "east").worldMin == [50, 20], "section retains its own world frame")
	index.aliases["cycle_a"] = "cycle_b"
	index.aliases["cycle_b"] = "cycle_a"
	expect(Catalog.select_entry(index, "cycle_a").is_empty(), "alias cycle cannot expose an unrelated image")
	index.maps.rooms.sections = []
	expect(Catalog.select_entry(index, "rooms", "west").is_empty(), "invalid section metadata fails closed")
	index.maps.town = "invalid"
	expect(Catalog.select_entry(index, "town").is_empty(), "invalid map metadata fails closed")
	expect(Catalog.select_entry({"maps": []}, "town").is_empty(), "invalid catalog cannot select a picture")
	var provenance := {"maps": {"town": {"path": "town.webp", "worldMin": [0, 0], "worldMax": [8, 8],
		"sourceInputs": {"a.png": "00"}, "sections": {}}}}
	Catalog.runtime_index(provenance)
	expect(not provenance.maps.town.has("sourceInputs") and Catalog.select_entry(provenance, "town").worldMax == [8, 8],
		"runtime index drops build provenance and keeps the picture fields")
	# The shipped index selects exactly the same rows once its provenance is gone.
	var shipped: Variant = JSON.parse_string(FileAccess.get_file_as_string(Catalog.INDEX))
	var trimmed: Variant = JSON.parse_string(FileAccess.get_file_as_string(Catalog.INDEX))
	var same := shipped is Dictionary and trimmed is Dictionary
	if same:
		Catalog.runtime_index(trimmed)
		for map_id: String in (shipped as Dictionary).get("maps", {}):
			var sections: Array = [""]
			sections.append_array(((shipped as Dictionary).maps[map_id].get("sections", {}) as Dictionary).keys())
			for section: String in sections:
				var expected := Catalog.select_entry(shipped, map_id, section)
				expected.erase("sourceInputs")
				same = same and Catalog.select_entry(trimmed, map_id, section) == expected \
					and not ((trimmed as Dictionary).maps[map_id] as Dictionary).has("sourceInputs")
	expect(same, "shipped index selects identical runtime rows without sourceInputs")
	print("Map background catalog: 12 checks, ", failures, " failures")
	quit(1 if failures else 0)
