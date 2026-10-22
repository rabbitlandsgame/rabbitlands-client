extends SceneTree
## Exercise the production GUI path, including circular rims over the map image.
const Presets := preload("res://src/ui/hud_presets.gd")
class CaptureNetwork extends EloriaNetworkClient:
	var outgoing: Array[PackedByteArray] = []
	func send_frame(frame: PackedByteArray, _sensitive := false) -> Error:
		outgoing.append(frame.duplicate())
		return OK

var main: Control
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func frames(count := 5) -> void:
	for index: int in count: await process_frame

func mouse_button(point: Vector2, pressed: bool, button := MOUSE_BUTTON_LEFT) -> void:
	var event := InputEventMouseButton.new()
	event.position = point
	event.global_position = point
	event.button_index = button
	event.pressed = pressed
	root.push_input(event, true)

func motion(point: Vector2, dragging := false) -> void:
	var event := InputEventMouseMotion.new()
	event.position = point
	event.global_position = point
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if dragging else 0
	root.push_input(event, true)

func drag(delta: Vector2, label: String, round_map := true) -> void:
	var map: Control = main.minimap_frame
	var local := map.size * 0.5
	if round_map: local += Vector2(-1, -1).normalized() * (map.size.x * 0.5 - 6)
	else: local = Vector2(4, map.size.y * 0.5)
	var origin := map.get_global_transform() * local
	var before := map.global_position
	motion(origin)
	mouse_button(origin, true)
	expect(main._minimap_dragging, label + ": visible rim starts a gameplay drag")
	motion(origin + delta, true)
	await frames()
	if not round_map and main.hud_workspace.manages_layout():
		var expected := Rect2(map.position, map.size * map.scale)
		var follows: bool = main.hud_workspace.frame_overlay.panels.any(func(panel: Dictionary) -> bool:
			return panel.rect.position.distance_to(expected.position) < 1 and panel.rect.size.distance_to(expected.size) < 1)
		expect(follows, label + ": the HUD outline follows while the pointer is held")
	# Routine relayouts while the button is held cannot return it to its anchor.
	main.hud_workspace.layout_hud()
	await frames()
	expect(map.global_position.distance_to(before + delta) < 2,
		label + ": scaled pointer movement survives a relayout during the drag")
	mouse_button(origin + delta, false)
	await frames()
	expect(not main._minimap_dragging and map.global_position.distance_to(before + delta) < 2,
		label + ": releasing the pointer keeps the new position")

func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	var network := root.get_node("Network")
	network.set_script(CaptureNetwork)
	network.block_for_hud_preview()
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	workspace.choose_preset("classic", true)
	main.chat_hud.dismiss()
	workspace.change_part("system_chat", "enabled", false)
	workspace.change_part("party", "enabled", false)
	await frames()
	network.outgoing.clear()
	expect(not workspace.is_open(), "all drag checks run during gameplay, with the editor closed")
	await drag(Vector2(-220, 120), "option 2 round minimap")
	await drag(Vector2(100, 35), "moving the same minimap again")
	expect(network.outgoing.is_empty(), "rim dragging never sends a map movement command")
	var config: Dictionary = workspace.model.working.parts.minimap
	expect(config.anchor == "free" and config.dock_target == "none" and config.edge_dock == "none",
		"gameplay dragging releases the old preset anchor and screen dock")
	var saved := Presets.new()
	saved.load_file(workspace.preferences_path)
	expect(saved.working.parts.minimap.position.distance_to(config.position) < 0.001,
		"the minimap's new gameplay position is saved in the selected preset")
	var moved: Vector2 = main.minimap_frame.global_position
	workspace.choose_preset("heritage", true)
	workspace.choose_preset("classic")
	await frames()
	expect(main.minimap_frame.global_position.distance_to(moved) < 2,
		"switching HUD designs and returning retains the moved minimap")
	workspace.change_part("minimap", "scale", 0.5)
	await frames()
	await drag(Vector2(-90, 30), "smaller round minimap")
	workspace.change_part("minimap", "map_shape", "square")
	workspace.change_part("minimap", "frame_shape", "rectangle")
	await frames()
	await drag(Vector2(75, 25), "square minimap", false)
	# Map controls retain their normal gameplay actions away from the rim.
	var center: Vector2 = main.minimap_frame.get_global_rect().get_center()
	motion(center)
	var zoom: float = main.map_camera.size
	mouse_button(center, true, MOUSE_BUTTON_WHEEL_UP)
	await frames()
	expect(main.map_camera.size < zoom and not main._minimap_dragging,
		"scrolling inside the map still changes its zoom")
	mouse_button(center, true, MOUSE_BUTTON_RIGHT)
	await frames()
	expect(main._minimap_menu.visible, "right-click still opens the minimap menu")
	main._minimap_menu.hide()
	# A long drag can reach the right/bottom viewport edges without the old rail reserve.
	var map: Control = main.minimap_frame
	var grab: Vector2 = map.get_global_transform() * Vector2(3, map.size.y * 0.5)
	motion(grab)
	mouse_button(grab, true)
	motion(grab + Vector2(10000, 10000), true)
	mouse_button(grab + Vector2(10000, 10000), false)
	await frames()
	var rect := map.get_global_rect()
	var bounds: Rect2 = main.game_view.get_global_rect()
	expect(bounds.grow(1).encloses(rect) and bounds.end.distance_to(rect.end) < 16,
		"gameplay dragging uses the available modern viewport and remains recoverable")
	workspace.choose_preset("current", true)
	workspace.change_part("minimap", "enabled", true)
	workspace.change_part("party", "enabled", false)
	workspace.change_part("system_chat", "enabled", false)
	main.chat_hud.dismiss()
	main._minimap_shape = "square"
	main._apply_minimap_shape()
	await frames()
	await drag(Vector2(100, 60), "Current HUD minimap", false)
	main._minimap_shape = "round"
	main._apply_minimap_shape()
	await frames()
	await drag(Vector2(60, 40), "Current HUD round minimap")
	main.queue_free()
	await frames(2)
	print("MINIMAP GAMEPLAY DRAG: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
