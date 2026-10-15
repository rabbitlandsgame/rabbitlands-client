# Capture real client frames of a region package.
#
# Loads world.glb through GLTFDocument, as the runtime WorldLoader does, and
# applies the game's environment binder and interior cutaway controller. The
# region's references/captures/index.json provides repeatable camera positions.
# Collision and navigation are verified separately by the package validators.
#
# Run from the godot-client directory:
#   Godot_v4.7.2-stable_win64_console.exe --path . --script \
#     ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
#     --rendering-driver vulkan --resolution 1600x1000 -- \
#     --package=<abs path to region package> --out=<abs path>
#     [--only=<substring>] [--environment=manifest]
#
# `--environment=manifest` lights the shots from the package's own
# `environment` block through the project's `WorldEnvironmentBinder`, instead of
# this file's neutral studio sun. Use it when the captures are meant to be
# evidence about the region's declared lighting and not only about its geometry.
extends SceneTree

const SETTLE_FRAMES := 24
const Cutaway = preload("res://src/world/interior_cutaway.gd")


func _err(message: String) -> void:
	printerr("[capture] ", message)


func _args() -> Dictionary:
	var out := {}
	for raw in OS.get_cmdline_user_args():
		var arg := str(raw)
		if arg.begins_with("--") and arg.contains("="):
			var parts := arg.substr(2).split("=", true, 1)
			out[parts[0]] = parts[1]
	return out


func _init() -> void:
	var opts := _args()
	var package: String = opts.get("package", "")
	var out_dir: String = opts.get("out", "")
	var only: String = opts.get("only", "")
	if package == "" or out_dir == "":
		_err("need --package=<dir> and --out=<dir>")
		quit(2)
		return

	DirAccess.make_dir_recursive_absolute(out_dir)

	var glb_path := package.path_join("world.glb")
	if not FileAccess.file_exists(glb_path):
		_err("no world.glb at " + glb_path)
		quit(2)
		return

	# Load the GLB exactly as a runtime package: no import step, no .tscn.
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	state.set_handle_binary_image(GLTFState.HANDLE_BINARY_EMBED_AS_BASISU)
	var bytes := FileAccess.get_file_as_bytes(glb_path)
	var err := doc.append_from_buffer(bytes, package, state)
	if err != OK:
		_err("GLTFDocument.append_from_buffer failed: %d" % err)
		quit(2)
		return
	var scene: Node3D = doc.generate_scene(state)
	if scene == null:
		_err("generate_scene returned null")
		quit(2)
		return

	var root := get_root()
	var world := Node3D.new()
	world.name = "World"
	root.add_child(world)
	world.add_child(scene)
	# The binder creates lamps only after their parent has entered the tree.
	await process_frame

	var mesh_count := 0
	var tri_count := 0
	for node in _walk(scene):
		if node is MeshInstance3D:
			mesh_count += 1
			var mesh: Mesh = (node as MeshInstance3D).mesh
			if mesh != null:
				for s in mesh.get_surface_count():
					var arrays := mesh.surface_get_arrays(s)
					var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
					tri_count += idx.size() / 3
	print("[capture] meshes=%d triangles=%d" % [mesh_count, tri_count])

	# A package that declares `environment.sky == "none"` is sealed - an interior,
	# rooms inside rock. Lighting it with the region rig floods it with sky and
	# puts a sun through its ceiling, which is not a moody frame but a wrong one:
	# the reviewer sees daylight in a vault that has none. Such a package is lit
	# from its own manifest instead.
	var manifest_env: Dictionary = {}
	var manifest_env_root: Dictionary = {}
	var manifest_file := FileAccess.open(package.path_join("world.json"), FileAccess.READ)
	if manifest_file != null:
		var parsed: Variant = JSON.parse_string(manifest_file.get_as_text())
		manifest_file.close()
		if parsed is Dictionary:
			manifest_env_root = parsed as Dictionary
		if typeof(parsed) == TYPE_DICTIONARY:
			manifest_env = manifest_env_root.get("environment", {})
	var sealed := str(manifest_env.get("sky", "")) == "none"
	var bind_manifest := WorldManifest.new()
	bind_manifest.data = manifest_env_root
	var cutaway := Cutaway.new()
	print("[capture] cutaway nodes=%d" % cutaway.configure(bind_manifest, scene))

	# environment: a plain daylight sky so the shot shows the map, not a mood
	var env := Environment.new()
	var sky := Sky.new()
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.36, 0.52, 0.74)
	sky_mat.sky_horizon_color = Color(0.72, 0.78, 0.84)
	sky_mat.ground_bottom_color = Color(0.26, 0.24, 0.22)
	sky_mat.ground_horizon_color = Color(0.62, 0.62, 0.60)
	sky.sky_material = sky_mat
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.45
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	# A package may declare its own exposure. The default suits a region whose
	# albedos sit in the middle of the range; a wet jungle under closed canopy
	# is painted much darker than that and renders as a silhouette at 1.05.
	env.tonemap_exposure = float(manifest_env.get("exposure", 1.05))
	env.ssao_enabled = true

	# A WorldEnvironment, not camera.environment: the camera override does not
	# supply the sky the background is drawn from, which leaves the frame in a
	# flat void.
	if sealed:
		var amb: Dictionary = manifest_env.get("ambient", {})
		var amb_colour: Variant = amb.get("colour", [0.14, 0.13, 0.18])
		env.background_mode = Environment.BG_COLOR
		env.background_color = Color(0.02, 0.02, 0.03)
		env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		env.ambient_light_color = Color(amb_colour[0], amb_colour[1], amb_colour[2])
		# lifted well above the manifest value: the manifest number is for a
		# renderer with the interior's own lamps, and this harness has none
		env.ambient_light_energy = float(amb.get("energy", 0.4)) * 4.0
		var fog: Dictionary = manifest_env.get("fog", {})
		if bool(fog.get("enabled", false)):
			var fc: Variant = fog.get("colour", [0.06, 0.06, 0.08])
			env.fog_enabled = true
			env.fog_light_color = Color(fc[0], fc[1], fc[2])
			env.fog_density = 0.010

	var world_env := WorldEnvironment.new()
	world_env.environment = env
	world.add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.9
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 1200.0
	sun.directional_shadow_split_1 = 0.06
	sun.directional_shadow_split_2 = 0.18
	sun.directional_shadow_split_3 = 0.5
	# The region faces south: its citadel, gate and terraces all present their
	# built faces that way, so the sun comes from the south-west or every shot
	# is of a wall in shadow.
	# A DirectionalLight3D shines along its own -Z. The region's built faces
	# look south and most cameras look north, so the light must travel north
	# too: yaw near zero, not near 180, or every shot is backlit.
	sun.rotation_degrees = Vector3(-46.0, 24.0, 0.0)

	# ...but a region that declares its own sun in the manifest gets that one.
	# The fixed rig above is Amberwood's art direction - its built faces look
	# south, so the light travels north - and it is simply wrong for a region
	# laid out on a different axis. Verdant Stair's terraces present south-west
	# and every frame came back backlit and near-black until this read the
	# manifest. `environment.sun.direction` points *toward* the sun, and a
	# DirectionalLight3D shines along its own -Z, so the node looks at -d.
	var sun_cfg: Dictionary = manifest_env.get("sun", {})
	var dir_raw: Variant = sun_cfg.get("direction", null)
	if not sealed and dir_raw is Array and (dir_raw as Array).size() == 3:
		var d := Vector3(float(dir_raw[0]), float(dir_raw[1]),
						 float(dir_raw[2])).normalized()
		if d.length() > 0.5 and absf(d.dot(Vector3.UP)) < 0.985:
			sun.look_at_from_position(Vector3.ZERO, -d, Vector3.UP)
		var sun_colour: Variant = sun_cfg.get("color", sun_cfg.get("colour", null))
		if sun_colour is Array and (sun_colour as Array).size() >= 3:
			sun.light_color = Color(float(sun_colour[0]), float(sun_colour[1]),
									float(sun_colour[2]))
		sun.light_energy = float(sun_cfg.get("energy", 1.2)) * 1.55
		# Ambient too: a closed jungle canopy is mostly bounce, and a rig with
		# 0.45 of sky and nothing else renders it as a silhouette.
		var open_amb: Dictionary = manifest_env.get("ambient", {})
		env.ambient_light_energy = maxf(
			0.45, float(open_amb.get("energy", 0.45)) * 2.6)

	if sealed:
		# straight down and weak: a sealed package has no sun, and this only
		# keeps surfaces from reading as flat unlit colour
		sun.light_energy = 0.30
		sun.light_color = Color(0.82, 0.80, 0.92)
		sun.shadow_enabled = false
		sun.rotation_degrees = Vector3(-88.0, 0.0, 0.0)
	world.add_child(sun)

	# The lamps the package declares, as real lights. A sealed package's manifest
	# carries a `lights` array standing in for its lanterns and braziers; without
	# these the ambient block alone lights every surface identically and the
	# frame shows no source for its own light.
	var manifest_lights: Array = []
	var lights_file := FileAccess.open(package.path_join("world.json"),
		FileAccess.READ)
	if lights_file != null:
		var lights_parsed: Variant = JSON.parse_string(lights_file.get_as_text())
		lights_file.close()
		if typeof(lights_parsed) == TYPE_DICTIONARY:
			manifest_lights = (lights_parsed as Dictionary).get("lights", [])
	var lamp_count := 0
	for entry in manifest_lights:
		var lamp: Dictionary = entry
		var at: Array = lamp.get("position", [])
		if at.size() != 3:
			continue
		var point := OmniLight3D.new()
		point.position = Vector3(float(at[0]), float(at[1]), float(at[2]))
		var col: Array = lamp.get("colour", lamp.get("color", [1.0, 1.0, 1.0]))
		point.light_color = Color(float(col[0]), float(col[1]), float(col[2]))
		point.light_energy = float(lamp.get("energy", 1.5))
		point.omni_range = float(lamp.get("range", 9.0))
		point.shadow_enabled = false
		world.add_child(point)
		lamp_count += 1
	if lamp_count:
		print("[capture] %d declared lamps" % lamp_count)

	# Bind the manifest's own environment, through the same
	# `WorldEnvironmentBinder` the game uses, so a capture shows the light the
	# region actually ships rather than this harness's neutral studio sun.
	#
	# Without this the frames are evidence about geometry only: a manifest can
	# declare a sun that lights the world from underneath, or omit `tonemap`
	# and render flat, and the captures look identical either way. Off by
	# default so existing regions' capture sets do not change under them; pass
	# `--environment=manifest` to use it.
	# Note the two light sources are different manifest keys and do not
	# collide: the loop above reads top-level `lights`, and the binder below
	# spawns `environment.lights`. A package declaring both gets both.
	if str(opts.get("environment", "harness")) == "manifest":
		var bound: bool = WorldEnvironmentBinder.apply(
			bind_manifest, world_env, sun, world)
		print("[capture] manifest point lights=%d" % get_nodes_in_group("manifest_lights").size())
		if bound and not sun.visible:
			print("[capture] environment: manifest (sun disabled)")
		elif bound and sun.is_inside_tree():
			var travel: Vector3 = -sun.global_transform.basis.z
			print("[capture] environment: manifest (sun travels %.2f, %.2f, %.2f%s)"
				% [travel.x, travel.y, travel.z,
				   "  WARNING: lights from below" if travel.y > 0.0 else ""])
		elif bound:
			print("[capture] environment: manifest (sun direction bound)")
		else:
			print("[capture] environment: manifest requested but not bound; "
				+ "keeping harness lighting")
	else:
		print("[capture] environment: harness studio lighting")

	var camera := Camera3D.new()
	camera.far = 2400.0
	camera.current = true
	world.add_child(camera)

	var index_path := package.path_join("references/captures/index.json")
	var views: Array = []
	if FileAccess.file_exists(index_path):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(index_path))
		if parsed is Array:
			views = parsed
	if views.is_empty():
		_err("no camera set at " + index_path)
		quit(2)
		return

	# let the renderer settle before the first shot, or shadows and sky are
	# still converging and every capture is subtly different
	for i in SETTLE_FRAMES:
		await process_frame

	var written := 0
	# The frames this run actually produced, in view order. `make_comparison`
	# reads an index.json from whichever capture directory it picks, so a
	# godot-captures directory without one makes the comparison step fail
	# outright rather than fall back - the frames are there and unusable.
	#
	# Seeded from any index already beside the frames, so a partial `--only`
	# run updates the shots it retook and keeps the rest. Writing only what
	# this run produced means re-taking one frame drops the other twenty-six
	# from the index while their files stay on disk.
	var produced: Array = []
	var existing := FileAccess.open(out_dir.path_join("index.json"),
		FileAccess.READ)
	if existing != null:
		var previous: Variant = JSON.parse_string(existing.get_as_text())
		existing.close()
		if typeof(previous) == TYPE_ARRAY:
			produced = previous

	for entry in views:
		var id: String = str(entry.get("id", ""))
		if only != "" and not id.contains(only):
			continue
		var eye: Array = entry.get("eye", [])
		var target: Array = entry.get("target", [])
		if eye.size() != 3 or target.size() != 3:
			continue
		# The region capture index writes `fieldOfViewDegrees`; the interior
		# preview writes `fov`. Accept either, or an interior comes back at
		# the 55-degree default instead of the framing it was authored with.
		camera.fov = float(entry.get("fieldOfViewDegrees",
			entry.get("fov", 55.0)))
		camera.global_position = Vector3(eye[0], eye[1], eye[2])
		var look := Vector3(target[0], target[1], target[2])
		if camera.global_position.distance_to(look) > 0.01:
			camera.look_at(look, Vector3.UP)
		var to_camera := camera.global_position - look
		cutaway.update(rad_to_deg(atan2(to_camera.x, to_camera.z)), true)
		for i in 3:
			await process_frame
		var image := get_root().get_texture().get_image()
		var path := out_dir.path_join(id + ".png")
		if image.save_png(path) == OK:
			written += 1
			var record: Dictionary = (entry as Dictionary).duplicate(true)
			record["file"] = id + ".png"
			record["source"] = "godot"
			record["engine"] = Engine.get_version_info().get("string", "")
			# The driver actually in use, not the project default: the run is
			# started with --rendering-driver, so the ProjectSettings value
			# says gl_compatibility while the frame was drawn with Vulkan.
			record["renderingDriver"] = RenderingServer.get_current_rendering_driver_name()
			record["renderingMethod"] = RenderingServer.get_current_rendering_method()
			var replaced := false
			for i in produced.size():
				if str((produced[i] as Dictionary).get("id", "")) == id:
					produced[i] = record
					replaced = true
					break
			if not replaced:
				produced.append(record)
			print("[capture] %s -> %s" % [id, path])
		else:
			_err("could not save " + path)

	var index_out := out_dir.path_join("index.json")
	var handle := FileAccess.open(index_out, FileAccess.WRITE)
	if handle != null:
		handle.store_string(JSON.stringify(produced, "  ") + "\n")
		handle.close()
		print("[capture] wrote %s" % index_out)
	else:
		_err("could not write " + index_out)

	print("[capture] wrote %d frames" % written)
	quit(0)


func _walk(node: Node) -> Array:
	var out: Array = [node]
	for child in node.get_children():
		out.append_array(_walk(child))
	return out
