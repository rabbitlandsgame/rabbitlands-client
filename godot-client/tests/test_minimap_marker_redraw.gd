extends SceneTree
## The minimap hands its overlay the marks fifteen times a second. A refresh in
## which no mark and not the camera moved must not redraw (the same picture is
## already on screen); any change - a mark moved in place, a new colour, the
## camera following the player - must.

const OVERLAY_PROBE := """extends "res://src/ui/minimap_marker_overlay.gd"
var draws := 0
func _draw() -> void:
	draws += 1
	super._draw()
"""

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: " + message)

func _marks(x: float, colour: Color) -> Array[Dictionary]:
	return [{"position": Vector3(x, 0, 100), "type": &"creature", "colour": colour},
		{"position": Vector3(100, 0, 100), "type": &"self", "colour": Color.WHITE, "radius": 5.5}]

func _run() -> void:
	var view := SubViewport.new()
	view.size = Vector2i(264, 264)
	view.disable_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 80.0
	camera.position = Vector3(100, 220, 100)
	camera.rotation = Vector3(-PI * 0.5, 0, 0)
	view.add_child(camera)
	var probe := GDScript.new()
	probe.source_code = OVERLAY_PROBE
	if probe.reload() != OK:
		_expect(false, "the overlay probe compiles")
		quit(1)
		return
	var overlay: Control = probe.new()
	overlay.size = Vector2(264, 264)
	root.add_child(overlay)
	overlay.call("configure", camera, view.size)
	await process_frame
	await process_frame
	var base: int = overlay.get("draws")

	var marks := _marks(110, Color.RED)
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 1, "new marks are drawn")
	overlay.call("set_marks", _marks(110, Color.RED))
	await process_frame
	_expect(int(overlay.get("draws")) == base + 1, "equal marks under an unmoved camera are not drawn again")
	# The actor marks are kept dictionaries moved in place.
	marks[0]["position"] = Vector3(112, 0, 100)
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 2, "a mark moved in place is drawn again")
	marks[0]["colour"] = Color.GREEN
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 3, "a mark that changed colour is drawn again")
	camera.position.x += 1.0
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 4, "the camera following the player redraws the marks")
	camera.size = 100.0
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 5, "a zoom redraws the marks")
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 5, "and then rests again")
	var point: Variant = overlay.call("mark_point", marks[1])
	# One metre left of the camera at 2.64 pixels a metre (264 px over 100 m).
	_expect(point is Vector2 and (point as Vector2).distance_to(Vector2(129.36, 132)) < 0.5,
		"the marks still project through the camera: %s" % str(point))
	overlay.call("set_marker_scale", 1.5)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 6, "other settings still redraw on their own")
	# main.gd hands over the marks and then moves the camera over the player in
	# the same frame; the picture is drawn after that move and must follow it.
	overlay.call("set_marks", marks)
	camera.position.z += 1.0
	await process_frame
	_expect(int(overlay.get("draws")) == base + 7, "a camera moved after the marks were handed over redraws them")
	overlay.call("set_marks", marks)
	await process_frame
	_expect(int(overlay.get("draws")) == base + 7, "the picture drawn after that move then rests")

	overlay.free()
	view.free()
	print("Minimap marker redraw: %d checks, %d failures" % [checks, failures])
	if failures == 0:
		print("PASS: minimap marks redraw only when something moved")
	quit(failures)
