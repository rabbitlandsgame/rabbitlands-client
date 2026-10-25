extends SceneTree
## Production-path regression checks for device graphics preferences. Use an
## isolated user directory; renderer checks build arguments without restarting.

const Options := preload("res://src/world/graphics_options.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Launch := preload("res://src/updates/launch_options.gd")
const Budget := preload("res://src/world/live_effect_budget.gd")
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	if "--texture-import-check" in OS.get_cmdline_user_args():
		_check_active_texture_import()
		print("texture tier import tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
		quit(0 if failures == 0 else 1)
		return
	var saved_config: Variant = FileAccess.get_file_as_bytes(Options.SETTINGS_PATH) \
		if FileAccess.file_exists(Options.SETTINGS_PATH) else null
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	var saved_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_check_images()
	_check_renderer()
	_check_budget()
	root.size = Vector2i(1280, 720)
	var main := load("res://src/app/main.tscn").instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	var layer: Weather3D = main.get("weather_layer")
	var window: Control = main.get("settings_window")
	main.call("_on_client_setting_changed", "Graphics", "quality", LookProfile.Quality.HIGH)
	var rain: Array = [1, 100, 70, 20, 20, 10, 0]
	layer.set_state(rain, rain, 0.0, true, true)
	expect(layer.falling("rain") == 2200, "high quality starts full settled rain")
	main.call("_on_client_setting_changed", "Graphics", "quality", LookProfile.Quality.LOW)
	expect(layer.falling("rain") == 1100 and not layer.settling(),
		"quality change immediately halves settled rain without starting a transition")
	layer.set_state(rain, [2, 100, 80, 30, 20, 10, 0], 8.0)
	var from: PackedFloat32Array = layer.get("_from")
	main.call("_on_client_setting_changed", "Graphics", "particles", false)
	expect(layer.settling() and layer.get("_ease_seconds") == 8.0 and layer.get("_from") == from,
		"effects toggle preserves the existing weather transition")
	layer.place_fire(Vector3.ZERO, 0, Vector2i.ZERO)
	var fires: Dictionary = layer.get("_fires")
	var fire: GPUParticles3D = fires[Vector2i.ZERO]
	var fire_at := fire.global_position
	layer.follow(Vector3(12, 0, 0))
	expect(fire.global_position == fire_at, "camera-following weather does not move a tile's fire")
	layer.follow(Vector3.ZERO)
	expect(not fire.emitting and fire.layers == 0 and not fire.get_node("Glow").visible
		and fire.get_node("StillFlame").visible, "new fire with effects off has a still cue and no particles or light")
	main.call("_on_client_setting_changed", "Graphics", "particles", true)
	expect(fire.emitting and fire.layers == 1 and not fire.get_node("StillFlame").visible,
		"effects on restores the existing fire")
	for index: int in range(1, 8):
		layer.place_fire(Vector3(index, 0, 0), 0, Vector2i(index, 0))
	var lights := 0
	for value: GPUParticles3D in fires.values():
		if value.get_node("Glow").visible:
			lights += 1
	expect(lights == Weather3D.FIRE_LIGHTS_BY_QUALITY[0], "low quality limits real fire lights")
	main.call("_apply_performance_preset")
	var viewport: SubViewport = main.get("main_viewport")
	expect(is_equal_approx(viewport.scaling_3d_scale, 0.75) and viewport.size == root.size,
		"performance scales only the 3D buffer, keeping native viewport coordinates")
	var text_overlay: TextureRect = main.get("_world_text_overlay")
	text_overlay.show()
	text_overlay.call("_sync_camera")
	expect(text_overlay.get("text_viewport").size == viewport.size
		and text_overlay.get("text_viewport").scaling_3d_scale == 1.0, "text pass stays at native resolution")
	var crowd: RefCounted = main.get("crowd")
	expect(crowd.get("body_cap") == 60 and crowd.get("full_rate_bodies") == 8
		and crowd.get("half_rate_bodies") == 8 and crowd.get("cloth_bodies") == 0,
		"performance lowers crowd, animation and cloth work")
	expect(Engine.max_fps == 30 and main.get("_effects_enabled")
		and not main.get("_shadows_enabled") and not Options.decorative_grass,
		"performance caps frames and decoration while keeping combat cues")
	var stored := ConfigFile.new()
	stored.load(Options.SETTINGS_PATH)
	expect(main.get("_vsync_preference") == "off"
		and stored.get_value("graphics", "vsync_mode", "") == "off",
		"performance preset applies and saves vertical sync Off")
	expect(stored.get_value("graphics", "map_texture_quality") == "half"
		and stored.get_value("graphics", "render_scale") == 0.75
		and stored.get_value("graphics", "crowd_bodies") == 60, "preset persists device preferences")
	expect(Options.active_texture_skip() == 0, "texture preference waits for a restart")
	main.call("_on_client_setting_changed", "Graphics", "render_scale", 0.5)
	main.call("_on_window_size_changed")
	expect(viewport.scaling_3d_scale == 0.5, "resizing preserves a custom render scale")
	main.call("_load_hud_settings")
	expect(viewport.scaling_3d_scale == 0.5 and crowd.get("body_cap") == 60,
		"reload restores render scale and crowd limits")
	window.call("open_tab", "Graphics")
	main.get_node("GameView").show()
	main.get_node("LoginPanel").hide()
	for _frame: int in 8:
		await process_frame
	expect(window.get("panel").size.y <= 720, "graphics controls fit a 720p screen")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var capture := OS.get_environment("RABBITLANDS_GRAPHICS_CAPTURE")
		if not capture.is_empty():
			expect(root.get_texture().get_image().save_png(capture) == OK, "graphics UI capture saved")
	main.queue_free()
	await process_frame
	Engine.max_fps = 0
	if saved_config != null:
		var file := FileAccess.open(Options.SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_config)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(Options.SETTINGS_PATH))
	OS.set_environment(LookProfile.QUALITY_VARIABLE, saved_quality)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, saved_look)
	print("low end graphics tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)

func _check_images() -> void:
	var source := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	source.fill(Color(0.2, 0.4, 0.6, 1.0))
	source.generate_mipmaps()
	for skip: int in [1, 2]:
		var reduced := Options.reduced_image(source, skip)
		expect(reduced.get_width() == 64 >> skip and reduced.get_height() == 64 >> skip
			and reduced.get_data().size() < source.get_data().size() / 3,
			"decoded texture tier %d reduces resident bytes" % skip)
	expect(source.get_width() == 64, "reducing an image leaves the shared source intact")
	expect(Options.mip_skip(60, 64, 6, 2, true) == 0,
		"reduced compressed bases always retain valid block alignment")
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://tests/fixtures/vram/shared-assets/vram/index.json"))
	for entry: Dictionary in (index.get("images", {}) as Dictionary).values():
		var descriptor := entry.duplicate()
		descriptor["path"] = "res://tests/fixtures/vram/shared-assets/vram/" + str(entry.file)
		var decoded := Vram.decode_sidecar(descriptor)
		var image: Image = decoded.image
		if image == null:
			expect(false, "compressed fixture decodes: " + str(decoded.reason))
			continue
		var reduced := Options.reduced_image(image, 1)
		expect(reduced.is_compressed() and reduced.get_format() == image.get_format()
			and reduced.get_width() == image.get_width() / 2
			and reduced.get_data().size() == image.get_data().size() - image.get_mipmap_offset(1),
			"reduced sidecar keeps its GPU compression and remaining mip chain")
	var manifest := {"externalResources": {"a.png": "x"}}
	var original_skip := Options.active_texture_skip()
	var token := Vram.cache_token(manifest, "res://tests/fixtures/vram")
	Options._texture_skip = 1
	expect(token != Vram.cache_token(manifest, "res://tests/fixtures/vram"),
		"scene cache separates full and reduced textures")
	Options._texture_skip = original_skip

func _check_renderer() -> void:
	var config := ConfigFile.new()
	config.load(Options.SETTINGS_PATH)
	var had_renderer := config.has_section_key("graphics", "renderer")
	var previous: Variant = config.get_value("graphics", "renderer", "auto")
	config.set_value("graphics", "renderer", "gl_compatibility")
	config.save(Options.SETTINGS_PATH)
	var launched := Launch.game_arguments([], ["--port=2001"], "C:/Game Folder", false)
	expect(launched.find("--rendering-method") < launched.find("--") and "opengl3" in launched,
		"updater selects the saved renderer before starting the child game")
	config.set_value("graphics", "renderer", "forward_plus")
	config.save(Options.SETTINGS_PATH)
	var compatibility := Launch.game_arguments(["--client-compatibility"], [], "C:/Game Folder", false)
	expect("gl_compatibility" in compatibility and not "forward_plus" in compatibility,
		"compatibility launcher overrides a saved Forward+ preference")
	if had_renderer:
		config.set_value("graphics", "renderer", previous)
	else:
		config.erase_section_key("graphics", "renderer")
	config.save(Options.SETTINGS_PATH)
	var args := Launch.restart_arguments("gl_compatibility", ["--path", "C:/Game Folder"],
		["--server=localhost"])
	expect(args.find("--rendering-method") < args.find("--") and "opengl3" in args
		and "--server=localhost" in args, "renderer restart preserves engine/game argument separation")
	expect(not Launch.needs_renderer_restart("forward_plus", "gl_compatibility",
		["--rendering-method", "gl_compatibility"], [], false), "explicit compatibility launch wins over saved renderer")
	expect(not Launch.needs_renderer_restart("forward_plus", "gl_compatibility", [],
		[Launch.RENDERER_RESTART], false), "engine fallback cannot cause a restart loop")
	expect(Launch.needs_renderer_restart("gl_compatibility", "forward_plus", [], [], false),
		"direct launches honor a saved renderer")

func _check_budget() -> void:
	var budget := Budget.new()
	budget.quality = 0
	expect(budget.limit(&"spell") == 24 and budget.limit(&"number") == 12,
		"low quality halves other fights' visual limits")
	for index: int in 24:
		budget._live[&"spell"] = index + 1
	expect(not budget.admit(&"spell", false) and budget.admit(&"spell", true),
		"player and target effects remain admitted over the low quality limit")

func _check_active_texture_import() -> void:
	OS.set_environment(Vram.ENVIRONMENT, "force")
	Vram.reconfigure()
	Vram.ensure_registered()
	var directory := "res://tests/fixtures/vram"
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + "/world.json"))
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_additional_data(Vram.PLAN_KEY, Vram.plan_for(manifest))
	expect(document.append_from_file(directory + "/world.glb", state) == OK,
		"production image extension imports the map fixture")
	var skip := Options.active_texture_skip()
	expect(skip > 0, "a reduced texture tier was loaded at startup")
	var images := state.get_images()
	for index: int in 4:
		expect(images[index].get_width() == (64 >> skip)
			and images[index] is ImageTexture
			and Vram.IMAGE_FORMATS.values().has((images[index] as ImageTexture).get_format()),
			"map sidecar %d uploads at the chosen tier and stays compressed" % index)
	var extension := preload("res://src/world/external_texture_pool.gd")
	extension.share(state, manifest.externalResources)
	var second := GLTFState.new()
	second.set_additional_data(Vram.PLAN_KEY, Vram.plan_for(manifest))
	expect(document.append_from_file(directory + "/world.glb", second) == OK,
		"a neighboring map imports with reduced textures already pooled")
	extension.share(second, manifest.externalResources)
	expect(is_same(state.get_images()[0], second.get_images()[0]),
		"neighboring maps share one reduced GPU allocation")
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + "/shared-assets/vram/index.json"))
	for sha: String in (index.images as Dictionary):
		var entry: Dictionary = Vram.sidecar_entry(sha, directory + "/shared-assets")
		var decoded := Vram.decode_sidecar(entry)
		var reduced := Options.reduced_image(decoded.image)
		var bytes := Vram.resident_bytes(sha, 999999, PackedStringArray([directory + "/shared-assets"]))
		expect(bytes == reduced.get_data().size(), "streaming budget matches the reduced compressed allocation")
		print("texture tier ", skip, " ", entry.format, " bytes ", entry.gpuBytes, " -> ", bytes)
