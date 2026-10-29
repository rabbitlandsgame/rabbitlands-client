extends SceneTree
## Offline component comparison. Timed processes never capture pixels or mesh
## arrays; separate qualification processes use fixed shader time and cameras.
const Graphics := preload("res://src/world/graphics_options.gd")
const TexturePool := preload("res://src/world/external_texture_pool.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
var config: Dictionary
var stage: Node3D
var camera: Camera3D
var loaders: Array[WorldLoader] = []
var checks: Array = []
var views: Array = []
var samples: Array = []
var trial_results: Array = []
var record_frames := false
var previous_draw := 0
var current_view := 0

func _init() -> void:
	_run.call_deferred()

func _json(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return value if value is Dictionary else {}

func _check(ok: bool, label: String, detail: Variant = null) -> void:
	checks.append({"ok":ok,"check":label,"detail":detail})
	print("ROAD_CHECK ","PASS " if ok else "FAIL ",label)

func _v(value: Array) -> Vector3:
	return Vector3(float(value[0]),float(value[1]),float(value[2]))

func _a(value: Vector3) -> Array:
	return [value.x,value.y,value.z]

func _wait_frames(count: int) -> void:
	for unused: int in count: await process_frame

func _memory() -> Dictionary:
	return {"static_bytes":OS.get_static_memory_usage(),
		"texture_gpu_bytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
		"buffer_gpu_bytes":Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED),
		"video_gpu_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED)}

func _window() -> Dictionary:
	return {"focused":root.has_focus(),"visible":root.visible,"size":[root.size.x,root.size.y],
		"renderer":RenderingServer.get_current_rendering_method(),"gpu":RenderingServer.get_video_adapter_name(),
		"max_fps":Engine.max_fps,"low_processor_usage":OS.low_processor_usage_mode,
		"display_backend":DisplayServer.get_name()}

func _draw() -> void:
	var now := Time.get_ticks_usec()
	if record_frames and previous_draw > 0:
		samples.append({"frame_ms":float(now-previous_draw)/1000.0,"focused":root.has_focus(),
			"view":current_view,
			"gpu_ms":RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid()),
			"render_cpu_ms":RenderingServer.viewport_get_measured_render_time_cpu(root.get_viewport_rid()),
			"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
			"primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
			"process_ms":Performance.get_monitor(Performance.TIME_PROCESS)*1000.0,
			"physics_ms":Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0})
	previous_draw = now

func _ground(point: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(point+Vector3.UP*3.0,point-Vector3.UP*8.0,8)
	var hit := stage.get_world_3d().direct_space_state.intersect_ray(query)
	return {"point":_a(point),"hit":not hit.is_empty(),
		"position":_a(hit.get("position",Vector3.ZERO)),
		"footstep":preload("res://src/audio/footstep_surface.gd").from_hit(hit),
		"collider":str((hit.collider as Node).name) if not hit.is_empty() else ""}

func _road_probes() -> Array:
	var points: Array = []
	var region := str(config.get("region","suncoil"))
	for loader: WorldLoader in loaders:
		for candidate: Node in loader.world_root.find_children("Walk_%s_%s--*" % [region,region],"MeshInstance3D",true,false):
			var node := candidate as MeshInstance3D
			if node.mesh == null: continue
			var to_stage := stage.global_transform.affine_inverse()*node.global_transform
			for surface: int in node.mesh.get_surface_count():
				var arrays := node.mesh.surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
				var count := indices.size() if not indices.is_empty() else vertices.size()
				for fraction: float in [0.2,0.5,0.8]:
					var offset := mini((int(float(count)*fraction)/3)*3,count-3)
					if offset < 0: continue
					var point := Vector3.ZERO
					for corner: int in 3:
						point += vertices[indices[offset+corner] if not indices.is_empty() else offset+corner]/3.0
					points.append(_a(to_stage*point))
	return points

func _pose(view: Dictionary) -> void:
	var target := _v(view.target)
	var yaw := deg_to_rad(float(view.get("yaw",35.0)))
	var pitch := deg_to_rad(float(view.get("pitch",45.0)))
	var distance := float(view.get("distance",28.0))
	var offset := Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*distance
	camera.fov = float(view.get("fov",55.0))
	camera.look_at_from_position(target+offset,target,Vector3.UP)

func _trial_debug(probes: Array) -> Array:
	var result: Array = []
	for loader: WorldLoader in loaders:
		var metadata: Dictionary = loader.world_root.get_meta(&"road_texture_trial",{})
		for overlay: Dictionary in metadata.get("layers",[]):
			var node := overlay.node as MeshInstance3D
			var material := node.material_override as ShaderMaterial
			var matrix: Transform3D = material.get_shader_parameter(&"trial_mesh_to_mask")
			var origin: Vector2 = material.get_shader_parameter(&"trial_mask_origin")
			var extent: Vector2 = material.get_shader_parameter(&"trial_mask_extent")
			var image := overlay.coverage_image as Image
			var coverage: Array = []
			for point: Array in probes:
				var local := matrix*(node.global_transform.affine_inverse()*_v(point))
				var uv := (Vector2(local.x,local.z)-origin)/extent
				var inside := uv.x >= 0 and uv.y >= 0 and uv.x < 1 and uv.y < 1
				coverage.append(image.get_pixel(mini(int(uv.x*image.get_width()),image.get_width()-1),mini(int(uv.y*image.get_height()),image.get_height()-1)).r if inside else -1.0)
			result.append({"name":str(node.name),"visible":node.is_visible_in_tree(),"layers":node.layers,
				"node_transform":str(node.global_transform),"mesh_aabb":str(node.mesh.get_aabb()),
				"mesh_to_mask":str(matrix),"origin":str(origin),"extent":str(extent),"coverage_at_probes":coverage})
	return result

func _shader_code(code: String, source: String, active: Dictionary, freeze := true) -> String:
	var include := RegEx.new()
	include.compile('(?m)^\\s*#include\\s+"([^"]+)"[^\\n]*')
	var matches := include.search_all(code)
	for index: int in range(matches.size()-1,-1,-1):
		var found: RegExMatch = matches[index]
		var path := found.get_string(1)
		if not path.begins_with("res://"): path = source.get_base_dir().path_join(path)
		_check(not active.has(path) and FileAccess.file_exists(path),"shader include resolves",path)
		if active.has(path) or not FileAccess.file_exists(path): continue
		active[path] = true
		var expanded := _shader_code(FileAccess.get_file_as_string(path),path,active,freeze)
		active.erase(path)
		code = code.substr(0,found.get_start())+expanded+code.substr(found.get_end())
	var token := RegEx.new()
	token.compile("\\bTIME\\b")
	return token.sub(code,"0.0",true) if freeze else code

func _frozen_material(source: Material, materials: Dictionary, shaders: Dictionary) -> Material:
	if source == null: return null
	if materials.has(source.get_instance_id()): return materials[source.get_instance_id()]
	# Time-independent materials need no qualification mutation. In particular,
	# preserve generated mask shaders and their private data samplers as-is.
	if source is ShaderMaterial and (source as ShaderMaterial).shader != null:
		var original := (source as ShaderMaterial).shader
		var expanded := _shader_code(original.code,original.resource_path,{},false)
		var time_token := RegEx.create_from_string("\\bTIME\\b")
		if time_token.search(expanded) == null:
			materials[source.get_instance_id()] = source
			return source
	var result := source.duplicate() as Material
	materials[source.get_instance_id()] = result
	if source is ShaderMaterial and (source as ShaderMaterial).shader != null:
		var original := (source as ShaderMaterial).shader
		if not shaders.has(original.get_instance_id()):
			var shader := Shader.new()
			shader.code = _shader_code(original.code,original.resource_path,{})
			shaders[original.get_instance_id()] = shader
		(result as ShaderMaterial).shader = shaders[original.get_instance_id()]
		# Generated trial shaders have private sampler/transform parameters.
		# Reapply by name after replacing the Shader; do not rely on duplicate's
		# lazy parameter cache to survive that replacement.
		for uniform: Dictionary in original.get_shader_uniform_list():
			var name: StringName = StringName(uniform.get("name",""))
			(result as ShaderMaterial).set_shader_parameter(name,(source as ShaderMaterial).get_shader_parameter(name))
	result.next_pass = _frozen_material(source.next_pass,materials,shaders)
	return result

func _freeze_time() -> void:
	var materials := {}
	var shaders := {}
	for candidate: Node in stage.find_children("*","GeometryInstance3D",true,false):
		var geometry := candidate as GeometryInstance3D
		if geometry.material_override != null: geometry.material_override = _frozen_material(geometry.material_override,materials,shaders)
		if geometry.material_overlay != null: geometry.material_overlay = _frozen_material(geometry.material_overlay,materials,shaders)
		if geometry is MeshInstance3D and (geometry as MeshInstance3D).mesh != null:
			var node := geometry as MeshInstance3D
			for surface: int in node.mesh.get_surface_count():
				node.set_surface_override_material(surface,_frozen_material(node.get_active_material(surface),materials,shaders))
		elif geometry is MultiMeshInstance3D and (geometry as MultiMeshInstance3D).multimesh != null:
			var batch := geometry as MultiMeshInstance3D
			batch.multimesh = batch.multimesh.duplicate()
			if batch.multimesh.mesh == null: continue
			batch.multimesh.mesh = batch.multimesh.mesh.duplicate()
			for surface: int in batch.multimesh.mesh.get_surface_count():
				batch.multimesh.mesh.surface_set_material(surface,_frozen_material(batch.multimesh.mesh.surface_get_material(surface),materials,shaders))

func _run() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--config="): config = _json(argument.trim_prefix("--config="))
	if config.is_empty():
		push_error("road benchmark needs --config")
		quit(1)
		return
	OS.low_processor_usage_mode = false
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	root.size = Vector2i(1280,720)
	root.grab_focus()
	Graphics.decorative_grass = false
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	RenderingServer.frame_post_draw.connect(_draw)
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(),true)
	stage = Node3D.new()
	root.add_child(stage)
	camera = Camera3D.new()
	stage.add_child(camera)
	camera.current = true
	if not (config.get("views",[]) as Array).is_empty(): _pose(config.views[0])
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var before := _memory()
	var load_start := Time.get_ticks_usec()
	var load_us := 0
	for path: String in config.manifests:
		var loader := WorldLoader.new()
		stage.add_child(loader)
		var began := Time.get_ticks_usec()
		loader.load_world(path,Vector3.INF,true)
		load_us += Time.get_ticks_usec()-began
		_check(is_instance_valid(loader.world_root),"chunk loads",path)
		if not is_instance_valid(loader.world_root): continue
		loaders.append(loader)
	_check(loaders.size() == config.manifests.size(),"all chunks loaded")
	var trial_install_us := 0
	if str(config.get("variant","baseline")) != "baseline":
		var installer: Variant = load("res://src/dev/road_texture_trial/road_texture_trial.gd")
		for index: int in loaders.size():
			var started := Time.get_ticks_usec()
			var result: Dictionary = installer.apply(loaders[index].world_root,str(config.trials[index]),"mask")
			trial_install_us += Time.get_ticks_usec()-started
			trial_results.append(result)
			_check(bool(result.get("ok",false)),"road texture trial installs",result.get("errors",[]))
			if bool(config.get("debug_coverage",false)) or config.has("debug_lift"):
				for overlay: Dictionary in loaders[index].world_root.get_meta(&"road_texture_trial",{}).get("layers",[]):
					var material := (overlay.node as MeshInstance3D).material_override as ShaderMaterial
					material.set_shader_parameter(&"trial_debug_coverage",bool(config.get("debug_coverage",false)))
					if config.has("debug_lift"): material.set_shader_parameter(&"trial_vertex_lift",Vector3(0,float(config.debug_lift),0))
	var lighting := WorldManifest.load_file(str(config.lighting_manifest))
	WorldEnvironmentBinder.apply(lighting,environment,sun,stage)
	LookSky.install(lighting,environment)
	LookGrade.apply(lighting,environment,sun)
	LookSky.apply(lighting,environment,180.0)
	LookSwitch.apply_shadow_quality(sun)
	await _wait_frames(6)
	for unused: int in 3: await physics_frame
	var ready_us := Time.get_ticks_usec()-load_start
	var probes: Array = config.get("probes",[])
	if probes.is_empty(): probes = _road_probes()
	_check(not probes.is_empty(),"road grounding witnesses exist")
	var ground: Array = []
	for point: Array in probes: ground.append(_ground(_v(point)))
	for witness: Dictionary in ground: _check(bool(witness.hit),"road witness has walk collision",witness)
	if bool(config.get("debug_trial",false)):
		var debug_file := FileAccess.open(str(config.output).get_base_dir().path_join("trial-debug.json"),FileAccess.WRITE)
		debug_file.store_string(JSON.stringify(_trial_debug(probes),"  "))
		debug_file.close()
	views = config.get("views",[])
	if views.is_empty() and not probes.is_empty():
		for yaw: float in [35.0,125.0,215.0,305.0]: views.append({"target":probes[mini(1,probes.size()-1)],"yaw":yaw,"pitch":45.0,"distance":24.0})
		views.append({"target":probes[0],"yaw":35.0,"pitch":22.0,"distance":12.0})
	_check(not views.is_empty(),"camera views exist")
	var captures: Array = []
	var qualification := bool(config.get("qualification",false))
	if qualification:
		if bool(config.get("freeze_shaders",true)): _freeze_time()
		for index: int in views.size():
			_pose(views[index])
			await _wait_frames(12)
			await RenderingServer.frame_post_draw
			var path := str(config.output).get_base_dir().path_join("view-%02d.png" % index)
			var picture := root.get_texture().get_image()
			_check(not picture.is_empty() and picture.save_png(path) == OK,"rendered view saved",path)
			captures.append({"path":path,"view":views[index]})
	else:
		for view: Dictionary in views:
			_pose(view)
			await _wait_frames(12)
		var began := Time.get_ticks_usec()
		var seconds := float(config.get("measure_seconds",6.0))
		record_frames = true
		while float(Time.get_ticks_usec()-began)/1000000.0 < seconds:
			var elapsed := float(Time.get_ticks_usec()-began)/1000000.0
			var index := int(elapsed/1.0)%views.size()
			current_view = index
			var pose: Dictionary = views[index].duplicate()
			pose.yaw = float(pose.get("yaw",35.0))+sin(elapsed*1.5)*8.0
			_pose(pose)
			await process_frame
		record_frames = false
	var after := _memory()
	var report := {"ok":checks.all(func(item: Dictionary)->bool:return bool(item.ok)),"configuration":config,
		"scope":"Offline foreground WorldLoader component, selected outdoor chunks; static scene camera route, no network/avatar or streaming. Fresh process; OS and driver caches retained. Qualification readbacks separate from timing.",
		"effective_settings":{"texture_skip":Graphics.active_texture_skip(),
			"texture_mode":preload("res://src/world/vram_textures.gd").mode_name(),
			"look":LookProfile.mode(),"decorative_grass":Graphics.decorative_grass},
		"engine":Engine.get_version_info(),"window":_window(),"checks":checks,"trial_results":trial_results,
		"timing":{"load_call_ms":float(load_us)/1000.0,"trial_install_ms":float(trial_install_us)/1000.0,
			"through_ready_ms":float(ready_us)/1000.0},
		"probes":probes,"ground":ground,"views":views,"captures":captures,"frames":samples,"before_memory":before,"after_memory":after}
	# Teardown is outside timing and keeps engine leak diagnostics meaningful.
	for loader: WorldLoader in loaders: loader.unload_world()
	stage.queue_free()
	loaders.clear()
	GlbSceneCache.clear()
	await _wait_frames(15)
	LookGround._class_textures.clear()
	LookGround._biome_shader = null
	preload("res://src/world/season_surfaces.gd")._shaders.clear()
	await _wait_frames(10)
	report["final_pools"] = {"mesh":MeshPool.retention_snapshot(),"texture":TexturePool.retention_snapshot()}
	var file := FileAccess.open(str(config.output),FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(report,"  "));file.close()
	print("ROAD_DONE ","PASS" if bool(report.ok) else "FAIL")
	quit(0 if bool(report.ok) else 1)
