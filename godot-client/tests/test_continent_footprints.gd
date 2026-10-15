extends SceneTree

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var overlay := load("res://src/ui/continent_map.gd").new() as Control
	root.add_child(overlay)
	overlay.size = Vector2(400, 200)
	var regions: Array[Dictionary] = [
		{"name": "West", "rect": Rect2(0, 0, 100, 100),
		 "polygon": [[0, 0], [100, 0], [65, 100], [0, 100]], "label": [35, 50]},
		{"name": "East", "rect": Rect2(65, 0, 135, 100),
		 "polygon": [[100, 0], [200, 0], [200, 100], [65, 100]], "label": [140, 50]}]
	overlay.call("configure", Vector2(200, 100), regions)
	assert(overlay.call("region_at", Vector2(150, 20)) == 0)
	assert(overlay.call("region_at", Vector2(150, 180)) == 1)
	assert(overlay.call("region_at", Vector2(410, 20)) == -1)
	for index in 2:
		assert(overlay.call("region_at", overlay.call("region_label_position", index)) == index)
	# Resizing uses the same keep-aspect fit for footprints and the background.
	overlay.size = Vector2(400, 400)
	assert(overlay.call("region_at", Vector2(150, 120)) == 0)
	assert(overlay.call("region_at", Vector2(150, 280)) == 1)
	assert(overlay.call("region_at", Vector2(150, 20)) == -1)
	print("Continent footprint picking PASS")
	overlay.free()
	quit()
