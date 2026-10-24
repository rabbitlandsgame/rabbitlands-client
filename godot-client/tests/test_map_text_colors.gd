extends SceneTree
## Focused color behavior without loading terrain or player preferences.
const TextColors := preload("res://src/ui/text_colors.gd")
const Overlay := preload("res://src/ui/map_marker_overlay.gd")
const Continent := preload("res://src/ui/continent_map.gd")
const MinimapLabels := preload("res://src/ui/hud_minimap_labels.gd")
const Tooltip := preload("res://src/ui/map_text_tooltip.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	TextColors.load_colors("res://test-artifacts/map-text-colors/absent.cfg")
	_expect(Overlay.personal_text_color({"color": Color("af65dd")}) == Color("af65dd"), "personal marks retain saved Color values")
	_expect(Overlay.personal_text_color({"colour": "#123456"}) == Color("123456"), "personal marks retain saved HTML values")
	_expect(Overlay.personal_text_color({"color": [255, 128, 0]}).is_equal_approx(Color(1, 128.0/255.0, 0)), "personal marks retain saved RGB byte values")
	_expect(Overlay.personal_text_color({}) == Color.GREEN, "uncolored personal marks use EL's default green")
	TextColors.set_color("map_personal", Color.MAGENTA)
	_expect(Overlay.personal_text_color({"color": Color.GREEN}) == Color.MAGENTA, "an explicit personal-mark setting wins over saved RGB")
	TextColors.reset("map_personal")
	_expect(Overlay.personal_text_color({"color": Color.GREEN}) == Color.GREEN, "reset restores saved personal-mark RGB")
	var map := Overlay.new()
	root.add_child(map)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(100, 100)
	root.add_child(viewport)
	var camera := Camera3D.new()
	viewport.add_child(camera)
	camera.position = Vector3(0, 10, 0)
	camera.rotation_degrees.x = -90
	await process_frame
	map.size = Vector2(100, 100)
	map.configure(camera, CoordinateAdapter.new({}), Vector2i(100, 100))
	# Looking up the role is separate from icon coloring and hover-label layout.
	map.set_markers([{"position": Vector3.ZERO, "label": "Server mark"}])
	var point := camera.unproject_position(Vector3.ZERO)
	_expect(map.label_at(point) == "Server mark" and map.label_color_at(point) == Color(0.33, 0.6, 1), "server map hover labels use EL's blue")
	map.set_markers([])
	map.set_player_marks([{"position": Vector3.ZERO, "label": "Personal mark", "color": Color.MAGENTA}])
	_expect(map.label_at(point) == "Personal mark" and map.label_color_at(point) == Color.MAGENTA, "personal hover labels keep their individual saved color")
	var atlas := Continent.new()
	root.add_child(atlas)
	atlas.set_current_region(1)
	_expect(atlas.label_color(1) == TextColors.color("map_current"), "current continent region has its own configurable text color")
	atlas.call("_set_hovered", 1)
	TextColors.set_color("map_hover", Color.CYAN)
	_expect(atlas.label_color(1) == Color.CYAN, "hover text updates immediately")
	var labels := MinimapLabels.new()
	root.add_child(labels)
	labels.config = {"text_color": Color.YELLOW, "text_color_custom": false}
	_expect(labels.label_color() == Color.WHITE, "factory minimap labels use the shared default")
	TextColors.set_color("map_minimap", Color.CYAN)
	_expect(labels.label_color() == Color.CYAN, "minimap labels respond to the text-color setting")
	labels.config.text_color_custom = true
	_expect(labels.label_color() == Color.YELLOW, "custom HUD minimap tint retains precedence")
	var tooltip := Tooltip.new()
	root.add_child(tooltip)
	tooltip.tooltip_text_color = Color.CYAN
	var hover: Label = tooltip._make_custom_tooltip("Server mark")
	root.add_child(hover)
	_expect(hover.get_theme_color("font_color") == Color.CYAN, "map tooltips display the mark's color")
	tooltip.tooltip_text_color = Color.MAGENTA
	_expect(hover.get_theme_color("font_color") == Color.MAGENTA, "visible map tooltips update without being rebuilt")
	for node: Node in [map, viewport, atlas, labels, tooltip, hover]:
		node.queue_free()
	await process_frame
	# Changing the palette after labels are freed exercises weak bindings.
	TextColors.reset()
	print("map text colors: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
