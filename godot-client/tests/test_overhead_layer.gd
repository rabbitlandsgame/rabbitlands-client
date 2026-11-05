extends SceneTree
## The 2D overhead layer core (src/ui/overhead/, wave 2 OV-1), headless.
##
## - OverheadStyle's numbers are today's (ReplicatedActor3D, WORLD_LABEL_STYLE,
##   the pointer's Label3D defaults);
## - the fixed-size scale k matches the design's probe A table and an emulated
##   fixed-size billboard, and maps to canvas units and device pixels;
## - projected origins equal Camera3D.unproject_position within 0.01 px
##   (perspective, keep-width, h/v offsets, orthographic, a scaled view);
## - behind-the-camera, off-screen, distance-range (Godot's camera distance rule
##   with margin hysteresis), tree visibility and freed anchors hide items;
## - pass parents are in priority order whatever order they are created in;
##   ranks are far to near, ties in registration order;
## - an update with nothing changed makes no RenderingServer call; camera,
##   fade and content changes send only their own calls;
## - the shaping and re-record budgets bound the work per frame;
## - a raster-scale change re-records once after it settles;
## - the quest pulse formula equals the quest marker's Tween;
## - the text cache keys, reference counts, evicts and lays out text;
## - the runtime switch (set_enabled, active, RABBITLANDS_OVERHEAD_2D /
##   --overhead-2d=) stops all work and resumes without a re-record, and hides
##   the layer's own content root, so an owner's hide/show cycle of the Control
##   cannot bring a switched-off layer back;
## - PER_BANNER keeps one root per item, and an item without content has none;
## - a re-record frees the canvas items it left empty;
## - configure() for another world re-judges the registered anchors.
## Prints placement cost for 160 and 300 banners (headless CPU, not a gate).

const Style := preload("res://src/ui/overhead/overhead_style.gd")
const TextCache := preload("res://src/ui/overhead/overhead_text_cache.gd")
const LayerScript := preload("res://src/ui/overhead/overhead_layer.gd")
const ItemScript := preload("res://src/ui/overhead/overhead_item.gd")
const WORLD_LABEL_STYLE := preload("res://src/ui/world_label_style.gd")

var failures := 0
var _container: TextureRect
var _viewport: SubViewport
var _camera: Camera3D
var _stage: Node3D
var _layer: LayerScript

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	var saved_switch := OS.get_environment(LayerScript.SWITCH_VARIABLE)
	OS.unset_environment(LayerScript.SWITCH_VARIABLE)
	LayerScript.reset_switch()
	root.size = Vector2i(1920, 1080)
	await process_frame
	_check_style()
	_check_switch_parsing()
	_build_world(Vector2i(1920, 1080))
	_check_scale_table()
	_check_device_mapping()
	_check_projection()
	_check_hiding_rules()
	_check_range_rule()
	_check_pass_order()
	_check_ranks()
	_check_quiet_updates()
	_check_shape_budget()
	_check_record_budget()
	_check_settle()
	_check_pulse()
	_check_text_cache()
	_check_builder()
	_check_switch()
	_check_per_banner()
	_check_removal()
	_check_batch_groups()
	_check_hidden_records()
	await _check_frame_signal()
	_report_cost()
	_layer.queue_free()
	LayerScript.reset_switch()
	if saved_switch.is_empty():
		OS.unset_environment(LayerScript.SWITCH_VARIABLE)
	else:
		OS.set_environment(LayerScript.SWITCH_VARIABLE, saved_switch)
	await process_frame
	print("overhead layer tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --- Fixtures ----------------------------------------------------------------------

## main.tscn's arrangement: a full-rect TextureRect showing a SubViewport at
## native size, and the layer beside it in the same parent.
func _build_world(view_size: Vector2i) -> void:
	_container = TextureRect.new()
	_container.name = "ViewportContainer"
	_container.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	root.add_child(_container)
	_container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_viewport = SubViewport.new()
	_viewport.size = view_size
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	_container.add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	_camera = Camera3D.new()
	_camera.fov = 50.0
	_camera.near = 1.0
	_camera.far = 1800.0
	_stage.add_child(_camera)
	_camera.current = true
	_aim(Vector3(0.0, 22.5, 13.0), -60.0)
	_layer = LayerScript.new()
	root.add_child(_layer)
	_layer.configure(_viewport, _container)

func _aim(at: Vector3, pitch_degrees: float, yaw_degrees := 0.0) -> void:
	_camera.global_transform = Transform3D(Basis.from_euler(Vector3(
		deg_to_rad(pitch_degrees), deg_to_rad(yaw_degrees), 0.0)), at)

func _anchor(at: Vector3) -> Node3D:
	var node := Node3D.new()
	_stage.add_child(node)
	node.global_position = at
	return node

func _banner(node: Node3D, text := "Amberhart", point := Vector3(0.0, 2.15, 0.0)) -> ItemScript:
	var item := ItemScript.new(node, point, &"Block")
	item.add_rect(Style.PASS_BACKING, Rect2(-40.0, -10.0, 80.0, 30.0), Style.OVERHEAD_BACKING)
	item.add_rect(Style.PASS_BAR_BACK, Rect2(-29.0, 12.0, 58.0, 9.0), Style.HEALTH_BAR_BACKING)
	item.add_text(text, Style.NAMEPLATE_FONT_SIZE, Vector2.ZERO, Color.YELLOW,
		Style.OVERHEAD_OUTLINE_SIZE)
	return item

## A second layer over the same view. Budgets wide open, so a loaded machine
## cannot defer a shape or a record and turn an order check into a flake.
func _fresh_layer(order_mode := Style.ORDER_LAYERED, batch_groups := true,
		follow_switch := true) -> LayerScript:
	var layer := LayerScript.new()
	layer.order_mode = order_mode
	layer.batch_groups = batch_groups
	layer.follow_switch = follow_switch
	layer.shape_budget_usec = 1000000
	layer.rerecord_budget_usec = 1000000
	root.add_child(layer)
	layer.configure(_viewport, _container)
	return layer

func _clear_layer() -> void:
	for item: Variant in _layer._items.duplicate():
		if item != null:
			_layer.remove_item(item)
	_layer.update_now()
	for child: Node in _stage.get_children():
		if child != _camera:
			child.free()
	_layer.shape_budget_usec = 1000000
	_layer.rerecord_budget_usec = 1000000
	_layer.snap_origins = true
	_layer.now_usec_override = -1
	_aim(Vector3(0.0, 22.5, 13.0), -60.0)

# --- Style -------------------------------------------------------------------------

func _check_style() -> void:
	var actor: GDScript = load("res://src/actors/replicated_actor_3d.gd")
	var constants: Dictionary = actor.get_script_constant_map()
	var twins: Array[String] = ["OVERHEAD_PIXEL", "NAMEPLATE_FONT_SIZE",
		"HEALTH_NUMBER_FONT_SIZE", "SPEECH_BUBBLE_FONT_SIZE", "OVERHEAD_OUTLINE_SIZE",
		"HEALTH_BAR_WIDTH", "HEALTH_BAR_THICKNESS", "HEALTH_BAR_BORDER", "HEALTH_BAR_BACKING",
		"HEALTH_BAR_DROP", "HEALTH_LABEL_DROP", "HEALTH_NUMBER_GAP", "OVERHEAD_BACKING",
		"NEGATIVE_STATUS_SIZE", "NEGATIVE_STATUS_GAP", "NEGATIVE_STATUS_RISE",
		"SPEECH_BUBBLE_RISE", "SPEECH_BUBBLE_WIDTH", "SPEECH_BUBBLE_TEXT",
		"SPEECH_BUBBLE_SURROUND", "TITLE_RISE", "TITLE_FONT_SIZE", "OCCUPATION_DROP",
		"OCCUPATION_FONT_SIZE", "OCCUPATION_COLOUR"]
	var style_constants: Dictionary = (Style as GDScript).get_script_constant_map()
	var mismatched: Array[String] = []
	for key: String in twins:
		if not constants.has(key) or not style_constants.has(key) or constants[key] != style_constants[key]:
			mismatched.append(key)
	expect(mismatched.is_empty(), "OverheadStyle equals ReplicatedActor3D's overhead constants: %s" % [mismatched])
	var label := Label3D.new()
	WORLD_LABEL_STYLE.apply(label, 12, Style.OVERHEAD_PIXEL, 4)
	expect(label.outline_render_priority == Style.PASS_TEXT_OUTLINE
		and label.render_priority == Style.PASS_TEXT,
		"text passes are WORLD_LABEL_STYLE's priorities (%d/%d)" % [label.outline_render_priority, label.render_priority])
	label.free()
	var pointer := Label3D.new()
	expect(pointer.outline_render_priority == Style.PASS_POINTER_OUTLINE
		and pointer.render_priority == Style.PASS_BACKING,
		"pointer passes are Label3D's default priorities -1/0")
	pointer.free()
	var ascending := true
	for index: int in range(1, Style.PASSES.size()):
		ascending = ascending and Style.PASSES[index - 1] < Style.PASSES[index]
	expect(ascending and Style.PASSES.size() == 7, "passes are listed in ascending priority")
	expect(is_equal_approx(Style.OVERHEAD_PIXEL, 2.0 * tan(deg_to_rad(25.0)) / 720.0),
		"OVERHEAD_PIXEL is 2 tan(25 deg) / 720")
	expect(is_equal_approx(Style.design_scale(Style.POINTER_PIXEL), 0.00075 / 0.0012953)
		and Style.font() == ThemeDB.fallback_font, "design_scale and the fallback font")

func _check_switch_parsing() -> void:
	var none := LayerScript.resolve_switch("", PackedStringArray())
	expect(none.mode == "" and none.source == "", "no request: default")
	var env_off := LayerScript.resolve_switch("3d", PackedStringArray())
	expect(env_off.mode == "off" and env_off.source == "environment", "RABBITLANDS_OVERHEAD_2D=3d is off")
	var arg_on := LayerScript.resolve_switch("off", PackedStringArray(["--overhead-2d=on"]))
	expect(arg_on.mode == "on" and arg_on.source == "argument", "the argument wins over the environment")
	var bad := LayerScript.resolve_switch("maybe", PackedStringArray(["--overhead-2d=2d"]))
	expect(bad.mode == "on" and Array(bad.rejected) == ["maybe"], "unknown spellings are rejected, 2d is on")
	for spelling: String in ["0", "false", "no", "legacy", "OFF"]:
		expect(LayerScript.resolve_switch(spelling, PackedStringArray()).mode == "off",
			"'%s' is off" % spelling)
	expect(LayerScript.enabled() == LayerScript.DEFAULT_ENABLED, "enabled() follows the default without a request")

# --- Scale and projection ----------------------------------------------------------

func _check_scale_table() -> void:
	# Design probe A: native px per design px on the 50-degree camera.
	var table := {Vector2i(1280, 720): 1.0, Vector2i(1920, 1080): 1.5,
		Vector2i(2560, 1440): 2.0, Vector2i(3440, 1440): 2.0, Vector2i(1024, 768): 768.0 / 720.0}
	var node := _anchor(Vector3(3.0, 0.0, -4.0))
	var item := _banner(node)
	_layer.add_item(item)
	for view_size: Vector2i in table.keys():
		_viewport.size = view_size
		_layer.update_now()
		expect(absf(_layer.scale_k() - float(table[view_size])) < 0.0005,
			"k at %s is %.4f (design table %.4f)" % [view_size, _layer.scale_k(), table[view_size]])
	# An emulated fixed-size billboard: 10 design px up the screen at the anchor's depth.
	_viewport.size = Vector2i(1920, 1080)
	_layer.update_now()
	var anchor_point := node.global_position + Vector3(0.0, 2.15, 0.0)
	var depth := -(_camera.get_camera_transform().affine_inverse() * anchor_point).z
	var up := _camera.global_transform.basis.y * (10.0 * Style.OVERHEAD_PIXEL * depth)
	var moved := _camera.unproject_position(anchor_point).y - _camera.unproject_position(anchor_point + up).y
	expect(absf(moved - 10.0 * _layer.scale_k()) < 0.02,
		"10 design px of a fixed-size billboard cover %.3f px = 10 k (%.3f)" % [moved, 10.0 * _layer.scale_k()])
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 40.0
	_layer.update_now()
	expect(absf(_layer.scale_k() - Style.OVERHEAD_PIXEL * 1080.0 * 0.5) < 0.0005,
		"orthographic k is OVERHEAD_PIXEL * H / 2, as the fixed-size shader scales")
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	_clear_layer()

func _check_device_mapping() -> void:
	var item := _banner(_anchor(Vector3(0.0, 0.0, -4.0)))
	_layer.add_item(item)
	_layer.update_now()
	# 1920x1080 window, 1280x720 design: the container is 1280x720 canvas units
	# over a 1920x1080 viewport, so a design px is 1 canvas unit, 1.5 device px.
	expect(absf(_layer.canvas_scale() - 1.0) < 0.001, "canvas units per design px at 1080p: %.4f" % _layer.canvas_scale())
	expect(absf(_layer.device_scale() - 1.5) < 0.001, "device px per canvas unit at 1080p: %.4f" % _layer.device_scale())
	expect(is_equal_approx(_layer.oversampling(), 1.5), "text is rasterised at 1.5x (%.4f)" % _layer.oversampling())
	expect(is_equal_approx(item.drawn_scale(), _layer.canvas_scale()), "items are placed at the canvas scale")
	# The viewport's own resolution cancels: same canvas scale at half resolution.
	_viewport.size = Vector2i(960, 540)
	_layer.update_now()
	expect(absf(_layer.canvas_scale() - 1.0) < 0.001, "canvas scale does not depend on the render resolution")
	_viewport.size = Vector2i(1920, 1080)
	_clear_layer()

func _check_projection() -> void:
	_layer.snap_origins = false
	var points: Array[Vector3] = [Vector3(0, 0, 0), Vector3(-6, 0, -8), Vector3(7, 1, -12),
		Vector3(4, 0, 6), Vector3(-3, 0, 3), Vector3(0, 40, 40)]
	var items: Array = []
	for point: Vector3 in points:
		var item := _banner(_anchor(point))
		_layer.add_item(item)
		items.append(item)
	var cases := [
		["perspective 1080p", Vector2i(1920, 1080), Camera3D.KEEP_HEIGHT, 0.0, 0.0, false],
		["keep width 4:3", Vector2i(1024, 768), Camera3D.KEEP_WIDTH, 0.0, 0.0, false],
		["h/v offset 21:9", Vector2i(3440, 1440), Camera3D.KEEP_HEIGHT, 0.6, -0.4, false],
		["orthographic", Vector2i(1920, 1080), Camera3D.KEEP_HEIGHT, 0.0, 0.0, true],
	]
	for case: Array in cases:
		_viewport.size = case[1]
		_camera.keep_aspect = case[2]
		_camera.h_offset = case[3]
		_camera.v_offset = case[4]
		_camera.projection = Camera3D.PROJECTION_ORTHOGONAL if case[5] else Camera3D.PROJECTION_PERSPECTIVE
		_camera.size = 60.0
		_aim(Vector3(1.0, 22.5, 13.0), -60.0, 8.0)
		_layer.update_now()
		var view_scale := _container.size / Vector2(_viewport.size)
		var worst := 0.0
		var checked := 0
		for item: ItemScript in items:
			var point: Vector3 = item.anchor.node.global_transform * item.anchor.point
			if _camera.is_position_behind(point):
				expect(not item.is_drawn(), "%s: an anchor behind the camera is not drawn" % case[0])
				continue
			var expected := _container.position + _camera.unproject_position(point) * view_scale
			if not item.is_drawn():
				continue
			worst = maxf(worst, (item.drawn_origin() - expected).length())
			checked += 1
		expect(checked >= 3 and worst < 0.01,
			"%s: %d origins equal unproject_position (worst %.5f units)" % [case[0], checked, worst])
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.h_offset = 0.0
	_camera.v_offset = 0.0
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	_viewport.size = Vector2i(1920, 1080)
	# Snapped origins land on whole device pixels.
	_layer.snap_origins = true
	_aim(Vector3(0.37, 22.5, 13.11), -60.0, 3.3)
	_layer.update_now()
	var whole := true
	for item: ItemScript in items:
		if item.is_drawn():
			var device := item.drawn_origin() * _layer.device_scale()
			whole = whole and device.is_equal_approx(device.round())
	expect(whole, "snapped origins are whole device pixels")
	_clear_layer()

func _check_hiding_rules() -> void:
	var front := _banner(_anchor(Vector3(0, 0, 0)))
	var behind := _banner(_anchor(Vector3(0, 40, 40)))
	var aside := _banner(_anchor(Vector3(400, 0, -10)))
	var parent := Node3D.new()
	_stage.add_child(parent)
	var child := Node3D.new()
	parent.add_child(child)
	var nested := _banner(child)
	var doomed_node := _anchor(Vector3(2, 0, 0))
	var doomed := _banner(doomed_node)
	for item: ItemScript in [front, behind, aside, nested, doomed]:
		_layer.add_item(item)
	_layer.update_now()
	expect(front.is_drawn() and nested.is_drawn() and doomed.is_drawn(), "anchors in view are drawn")
	expect(not behind.is_drawn(), "an anchor behind the near plane is hidden")
	expect(not aside.is_drawn(), "an item whose extent is off screen is culled")
	parent.hide()
	doomed_node.free()
	front.fade = 0.0
	_layer.update_now()
	expect(not nested.is_drawn(), "an item follows its anchor's tree visibility")
	expect(not doomed.is_drawn(), "a freed anchor hides its item without errors")
	expect(not front.is_drawn(), "fade 0 hides an item")
	nested.follow_tree_visibility = false
	front.fade = 1.0
	front.visible = false
	_layer.update_now()
	expect(nested.is_drawn(), "follow_tree_visibility off leaves tree visibility to the producer")
	expect(not front.is_drawn(), "visible = false hides an item")
	front.visible = true
	_layer.visible = false
	_layer.update_now()
	expect(not _layer.drawing and _layer.items_drawn == 0, "a hidden layer draws nothing")
	_layer.visible = true
	_viewport.remove_child(_stage)
	_layer.update_now()
	expect(not _layer.drawing, "no camera, no drawing")
	_viewport.add_child(_stage)
	_camera.current = true
	_layer.update_now()
	expect(_layer.drawing and front.is_drawn(), "drawing resumes with the camera")
	var elsewhere := SubViewport.new()
	elsewhere.own_world_3d = true
	root.add_child(elsewhere)
	var stranger := Node3D.new()
	elsewhere.add_child(stranger)
	expect(_layer.accepts(front.anchor.node) and not _layer.accepts(stranger),
		"accepts() only nodes of the layer's world")
	expect(LayerScript.for_world(_viewport.find_world_3d()) == _layer
		and LayerScript.for_world(elsewhere.find_world_3d()) == null
		and LayerScript.current() == _layer, "for_world() and current() find the layer")
	var foreign := ItemScript.new(stranger, Vector3.ZERO, &"Foreign")
	foreign.add_rect(Style.PASS_BACKING, Rect2(-10, -10, 20, 20), Color.BLACK)
	_layer.add_item(foreign)
	_layer.update_now()
	expect(not foreign.is_drawn(), "an anchor in another world never draws")
	_layer.configure(elsewhere, null)
	var in_world := func(item: ItemScript) -> bool:
		return (_layer._anchor_state[item.anchor._slot] & LayerScript.A_IN_WORLD) != 0
	expect(in_world.call(foreign) and not in_world.call(front),
		"configure() for another world re-judges the registered anchors")
	_layer.configure(_viewport, _container)
	expect(not in_world.call(foreign) and in_world.call(front), "and back")
	_layer.remove_item(foreign)
	elsewhere.free()
	var before := front.drawn_origin()
	front.set_anchor_point(Vector3(0.0, 4.0, 0.0))
	_layer.update_now()
	expect(front.drawn_origin().y < before.y - 10.0, "set_anchor_point moves the projected origin")
	_clear_layer()

func _check_range_rule() -> void:
	# The camera stands at the origin looking down -z; distance is Euclidean
	# from the camera's position, as RendererSceneCull measures visibility ranges.
	_aim(Vector3.ZERO, 0.0)
	var node := _anchor(Vector3(0, 0, -20))
	var item := _banner(node, "Door", Vector3.ZERO)
	item.range_end = 20.0
	_layer.add_item(item)
	_layer.update_now()
	expect(item.is_drawn(), "at exactly range_end the item shows (hidden only beyond it)")
	node.global_position = Vector3(0, 0, -20.01)
	_layer.update_now()
	expect(not item.is_drawn(), "beyond range_end the item hides")
	item.range_end_margin = 1.0
	node.global_position = Vector3(0, 0, -19.5)
	_layer.update_now()
	expect(not item.is_drawn(), "hidden: shows again only within range_end - margin")
	node.global_position = Vector3(0, 0, -18.9)
	_layer.update_now()
	expect(item.is_drawn(), "within range_end - margin it shows")
	node.global_position = Vector3(0, 0, -20.9)
	_layer.update_now()
	expect(item.is_drawn(), "shown: hides only beyond range_end + margin")
	node.global_position = Vector3(3.0, 4.0, -21.2)
	_layer.update_now()
	expect(not item.is_drawn(), "distance is Euclidean (|(3,4,-21.2)| = %.2f > 21)" % Vector3(3, 4, -21.2).length())
	_clear_layer()

# --- Order -------------------------------------------------------------------------

func _check_pass_order() -> void:
	var fresh := _fresh_layer()
	var item := ItemScript.new(_anchor(Vector3.ZERO), Vector3.ZERO)
	item.add_text("!", 30, Vector2.ZERO, Color.WHITE, 2)
	item.add_rect(Style.PASS_ICONS, Rect2(0, 0, 20, 20), Color.WHITE)
	item.add_rect(Style.PASS_BACKING, Rect2(0, 0, 4, 4), Color.BLACK)
	item.add_rect(Style.PASS_POINTER_OUTLINE, Rect2(0, 0, 4, 4), Color.BLACK)
	item.add_rect(Style.PASS_BAR_FILL, Rect2(0, 0, 4, 4), Color.GREEN)
	fresh.add_item(item)
	fresh.update_now()
	var expected: Array[int] = [Style.PASS_POINTER_OUTLINE, Style.PASS_BACKING, Style.PASS_BAR_FILL,
		Style.PASS_ICONS, Style.PASS_TEXT_OUTLINE, Style.PASS_TEXT]
	expect(fresh.pass_order() == expected, "pass parents draw in priority order: %s" % [fresh.pass_order()])
	var indices: Array = []
	for pass_id: int in fresh.pass_order():
		indices.append(fresh._pass_draw_index[pass_id])
	expect(indices == [0, 1, 3, 4, 5, 6], "pass draw indices are positions in PASSES: %s" % [indices])
	expect(item.canvas_items().size() == 6 and fresh.pass_parent(Style.PASS_BAR_BACK) == RID(),
		"one canvas item per used pass, parents only for used passes")
	fresh.free()
	_clear_layer()

func _check_ranks() -> void:
	_aim(Vector3.ZERO, 0.0)
	var near := _banner(_anchor(Vector3(0, 0, -10)), "Near")
	var far := _banner(_anchor(Vector3(1, 0, -30)), "Far")
	var middle := _banner(_anchor(Vector3(-1, 0, -20)), "Middle")
	var sharing := ItemScript.new(null, Vector3.ZERO, &"Quest")
	sharing.share_anchor(middle)
	sharing.add_text("!", 30, Vector2(0, -36), Color.YELLOW, 2)
	for item: ItemScript in [near, far, middle, sharing]:
		_layer.add_item(item)
	_layer.update_now()
	expect(far.rank() == 0 and middle.rank() == 1 and sharing.rank() == 2 and near.rank() == 3,
		"ranks run far to near, ties in registration order: far %d middle %d quest %d near %d"
			% [far.rank(), middle.rank(), sharing.rank(), near.rank()])
	expect(_layer.anchors_projected == 3, "a shared anchor is projected once (%d)" % _layer.anchors_projected)
	far.anchor.node.global_position = Vector3(1, 0, -5)
	_layer.update_now()
	expect(middle.rank() == 0 and sharing.rank() == 1 and near.rank() == 2 and far.rank() == 3,
		"ranks follow a move: the moved item is now nearest")
	_clear_layer()

func _check_quiet_updates() -> void:
	var items: Array = []
	for index: int in range(12):
		var item := _banner(_anchor(Vector3(index * 2.0 - 11.0, 0, -index * 1.5)), "Walker %d" % index)
		_layer.add_item(item)
		items.append(item)
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 12 and _layer.items_drawn == 12, "first update records and draws all 12")
	_layer.update_now()
	expect(_layer.rs_calls_this_frame == 0 and _layer.rerecords_this_frame == 0,
		"an update with nothing changed makes no RenderingServer call (%d)" % _layer.rs_calls_this_frame)
	_aim(Vector3(0.0, 22.5, 13.0), -60.0, 0.5)
	_layer.update_now()
	var per_item := (items[0] as ItemScript).canvas_items().size()
	expect(_layer.rerecords_this_frame == 0 and _layer.rs_calls_this_frame == 12 * per_item
		and _layer.rank_changes_this_frame == 0,
		"a camera move sends one transform per canvas item and nothing else (%d calls)" % _layer.rs_calls_this_frame)
	(items[3] as ItemScript).fade = 0.5
	_layer.update_now()
	expect(_layer.rs_calls_this_frame == per_item and _layer.rerecords_this_frame == 0,
		"a fade sends one modulate per canvas item, no re-record (%d)" % _layer.rs_calls_this_frame)
	(items[5] as ItemScript).clear()
	(items[5] as ItemScript).add_rect(Style.PASS_BACKING, Rect2(-10, -10, 20, 20), Color.BLACK)
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 1, "a content change re-records that item only")
	_layer.update_now()
	expect(_layer.rs_calls_this_frame == 0, "and the next quiet update is quiet again")
	_clear_layer()

func _check_shape_budget() -> void:
	_layer.shape_budget_usec = 1
	var items: Array = []
	for index: int in range(20):
		var item := ItemScript.new(_anchor(Vector3(index - 10.0, 0, -index * 0.5)), Vector3(0, 2, 0))
		item.add_text("Budgeted Walker %d" % (index * 7919 % 10007), 12, Vector2.ZERO, Color.WHITE, 4)
		_layer.add_item(item)
		items.append(item)
	var drawn: Array[int] = []
	for _frame: int in range(4):
		_layer.update_now()
		drawn.append(_layer.items_drawn)
	expect(drawn == [1, 2, 3, 4], "a 1 us budget shapes one text a frame, unshaped items wait: %s" % [drawn])
	expect(_layer.text_cache.shaped_this_frame == 1 and _layer.text_cache.deferred_this_frame > 0,
		"the cache reports deferred shapes")
	_layer.shape_budget_usec = 1000000
	_layer.update_now()
	expect(_layer.items_drawn == 20, "with room in the budget the rest are shaped in one frame")
	_clear_layer()

func _check_record_budget() -> void:
	_layer.rerecord_budget_usec = 0
	for index: int in range(5):
		var item := ItemScript.new(_anchor(Vector3(index - 2.0, 0, -index)), Vector3(0, 2, 0))
		item.add_rect(Style.PASS_BACKING, Rect2(-10, -10, 20, 20), Color.BLACK)
		_layer.add_item(item)
	var drawn: Array[int] = []
	for _frame: int in range(3):
		_layer.update_now()
		drawn.append(_layer.items_drawn)
	expect(drawn == [1, 2, 3] and _layer.rerecords_deferred == 2,
		"a spent re-record budget defers the rest (at least one a frame): %s" % [drawn])
	_clear_layer()

func _check_settle() -> void:
	var item := _banner(_anchor(Vector3(0, 0, -3)))
	var bare := ItemScript.new(_anchor(Vector3(2, 0, -3)), Vector3.ZERO)
	bare.add_rect(Style.PASS_BACKING, Rect2(-10, -10, 20, 20), Color.BLACK)
	_layer.add_item(item)
	_layer.add_item(bare)
	_layer.now_usec_override = 1000000
	_layer.update_now()
	var first := _layer.oversampling()
	_camera.fov = 40.0
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 0 and is_equal_approx(_layer.oversampling(), first)
		and absf(item.drawn_scale() - _layer.canvas_scale()) < 0.0001,
		"a new scale moves the transform at once and keeps the raster (%.4f -> %.4f)" % [first, _layer.canvas_scale() * _layer.device_scale()])
	_layer.now_usec_override = 1000000 + Style.SCALE_SETTLE_USEC - 1
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 0, "no re-record before the scale has settled")
	_layer.now_usec_override = 1000000 + Style.SCALE_SETTLE_USEC
	_layer.update_now()
	var expected := snappedf(_layer.canvas_scale() * _layer.device_scale(), Style.OVERSAMPLING_STEP)
	expect(_layer.rerecords_this_frame == 1 and is_equal_approx(_layer.oversampling(), expected),
		"after %d ms the text items re-record once at %.4f (rect-only items do not)" % [Style.SCALE_SETTLE_USEC / 1000, expected])
	_camera.fov = 50.0
	_clear_layer()

func _check_pulse() -> void:
	var colour := Color(1.0, 0.85, 0.2)
	var bright := colour.lightened(Style.QUEST_LIGHTEN)
	var item := ItemScript.new()
	item.set_pulse(0, Style.QUEST_PULSE_HALF_SECONDS, Vector2(0, -Style.QUEST_RISE_FROM),
		Vector2(0, -Style.QUEST_RISE_TO), colour, bright)
	# The quest marker's Tween (replicated_actor_3d.gd set_quest_available).
	var label := Label3D.new()
	label.modulate = colour
	label.offset = Vector2(0.0, Style.QUEST_RISE_FROM)
	var tween := create_tween().set_loops()
	tween.tween_property(label, "modulate", bright, Style.QUEST_PULSE_HALF_SECONDS)
	tween.parallel().tween_property(label, "offset:y", Style.QUEST_RISE_TO,
		Style.QUEST_PULSE_HALF_SECONDS).set_trans(Tween.TRANS_SINE)
	tween.tween_property(label, "modulate", colour, Style.QUEST_PULSE_HALF_SECONDS)
	tween.parallel().tween_property(label, "offset:y", Style.QUEST_RISE_FROM,
		Style.QUEST_PULSE_HALF_SECONDS).set_trans(Tween.TRANS_SINE)
	tween.pause()
	var worst_offset := 0.0
	var worst_colour := 0.0
	var step := 0.1
	for index: int in range(1, 41):
		tween.custom_step(step)
		var state: Array = item.pulse_state(int(round(index * step * 1000000.0)))
		worst_offset = maxf(worst_offset, absf(-(state[0] as Vector2).y - label.offset.y))
		var tint: Color = state[1]
		worst_colour = maxf(worst_colour, maxf(absf(tint.r - label.modulate.r),
			maxf(absf(tint.g - label.modulate.g), absf(tint.b - label.modulate.b))))
	tween.kill()
	label.free()
	expect(worst_offset < 0.01 and worst_colour < 0.002,
		"the pulse formula follows the quest Tween over 4 s (offset %.4f px, colour %.4f)" % [worst_offset, worst_colour])
	# Applied per frame as an offset and a pass tint, without a re-record.
	var placed := _banner(_anchor(Vector3(0, 0, -3)), "Quest giver")
	placed.set_pulse(0, Style.QUEST_PULSE_HALF_SECONDS, Vector2(0, -Style.QUEST_RISE_FROM),
		Vector2(0, -Style.QUEST_RISE_TO), colour, bright)
	_layer.add_item(placed)
	_layer.snap_origins = false
	_layer.now_usec_override = 0
	_layer.update_now()
	var start := placed.drawn_origin()
	_layer.now_usec_override = 800000
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 0 and absf(start.y - placed.drawn_origin().y
		- (Style.QUEST_RISE_TO - Style.QUEST_RISE_FROM) * placed.drawn_scale()) < 0.001
		and placed.pass_modulate(Style.PASS_TEXT).is_equal_approx(bright),
		"the layer bobs and tints a pulsing item without re-recording it")
	placed.clear_pulse()
	expect(placed.pass_modulate(Style.PASS_TEXT) == Color.WHITE, "clear_pulse restores the tint")
	_clear_layer()

# --- Text --------------------------------------------------------------------------

func _check_text_cache() -> void:
	var cache := TextCache.new()
	cache.now_usec_override = 0
	expect(TextCache.key_for("Amberhart", 12) == "12|0|1|Amberhart", "key is size|wrap|alignment|text")
	var size := cache.measure("Amberhart", 12)
	var line := TextLine.new()
	line.add_string("Amberhart", ThemeDB.fallback_font, 12)
	expect(size.is_equal_approx(line.get_size()), "measure() is TextLine's size (%s)" % size)
	var long_speech := "The tide is out past the Lakehead docks, so mind the mud on the far bank before you cross."
	var wrapped := cache.entry(long_speech, 15, 270)
	cache.shape(wrapped, true)
	expect(wrapped.paragraph != null and wrapped.paragraph.get_line_count() >= 2
		and is_equal_approx(wrapped.box_width, 270.0) and wrapped.size.x <= 270.0,
		"speech wraps at 270 design px (%d lines, widest %.1f)" % [wrapped.paragraph.get_line_count() if wrapped.paragraph else 0, wrapped.size.x])
	var door := cache.entry("Calloway's Books\nClick to enter", 15)
	cache.shape(door, true)
	var widest := cache.measure("Calloway's Books", 15).x
	expect(door.paragraph != null and door.paragraph.get_line_count() == 2
		and absf(door.box_width - widest) < 0.5, "a two-line label aligns within its widest line")
	# Reference counts and eviction on an injected clock.
	cache.idle_usec = 1000
	var held := cache.entry("Held", 12)
	cache.acquire(held)
	cache.now_usec_override = 5000
	var dropped := cache.sweep(true)
	expect(cache.has_entry("Held", 12), "a held entry is never evicted")
	expect(dropped == 4 and cache.size() == 1, "idle entries are dropped after idle_usec (%d dropped)" % dropped)
	cache.release(held)
	cache.now_usec_override = 5500
	expect(cache.sweep(true) == 0, "a released entry waits idle_usec")
	cache.now_usec_override = 6000
	expect(cache.sweep(true) == 1 and cache.size() == 0, "then goes")
	# Through the layer: recordings hold their texts, removal releases them.
	var item := _banner(_anchor(Vector3(0, 0, -3)), "Refcounted")
	_layer.add_item(item)
	_layer.update_now()
	var entry := _layer.text_cache.entry("Refcounted", 12)
	expect(entry.refs == 1, "a recorded item holds its text (refs %d)" % entry.refs)
	item.clear()
	item.add_text("Renamed", 12, Vector2.ZERO, Color.WHITE)
	_layer.update_now()
	expect(entry.refs == 0 and _layer.text_cache.entry("Renamed", 12).refs == 1,
		"a re-record swaps the held texts")
	_layer.remove_item(item)
	expect(_layer.text_cache.entry("Renamed", 12).refs == 0, "removal releases the text")
	_clear_layer()

func _check_builder() -> void:
	var calls := [0]
	var item := ItemScript.new(_anchor(Vector3(0, 0, -3)), Vector3(0, 2, 0))
	item.builder = func(target: ItemScript, cache: TextCache) -> bool:
		calls[0] += 1
		var width := cache.measure("Built", 12).x
		target.clear()
		target.add_rect(Style.PASS_BACKING, Rect2(-width * 0.5 - 4.0, -10.0, width + 8.0, 20.0), Color.BLACK)
		target.add_text("Built", 12, Vector2.ZERO, Color.WHITE, 4)
		return true
	_layer.add_item(item)
	_layer.update_now()
	_layer.update_now()
	expect(calls[0] == 1 and item.is_drawn() and item.ops().size() == 2,
		"a builder runs once at the first record")
	item.invalidate()
	_layer.update_now()
	expect(calls[0] == 2 and _layer.rerecords_this_frame == 1, "invalidate() runs it again")
	var waiting := ItemScript.new(_anchor(Vector3(1, 0, -3)), Vector3(0, 2, 0))
	waiting.builder = func(_target: ItemScript, _cache: TextCache) -> bool:
		return false
	_layer.add_item(waiting)
	_layer.update_now()
	expect(not waiting.is_drawn() and not waiting.is_recorded(), "a builder that is not ready keeps the item hidden")
	_clear_layer()

# --- Switch ------------------------------------------------------------------------

func _check_switch() -> void:
	var items: Array = []
	for index: int in range(6):
		var item := _banner(_anchor(Vector3(index - 3.0, 0, -index)), "Switch %d" % index)
		_layer.add_item(item)
		items.append(item)
	var loner := _fresh_layer(Style.ORDER_LAYERED, true, false)
	_layer.update_now()
	var heard: Array = []
	var listener := func(on: bool) -> void: heard.append(on)
	LayerScript.events().switched.connect(listener)
	LayerScript.set_enabled(false)
	expect(heard == [false] and not _layer.active and loner.active and not LayerScript.enabled(),
		"set_enabled(false) turns following layers off and tells producers")
	_layer.update_now()
	expect(not _layer.drawing and _layer.rs_calls_this_frame == 0 and _layer.items_drawn == 0,
		"an inactive layer does no work (%d calls, %d us)" % [_layer.rs_calls_this_frame, _layer.last_update_usec])
	expect((items[0] as ItemScript).is_recorded(), "an inactive layer keeps its recordings")
	expect(not (items[0] as ItemScript).is_drawn() and (items[0] as ItemScript).rank() == -1,
		"an inactive layer reports its items as not drawn")
	# main.gd's _sync_world_overlay_visibility hides and shows the overlays
	# (full map, console). CanvasItem.set_visible writes the Control's own canvas
	# item at the server, so the layer hides a content root of its own: an
	# owner's hide/show cycle must not bring a switched-off layer's last frame back.
	_layer.visible = false
	_layer.visible = true
	_layer.update_now()
	expect(_layer.content_root().is_valid() and _layer.content_root() != _layer.get_canvas_item()
		and not _layer.content_shown() and _layer.rs_calls_this_frame == 0,
		"the layer hides its own content root, not the Control's canvas item, while switched off")
	LayerScript.set_enabled(false)
	expect(heard == [false], "setting the same state again is silent")
	LayerScript.set_enabled(true)
	_layer.update_now()
	expect(heard == [false, true] and _layer.active and _layer.items_drawn == 6
		and _layer.rerecords_this_frame == 0 and _layer.content_shown()
		and (items[0] as ItemScript).is_drawn(),
		"switching back draws again without a re-record")
	OS.set_environment(LayerScript.SWITCH_VARIABLE, "off")
	LayerScript.reset_switch()
	expect(not LayerScript.enabled() and heard == [false, true, false],
		"RABBITLANDS_OVERHEAD_2D=off is the launch default after reset_switch()")
	OS.unset_environment(LayerScript.SWITCH_VARIABLE)
	LayerScript.reset_switch()
	expect(LayerScript.enabled() == LayerScript.DEFAULT_ENABLED and _layer.active == LayerScript.DEFAULT_ENABLED,
		"and back to the default")
	LayerScript.events().switched.disconnect(listener)
	_layer.active = false
	_layer.active = true
	_layer.update_now()
	expect(_layer.items_drawn == 6 and _layer.rerecords_this_frame == 0, "`active` toggles one layer")
	loner.free()
	_clear_layer()

func _check_per_banner() -> void:
	var layer := _fresh_layer(Style.ORDER_PER_BANNER)
	var items: Array = []
	for index: int in range(5):
		var item := _banner(_anchor(Vector3(index - 2.0, 0, -index * 4.0)), "Banner %d" % index)
		layer.add_item(item)
		items.append(item)
	# An item with no content yet (a producer's builder that drew nothing) has
	# no root: placing, ranking and fading it must not address an empty RID
	# (the RenderingServer would print an error each time).
	var empty := ItemScript.new(_anchor(Vector3(0.5, 0, -1.0)), Vector3(0, 2, 0), &"Empty")
	layer.add_item(empty)
	layer.update_now()
	var roots := true
	for item: ItemScript in items:
		roots = roots and item._root.is_valid() and item.canvas_items().size() == 4 and item.is_drawn()
	expect(roots and layer._pass_parents.is_empty(), "PER_BANNER: one root per item holding its passes")
	expect(empty.is_drawn() and not empty._root.is_valid(), "PER_BANNER: an empty item has no root")
	_aim(Vector3(0.0, 22.5, 13.0), -60.0, 0.5)
	empty.fade = 0.5
	layer.update_now()
	expect(layer.rs_calls_this_frame == 5,
		"PER_BANNER: one transform call per item, none for the empty one (%d)" % layer.rs_calls_this_frame)
	expect((items[4] as ItemScript).rank() == 0, "PER_BANNER keeps far-to-near ranks")
	empty.add_rect(Style.PASS_BACKING, Rect2(-5, -5, 10, 10), Color.BLACK)
	layer.update_now()
	expect(empty._root.is_valid() and empty.is_drawn() and empty.canvas_items().size() == 1,
		"PER_BANNER: content gives the item its root")
	layer.free()
	_clear_layer()

func _check_batch_groups() -> void:
	var icon_a := GradientTexture2D.new()
	var icon_b := GradientTexture2D.new()
	var make := func(layer: LayerScript) -> Array:
		var made: Array = []
		for index: int in range(4):
			var item := ItemScript.new(_anchor(Vector3(index - 2.0, 0, -index * 3.0)), Vector3(0, 2, 0))
			item.add_text("Name %d" % index, Style.NAMEPLATE_FONT_SIZE, Vector2.ZERO, Color.WHITE, 4)
			item.add_text("%d/9" % index, Style.HEALTH_NUMBER_FONT_SIZE, Vector2(30, 16), Color.WHITE, 4)
			item.add_texture_rect(Style.PASS_ICONS, Rect2(-20, -40, 20, 20), icon_a if index % 2 == 0 else icon_b)
			layer.add_item(item)
			made.append(item)
		layer.update_now()
		return made
	var grouped := _fresh_layer()
	var items: Array = make.call(grouped)
	var sizes: Array[int] = [11, 12]
	var textures: Array[int] = [LayerScript.TEXTURE_GROUP_BASE, LayerScript.TEXTURE_GROUP_BASE + 1]
	var single: Array[int] = [0]
	expect(grouped.pass_groups(Style.PASS_TEXT) == sizes
		and grouped.pass_groups(Style.PASS_TEXT_OUTLINE) == sizes,
		"text batches by font size inside its pass: %s" % [grouped.pass_groups(Style.PASS_TEXT)])
	expect(grouped.pass_groups(Style.PASS_ICONS) == textures, "texture rects batch by texture")
	expect((items[0] as ItemScript).canvas_items().size() == 5,
		"an item keeps one canvas item per pass and group (2 sizes x outline/fill + icon)")
	expect((items[3] as ItemScript).rank() == 0 and (items[0] as ItemScript).rank() == 3,
		"ranks still run far to near inside every group")
	# A re-record frees the canvas items it no longer draws into: an actor whose
	# status icons change keeps one canvas item per icon it shows, not one per
	# icon kind it has ever shown (each would still be moved and ranked).
	var changing: ItemScript = items[1]
	var icons: Array[Texture2D] = [icon_a, icon_b, GradientTexture2D.new(), GradientTexture2D.new()]
	var counts: Array[int] = []
	for icon: Texture2D in icons:
		changing.clear()
		changing.add_texture_rect(Style.PASS_ICONS, Rect2(-20, -40, 20, 20), icon)
		grouped.update_now()
		counts.append(changing.canvas_items().size())
	expect(counts == [1, 1, 1, 1] and changing.is_drawn() and grouped._slot_rids[changing._index].size() == 1,
		"a re-record frees the canvas items it left empty: %s" % [counts])
	grouped.update_now()
	expect(grouped.rs_calls_this_frame == 0, "and the next update is quiet")
	grouped.free()
	var strict := _fresh_layer(Style.ORDER_LAYERED, false)
	items = make.call(strict)
	expect(strict.pass_groups(Style.PASS_TEXT) == single
		and (items[0] as ItemScript).canvas_items().size() == 3,
		"batch_groups off keeps one canvas item per pass (the strict per-pass order)")
	strict.free()
	_clear_layer()

func _check_hidden_records() -> void:
	var item := _banner(_anchor(Vector3(0, 0, -3)), "Hidden at first")
	item.visible = false
	_layer.add_item(item)
	_layer.update_now()
	expect(not item.is_recorded() and _layer.rerecords_this_frame == 0, "a hidden item is not recorded")
	item.visible = true
	_layer.update_now()
	expect(item.is_recorded() and item.is_drawn() and _layer.rerecords_this_frame == 1,
		"it is recorded and drawn in the update that first shows it")
	item.fade = 0.0
	item.clear()
	item.add_text("Changed while faded out", 12, Vector2.ZERO, Color.WHITE)
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 0, "a change while faded out waits")
	item.fade = 1.0
	_layer.update_now()
	expect(_layer.rerecords_this_frame == 1 and item.is_drawn(), "and records when it fades in")
	_clear_layer()

func _check_removal() -> void:
	var a := _banner(_anchor(Vector3(0, 0, -2)), "A")
	var b := _banner(_anchor(Vector3(1, 0, -4)), "B")
	var c := _banner(_anchor(Vector3(2, 0, -6)), "C")
	for item: ItemScript in [a, b, c]:
		_layer.add_item(item)
	_layer.update_now()
	_layer.remove_item(b)
	expect(b.canvas_items().is_empty() and b.layer() == null and _layer.item_count() == 2,
		"removal frees the item's canvas items")
	_layer.update_now()
	expect(a._index == 0 and c._index == 1 and _layer.items_drawn == 2, "slots compact in order")
	_layer.add_item(b)
	_layer.update_now()
	expect(b.is_drawn() and b._index == 2, "a removed item can be added again")
	_clear_layer()

func _check_frame_signal() -> void:
	var item := _banner(_anchor(Vector3(0, 0, -3)), "Signal")
	_layer.add_item(item)
	var before := _layer.frames_updated
	await process_frame
	await process_frame
	var headless := DisplayServer.get_name() == "headless"
	expect(not headless or _layer.frames_updated == before,
		"headless, frame_pre_draw never fires: no update without update_when_headless")
	_layer.update_when_headless = true
	await process_frame
	await process_frame
	await process_frame
	expect(_layer.frames_updated > before and item.is_drawn(),
		"the layer updates itself each frame (frame_pre_draw; process_frame when headless): %d frames"
			% (_layer.frames_updated - before))
	_layer.update_when_headless = false
	before = _layer.frames_updated
	await process_frame
	expect(not headless or _layer.frames_updated == before, "update_when_headless off stops it again")
	var stats := _layer.stats()
	for key: String in ["last_update_usec", "items_drawn", "rerecords_this_frame", "rs_calls_this_frame",
			"k", "oversampling", "text"]:
		expect(stats.has(key), "stats() reports %s" % key)
	_clear_layer()

# --- Cost (printed, not asserted) ----------------------------------------------------

func _report_cost() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for count: int in [160, 300]:
		for index: int in range(count):
			var item := _banner(_anchor(Vector3(rng.randf_range(-25, 25), 0, rng.randf_range(-35, 5))),
				"Crowd Walker %d" % (index * 7919 % 10007))
			_layer.add_item(item)
		_layer.update_now()
		var first_record := _layer.last_update_usec
		var samples := PackedFloat64Array()
		for frame: int in range(120):
			var yaw := frame * 0.01
			_camera.global_transform = Transform3D(Basis.from_euler(Vector3(deg_to_rad(-60), yaw, 0)),
				Vector3(sin(yaw) * 13, 22.5, cos(yaw) * 13))
			_layer.update_now()
			samples.append(_layer.last_update_usec)
		samples.sort()
		var total := 0.0
		for value: float in samples:
			total += value
		print("COST overhead layer %d banners (4 canvas items each, orbiting camera): first record %d us; update mean %.1f us p50 %.1f p95 %.1f; last frame place %d us apply %d us; drawn %d"
			% [count, first_record, total / samples.size(), samples[samples.size() / 2],
				samples[int(samples.size() * 0.95)], _layer.last_place_usec, _layer.last_apply_usec,
				_layer.items_drawn])
		_clear_layer()
