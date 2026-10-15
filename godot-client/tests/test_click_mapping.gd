extends SceneTree
## Clicks must select the cell under the cursor, including its upper half.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_tile_cells()
	await _check_viewport_picking()
	print("Click mapping: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)

func _check_tile_cells() -> void:
	for inverted: bool in [false, true]:
		for tile_metres: float in [0.5, 1.0, 2.0]:
			var adapter := CoordinateAdapter.new({
				"metresPerTile": tile_metres, "serverOrigin": [100.0, 200.0],
				"origin": [10.0, 30.0, -5.0], "walkingHeight": 31.15,
				"invertServerY": inverted})
			for tile: Vector2i in [Vector2i(102, 198), Vector2i.ZERO, Vector2i(-3, -7)]:
				_expect(adapter.godot_to_server(adapter.tile_center(tile.x, tile.y)) == tile,
					"the visible tile center maps back to %s" % tile)
				# Probe each side of the old rounding boundary and each actual cell edge.
				for x: float in [0.0, 0.01, 0.49, 0.5, 0.51, 0.99]:
					for y: float in [0.0, 0.01, 0.49, 0.5, 0.51, 0.99]:
						var point := adapter.server_to_godot(tile.x + x, tile.y + y)
						_expect(adapter.godot_to_server(point) == tile,
							"point (%s + %.2f, %.2f) stays in its tile" % [tile, x, y])
				for offset: Vector2 in [Vector2(-0.01, 0.5), Vector2(1.01, 0.5),
						Vector2(0.5, -0.01), Vector2(0.5, 1.01)]:
					var expected := tile + Vector2i(floori(offset.x), floori(offset.y))
					var point := adapter.server_to_godot(tile.x + offset.x, tile.y + offset.y)
					_expect(adapter.godot_to_server(point) == expected,
						"crossing the cell edge selects adjacent tile %s" % expected)

func _check_viewport_picking() -> void:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var game_view: Control = main.get("game_view")
	game_view.show()
	var container: TextureRect = main.get("viewport_container")
	var viewport: SubViewport = main.get("main_viewport")
	var rig: IsometricCameraController = main.get("camera_rig")
	var camera: Camera3D = main.get("gameplay_camera")
	var adapter := CoordinateAdapter.new({"serverOrigin": [360.0, 360.0],
		"origin": [0.0, 31.15, 0.0], "walkingHeight": 31.15})
	main.set("adapter", adapter)
	# The picked surface is above the fallback plane, like a raised walkway.
	var surface := StaticBody3D.new()
	surface.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	surface.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200.0, 1.0, 200.0)
	shape.shape = box
	surface.add_child(shape)
	(main.get("world_root") as Node3D).add_child(surface)
	surface.position.y = 34.5
	await physics_frame
	await physics_frame
	var target := Vector2i(360, 360)
	var center := adapter.tile_center(target.x, target.y)
	center.y = 35.0
	for window_size: Vector2i in [Vector2i(1100, 720), Vector2i(1920, 1080),
			Vector2i(882, 758)]:
		root.size = window_size
		await process_frame
		main.call("_on_window_size_changed")
		for yaw: float in [0.0, 45.0, 135.0, 270.0]:
			for distance: float in [3.0, 8.0, 26.0, 90.0]:
				rig.yaw_degrees = yaw
				rig.distance = distance
				rig.set_focus(center)
				for offset: Vector2 in [Vector2(0.25, 0.25), Vector2(0.5, 0.5),
						Vector2(0.75, 0.75), Vector2(0.9, 0.1)]:
					var point := adapter.server_to_godot(target.x + offset.x,
						target.y + offset.y, 35.0)
					var projected := camera.unproject_position(point)
					var local_click := projected * container.size / Vector2(viewport.size)
					var pixels: Vector2 = main.call("_local_viewport_position", local_click)
					_expect(pixels.distance_to(projected) < 0.01,
						"local click preserves rendered pixels at %s" % window_size)
					var global_click := container.get_global_transform() * local_click
					var global_pixels: Vector2 = main.call("_viewport_position", global_click)
					_expect(global_pixels.distance_to(projected) < 0.01,
						"global click preserves rendered pixels at %s" % window_size)
					var hit: Variant = main.call("_navigation_ray_position",
						rig.ray_origin(pixels), rig.ray_direction(pixels))
					_expect(hit is Vector3 and (hit as Vector3).distance_to(point) < 0.01,
						"the gameplay ray hits the displayed walkway under the cursor")
					if hit is Vector3:
						_expect(adapter.godot_to_server(hit) == target,
							"gameplay click selects %s at yaw %.0f zoom %.0f" % [target, yaw, distance])
					_expect(main.call("_map_target_tile", camera, pixels) == target,
						"map and location targets agree with the gameplay click")
	main.queue_free()
	await process_frame

func _expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		if failures <= 12:
			push_error("FAIL: " + label)
