extends SceneTree
## Creation options, saved IDs, and real server appearance round trips.
var failures := 0
var checks := 0

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var skins := AppearanceChoices.options("skin")
	expect(skins.size() == 9 and not skins.any(func(row: Dictionary) -> bool: return row.id == 0), "human creation offers the nine named skin colors")
	var control := OptionButton.new()
	AppearanceChoices.populate(control, skins)
	expect(control.get_selected_id() == 1, "skin has a valid pale beige default")
	control.select(control.get_item_index(6))
	AppearanceChoices.populate(control, skins)
	expect(control.get_selected_id() == 6, "refresh preserves the selected blue")
	control.free()
	for culture: String in ["luminous", "votary", "glasswarden", "orun", "greyhaven", "ssarathi", "stoneborn", "mycelari"]:
		var race_skins := AppearanceChoices.options("skin", culture)
		if culture != "luminous":
			expect(race_skins.size() == 10 and race_skins[0].id == 0 and race_skins[0].label == "Race default", "non-human races offer their authored skin")
		for category: String in ["skin", "eyes", "hair_color", "wardrobe"]:
			for part in [4, 5, 6]:
				var seen := {}
				for row: Dictionary in AppearanceChoices.options(category, culture, part):
					var label: String = row.label.to_lower()
					expect(not seen.has(label), "unique color names for " + culture + " " + category)
					expect(not "natural" in label and not "traditional" in label and label != "accent", "color labels describe the color")
					seen[label] = true
	for value in range(200):
		var style := value % 4 if value < 100 else (value - 100) % 5
		var color := value if value < 20 else ((value - 20) / 4 if value < 100 else (value - 100) / 5)
		expect(AppearanceVariants.hair_style(value) == style and AppearanceVariants.hair_color_index(value) == color, "all historical appearance IDs keep their meaning")
	var fixtures: Array = []
	var unique := {}
	var actor_types := [0, 1, 2, 3, 4, 5, 37, 38, 39, 40, 41, 42, 79, 80, 81, 82]
	for style in range(10):
		for color in range(20):
			var hair := AppearanceVariants.pack_hair(style, color)
			expect(not unique.has(hair), "every style/color pair has its own saved value")
			unique[hair] = true
			var look := {"hair": hair, "head": 0, "skin": 6, "eyes": 4, "actor_type": actor_types[(style * 20 + color) % 16]}
			var packet := EloriaProtocol.create_character("Hair%03d" % (style * 20 + color), "secret", look)
			var tail := packet.slice(packet.size() - 9)
			var decoded := AppearanceVariants.hair_from_wire(tail[1], tail[6])
			expect(AppearanceVariants.hair_style(decoded) == style and AppearanceVariants.hair_color_index(decoded) == color, "creation bytes preserve style and color")
			fixtures.append({"style": style, "color": color, "packet": packet.hex_encode()})
	var directory := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if not directory.is_empty():
		DirAccess.make_dir_recursive_absolute(directory)
		FileAccess.open(directory.path_join("hair-create.json"), FileAccess.WRITE).store_string(JSON.stringify(fixtures))
		var responses := directory.path_join("hair-server.json")
		if FileAccess.file_exists(responses):
			var rows: Array = JSON.parse_string(FileAccess.get_file_as_string(responses))
			expect(rows.size() == 200, "server returns every saved appearance")
			for row: Dictionary in rows:
				var actor := EloriaProtocol.decode_actor(str(row.packet).hex_decode().slice(3), true)
				var look: Dictionary = actor.appearance
				expect(AppearanceVariants.hair_style(look.hair) == row.style and AppearanceVariants.hair_color_index(look.hair) == row.color, "database and actor spawn preserve the selected hair")
				expect(look.skin == 6 and look.eyes == 4 and AppearanceVariants.head_style(look.head) == 0, "round trip preserves other colors and keeps headwear retired")
	print("APPEARANCE_OPTIONS: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
