extends Control
## Projection shared by permanent markers on north-up map pictures.

var _minimum := Vector2.ZERO
var _maximum := Vector2.ONE
var _image_size := Vector2.ONE
var _marks: Array = []

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)

func configure(minimum: Vector2, maximum: Vector2, image_size: Vector2, marks: Array) -> void:
	_minimum = minimum
	_maximum = maximum
	_image_size = image_size
	_marks = marks
	queue_redraw()

func mark_point(mark: Dictionary) -> Variant:
	var coordinates: Array = mark.get("position", []) as Array
	var span := _maximum - _minimum
	if coordinates.size() != 2 or span.x <= 0.0 or span.y <= 0.0 or _image_size.x <= 0.0 or _image_size.y <= 0.0:
		return null
	var fraction := (Vector2(float(coordinates[0]), float(coordinates[1])) - _minimum) / span
	if not Rect2(Vector2.ZERO, Vector2.ONE).has_point(fraction):
		return null
	var scale := minf(size.x / _image_size.x, size.y / _image_size.y)
	var displayed := _image_size * scale
	return (size - displayed) * 0.5 + fraction * displayed

func label_at(at: Vector2) -> String:
	var nearest := 14.0
	var label := ""
	for value: Variant in _marks:
		var mark: Dictionary = value as Dictionary
		var point: Variant = mark_point(mark)
		if point is Vector2:
			var distance := at.distance_to(point as Vector2)
			if distance < nearest:
				nearest = distance
				label = str(mark.get("label", "Storage"))
	return label
