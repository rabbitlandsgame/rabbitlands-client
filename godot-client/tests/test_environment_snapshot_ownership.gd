extends SceneTree
## Functional copy contract plus a real renderer lifecycle. On Compatibility,
## shutdown stderr must also be clean: the former copy creates two orphan GL
## sky textures before the first draw, without retaining a Resource or RID.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)

func _run() -> void:
	var script := load("res://src/app/main.gd") as GDScript
	if script == null or not script.can_instantiate():
		_expect(false, "Main compiles for environment snapshot ownership")
		quit(1)
		return
	var main := script.new() as Control
	var source_sky := Sky.new()
	source_sky.radiance_size = Sky.RADIANCE_SIZE_128
	source_sky.process_mode = Sky.PROCESS_MODE_QUALITY
	var source_material := ProceduralSkyMaterial.new()
	source_material.sky_top_color = Color(0.12, 0.24, 0.48)
	source_sky.sky_material = source_material
	var live := Environment.new()
	live.background_mode = Environment.BG_SKY
	live.sky = source_sky
	var gradient := Gradient.new()
	gradient.set_color(0, Color.RED)
	var glow := GradientTexture2D.new()
	glow.gradient = gradient
	live.glow_map = glow
	var viewport := SubViewport.new()
	viewport.size = Vector2i(64, 64)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var environment_node := WorldEnvironment.new()
	environment_node.environment = live
	viewport.add_child(environment_node)
	var camera := Camera3D.new()
	camera.current = true
	viewport.add_child(camera)
	root.add_child(viewport)
	# Deliberately before the first draw, matching the production bind sequence.
	main.call("_keep_unlooked_environment", live)
	var snapshot := main.get("_unlooked_environment") as Environment
	var kept: Dictionary = main.get("_unlooked_sky")
	_expect(live.sky == source_sky and live.sky.sky_material == source_material,
		"snapshot never mutates the live environment or its Sky")
	_expect(snapshot != null and snapshot != live and snapshot.sky == null,
		"stored environment is independent and contains no Sky")
	var kept_material := kept.get("material") as ProceduralSkyMaterial
	_expect(kept_material != null and kept_material != source_material
		and kept_material.sky_top_color == source_material.sky_top_color,
		"stored sky material is independently copied")
	_expect(int(kept.radiance_size) == Sky.RADIANCE_SIZE_128 and int(kept.process_mode) == Sky.PROCESS_MODE_QUALITY,
		"stored Sky settings are preserved")
	var snapshot_glow := snapshot.glow_map as GradientTexture2D
	_expect(snapshot_glow != null and snapshot_glow != glow and snapshot_glow.gradient != gradient,
		"remaining environment resources and nested resources retain deep-copy independence")
	var top_before := source_material.sky_top_color
	source_material.sky_top_color = Color(0.7, 0.1, 0.2)
	gradient.set_color(0, Color.BLUE)
	_expect(kept_material.sky_top_color == top_before and snapshot_glow.gradient.get_color(0) == Color.RED,
		"live day/night and resource edits cannot alter the stored snapshot")
	var restored := main.call("_unlooked_environment_copy") as Environment
	var restored_sky := restored.sky
	var restored_material := restored_sky.sky_material as ProceduralSkyMaterial
	_expect(restored_sky != source_sky and restored_material != kept_material and restored_material != source_material,
		"recreated environment owns a fresh Sky and another independent material")
	_expect(restored_sky.radiance_size == Sky.RADIANCE_SIZE_128 and restored_sky.process_mode == Sky.PROCESS_MODE_QUALITY,
		"recreated Sky retains its declared radiance and processing mode")
	restored_material.sky_top_color = Color.GREEN
	_expect(kept_material.sky_top_color == top_before,
		"day/night edits of a restored copy do not contaminate future restores")
	# Keep every deliberately created Sky alive until the renderer has drained
	# its dirty queue. Only the production snapshot call must avoid a new Sky.
	for index: int in 4:
		await process_frame
	environment_node.environment = null
	viewport.free()
	restored.sky = null
	restored_sky = null
	restored = null
	live.sky = null
	source_sky = null
	live = null
	main.set("_unlooked_environment", null)
	main.set("_unlooked_sky", {})
	main.free()
	for index: int in 4:
		await process_frame
	print("ENVIRONMENT_SNAPSHOT_OWNERSHIP failures=", failures)
	quit(0 if failures == 0 else 1)
