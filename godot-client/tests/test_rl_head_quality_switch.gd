extends SceneTree
## Headless checks for the RL head's tier activation on the real
## ReplicatedActor3D (the RL head is a Human's head at High only):
##   * High <-> Medium round trips in place restore the exact Medium actor
##     (mesh arrays, materials and their parameters, visibility, shadows, LOD
##     bias, layers, skins) for presets, beards, a game hairstyle, an open band
##     and a closed helm; RL_HEADS=classic switches a live actor to develop's
##     classic High head and back;
##   * RL caches outlive the last RL head for the retention time (a switch back
##     up within it parses nothing again), then are all released; no rig is
##     left behind; prewarm parses the RL files on workers and publishes them;
##   * body refinement never touches RL meshes (no cache entries for them);
##   * RL meshes carry the animated-head culling envelope and the body's layers;
##   * the portrait pose (dialogue layer lease, leaderboard): first level of
##     detail with the gameplay camera 26 m away, neutral face, eyes open;
##   * female facial hair at High: no beard, no stubble, the saved value kept;
##   * a missing RL hairstyle falls back to the game hairstyle;
##   * editing between an RL module and game hairstyles in place, and closed
##     helms hiding and restoring the RL hair;
##   * spring hair stays bounded under the cosmetic height/build scale.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head_quality_switch.gd

const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const PORTRAIT_LAYER := preload("res://src/ui/campaign_portrait_layer.gd")
const HIGH := ActorRenderQuality.Quality.HIGH
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const LOW := ActorRenderQuality.Quality.LOW

var _checks := 0
var _failures := 0
var _models: Dictionary
var _equipment: Dictionary
var _animation: Dictionary
var _next_id := 9600


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures += 1
		push_error("rl head quality switch: " + message)


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _run() -> void:
	_models = (_json("res://data/actors/models.json") as Dictionary).models
	_equipment = _json("res://data/actors/equipment.json")
	_animation = _json("res://data/animations/luminous.json")
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	await _check_round_trips()
	await _check_classic_switch()
	await _check_release()
	await _check_prewarm()
	await _check_refinement_and_presentation()
	await _check_portrait_pose()
	await _check_female_facial_hair()
	await _check_missing_hair()
	await _check_hair_edits_and_helms()
	await _check_spring_scale()
	print("rl head quality switch: %d checks, %d failures" % [_checks, _failures])
	print("rl head quality switch: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _spawn(sex: String, appearance: Dictionary, equipment: Dictionary, quality: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_next_id += 1
	actor.apply_render_quality(quality, false)
	root.add_child(actor)
	var errors := actor.configure({"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": appearance, "equipment_visuals": equipment}, CoordinateAdapter.new({"walkingHeight": 0.0}),
		_models["luminous_" + sex], _animation, _equipment)
	_expect(errors.is_empty(), "%s configures: %s" % [sex, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor


static func _sha(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	var bytes := var_to_bytes(value)
	if not bytes.is_empty():
		context.update(bytes)
	return context.finish().hex_encode().left(20)


func _material(material: Material) -> String:
	if material == null:
		return ""
	var parameters := {"class": material.get_class()}
	if material is ShaderMaterial:
		var shader := (material as ShaderMaterial).shader
		parameters["shader"] = shader.resource_path if shader != null else ""
		if shader != null:
			for uniform: Dictionary in shader.get_shader_uniform_list():
				var value: Variant = (material as ShaderMaterial).get_shader_parameter(uniform.name)
				parameters[str(uniform.name)] = value.get_instance_id() if value is Object else value
	else:
		for property: Dictionary in material.get_property_list():
			if int(property.usage) & PROPERTY_USAGE_STORAGE and str(property.name) not in ["resource_name",
					"resource_path", "resource_local_to_scene", "script"]:
				var value: Variant = material.get(property.name)
				parameters[str(property.name)] = value.get_instance_id() if value is Object else value
	return _sha(var_to_str(parameters))


func _mesh(mesh: Mesh) -> String:
	if mesh == null:
		return ""
	var parts: Array = []
	for surface: int in mesh.get_surface_count():
		parts.append(_sha(mesh.surface_get_arrays(surface)))
		parts.append(_material(mesh.surface_get_material(surface)))
	return _sha(parts)


## Everything a viewer of the actor sees, per visible mesh path.
func _capture(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if not instance.is_visible_in_tree() or instance.is_queued_for_deletion():
			continue
		var materials: Array = []
		for surface: int in (instance.mesh.get_surface_count() if instance.mesh != null else 0):
			materials.append(_material(instance.get_active_material(surface)))
		var binds: Array = []
		if instance.skin != null:
			for bind: int in instance.skin.get_bind_count():
				binds.append([instance.skin.get_bind_name(bind), instance.skin.get_bind_pose(bind)])
		var path := str(actor.get_path_to(instance))
		result[path] = {"mesh": _mesh(instance.mesh), "materials": materials,
			"shadow": instance.cast_shadow, "lod_bias": instance.lod_bias, "layers": instance.layers,
			"margin": instance.extra_cull_margin, "skin": _sha(binds)}
	return result


func _differences(a: Dictionary, b: Dictionary) -> Array:
	var out: Array = []
	for path: String in a:
		if not b.has(path):
			out.append("missing " + path)
		elif a[path] != b[path]:
			var fields: Array = []
			for key: String in a[path]:
				if a[path][key] != b[path][key]:
					fields.append(key)
			out.append("%s %s" % [path, fields])
	for path: String in b:
		if not a.has(path):
			out.append("extra " + path)
	return out


func _looks() -> Dictionary:
	return {
		"default": [{}, {}],
		"rowan": [PRESETS.appearance("Rowan"), {}],
		"mira": [PRESETS.appearance("Mira"), {}],
		"tavi": [PRESETS.appearance("Tavi"), {}],
		"mohawk_beard": [{"facial_hair": 5, "hair": AppearanceVariants.pack_hair(9, 18), "skin": 7, "eyes": 9}, {}],
		"band_111": [PRESETS.appearance("Mira"), {3: 111}],
		"closed_helm": [PRESETS.appearance("Rowan").merged({"facial_hair": 5}, true), {3: 143}],
	}


func _check_round_trips() -> void:
	for sex: String in ["male", "female"]:
		var looks := _looks()
		for look: String in looks:
			var appearance: Dictionary = looks[look][0]
			var equipment: Dictionary = looks[look][1]
			var actor := _spawn(sex, appearance, equipment, MEDIUM)
			await process_frame
			var medium := _capture(actor)
			var native := actor.get_node("NativeModel") as Node3D
			var body := native.find_child("body", true, false) as MeshInstance3D
			var body_mesh := body.mesh
			actor.apply_render_quality(HIGH, false)
			await process_frame
			var rig := actor.rl_head()
			_expect(rig != null, "%s %s: the RL head appears at High in place" % [sex, look])
			if rig != null:
				for part: String in ["eyes", "eyebrows", "scalp"]:
					var node := native.find_child(part, true, false) as MeshInstance3D
					_expect(node != null and not node.visible, "%s %s: body %s hidden under the RL head" % [sex, look, part])
				var shell := native.find_child("PortraitFacialHair", true, false) as MeshInstance3D
				_expect(not body.has_meta(HighPortraitAppearance.META) and (shell == null or not shell.visible),
					"%s %s: no classic High portrait and no visible beard shell under the RL head" % [sex, look])
				_expect(body.has_meta(RLHeadBodyCut.CUT_META), "%s %s: the body is cut at the neck" % [sex, look])
			actor.apply_render_quality(MEDIUM, false)
			await process_frame
			var back := _capture(actor)
			var diff := _differences(medium, back)
			_expect(actor.rl_head() == null and diff.is_empty(),
				"%s %s: Medium -> High -> Medium restores the exact Medium actor %s" % [sex, look, diff.slice(0, 6)])
			_expect(body.mesh == body_mesh, "%s %s: the body mesh is the very Medium mesh again" % [sex, look])
			# Twice, and through Low, for good measure.
			actor.apply_render_quality(HIGH, false)
			actor.apply_render_quality(LOW, false)
			actor.apply_render_quality(HIGH, false)
			actor.apply_render_quality(MEDIUM, false)
			await process_frame
			diff = _differences(medium, _capture(actor))
			_expect(diff.is_empty(), "%s %s: High/Low/High/Medium also restores it %s" % [sex, look, diff.slice(0, 6)])
			actor.free()
			await process_frame


func _check_classic_switch() -> void:
	var actor := _spawn("female", PRESETS.appearance("Mira"), {}, HIGH)
	await process_frame
	_expect(actor.rl_head() != null, "Mira at High draws the RL head")
	OS.set_environment("RL_HEADS", "classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	actor.apply_render_quality(HIGH, false)
	await process_frame
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	_expect(actor.rl_head() == null and body.has_meta(HighPortraitAppearance.META),
		"RL_HEADS=classic switches a live actor to the classic High head")
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	actor.apply_render_quality(HIGH, false)
	await process_frame
	_expect(actor.rl_head() != null and not body.has_meta(HighPortraitAppearance.META),
		"clearing RL_HEADS puts the RL head back")
	actor.free()
	await process_frame


func _check_release() -> void:
	await process_frame
	var actors: Array[ReplicatedActor3D] = []
	for index: int in 3:
		actors.append(_spawn(["male", "female"][index % 2], PRESETS.appearance(["Rowan", "Mira"][index % 2]), {}, HIGH))
	await process_frame
	_expect(RLHeadLibrary.users() == 3 and RLHeadLibrary.is_loaded(), "three RL heads hold the caches (%d)" % RLHeadLibrary.users())
	actors[0].apply_render_quality(MEDIUM, false)
	await process_frame
	_expect(RLHeadLibrary.users() == 2 and RLHeadLibrary.is_loaded(), "one switched down leaves the caches loaded")
	_expect(RLHeadRig.find_on(actors[0].get_skeleton()) == null, "the switched actor keeps no rig")
	# The last one going keeps the caches for the retention time: switching
	# back up within it reads and parses nothing again.
	RLHeadLibrary.retain_seconds = 0.4
	actors[1].apply_render_quality(LOW, false)
	actors[2].free()
	await process_frame
	await process_frame
	_expect(RLHeadLibrary.users() == 0 and RLHeadLibrary.is_loaded() and RLHeadLibrary.retaining(),
		"the last RL head going keeps the caches for the retention time")
	var misses := int(GlbSceneCache.retention_snapshot()["lookup_misses"])
	actors[0].apply_render_quality(HIGH, false)
	await process_frame
	_expect(actors[0].rl_head() != null and RLHeadLibrary.users() == 1
		and int(GlbSceneCache.retention_snapshot()["lookup_misses"]) == misses,
		"a switch back up within the retention time parses no RL file again")
	actors[0].apply_render_quality(MEDIUM, false)
	await process_frame
	var waited := Time.get_ticks_msec()
	while RLHeadLibrary.is_loaded() and Time.get_ticks_msec() - waited < 3000:
		await process_frame
	_expect(RLHeadLibrary.users() == 0 and not RLHeadLibrary.is_loaded() and RLHeadBodyCut._cuts.is_empty()
		and RLHeadwearFit._meshes.is_empty() and RLHeadRig._shape_indices.is_empty(),
		"after the retention time every RL cache is released")
	var scenes := 0
	for key: Variant in GlbSceneCache._scenes:
		scenes += 1 if str(key).contains("rl_heads") else 0
	_expect(scenes == 0, "GlbSceneCache lets go of the RL files (%d left)" % scenes)
	RLHeadLibrary.retain_seconds = 0.0
	actors[0].apply_render_quality(HIGH, false)
	await process_frame
	_expect(actors[0].rl_head() != null and RLHeadLibrary.users() == 1, "the next High actor loads them again")
	for actor: ReplicatedActor3D in [actors[0], actors[1]]:
		actor.free()
	await process_frame
	await process_frame
	_expect(RLHeadLibrary.users() == 0 and not RLHeadLibrary.is_loaded(),
		"freeing actors releases their RL heads (at once with no retention time)")
	RLHeadLibrary.retain_seconds = RLHeadLibrary.RETAIN_SECONDS


## prewarm parses every RL file on the WorkerThreadPool and publishes it to
## GlbSceneCache without the main thread waiting; the first High actor then
## parses nothing; release_if_unused lets unused prewarmed files go.
func _check_prewarm() -> void:
	RLHeadLibrary.retain_seconds = 0.0
	RLHeadLibrary.clear()
	await process_frame
	var paths := RLHeadLibrary.warm_paths()
	_expect(paths.size() >= 4, "every head, hairstyle and beard is prewarmed (%d files)" % paths.size())
	RLHeadLibrary.prewarm()
	_expect(RLHeadLibrary.warming() or GlbSceneCache.missing(_global(paths)).is_empty(),
		"prewarm starts worker parses")
	var began := Time.get_ticks_msec()
	while RLHeadLibrary.warming() and Time.get_ticks_msec() - began < 20000:
		await process_frame
	_expect(not RLHeadLibrary.warming() and GlbSceneCache.missing(_global(paths)).is_empty(),
		"every prewarmed file is published (%d ms)" % (Time.get_ticks_msec() - began))
	var misses := int(GlbSceneCache.retention_snapshot()["lookup_misses"])
	var actor := _spawn("female", PRESETS.appearance("Mira"), {}, HIGH)
	await process_frame
	_expect(actor.rl_head() != null and int(GlbSceneCache.retention_snapshot()["lookup_misses"]) == misses,
		"the first High actor after a prewarm parses nothing on the main thread")
	actor.free()
	await process_frame
	await process_frame
	_expect(not RLHeadLibrary.is_loaded(), "the prewarmed files go with the last RL head")
	RLHeadLibrary.prewarm()
	began = Time.get_ticks_msec()
	while RLHeadLibrary.warming() and Time.get_ticks_msec() - began < 20000:
		await process_frame
	await process_frame
	_expect(RLHeadLibrary.is_loaded() and RLHeadLibrary.users() == 0, "a prewarm with no RL head holds the parsed files")
	RLHeadLibrary.release_if_unused()
	await process_frame
	_expect(not RLHeadLibrary.is_loaded(), "release_if_unused lets unused prewarmed files go")
	RLHeadLibrary.retain_seconds = RLHeadLibrary.RETAIN_SECONDS


static func _global(paths: PackedStringArray) -> PackedStringArray:
	var result := PackedStringArray()
	for path: String in paths:
		result.append(ProjectSettings.globalize_path(path))
	return result


func _check_refinement_and_presentation() -> void:
	var actor := _spawn("male", PRESETS.appearance("Tavi"), {5: 209}, HIGH)
	await process_frame
	var rig := actor.rl_head()
	_expect(rig != null, "Tavi draws the RL head")
	if rig == null:
		actor.free()
		return
	var ids := {}
	for mesh_node: MeshInstance3D in rig.all_meshes():
		ids[str(mesh_node.mesh.get_instance_id())] = mesh_node.name
		_expect(mesh_node.has_meta(RLHeadRig.MESH_META), "%s carries the RL mesh tag" % mesh_node.name)
		_expect(mesh_node.extra_cull_margin >= actor._animated_head_cull_margin() - 1e-6,
			"%s keeps the animated-head culling envelope (%.2f)" % [mesh_node.name, mesh_node.extra_cull_margin])
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	for mesh_node: MeshInstance3D in rig.all_meshes():
		_expect(mesh_node.layers == body.layers, "%s draws on the body's layers" % mesh_node.name)
	var leaked: Array = []
	for cache: Dictionary in [CharacterProportions._body_meshes, CharacterProportions._body_unchanged]:
		for key: Variant in cache:
			var source := str(key).get_slice("|", 0)
			if ids.has(source):
				leaked.append(ids[source])
	_expect(leaked.is_empty(), "body refinement made no cache entry for an RL mesh %s" % [leaked])
	_expect(rig.mesh_nodes()["beard"].size() > 0 and rig.appearance.beard == "full_beard",
		"Tavi's facial_hair 5 is the RL full beard")
	actor.free()
	await process_frame


func _check_portrait_pose() -> void:
	var actor := _spawn("male", PRESETS.appearance("Rowan"), {}, HIGH)
	actor.set_process(true)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	camera.global_position = actor.global_position + Vector3(0.0, 1.6, 26.0)
	for frame: int in 14:
		await process_frame
	var rig := actor.rl_head()
	_expect(rig != null and rig.lod_band() > 0, "26 m from the gameplay camera the RL head draws a far level (%d)"
		% (rig.lod_band() if rig != null else -1))
	var layer := PORTRAIT_LAYER.new()
	var mask := layer.bind(actor)
	await process_frame
	_expect(mask != 0 and rig.portrait_pose() and rig.lod_band() == 0, "a dialogue portrait holds the first level")
	var shown_first := true
	for level: int in rig.mesh_nodes()["head"].size():
		for mesh_node: MeshInstance3D in rig.mesh_nodes()["head"][level]:
			shown_first = shown_first and mesh_node.visible == (level == 0)
			_expect((mesh_node.layers & mask) != 0, "%s joins the portrait layer" % mesh_node.name)
	_expect(shown_first, "only the first head level is visible in the portrait")
	var expression := rig.expression()
	expression.set_expression("smile", 1.0, 0.0)
	expression.blink()
	expression.advance(0.08)
	for frame: int in 14:
		await process_frame
	var weights := expression.weights()
	_expect(weights.is_empty() and expression.is_held_neutral(),
		"the portrait face is neutral with open eyes, no blink %s" % weights)
	layer.clear()
	await process_frame
	_expect(not rig.portrait_pose() and not expression.is_held_neutral(), "ending the line releases the pose")
	for frame: int in 14:
		await process_frame
	_expect(rig.lod_band() > 0, "released, the far level returns")
	# Leaderboard-style: processing off after one frame, the pose held.
	actor.hold_portrait_pose(self)
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	await process_frame
	_expect(rig.lod_band() == 0 and expression.weights().is_empty(), "a leaderboard card shows the first level, eyes open")
	actor.release_portrait_pose(self)
	camera.queue_free()
	actor.free()
	await process_frame


func _check_female_facial_hair() -> void:
	for value: int in range(1, 6):
		var actor := _spawn("female", {"facial_hair": value, "hair": AppearanceVariants.pack_hair(2, 3)}, {}, HIGH)
		await process_frame
		var rig := actor.rl_head()
		var native := actor.get_node("NativeModel") as Node3D
		_expect(rig != null and (rig.mesh_nodes()["beard"] as Array).is_empty() and rig.appearance.stubble_amount() == 0.0
			and native.find_child("PortraitFacialHair", true, false) == null,
			"female facial_hair %d draws no beard and no stubble at High" % value)
		_expect(int(actor._appearance.get("facial_hair", -1)) == value, "female facial_hair %d stays saved" % value)
		var material := (native.find_child("body", true, false) as MeshInstance3D).get_active_material(0) as ShaderMaterial
		_expect(material == null or material.get_shader_parameter("stubble_enabled") != true,
			"female facial_hair %d paints no stubble on the body under the RL head" % value)
		actor.apply_render_quality(MEDIUM, false)
		await process_frame
		_expect((native.find_child("PortraitFacialHair", true, false) != null) == (value >= 2),
			"female facial_hair %d at Medium is develop's grooming again" % value)
		actor.free()
		await process_frame


func _check_missing_hair() -> void:
	var saved: Variant = RLHeadLibrary._hair_info.get("rowan_shag")
	RLHeadLibrary.hair_info("rowan_shag")
	RLHeadLibrary._hair_info["rowan_shag"] = {}
	var actor := _spawn("male", PRESETS.appearance("Rowan"), {}, HIGH)
	await process_frame
	var rig := actor.rl_head()
	var shown := 0
	for child: Node in actor.get_skeleton().get_children():
		if str(child.name).begins_with("AppearanceHair_") and (child as Node3D).visible:
			shown += 1
	_expect(rig != null and not rig.draws_module_hair() and rig.hair_external() and shown == 1,
		"a missing RL hairstyle falls back to the game hairstyle under the RL head")
	actor.free()
	RLHeadLibrary._hair_info.erase("rowan_shag")
	if saved != null:
		RLHeadLibrary._hair_info["rowan_shag"] = saved
	await process_frame


func _visible_holders(actor: ReplicatedActor3D) -> Array:
	var names: Array = []
	for child: Node in actor.get_skeleton().get_children():
		if str(child.name).begins_with("AppearanceHair_") and (child as Node3D).visible:
			names.append(str(child.name))
	return names


func _check_hair_edits_and_helms() -> void:
	var actor := _spawn("male", PRESETS.appearance("Rowan"), {}, HIGH)
	await process_frame
	var rig := actor.rl_head()
	_expect(rig.draws_module_hair() and _visible_holders(actor) == [RLHeadRig.HAIR_NODE_NAME],
		"Rowan's Parted is the rowan_shag module %s" % [_visible_holders(actor)])
	actor.apply_appearance_variants(PRESETS.appearance("Rowan").merged({"hair": AppearanceVariants.pack_hair(2, 1)}, true))
	await process_frame
	_expect(not rig.draws_module_hair() and rig.hair_external() and _visible_holders(actor) == ["AppearanceHair_2"],
		"editing to Long draws the game hairstyle under the RL head %s" % [_visible_holders(actor)])
	actor.apply_appearance_variants(PRESETS.appearance("Rowan"))
	await process_frame
	_expect(rig.draws_module_hair() and _visible_holders(actor) == [RLHeadRig.HAIR_NODE_NAME],
		"and back to Parted draws the module again %s" % [_visible_holders(actor)])
	actor.apply_equipment_visuals({3: 143})
	await process_frame
	_expect(_visible_holders(actor).is_empty(), "a closed helm hides the RL hair %s" % [_visible_holders(actor)])
	actor.apply_equipment_visuals({})
	await process_frame
	_expect(_visible_holders(actor) == [RLHeadRig.HAIR_NODE_NAME], "taking it off shows the module again")
	actor.apply_appearance_variants(PRESETS.appearance("Rowan").merged({"hair": AppearanceVariants.pack_hair(0, 1)}, true))
	await process_frame
	_expect(_visible_holders(actor).is_empty() and not rig.hair_external(), "Bald draws no hair and no hairline")
	actor.free()
	await process_frame


func _check_spring_scale() -> void:
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.current = true
	for scale: Array in [[0, 0], [0, 100], [100, 0], [100, 100]]:
		var look := PRESETS.appearance("Rowan").merged({"build": scale[0], "height": scale[1]}, true)
		var actor := _spawn("male", look, {}, HIGH)
		actor.set_process(true)
		camera.global_position = actor.global_position + Vector3(0.0, 1.6, 2.5)
		var rig := actor.rl_head()
		var motion := rig.hair_motion() if rig != null else null
		var skeleton: Skeleton3D = motion._skeleton if motion != null else null
		var worst := 0.0
		for step: int in 40:
			actor.position.x += 0.05 * sin(step * 0.6)
			await process_frame
			if skeleton != null and motion.is_running():
				for bone: int in skeleton.get_bone_count():
					worst = maxf(worst, skeleton.get_bone_global_pose(bone).origin.distance_to(
						skeleton.get_bone_global_rest(bone).origin))
		_expect(motion != null and motion.has_springs(), "build %d height %d: the hair has springs" % scale)
		_expect(worst < 0.12, "build %d height %d: spring locks stay bounded (%.1f mm off rest)"
			% [scale[0], scale[1], worst * 1000.0])
		actor.free()
		await process_frame
	camera.queue_free()
	await process_frame
