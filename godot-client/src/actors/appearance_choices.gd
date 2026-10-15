class_name AppearanceChoices
extends RefCounted

# Display order is independent of the persistent appearance byte.
static func options(category: String, culture := "luminous", part := 0) -> Array[Dictionary]:
	var names: Array = []
	var order: Array = []
	var colors: Array[Color] = []
	match category:
		"hair":
			names = ["Bald", "Parted", "Long", "Buns", "Buzzcut", "Bob", "Ponytail", "Long braid", "Topknot", "Mohawk"]
			order = [0, 4, 1, 9, 5, 8, 3, 6, 2, 7]
		"skin":
			names = ["", "Pale beige", "Golden tan", "Warm brown", "Deep brown", "Ebony brown", "Frost blue", "Moss green", "Dusk violet", "Stone grey"]
			order = [1, 2, 3, 4, 5, 9, 7, 6, 8]
			for id: int in range(names.size()):
				colors.append(AppearanceVariants.skin_color(id))
		"eyes":
			names = ["Sky blue", "Emerald green", "Chestnut brown", "Amber gold", "Violet purple", "Turquoise blue", "Brick red", "Silver grey", "Slate blue", "Amber orange", "Lime green", "Rose pink"]
			order = [7, 8, 2, 3, 9, 6, 10, 1, 5, 0, 4, 11]
			for id: int in range(names.size()):
				colors.append(AppearanceVariants.eye_color(id))
		"hair_color":
			names = ["Soft black", "Dark brown", "Chestnut brown", "Golden blond", "Copper red", "Silver grey", "Ivory white", "Steel blue", "Pine green", "Violet purple", "Rose pink", "Teal blue", "Sandy brown", "Charcoal grey", "Copper orange", "Auburn brown", "Pale pink", "Jade green", "Pale gold", "Midnight blue"]
			order = [6, 5, 13, 0, 18, 3, 12, 2, 1, 14, 15, 4, 17, 8, 11, 7, 19, 9, 16, 10]
			for id: int in range(names.size()):
				colors.append(AppearanceVariants.hair_color(id))
		"wardrobe":
			names = wardrobe_names(culture, part)
			order = range(names.size())
			for id: int in order:
				colors.append(AppearanceVariants.wardrobe_color(culture, part, id))
	var result: Array[Dictionary] = []
	for id: int in order:
		var entry: Dictionary = {"id": id, "label": names[id]}
		if not colors.is_empty():
			var color := colors[id]
			# The culture palette can repeat a common dye (e.g. Greyhaven ivory).
			# Keep the original ID as the representative so the default stays valid.
			var threshold := 0.075 if category == "wardrobe" else 0.001
			if result.any(func(row: Dictionary) -> bool:
				var previous: Color = row.color
				return Vector3(color.r - previous.r, color.g - previous.g, color.b - previous.b).length() < threshold):
				continue
			entry["color"] = color
		result.append(entry)
	if category == "wardrobe":
		result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			var ca: Color = a.color
			var cb: Color = b.color
			var family_a := -1 if ca.s < 0.16 else int(ca.h * 12.0)
			var family_b := -1 if cb.s < 0.16 else int(cb.h * 12.0)
			return ca.v > cb.v if family_a == family_b else family_a < family_b)
	if category == "skin" and culture != "luminous" and not culture.is_empty():
		# Zero leaves the race's authored skin colors and markings intact.
		# There is no single swatch for a textured, potentially multicolor skin.
		result.push_front({"id": 0, "label": "Race default"})
	return result

static func populate(control: OptionButton, choices: Array[Dictionary]) -> void:
	var previous := control.get_selected_id() if control.item_count > 0 else 0
	control.clear()
	for entry: Dictionary in choices:
		if entry.has("color"):
			var swatch := Image.create(16, 16, false, Image.FORMAT_RGBA8)
			swatch.fill(entry.color)
			control.add_icon_item(ImageTexture.create_from_image(swatch), entry.label, entry.id)
		else:
			control.add_item(entry.label, entry.id)
	var selected := control.get_item_index(previous)
	control.select(selected if selected >= 0 else (0 if not choices.is_empty() else -1))

static func wardrobe_names(culture: String, part: int) -> Array:
	# Names describe the actual palette for each garment, independent of race.
	var palettes := {
		"luminous": ["Teal blue", "Slate blue", "Walnut brown", "Champagne gold"],
		"votary": ["Steel blue", "Slate blue", "Blue grey", "Ice white"],
		"glasswarden": ["Indigo purple", "Ink blue", "Walnut brown", "Antique gold"],
		"orun": ["Burnt orange", "Umber brown", "Walnut brown", "Turquoise blue"],
		"greyhaven": ["Ivory white", "Slate blue", "Espresso brown", "Bronze gold"],
		"ssarathi": ["Jade green", "Pine green", "Olive brown", "Antique gold"],
		"stoneborn": ["Warm grey", "Slate grey", "Taupe brown", "Turquoise blue"],
		"mycelari": ["Moss green", "Olive green", "Walnut brown", "Apricot orange"]}
	var row: Array = palettes.get(culture, palettes["luminous"])
	var column := 1 if part == AppearanceVariants.PART_PANTS else (2 if part == AppearanceVariants.PART_BOOTS else 0)
	var base: String = row[column]
	return [base, "Light " + base.to_lower(), "Dark " + base.to_lower(), row[3],
		"Crimson red", "Forest green", "Navy blue", "Ochre gold", "Plum purple", "Rust orange", "Cream white", "Charcoal grey"]
