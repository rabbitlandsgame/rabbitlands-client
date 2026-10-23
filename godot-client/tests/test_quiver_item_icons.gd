extends SceneTree
## Raw PNG pixels must match the textures used by inventory/equipment slots.
## This catches missing or stale imports when launching directly with --path.

const ItemAtlasScript := preload("res://src/ui/item_atlas.gd")
var failures := 0

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/items/atlases.json"))
	var atlas = ItemAtlasScript.new()
	atlas.configure(config)
	var button := Button.new()
	for image_id: int in range(599, 617):
		var source: Dictionary = atlas.icon_source(image_id)
		_expect(not source.is_empty(), "equipment %d has a registered icon" % image_id)
		var texture: Texture2D = atlas.icon_for(image_id)
		_expect(texture != null, "equipment %d has an imported texture" % image_id)
		if texture == null or source.is_empty():
			continue
		button.icon = texture
		var actual: Image = button.icon.get_image()
		var sheet := Image.load_from_file(ProjectSettings.globalize_path(str(source.path)))
		var region: Rect2 = source.region as Rect2
		var expected := sheet.get_region(Rect2i(region))
		actual.convert(Image.FORMAT_RGBA8)
		expected.convert(Image.FORMAT_RGBA8)
		_expect(actual.get_size() == Vector2i(50, 50),
			"equipment %d fills its 50px icon region" % image_id)
		_expect(actual.get_data() == expected.get_data(),
			"equipment %d uses the current painted PNG; refresh its texture import if this fails" % image_id)
	button.free()
	print("painted equipment inventory texture tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
