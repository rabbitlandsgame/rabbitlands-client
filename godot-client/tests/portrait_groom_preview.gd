extends SceneTree
## Actual native Human source meshes, animation, face masks and grooming.
## Run as a normal rendered project; RL_GROOM_OUTPUT stores local evidence.
const Groom := preload("res://src/actors/portrait_groom.gd")
const Face := preload("res://src/actors/face_appearance.gdshader")
var _failures := 0
var _folder := ""
var _records: Array[Dictionary] = []
var _stage: Node3D
var _camera: Camera3D
var _source := ""

class Quantization extends GLTFDocumentExtension:
	func _get_supported_extensions() -> PackedStringArray:
		return PackedStringArray(["KHR_mesh_quantization"])

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_source = OS.get_environment("RL_GROOM_SOURCE")
	_folder = OS.get_environment("RL_GROOM_OUTPUT")
	DirAccess.make_dir_recursive_absolute(_folder)
	GLTFDocument.register_gltf_document_extension(Quantization.new())
	root.size = Vector2i(640, 640)
	_stage = Node3D.new()
	root.add_child(_stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("19242b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("abbcd2")
	world.environment.ambient_light_energy = 0.58
	_stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = 1.35
	light.light_color = Color("ffe6c8")
	_stage.add_child(light)
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-25, 150, 0)
	rim.light_energy = 0.65
	rim.light_color = Color("92bbca")
	_stage.add_child(rim)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 0.58
	_stage.add_child(_camera)
	_camera.current = true
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(_source.path_join("data/actors/models.json"))).models
	var presets: Array[Dictionary] = [
		{"id": "rowan", "slug": "luminous_male", "hair_style": 1, "hair_color": 1, "hair_detail": 1, "facial_hair": 0, "jaw": 62, "cheekbones": 68, "nose": 44},
		{"id": "mira", "slug": "luminous_female", "hair_style": 3, "hair_color": 14, "hair_detail": 2, "facial_hair": 0, "jaw": 30, "cheekbones": 72, "nose": 40},
		{"id": "tavi", "slug": "luminous_male", "hair_style": 1, "hair_color": 1, "hair_detail": 2, "facial_hair": 5, "jaw": 78, "cheekbones": 62, "nose": 66},
		{"id": "sera", "slug": "luminous_female", "hair_style": 5, "hair_color": 0, "hair_detail": 1, "facial_hair": 0, "jaw": 48, "cheekbones": 55, "nose": 50},
	]
	for preset: Dictionary in presets:
		var config: Dictionary = registry[preset.slug]
		var native := _load_native(str(config.scene))
		if native == null:
			continue
		_stage.add_child(native)
		var skeleton := native.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
		_pose_idle(skeleton)
		for part: Node in native.find_children("*", "MeshInstance3D", true, false):
			if str(part.name).begins_with("wardrobe_head"):
				(part as MeshInstance3D).hide()
		var holder := Node3D.new()
		holder.name = "AppearanceHair_%d" % preset.hair_style
		skeleton.add_child(holder)
		var hair_source := _load_native(config.hairStyles[preset.hair_style])
		for item: Node in hair_source.find_children("*", "MeshInstance3D", true, false):
			var original := item as MeshInstance3D
			var piece := MeshInstance3D.new()
			piece.name = "NativeHair_" + str(original.name)
			piece.mesh = original.mesh
			piece.skin = original.skin
			piece.transform = original.transform
			holder.add_child(piece)
			piece.skeleton = NodePath("../..")
		hair_source.free()
		var appearance := {"hair": AppearanceVariants.pack_hair(preset.hair_style, preset.hair_color), "skin": 1, "eyes": 1}
		appearance.merge(preset)
		_skin(native, config, appearance)
		var head := skeleton.find_bone("Head")
		var focus := (skeleton.global_transform * skeleton.get_bone_global_pose(head)).origin + Vector3(0, 0.055, 0.0)
		for mode: String in ["before", "after"]:
			var look := appearance.duplicate()
			if mode == "before":
				look.hair_detail = 0
				look.facial_hair = 0
			else:
				CharacterProportions.apply(native, skeleton, appearance)
			var start := Time.get_ticks_usec()
			Groom.apply(native, skeleton, look, config)
			var elapsed := Time.get_ticks_usec() - start
			var beard := native.get_node_or_null("PortraitFacialHair") as MeshInstance3D
			if mode == "after":
				_records.append({"id": preset.id, "groom_usec": elapsed, "cache": Groom.cache_metrics()})
				var distant := native.duplicate() as Node3D
				_stage.add_child(distant)
				distant.position = Vector3(12345.67, 112.3, -9988.76)
				distant.rotation = Vector3(0.12, 1.234, -0.23)
				var distant_skeleton := distant.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
				var cache_before := Groom.cache_metrics()
				var hit_start := Time.get_ticks_usec()
				Groom.apply(distant, distant_skeleton, look, config)
				var hit_usec := Time.get_ticks_usec() - hit_start
				_expect(Groom.cache_metrics() == cache_before, "world translation/rotation share grooming cache")
				if beard != null:
					_expect((distant.get_node("PortraitFacialHair") as MeshInstance3D).mesh == beard.mesh,
						"distant actors share fitted beard resource")
				_records.append({"id": preset.id, "warm_groom_usec": hit_usec})
				distant.free()
			if mode == "after" and preset.facial_hair > 0:
				_expect(beard != null, "selected beard exists")
				if beard != null:
					var arrays := beard.mesh.surface_get_arrays(0)
					_expect(arrays[Mesh.ARRAY_VERTEX].size() < 2000, "beard patch compacts imported attributes")
					var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
					var count: int = weights.size() / arrays[Mesh.ARRAY_VERTEX].size()
					for index: int in arrays[Mesh.ARRAY_VERTEX].size():
						var total := 0.0
						for influence: int in count:
							total += weights[index * count + influence]
						_expect(absf(total - 1.0) < 0.0001, "beard interpolated skin remains normalized")
					_records.append({"id": preset.id, "groom_usec": elapsed, "beard_vertices": arrays[Mesh.ARRAY_VERTEX].size(), "beard_triangles": arrays[Mesh.ARRAY_INDEX].size() / 3, "skin_bind_count": beard.skin.get_bind_count()})
			for angle: String in ["front", "threequarter", "side"]:
				var offset: Vector3 = {"front": Vector3(0, 0.17, 0.9), "threequarter": Vector3(0.40, 0.17, 0.9), "side": Vector3(0.9, 0.17, 0.02)}[angle]
				_camera.position = focus + offset
				_camera.look_at(focus)
				for frame: int in 5:
					await process_frame
				await RenderingServer.frame_post_draw
				var file := "%s-%s-%s.png" % [preset.id, mode, angle]
				root.get_texture().get_image().save_png(_folder.path_join(file))
				print("RENDER ", file)
		native.free()
	FileAccess.open(_folder.path_join("groom-metrics.json"), FileAccess.WRITE).store_string(JSON.stringify({"failures": _failures, "models": _records}, "\t"))
	quit(_failures)

func _load_native(path: String) -> Node3D:
	var absolute := _source.path_join(path.trim_prefix("res://"))
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(absolute, state)
	_expect(error == OK, "native glTF loads " + path)
	return document.generate_scene(state) as Node3D if error == OK else null

func _pose_idle(target: Skeleton3D) -> void:
	var source := _load_native("res://assets/actors/native/shared/Universal_Animation_Library.glb")
	_stage.add_child(source)
	var player := source.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	var animation := player.get_animation("Idle_Subtle")
	var owner := target.get_parent()
	var idle := Animation.new()
	idle.length = animation.length
	for track: int in animation.get_track_count():
		var path := animation.track_get_path(track)
		var name := path.get_concatenated_subnames()
		if name.is_empty():
			name = str(path).get_file()
		if target.find_bone(name) < 0:
			continue
		var next := idle.get_track_count()
		animation.copy_track(track, idle)
		idle.track_set_path(next, NodePath(str(owner.get_path_to(target)) + ":" + name))
	var library := AnimationLibrary.new()
	library.add_animation("Idle", idle)
	var actor_player := AnimationPlayer.new()
	owner.add_child(actor_player)
	actor_player.add_animation_library("", library)
	actor_player.play("Idle")
	actor_player.seek(0.3, true)
	actor_player.pause()
	source.free()

func _skin(native: Node3D, config: Dictionary, appearance: Dictionary) -> void:
	var mask_image := Image.load_from_file(_source.path_join(str(config.faceAppearance.mask).trim_prefix("res://")))
	var mask := ImageTexture.create_from_image(mask_image)
	for group: String in config.faceAppearance.groups:
		var mesh := native.find_child(group, true, false) as MeshInstance3D
		if mesh == null:
			continue
		var original := mesh.mesh.surface_get_material(0) as StandardMaterial3D
		var material := ShaderMaterial.new()
		material.shader = Face
		material.set_shader_parameter("base_texture", original.albedo_texture)
		material.set_shader_parameter("region_texture", mask)
		material.set_shader_parameter("base_color", original.albedo_color)
		material.set_shader_parameter("hair_tint", AppearanceVariants.hair_color(appearance.hair))
		material.set_shader_parameter("eye_tint", AppearanceVariants.eye_color(appearance.eyes))
		material.set_shader_parameter("recolor_skin", true)
		material.set_shader_parameter("skin_color", AppearanceVariants.skin_color(appearance.skin))
		var refs: Array = config.skinPalette.references[group][0]
		material.set_shader_parameter("skin_reference", Color(refs[0], refs[1], refs[2]))
		material.set_shader_parameter("normal_texture", original.normal_texture)
		material.set_shader_parameter("use_normal", original.normal_enabled)
		mesh.material_override = material

func _expect(ok: bool, message: String) -> void:
	if not ok:
		_failures += 1
		push_error(message)
