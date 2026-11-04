extends SceneTree
## Windowed probe for the 2D overhead layer core (wave 2 OV-1). A renderer
## correctness check, not a timing gate: run it windowed under the GPU lock,
## once per renderer (Forward+, `--rendering-method mobile`,
## `--rendering-method gl_compatibility`).
##
## Claims checked:
## 1. Batching. N banners (default 300; ELORIA_OVERHEAD_PROBE_BANNERS) drawn
##    through the layer cost a handful of 2D draw calls on the root viewport
##    (Viewport.RENDER_INFO_TYPE_CANVAS), not a few per banner: Godot 4.7.2
##    batches consecutive RenderingServer canvas items that share a texture,
##    and the LAYERED pass parents put like with like. ORDER_PER_BANNER is
##    measured beside it for the record (it interleaves textures per banner).
## 2. Crisp text. Text the layer draws at the fixed-size scale (1.5 native
##    pixels per design pixel at 1920x1080) rasterises pixel for pixel like the
##    same string drawn by an ordinary Control (CanvasItem.draw_string with the
##    viewport's own oversampling): explicit oversampling = what 2D text gets.
## 3. The runtime switch works in a window: with the layer switched off the
##    canvas draw calls fall back to the scene without banners, also after a
##    hide/show cycle of the layer's Control (main.gd hides the overlays for
##    the full map and the console).
## 4. Texture rects draw an AtlasTexture's region, not its whole atlas.
## Also reported, informational only (single run, no interleaving): the root
## viewport's GPU time with the layer on and off, and the layer's CPU update.
##
## Output: one line `OVERHEAD_LAYER_PROBE {json}`, and PNGs (the crowd, the
## text pair, 4x nearest-neighbour crops) under ELORIA_ARTIFACT_DIR or
## res://test-artifacts/overhead-layer-probe/<renderer>/. Exit code = failures.

const Style := preload("res://src/ui/overhead/overhead_style.gd")
const LayerScript := preload("res://src/ui/overhead/overhead_layer.gd")
const ItemScript := preload("res://src/ui/overhead/overhead_item.gd")

const SCREEN_SIZE := Vector2i(1920, 1080)
const SAMPLE_FRAMES := 90
const WARM_FRAMES := 30
## A banner's canvas draw calls must stay below this in total for N banners
## (LAYERED): a handful per pass, not per banner.
const BATCHED_CALL_LIMIT := 40
const TEXT_SAMPLE := "Crownwater Wyvern 62/100"

var _failures := 0
var _artifacts := ""
var _renderer := ""
var _container: TextureRect
var _viewport: SubViewport
var _camera: Camera3D
var _stage: Node3D
var _layer: LayerScript
var _items: Array = []
var _gradient: GradientTexture2D
var _summary := {}

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, label: String) -> void:
	if ok:
		print("PASS: ", label)
	else:
		_failures += 1
		push_error("FAIL: " + label)

func _run() -> void:
	_renderer = RenderingServer.get_current_rendering_method()
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/overhead-layer-probe")
	_artifacts = _artifacts.path_join(_renderer)
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK, "artifact directory is writable")
	_expect(DisplayServer.get_name() != "headless", "the probe runs windowed")
	root.size = SCREEN_SIZE
	var banners := int(OS.get_environment("ELORIA_OVERHEAD_PROBE_BANNERS")) \
		if not OS.get_environment("ELORIA_OVERHEAD_PROBE_BANNERS").is_empty() else 300
	_summary = {"renderer": _renderer, "adapter": RenderingServer.get_video_adapter_name(),
		"banners": banners, "window": [SCREEN_SIZE.x, SCREEN_SIZE.y]}
	_build_world()
	_build_banners(banners)
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	RenderingServer.viewport_set_measure_render_time(_viewport.get_viewport_rid(), true)
	for _frame: int in range(WARM_FRAMES):
		await process_frame
	_expect(_layer.items_drawn >= banners * 0.9,
		"%d of %d banners are drawn after warm-up" % [_layer.items_drawn, banners])
	_summary["k"] = _layer.scale_k()
	_summary["oversampling"] = _layer.oversampling()
	_summary["canvas_scale"] = _layer.canvas_scale()

	# ABAB within one run: layer on, off, on, off.
	var phases: Array = []
	for phase: String in ["layered_on", "off", "layered_on", "off"]:
		LayerScript.set_enabled(phase != "off")
		for _frame: int in range(6):
			await process_frame
		phases.append(await _sample(phase))
	LayerScript.set_enabled(true)
	var on_calls := _mean_of(phases, "layered_on", "canvas_draw_calls")
	var off_calls := _mean_of(phases, "off", "canvas_draw_calls")
	_summary["phases"] = phases
	_summary["canvas_draw_calls_layer"] = on_calls - off_calls
	_expect(on_calls - off_calls <= BATCHED_CALL_LIMIT,
		"%d banners add %.1f canvas draw calls (LAYERED; limit %d)" % [banners, on_calls - off_calls, BATCHED_CALL_LIMIT])
	_expect(_mean_of(phases, "off", "items_drawn") == 0.0, "switched off, the layer draws nothing")
	# An owner's hide/show cycle (main.gd _sync_world_overlay_visibility: full
	# map, console) while switched off must not bring the last frame back.
	LayerScript.set_enabled(false)
	for _frame: int in range(6):
		await process_frame
	_layer.visible = false
	await process_frame
	_layer.visible = true
	for _frame: int in range(6):
		await process_frame
	var cycled := await _sample("off_after_hide_show")
	phases.append(cycled)
	_expect(absf(float(cycled.canvas_draw_calls) - off_calls) < 0.5,
		"switched off, a hide/show cycle of the Control draws nothing (%.1f canvas draw calls, off %.1f)"
			% [cycled.canvas_draw_calls, off_calls])
	LayerScript.set_enabled(true)
	for _frame: int in range(6):
		await process_frame
	_summary["root_gpu_ms_layer"] = _mean_of(phases, "layered_on", "root_gpu_ms") \
		- _mean_of(phases, "off", "root_gpu_ms")

	await _capture("crowd-layered.png")

	# The strict per-pass order (batch_groups off) for the record.
	var strict := LayerScript.new()
	strict.batch_groups = false
	strict.follow_switch = false
	root.add_child(strict)
	strict.configure(_viewport, _container)
	_layer.active = false
	_layer.follow_switch = false
	for item: ItemScript in _items:
		strict.add_item(item)
	for _frame: int in range(WARM_FRAMES):
		await process_frame
	var strict_sample := await _sample("layered_strict", strict)
	_summary["layered_strict"] = strict_sample
	_summary["canvas_draw_calls_strict"] = float(strict_sample.canvas_draw_calls) - off_calls
	await _capture("crowd-layered-strict.png")
	strict.queue_free()

	# PER_BANNER for the record.
	var per_banner := LayerScript.new()
	per_banner.order_mode = Style.ORDER_PER_BANNER
	per_banner.follow_switch = false
	root.add_child(per_banner)
	per_banner.configure(_viewport, _container)
	for item: ItemScript in _items:
		per_banner.add_item(item)
	for _frame: int in range(WARM_FRAMES):
		await process_frame
	var per_banner_sample := await _sample("per_banner", per_banner)
	_summary["per_banner"] = per_banner_sample
	_summary["canvas_draw_calls_per_banner"] = float(per_banner_sample.canvas_draw_calls) - off_calls
	await _capture("crowd-per-banner.png")
	for item: ItemScript in _items:
		_layer.add_item(item)
	per_banner.queue_free()
	_layer.follow_switch = true
	_layer.active = true

	await _check_text_pair()
	await _check_atlas_region()
	print("OVERHEAD_LAYER_PROBE ", JSON.stringify(_summary))
	print("overhead layer probe (%s): %s" % [_renderer, "PASS" if _failures == 0 else "FAIL (%d)" % _failures])
	quit(_failures)

func _build_world() -> void:
	_container = TextureRect.new()
	_container.name = "ViewportContainer"
	_container.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	root.add_child(_container)
	_container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_viewport = SubViewport.new()
	_viewport.size = SCREEN_SIZE
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_container.add_child(_viewport)
	_container.texture = _viewport.get_texture()
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 30.0, 0.0)
	_stage.add_child(sun)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(200.0, 200.0)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.32, 0.42, 0.24)
	plane.material = material
	ground.mesh = plane
	_stage.add_child(ground)
	_camera = Camera3D.new()
	_camera.fov = 50.0
	_camera.near = 1.0
	_camera.far = 1800.0
	_stage.add_child(_camera)
	_camera.current = true
	_camera.global_transform = Transform3D(Basis.from_euler(Vector3(deg_to_rad(-60.0), 0.0, 0.0)),
		Vector3(0.0, 22.5, 13.0))
	_layer = LayerScript.new()
	root.add_child(_layer)
	_layer.configure(_viewport, _container)
	_gradient = GradientTexture2D.new()
	_gradient.width = 1
	_gradient.height = 16
	_gradient.fill_to = Vector2(0.0, 1.0)
	_gradient.gradient = Gradient.new()
	_gradient.gradient.colors = PackedColorArray([Color.WHITE, Color(0.45, 0.45, 0.45)])

## Banner-shaped items (backing, bar, gradient fill, name and numbers with
## outlines) on a grid that fills the view.
func _build_banners(count: int) -> void:
	var columns := 20
	var rows := ceili(float(count) / columns)
	for index: int in range(count):
		var column := index % columns
		var row := index / columns
		var node := Node3D.new()
		_stage.add_child(node)
		node.global_position = Vector3(lerpf(-19.0, 19.0, column / float(columns - 1)), 0.0,
			lerpf(7.0, -15.0, row / float(maxi(1, rows - 1))))
		var item := ItemScript.new(node, Vector3(0.0, 2.15, 0.0), &"Block")
		item.add_rect(Style.PASS_BACKING, Rect2(-44.0, -9.0, 88.0, 33.0), Style.OVERHEAD_BACKING)
		item.add_rect(Style.PASS_BAR_BACK, Rect2(-41.0, 11.5, 58.0, 9.0), Style.HEALTH_BAR_BACKING)
		item.add_texture_rect(Style.PASS_BAR_FILL, Rect2(-40.0, 12.5, 56.0 * (0.3 + 0.7 * fposmod(index * 0.37, 1.0)), 7.0),
			_gradient, Color(0.2, 0.85, 0.1))
		item.add_text("Walker %d" % (index * 7919 % 10007), Style.NAMEPLATE_FONT_SIZE, Vector2.ZERO,
			Color(1.0, 1.0, 0.0), Style.OVERHEAD_OUTLINE_SIZE)
		item.add_text("%d/100" % (index % 100), Style.HEALTH_NUMBER_FONT_SIZE, Vector2(31.0, 16.0),
			Color.WHITE, Style.OVERHEAD_OUTLINE_SIZE)
		_layer.add_item(item)
		_items.append(item)

func _sample(label: String, layer: LayerScript = null) -> Dictionary:
	var target := layer if layer != null else _layer
	var calls := 0.0
	var total_calls := 0.0
	var root_gpu := 0.0
	var world_gpu := 0.0
	var update_usec := PackedFloat64Array()
	var drawn := 0.0
	for _frame: int in range(SAMPLE_FRAMES):
		await RenderingServer.frame_post_draw
		calls += root.get_render_info(Viewport.RENDER_INFO_TYPE_CANVAS, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME)
		total_calls += RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)
		root_gpu += RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid())
		world_gpu += RenderingServer.viewport_get_measured_render_time_gpu(_viewport.get_viewport_rid())
		update_usec.append(target.last_update_usec)
		drawn += target.items_drawn
	update_usec.sort()
	var mean_update := 0.0
	for value: float in update_usec:
		mean_update += value
	return {"phase": label, "canvas_draw_calls": calls / SAMPLE_FRAMES,
		"total_draw_calls": total_calls / SAMPLE_FRAMES, "root_gpu_ms": root_gpu / SAMPLE_FRAMES,
		"world_gpu_ms": world_gpu / SAMPLE_FRAMES, "items_drawn": drawn / SAMPLE_FRAMES,
		"update_usec_mean": mean_update / update_usec.size(),
		"update_usec_p95": update_usec[int(update_usec.size() * 0.95)]}

func _mean_of(phases: Array, label: String, key: String) -> float:
	var total := 0.0
	var count := 0
	for phase: Dictionary in phases:
		if phase.phase == label:
			total += float(phase[key])
			count += 1
	return total / maxi(1, count)

func _capture(file_name: String) -> void:
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.save_png(_artifacts.path_join(file_name))

## Claim 4: a texture rect draws any Texture2D as a Control would, so an
## AtlasTexture shows its region and not its whole atlas (an AtlasTexture's RID
## is the atlas's). The atlas is 4 red texels then 4 blue; the region is the
## blue half, so every sample inside the drawn rect must be blue, where the
## whole atlas would put red at its left quarter.
func _check_atlas_region() -> void:
	for banner: ItemScript in _items:
		banner.visible = false
	var image := Image.create(8, 1, false, Image.FORMAT_RGBA8)
	for x: int in range(8):
		image.set_pixel(x, 0, Color.RED if x < 4 else Color.BLUE)
	var atlas := AtlasTexture.new()
	atlas.atlas = ImageTexture.create_from_image(image)
	atlas.region = Rect2(4.0, 0.0, 4.0, 1.0)
	var node := Node3D.new()
	_stage.add_child(node)
	node.global_position = _camera.project_position(Vector2(SCREEN_SIZE) * Vector2(0.6, 0.5), 20.0)
	var item := ItemScript.new(node, Vector3.ZERO, &"Atlas")
	item.add_texture_rect(Style.PASS_ICONS, Rect2(-20.0, -20.0, 40.0, 40.0), atlas)
	_layer.add_item(item)
	for _frame: int in range(60):
		await process_frame
		if item.is_drawn():
			break
	_expect(item.is_drawn(), "the atlas item is drawn")
	if item.is_drawn():
		await RenderingServer.frame_post_draw
		var shot := root.get_texture().get_image()
		var device_scale := _layer.device_scale()
		var per_design := item.drawn_scale() * device_scale
		var centre := item.drawn_origin() * device_scale
		var colours: Array = []
		var blue := true
		for dx: float in [-10.0, 0.0, 10.0]:
			var colour := shot.get_pixelv(Vector2i((centre + Vector2(dx * per_design, 0.0)).round()))
			colours.append([snappedf(colour.r, 0.01), snappedf(colour.g, 0.01), snappedf(colour.b, 0.01)])
			blue = blue and colour.b > 0.9 and colour.r < 0.1 and colour.g < 0.1
		var half := Vector2(24.0, 24.0) * per_design
		var crop := shot.get_region(Rect2i(Vector2i((centre - half).round()), Vector2i((half * 2.0).ceil())))
		crop.save_png(_artifacts.path_join("atlas-region.png"))
		_summary["atlas_region"] = colours
		_expect(blue, "an AtlasTexture draws its region, not its whole atlas (samples %s)" % [colours])
	_layer.remove_item(item)
	node.queue_free()
	for banner: ItemScript in _items:
		banner.visible = true

## Claim 2: the layer's text against the same string drawn by a Control.
func _check_text_pair() -> void:
	for item: ItemScript in _items:
		item.visible = false
	var backdrop := ColorRect.new()
	backdrop.color = Color(0.18, 0.2, 0.22)
	root.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.move_child(backdrop, _layer.get_index())
	# An anchor that projects near the middle of the view.
	var probe_node := Node3D.new()
	_stage.add_child(probe_node)
	probe_node.global_position = _camera.project_position(Vector2(SCREEN_SIZE) * Vector2(0.4, 0.45), 20.0)
	var item := ItemScript.new(probe_node, Vector3.ZERO, &"Text")
	item.add_text(TEXT_SAMPLE, Style.NAMEPLATE_FONT_SIZE, Vector2.ZERO, Color(1.0, 1.0, 0.0),
		Style.OVERHEAD_OUTLINE_SIZE, Color.BLACK, 0, HORIZONTAL_ALIGNMENT_LEFT, VERTICAL_ALIGNMENT_TOP)
	_layer.add_item(item)
	for _frame: int in range(60):
		await process_frame
		if item.is_drawn():
			break
	_expect(item.is_drawn(), "the text item is drawn")
	if not item.is_drawn():
		return
	var origin := item.drawn_origin()
	var device_scale := _layer.device_scale()
	_expect((origin * device_scale).is_equal_approx((origin * device_scale).round()),
		"the text origin is a whole device pixel (%s)" % (origin * device_scale))
	# The reference: an ordinary Control 60 design px lower, drawing the same
	# string with CanvasItem.draw_string (its own, the viewport's, oversampling).
	var font := Style.font()
	var line := TextLine.new()
	line.add_string(TEXT_SAMPLE, font, Style.NAMEPLATE_FONT_SIZE)
	var reference := Control.new()
	reference.mouse_filter = Control.MOUSE_FILTER_IGNORE
	reference.position = origin + Vector2(0.0, 60.0)
	reference.size = line.get_size() + Vector2(16.0, 16.0)
	reference.draw.connect(func() -> void:
		var baseline := Vector2(0.0, line.get_line_ascent())
		reference.draw_string_outline(font, baseline, TEXT_SAMPLE, HORIZONTAL_ALIGNMENT_LEFT, -1,
			Style.NAMEPLATE_FONT_SIZE, Style.OVERHEAD_OUTLINE_SIZE, Color.BLACK)
		reference.draw_string(font, baseline, TEXT_SAMPLE, HORIZONTAL_ALIGNMENT_LEFT, -1,
			Style.NAMEPLATE_FONT_SIZE, Color(1.0, 1.0, 0.0)))
	root.add_child(reference)
	# A Label beside it, for the eye (its layout differs; not compared).
	var label := Label.new()
	label.text = TEXT_SAMPLE
	label.add_theme_font_size_override("font_size", Style.NAMEPLATE_FONT_SIZE)
	label.add_theme_constant_override("outline_size", Style.OVERHEAD_OUTLINE_SIZE)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_color_override("font_color", Color(1.0, 1.0, 0.0))
	label.position = origin + Vector2(0.0, 120.0)
	root.add_child(label)
	for _frame: int in range(3):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.save_png(_artifacts.path_join("text-pair.png"))
	var crop_size := Vector2i(((line.get_size() + Vector2(12.0, 8.0)) * device_scale).ceil())
	var layer_at := Vector2i(((origin - Vector2(4.0, 4.0)) * device_scale).round())
	var reference_at := Vector2i(((reference.position - Vector2(4.0, 4.0)) * device_scale).round())
	var layer_crop := image.get_region(Rect2i(layer_at, crop_size))
	var reference_crop := image.get_region(Rect2i(reference_at, crop_size))
	var label_crop := image.get_region(Rect2i(Vector2i(((label.position - Vector2(4.0, 4.0)) * device_scale).round()),
		crop_size + Vector2i(0, 12)))
	var differing := 0
	var worst := 0.0
	for y: int in range(crop_size.y):
		for x: int in range(crop_size.x):
			var a := layer_crop.get_pixel(x, y)
			var b := reference_crop.get_pixel(x, y)
			var delta := maxf(absf(a.r - b.r), maxf(absf(a.g - b.g), absf(a.b - b.b)))
			worst = maxf(worst, delta)
			if delta > 2.0 / 255.0:
				differing += 1
	for pair: Array in [[layer_crop, "text-layer-4x.png"], [reference_crop, "text-control-4x.png"],
			[label_crop, "text-label-4x.png"]]:
		var crop: Image = (pair[0] as Image).duplicate()
		crop.resize(crop.get_width() * 4, crop.get_height() * 4, Image.INTERPOLATE_NEAREST)
		crop.save_png(_artifacts.path_join(str(pair[1])))
	_summary["text_pair"] = {"crop": [crop_size.x, crop_size.y], "differing_pixels": differing,
		"worst_channel_delta": worst, "oversampling": _layer.oversampling(),
		"root_oversampling": root.get_oversampling()}
	_expect(differing == 0,
		"the layer's text equals a Control's draw_string pixel for pixel (%d of %d differ, worst %.3f)"
			% [differing, crop_size.x * crop_size.y, worst])
	reference.queue_free()
	label.queue_free()
	backdrop.queue_free()
	_layer.remove_item(item)
	for banner: ItemScript in _items:
		banner.visible = true
