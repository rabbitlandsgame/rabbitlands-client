extends SceneTree
## The worn-item icon treatment, checked pixel by pixel.
##
## Eternal Lands draws a worn item as its own artwork mirrored across the
## vertical axis with an orange exclamation mark in the lower-right corner.
## The mirror is the load-bearing half - a degraded item shares its picture
## with the fresh one it came from - and a mirror is exactly the kind of thing
## that looks right in a screenshot while being subtly wrong, so it is asserted
## against the source pixels rather than inspected.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var atlas: ItemAtlas = ItemAtlas.new()
	var file: FileAccess = FileAccess.open("res://data/items/atlases.json",
		FileAccess.READ)
	_expect(file != null, "the atlas configuration is readable")
	if file == null:
		quit(1)
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	_expect(parsed is Dictionary, "the atlas configuration parses")
	atlas.configure(parsed as Dictionary)

	var image_id := 1
	var plain: Texture2D = atlas.icon_for(image_id)
	_expect(plain != null, "the plain icon resolves")
	var worn: Texture2D = atlas.worn_icon_for(image_id)
	_expect(worn != null, "the worn icon resolves")
	if plain == null or worn == null:
		quit(1)
		return

	var plain_image: Image = plain.get_image()
	var worn_image: Image = worn.get_image()
	_expect(worn_image.get_size() == plain_image.get_size(),
		"the worn icon is the same size as the plain one, so it drops into the"
			+ " same slot without scaling")

	var width: int = plain_image.get_width()
	var height: int = plain_image.get_height()
	# The geometry comes from the drawing code rather than being restated here,
	# so moving the mark cannot leave this test checking the wrong rows.
	var metrics: Dictionary = ItemAtlas.worn_mark_metrics(width, height)
	var bounds: Rect2i = metrics.bounds as Rect2i
	# The mirror is checked on the rows above the mark, where nothing has been
	# drawn over the mirrored artwork.
	var checked := 0
	var mismatched := 0
	for y: int in range(0, bounds.position.y):
		for x: int in range(width):
			var source: Color = plain_image.get_pixel(width - 1 - x, y)
			var mirrored: Color = worn_image.get_pixel(x, y)
			checked += 1
			if not source.is_equal_approx(mirrored):
				mismatched += 1
	_expect(checked > 0, "there were pixels to compare")
	_expect(mismatched == 0,
		"every pixel above the mark is the source mirrored across the vertical"
			+ " axis (%d of %d differed)" % [mismatched, checked])

	# And the mark itself: orange pixels in the lower-right quadrant that the
	# plain icon does not have.
	var orange := 0
	for y: int in range(bounds.position.y, mini(height, bounds.end.y)):
		for x: int in range(bounds.position.x, mini(width, bounds.end.x)):
			if _is_mark(worn_image.get_pixel(x, y)):
				orange += 1
	_expect(orange > 0,
		"the lower-right corner carries the orange mark (%d pixels)" % orange)

	# The bar and the dot must not merge, or the mark reads as a plain bar.
	var column: int = int(metrics.left)
	var runs := 0
	var inside := false
	for y: int in range(height):
		var is_orange: bool = _is_mark(worn_image.get_pixel(column, y))
		if is_orange and not inside:
			runs += 1
		inside = is_orange
	_expect(runs == 2,
		"the mark is a bar and a separate dot, not one shape (%d runs)" % runs)

	# A second call must not redo the work, and must not return a different
	# texture - these end up in Button.icon, which compares by reference.
	_expect(atlas.worn_icon_for(image_id) == worn,
		"the worn icon is cached per image id")

	# An image id the atlas cannot resolve has no worn form either, rather than
	# a half-built texture.
	_expect(atlas.worn_icon_for(-1) == null,
		"an unresolvable image id yields nothing")

	print("worn item icon tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## The mark colour after the round trip through an 8-bit image. `is_equal_approx`
## is far tighter than one 255th, so comparing against the constant directly
## never matches anything that has actually been stored in a texture.
func _is_mark(colour: Color) -> bool:
	var wanted: Color = ItemAtlas.WORN_MARK_COLOUR
	return (absf(colour.r - wanted.r) < 0.02
		and absf(colour.g - wanted.g) < 0.02
		and absf(colour.b - wanted.b) < 0.02
		and colour.a > 0.9)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
