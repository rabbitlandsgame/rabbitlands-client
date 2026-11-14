extends SceneTree
## Run with a renderer and RL_BOOK_PREVIEW for a contact sheet; headless also works.
const Atlas := preload("res://src/ui/item_atlas.gd")
const Catalog := preload("res://src/ui/merchant_catalog.gd")
var failures := 0

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	var atlas := Atlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	var samples := {
		"Manual of Charge": 640, "Manual of Aimed Shot": 641, "Tome of Blink": 642,
		"Book of Iron Working": 643, "Book of Steel Smelting": 644,
		"Book of Fine Brewing": 645, "Book of Gem Setting": 646,
		"Book of Fine Tailoring": 647, "Book of Clockwork": 648,
		"Book of Beginnings": 64}
	var grid := GridContainer.new()
	grid.columns = 5
	grid.position = Vector2(20, 20)
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 14)
	root.add_child(grid)
	var hashes: Array[int] = []
	for title: String in samples:
		var id: int = samples[title]
		expect(atlas.supports(id) and not atlas.uses_substitute(id), title + " has registered artwork")
		var texture: Texture2D = atlas.icon_for(id)
		expect(texture != null and texture.get_size() == Vector2(50, 50), title + " cover loads at item size")
		if texture == null: continue
		expect(texture == atlas.icon_for(id), "covers reuse the icon cache")
		var source: Dictionary = atlas.icon_source(id)
		expect(not source.is_empty(), "cover is available to rich text and inspection")
		var pixels := texture.get_image()
		if pixels.is_compressed(): pixels.decompress()
		expect(not hashes.has(hash(pixels.get_data())), "every subject has distinct artwork")
		hashes.append(hash(pixels.get_data()))
		var cell := VBoxContainer.new()
		cell.custom_minimum_size = Vector2(176, 130)
		var image := TextureRect.new()
		image.texture = texture
		image.custom_minimum_size = Vector2(50, 50)
		image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		image.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		cell.add_child(image)
		var label := Label.new()
		label.text = Catalog.category({"name": title})
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.add_theme_font_size_override("font_size", 16)
		cell.add_child(label)
		var name_label := Label.new()
		name_label.text = title
		name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		name_label.add_theme_font_size_override("font_size", 12)
		cell.add_child(name_label)
		grid.add_child(cell)
	for _frame: int in 4: await process_frame
	var output := OS.get_environment("RL_BOOK_PREVIEW")
	if not output.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(output)
	print("book cover checks: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
