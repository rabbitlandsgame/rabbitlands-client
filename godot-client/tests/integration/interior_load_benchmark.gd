extends SceneTree
## One process-cold foreground map load. No Main, network or avatar startup.
## The controller fixture uses production camera/environment/section/cutaway/
## occluder controllers. First-ready means first draw + three grounded physics
## frames, not the actual application curtain. Readbacks are qualification-only.
const Graphics := preload("res://src/world/graphics_options.gd")
const Cache := preload("res://src/world/map_geometry_cache.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const Fingerprint := preload("res://tests/integration/interior_load_benchmark_fingerprint.gd")
const Rig := preload("res://tests/integration/interior_load_benchmark_rig.tscn")
var config: Dictionary
var checks: Array = []
var frames: Array = []
var memory: Array = []
var stage: Node3D
var loader: WorldLoader
var rig: IsometricCameraController
var actor: Node3D
var sections := SecretSections.new()
var cutaway := InteriorCutaway.new()
var fade := OccluderFade.new()
var phase := "setup"
var last_frame_us := 0
var recording := false

func _init() -> void:
	_run.call_deferred()

func _check(ok: bool, label: String, detail: Variant = null) -> void:
	checks.append({"ok":ok,"check":label,"detail":detail})
	print("INTERIOR_CHECK ", "PASS " if ok else "FAIL ", label)

func _json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func _write(path: String, value: Dictionary) -> void:
	var file := FileAccess.open(path,FileAccess.WRITE)
	if file == null:
		push_error("interior benchmark cannot write report: " + path)
		return
	file.store_string(JSON.stringify(value,"  "))
	file.close()

func _frame() -> void:
	var now := Time.get_ticks_usec()
	if recording:
		frames.append({"start_us":last_frame_us,"time_us":now,"frame_ms":float(now-last_frame_us)/1000.0,
			"phase":phase,"focused":DisplayServer.window_is_focused(),
			"process_ms":Performance.get_monitor(Performance.TIME_PROCESS)*1000.0,
			"physics_ms":Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0})
	last_frame_us = now

func _settle(count: int) -> void:
	for index: int in count: await process_frame

func _memory(label: String) -> void:
	memory.append({"phase":label,"time_us":Time.get_ticks_usec(),
		"static_bytes":OS.get_static_memory_usage(),
		"texture_gpu_bytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
		"buffer_gpu_bytes":Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED),
		"video_gpu_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED)})

func _window() -> Dictionary:
	return {"focused":DisplayServer.window_is_focused(),"position":str(DisplayServer.window_get_position()),
		"size":str(DisplayServer.window_get_size()),"low_processor_usage_mode":OS.low_processor_usage_mode,
		"sleep_usec":OS.low_processor_usage_mode_sleep_usec,"max_fps":Engine.max_fps,
		"renderer":RenderingServer.get_current_rendering_method(),"gpu":RenderingServer.get_video_adapter_name()}

func _ground(point: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(point+Vector3.UP*4.0,point+Vector3.DOWN*8.0,8)
	var hit := stage.get_world_3d().direct_space_state.intersect_ray(query)
	return {"hit":not hit.is_empty(),"height":float((hit.get("position",Vector3.ZERO) as Vector3).y)}

func _focus(point: Vector3) -> void:
	actor.position = point
	rig.set_focus(point)
	sections.update(point,true)
	cutaway.update(rig.yaw_degrees,true,sections.current_section(),point)
	fade.update(1.0/60.0,rig.camera,actor)

func _assets() -> Dictionary:
	var timings := {}
	var counts := {}
	for record: Dictionary in GlbSceneCache._geometry_entries.values():
		for key: Variant in record.get("timings_us",{}):
			timings[str(key)] = int(timings.get(str(key),0))+int(record.timings_us[key])
		for key: Variant in record.get("diagnostics",{}).get("counts",{}):
			counts[str(key)] = int(counts.get(str(key),0))+int(record.diagnostics.counts[key])
	return {"entries":GlbSceneCache._geometry_entries.size(),"timings_us":timings,"counts":counts,
		"cache":GlbSceneCache.retention_snapshot()}

func _shader_code(code: String, source: String, active: Dictionary) -> String:
	# Qualification-only deterministic animation witness. Expand authored shader
	# includes, then replace standalone TIME tokens, preserving original shaders
	# for the separate pre-controller fingerprint and every timed process.
	var include := RegEx.new()
	include.compile('(?m)^\\s*#include\\s+"([^"]+)"[^\\n]*')
	var matches := include.search_all(code)
	for index: int in range(matches.size()-1,-1,-1):
		var found: RegExMatch = matches[index]
		var path := found.get_string(1)
		if not path.begins_with("res://"): path = source.get_base_dir().path_join(path)
		_check(not active.has(path) and FileAccess.file_exists(path),"shader witness include resolves",path)
		if active.has(path) or not FileAccess.file_exists(path): continue
		active[path] = true
		var expanded := _shader_code(FileAccess.get_file_as_string(path),path,active)
		active.erase(path)
		code = code.substr(0,found.get_start())+expanded+code.substr(found.get_end())
	var time_token := RegEx.new()
	time_token.compile("\\bTIME\\b")
	return time_token.sub(code,"0.0",true)

func _frozen_material(source: Material, materials: Dictionary, shaders: Dictionary) -> Material:
	if source == null: return null
	if materials.has(source.get_instance_id()): return materials[source.get_instance_id()]
	var result := source.duplicate() as Material
	materials[source.get_instance_id()] = result
	if source is ShaderMaterial and (source as ShaderMaterial).shader != null:
		var original := (source as ShaderMaterial).shader
		if not shaders.has(original.get_instance_id()):
			var shader := Shader.new()
			shader.code = _shader_code(original.code,original.resource_path,{})
			shaders[original.get_instance_id()] = shader
		(result as ShaderMaterial).shader = shaders[original.get_instance_id()]
	result.next_pass = _frozen_material(source.next_pass,materials,shaders)
	return result

func _freeze_shader_time() -> Dictionary:
	var materials := {}
	var shaders := {}
	for node: Node in loader.world_root.find_children("*","GeometryInstance3D",true,false):
		var geometry := node as GeometryInstance3D
		if geometry.material_override != null:
			geometry.material_override = _frozen_material(geometry.material_override,materials,shaders)
		if geometry.material_overlay != null:
			geometry.material_overlay = _frozen_material(geometry.material_overlay,materials,shaders)
		if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
			var mesh := node as MeshInstance3D
			for surface: int in mesh.mesh.get_surface_count():
				mesh.set_surface_override_material(surface,_frozen_material(mesh.get_active_material(surface),materials,shaders))
		elif node is MultiMeshInstance3D and (node as MultiMeshInstance3D).multimesh != null:
			var batch := node as MultiMeshInstance3D
			if batch.multimesh.mesh == null: continue
			batch.multimesh = batch.multimesh.duplicate()
			batch.multimesh.mesh = batch.multimesh.mesh.duplicate()
			for surface: int in batch.multimesh.mesh.get_surface_count():
				batch.multimesh.mesh.surface_set_material(surface,_frozen_material(batch.multimesh.mesh.surface_get_material(surface),materials,shaders))
	return {"method":"Qualification-only private Material/Shader copies expand includes and replace standalone TIME tokens with 0.0, identically in both arms; original shader code and full textures are fingerprinted before this change. Timed processes use authored shaders.","materials":materials.size(),"shaders":shaders.size()}

func _qualify(point: Vector3) -> Dictionary:
	# Called only in a separate, explicitly untimed qualification process.
	var frozen := _freeze_shader_time()
	var image_root := str(config.report).get_base_dir().path_join("views")
	DirAccess.make_dir_recursive_absolute(image_root)
	var views: Array = []
	var probes: Array = []
	var points: Array = config.get("qualification_points",[Array([point.x,point.y,point.z])])
	for value: Array in points:
		var position := Vector3(float(value[0]),float(value[1]),float(value[2]))
		_focus(position)
		await physics_frame
		var probe := _ground(position)
		_check(bool(probe.hit),"authored qualification point has navigation ground",value)
		probes.append({"position":value,"ground":probe,"section":sections.current_section()})
		for yaw: float in [0.0,90.0]:
			rig.yaw_degrees = yaw
			_focus(position)
			await _settle(4)
			await RenderingServer.frame_post_draw
			var image := root.get_texture().get_image()
			var context := HashingContext.new()
			context.start(HashingContext.HASH_SHA256)
			context.update(image.get_data())
			var filename := "view-%03d.png" % views.size()
			_check(image.save_png(image_root.path_join(filename)) == OK,"pixel evidence saved",filename)
			views.append({"point":value,"yaw":yaw,"width":image.get_width(),"height":image.get_height(),
				"sha256":context.finish().hex_encode(),"visible":_visibility(),"image":filename,
				"camera_transform":str(rig.camera.global_transform),
				"camera_digest":Fingerprint._hash([rig.global_transform,rig.camera.global_transform,rig.camera.near,rig.camera.far,rig.camera.fov]),
				"fade_state":_fade_state()})
	return {"views":views,"ground":probes,"deterministic_shader_time":frozen}

func _visibility() -> String:
	var values: Array = []
	for node: Node in loader.world_root.find_children("*","Node3D",true,false):
		values.append([Fingerprint._path(loader.world_root,node),(node as Node3D).visible])
	return Fingerprint._hash(values)

func _fade_state() -> Array:
	var result: Array = []
	for occluder: Variant in fade._active:
		var materials: Array = []
		if is_instance_valid(occluder.node) and occluder.node.mesh != null:
			for surface: int in occluder.node.mesh.get_surface_count():
				var material := occluder.node.get_active_material(surface) as Material
				if material is BaseMaterial3D:
					var base := material as BaseMaterial3D
					materials.append({"type":base.get_class(),"alpha":base.albedo_color.a,"transparency":base.transparency,
						"scissor":base.alpha_scissor_threshold,"filter":base.texture_filter})
		result.append({"node":Fingerprint._path(loader.world_root,occluder.node) if is_instance_valid(occluder.node) else "placement",
			"fade":occluder.fade,"target":occluder.target,"applied":occluder.applied,"release_hold":occluder.release_hold,
			"materials":materials})
	result.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return str(a.node)<str(b.node))
	return result

func _run() -> void:
	OS.low_processor_usage_mode_sleep_usec = 1
	Engine.max_fps = 60
	Graphics._texture_skip = 0
	config = _json(OS.get_environment("RL_INTERIOR_CONFIG"))
	_check(not config.is_empty(),"configuration exists")
	_check(DisplayServer.get_name() != "headless","rendered backend")
	_check(preload("res://src/world/gltf_quantization.gd").ensure_registered()
		and preload("res://src/world/vram_textures.gd").ensure_registered()
		and preload("res://src/world/map_mesh_extension.gd").ensure_registered(),"main initializes extensions")
	_check(preload("res://src/world/vram_textures.gd").mode_name() == "off" and Graphics.active_texture_skip() == 0,
		"same original full-resolution textures")
	_check(preload("res://src/runtime/optimization_profile.gd").selected("prepared_content") == "raw",
		"experimental prepared-content profile disabled")
	process_frame.connect(_frame)
	stage = Node3D.new()
	root.add_child(stage)
	rig = Rig.instantiate()
	stage.add_child(rig)
	actor = Node3D.new()
	stage.add_child(actor)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	stage.add_child(sun)
	loader = WorldLoader.new()
	stage.add_child(loader)
	await _settle(4)
	var window_start := _window()
	var qualification := bool(config.get("qualification",false))
	_memory("before_load")
	var point_value: Array = config.focus
	var point := Vector3(float(point_value[0]),float(point_value[1]),float(point_value[2]))
	phase = "foreground_load"
	last_frame_us = Time.get_ticks_usec()
	recording = not qualification
	var began := Time.get_ticks_usec()
	loader.load_world(str(config.manifest),Vector3.INF,true)
	var load_ended := Time.get_ticks_usec()
	_check(is_instance_valid(loader.world_root),"foreground map loads")
	if not is_instance_valid(loader.world_root):
		_write(str(config.report),{"ok":false,"configuration":config,"checks":checks})
		quit(1)
		return
	_memory("after_load")
	var scene_witness := {}
	# Fingerprint BEFORE controllers change visibility or add fading overrides.
	if qualification:
		scene_witness = Fingerprint.scene(loader.world_root)
		_check((scene_witness.get("warnings",[]) as Array).is_empty(),"fingerprint is complete",scene_witness.get("warnings"))
	phase = "controller_binding"
	var bind_began := Time.get_ticks_usec()
	WorldEnvironmentBinder.apply(loader.manifest,environment,sun,loader.world_root)
	WorldEnvironmentBinder.apply_camera(loader.manifest,rig)
	var section_members := sections.configure(loader.manifest,loader.world_root)
	var cuts := cutaway.configure(loader.manifest,loader.world_root)
	var occluders := fade.configure(loader.manifest,loader.world_root)
	fade.set_enabled(true)
	_focus(point)
	var bind_ended := Time.get_ticks_usec()
	_memory("after_binding")
	phase = "first_draw"
	await RenderingServer.frame_post_draw
	var draw_ended := Time.get_ticks_usec()
	phase = "ground_ready"
	var standing := 0
	var ground_frames: Array = []
	for attempt: int in 120:
		await physics_frame
		var hit := _ground(point)
		ground_frames.append(hit)
		standing = standing+1 if bool(hit.hit) else 0
		if standing >= 3: break
	var ready_ended := Time.get_ticks_usec()
	_check(standing >= 3,"three consecutive grounded physics frames",ground_frames)
	_memory("first_ready")
	phase = "post_ready_settle"
	await _settle(30)
	var settle_ended := Time.get_ticks_usec()
	recording = false
	var intervals := [{"phase":"foreground_load","start_us":began,"end_us":load_ended},
		{"phase":"controller_binding","start_us":bind_began,"end_us":bind_ended},
		{"phase":"first_draw","start_us":bind_ended,"end_us":draw_ended},
		{"phase":"ground_ready","start_us":draw_ended,"end_us":ready_ended},
		{"phase":"post_ready_settle","start_us":ready_ended,"end_us":settle_ended}]
	for frame: Dictionary in frames:
		frame["intersects_phases"] = []
		for interval: Dictionary in intervals:
			if int(frame.time_us) > int(interval.start_us) and int(frame.start_us) < int(interval.end_us):
				(frame.intersects_phases as Array).append(interval.phase)
	_memory("settled")
	var assets := _assets()
	var expected := "geometry" if str(config.mode) == "native" else "geometry_raw"
	_check(str(loader.cache_status) == expected,"expected scoped cache branch",str(loader.cache_status))
	_check((str(config.mode) == "native" or loader.cache_file.is_empty()) and loader._cache_write_countdown == 0,"legacy disk cache unused")
	if str(config.target) == "landfall_insides":
		_check(int(assets.entries) == (155 if str(config.mode) == "native" else 0),"expected underground native asset count",assets.entries)
	var witness := {}
	if qualification:
		witness = await _qualify(point)
		witness.scene = scene_witness
	var diagnostic := loader.diagnostic_snapshot()
	var window_end := _window()
	sections.reset()
	cutaway.reset()
	fade.reset()
	loader.unload_world()
	loader.queue_free()
	GlbSceneCache.clear()
	stage.queue_free()
	await _settle(15)
	# Release process-owned shader references before the renderer shuts down.
	preload("res://src/world/look/look_ground.gd")._class_textures.clear()
	preload("res://src/world/look/look_ground.gd")._biome_shader = null
	preload("res://src/world/season_surfaces.gd")._shaders.clear()
	await _settle(15)
	_check(MeshPool.live_count() == 0,"mesh pool releases all entries",MeshPool.retention_snapshot())
	_check(int(TexturePool.retention_snapshot().live_entries) == 0,"texture pool releases all entries",TexturePool.retention_snapshot())
	var ok := true
	for check: Dictionary in checks: ok = ok and bool(check.ok)
	var report := {"ok":ok,"configuration":config,"configuration_sha256":OS.get_environment("RL_INTERIOR_CONFIG_SHA"),
		"scope":"Foreground WorldLoader plus production environment/camera/secret/cutaway/fade controller fixture; no Main/network/avatar/actual curtain. Process-cold, OS/driver caches retained. Qualification readbacks run in separate processes.",
		"engine":Engine.get_version_info(),"window_start":window_start,"window_end":window_end,
		"effective_settings":{"vram_mode":preload("res://src/world/vram_textures.gd").mode_name(),
			"texture_skip":Graphics.active_texture_skip(),"optimization_profile":preload("res://src/runtime/optimization_profile.gd").snapshot(),
			"container_reuse_environment":OS.get_environment("ELORIA_GEOMETRY_CONTAINER_REUSE"),
			"bound_prepare_environment":OS.get_environment("ELORIA_UNDERGROUND_BOUND_PREPARE"),
			"early_world_filter_environment":OS.get_environment("ELORIA_EARLY_WORLD_OBJECT_FILTER")},
		"checks":checks,"qualification":witness,"frames":frames,"phase_intervals_us":intervals,"memory":memory,
		"timing":{"load_call_ms":float(load_ended-began)/1000.0,"controller_binding_ms":float(bind_ended-bind_began)/1000.0,
			"through_first_draw_ms":float(draw_ended-began)/1000.0,"first_ready_ms":float(ready_ended-began)/1000.0,
			"through_settled_ms":float(settle_ended-began)/1000.0},"loader":diagnostic,"geometry_assets":assets,
		"controllers":{"section_members":section_members,"cutaway_members":cuts,"occluders":occluders},
		"final_texture_pool":TexturePool.retention_snapshot(),"final_mesh_pool":MeshPool.retention_snapshot()}
	_write(str(config.report),report)
	print("INTERIOR_DONE ","PASS" if ok else "FAIL")
	quit(0 if ok else 1)
