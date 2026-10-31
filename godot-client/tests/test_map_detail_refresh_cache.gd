extends SceneTree
## Actual Main ownership queries, without Main._ready, a map import or rendering.

## Compile only after autoload registration: Main references Network/AppState.
const PROBE_SOURCE := """extends "res://src/app/main.gd"
var ownership_queries := 0
var mark_collections := 0
func _map_owning_point(point: Vector3) -> String:
	ownership_queries += 1
	return super._map_owning_point(point)
func _collect_minimap_marks() -> Array[Dictionary]:
	mark_collections += 1
	return [{"position": Vector3(mark_collections, 0, 0), "type": &"creature", "colour": Color.RED}]
"""

class MarkReceiver:
	extends Control
	var calls := 0
	var marks: Array[Dictionary] = []
	func set_marks(value: Array[Dictionary]) -> void:
		calls += 1
		marks = value

class BackgroundReceiver:
	extends Control
	var calls := 0
	func refresh(_viewport_size := Vector2i.ZERO) -> void:
		calls += 1

var checks := 0
var failures := 0
var main: Variant
var mini_view: SubViewport
var full_view: SubViewport
var mini_camera: Camera3D
var full_camera: Camera3D
var owned_controls: Array[Control] = []

func _init() -> void:
	_run.call_deferred()

func _region(id: String, low: float, high: float) -> Dictionary:
	return {"serverMap": id, "frame": "test", "globalTranslation": [0.0, 0.0, 0.0],
		"continentPolygon": [[low, 0.0], [high, 0.0], [high, 200.0], [low, 200.0]]}

func _viewport_at(point: Vector3) -> SubViewport:
	var view := SubViewport.new()
	view.size = Vector2i(400, 400)
	view.disable_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.size = 80.0
	camera.position = point
	camera.rotation_degrees = Vector3(-90, 0, 0)
	camera.current = true
	view.add_child(camera)
	return view

func _resident() -> void:
	# The unknown resident is intentionally not a texture-bearing region: Main
	# still runs real ownership selection and real picture-bind invalidation,
	# without requiring ImageTexture creation or loading any bitmap.
	main._neighbour_pictures = {"test_resident": {"transform": Transform3D.IDENTITY, "height": 0.0}}

func _expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("map detail refresh cache: " + message)

func _refresh(expected_queries: int, wanted: Array, message: String) -> void:
	var before: int = main.ownership_queries
	main._update_map_detail_levels()
	_expect(main.ownership_queries - before == expected_queries,
		"%s query count: expected %d, got %d" % [message, expected_queries, main.ownership_queries - before])
	var observed: Array = main._map_detail_visible.keys()
	observed.sort()
	var expected := wanted.duplicate()
	expected.sort()
	_expect(observed == expected, "%s owners: expected %s, got %s" % [message, expected, observed])

func _run() -> void:
	var state := root.get_node("AppState")
	var previous_map: String = state.current_map
	var probe := GDScript.new()
	probe.source_code = PROBE_SOURCE
	if probe.reload() != OK or not probe.can_instantiate():
		_expect(false, "actual Main probe compiles after autoload registration")
		quit(1)
		return
	main = probe.new()
	mini_view = _viewport_at(Vector3(100, 300, 100))
	full_view = _viewport_at(Vector3(300, 300, 100))
	mini_camera = mini_view.get_child(0) as Camera3D
	full_camera = full_view.get_child(0) as Camera3D
	main.map_viewport = mini_view
	main.map_camera = mini_camera
	main.full_map_viewport = full_view
	main.full_map_camera = full_camera
	main.minimap_frame = Panel.new()
	main.full_map = Control.new()
	main.map_image = TextureRect.new()
	owned_controls.assign([main.minimap_frame, main.full_map, main.map_image])
	main.minimap_frame.show()
	main.full_map.hide()
	main.map_image.show()
	main._full_map_zoom = 0.5
	main.cartography = {"continent": {"originMetres": [0.0, 0.0], "metresPerPixel": 1.0}}
	main.cartography_regions = [_region("alpha", 0, 200), _region("beta", 200, 400)]
	state.current_map = "alpha"
	_resident()
	await process_frame

	_refresh(9, ["alpha"], "initial mini view")
	_refresh(0, ["alpha"], "unchanged mini reuses ownership")
	mini_camera.position.y += 50.0
	_refresh(0, ["alpha"], "height-only change leaves queried XZ unchanged")
	mini_camera.position.x = 210.0
	_refresh(9, ["alpha", "beta"], "pan crosses the actual rectangle seam")
	_refresh(0, ["alpha", "beta"], "changed picture sync remembers its final state")
	mini_camera.rotation_degrees.y = 30.0
	_refresh(9, ["alpha", "beta"], "rotation changes samples")
	mini_camera.size = 100.0
	_refresh(9, ["alpha", "beta"], "zoom changes samples")
	mini_view.size = Vector2i(800, 400)
	_refresh(9, ["alpha", "beta"], "aspect resize changes samples")
	mini_view.size = Vector2i(1600, 800)
	_refresh(9, ["alpha", "beta"], "same-aspect logical resize remains an explicit input")
	_refresh(0, ["alpha", "beta"], "resized view reuses ownership")

	mini_camera.position = Vector3(100, 300, 100)
	mini_camera.rotation_degrees = Vector3(-90, 0, 0)
	mini_camera.size = 80.0
	mini_view.size = Vector2i(400, 400)
	main.full_map.show()
	_refresh(18, ["alpha", "beta"], "both maps contribute ordered samples")
	_refresh(0, ["alpha", "beta"], "both unchanged maps reuse ownership")
	main._full_map_zoom = 1.0
	_refresh(9, ["alpha"], "full-map detail zoom threshold")
	main._full_map_zoom = 0.5
	main.minimap_frame.hide()
	_refresh(9, ["alpha", "beta"], "full map remains active without minimap")
	main.map_image.hide()
	_refresh(0, ["alpha"], "hidden full-map image contributes no samples")
	main.map_image.show()
	_refresh(9, ["alpha", "beta"], "full-map image becomes visible")
	main.full_map.hide()
	main.minimap_frame.show()
	mini_camera.position.x = 300.0
	_refresh(9, ["alpha", "beta"], "mini-only beta view")

	# Mutable context arrays must be copied into the remembered key.
	(main.cartography.continent.originMetres as Array)[0] = 200.0
	_refresh(9, ["alpha"], "in-place continent-origin mutation")
	(main.cartography.continent.originMetres as Array)[0] = 0.0
	_refresh(9, ["alpha", "beta"], "continent origin restored")
	main.cartography.continent.metresPerPixel = 2.0
	_refresh(9, ["alpha"], "continent scale mutation")
	main.cartography.continent.metresPerPixel = 1.0
	_refresh(9, ["alpha", "beta"], "continent scale restored")
	(main.cartography_regions[0].globalTranslation as Array)[0] = -200.0
	_refresh(9, ["alpha"], "in-place active translation mutation")
	(main.cartography_regions[0].globalTranslation as Array)[0] = 0.0
	_refresh(9, ["alpha", "beta"], "active translation restored")
	main.cartography_regions[0].frame = "other"
	_refresh(9, ["alpha"], "active ownership frame mutation")
	main.cartography_regions[0].frame = "test"
	_refresh(9, ["alpha", "beta"], "active ownership frame restored")
	state.current_map = "beta"
	_refresh(9, ["beta"], "current map changes without camera movement")
	state.current_map = "./maps/ALPHA.elm"
	_refresh(9, ["alpha", "beta"], "normalised current-map input")
	state.current_map = "alpha"
	_refresh(0, ["alpha", "beta"], "equivalent normalised map reuses ownership")
	main._map_detail_visible.erase("beta")
	_refresh(9, ["alpha", "beta"], "external visible-detail reset")

	main.cartography_regions = [_region("alpha", 0, 200), _region("beta", 450, 650)]
	_refresh(9, ["alpha"], "same-count replacement rebuilds polygon geometry")
	main.cartography_regions[1].continentPolygon = [[200.0, 0.0], [400.0, 0.0], [400.0, 200.0], [200.0, 200.0]]
	main._invalidate_cartography_ownership_cache()
	_expect(main.cartography_regions.size() == 2, "invalidating identity references never clears live regions")
	_refresh(9, ["alpha", "beta"], "explicit in-place geometry invalidation")
	_refresh(0, ["alpha", "beta"], "new geometry reuses ownership")
	main._region_polygons.clear()
	_refresh(9, ["alpha", "beta"], "legacy polygon-cache clear is detected")
	main._sync_map_background_pictures()
	_refresh(9, ["alpha", "beta"], "same-map picture or section rebind invalidates query")
	_refresh(0, ["alpha", "beta"], "rebound pictures reuse ownership")
	main._remove_map_picture()
	_expect(main._map_detail_visible.is_empty() and main._neighbour_pictures.is_empty(), "picture removal drops its resident/detail state")
	_resident()
	_refresh(9, ["alpha", "beta"], "same-map resident pictures installed after removal")
	main._neighbour_pictures.clear()
	main._update_map_detail_levels()
	_expect(main._map_detail_query_signature.is_empty(), "no neighbours release the query memo")
	_resident()
	_refresh(9, ["alpha", "beta"], "neighbour residency returns")

	# Exercise the actual caller: a detail memo hit must never reuse or suppress
	# moving marks, background refreshes, or the map's existing cadence.
	var marks := MarkReceiver.new()
	var background := BackgroundReceiver.new()
	main.minimap_marker_overlay = marks
	main.minimap_background = background
	owned_controls.append_array([marks, background])
	var before: int = main.ownership_queries
	for tick: int in 2:
		main._minimap_refresh_msec = 0
		main._update_map_viewports()
		_expect(marks.marks[0].position.x == float(tick + 1), "live marker position still refreshed on detail memo hit")
	_expect(main.ownership_queries == before, "actual map-refresh caller reuses only detail ownership")
	_expect(main.mark_collections == 2 and marks.calls == 2 and background.calls == 2,
		"both live collections and background refreshes remain visible")

	state.current_map = previous_map
	main.free()
	for control: Control in owned_controls:
		control.free()
	mini_view.free()
	full_view.free()
	print("Map detail refresh cache: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
