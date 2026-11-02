extends SceneTree
## Headless checks for how the game loads RL head files at High:
##   * a remote Human whose files are not parsed draws the classic High head
##     while they are parsed on a worker - none on the main thread - and then
##     the RL head in place, exactly as a direct High build draws it;
##   * one switched below High while it waits draws what a Medium build draws;
##   * the player's own actor and portraits (render_quality_is_local) build at
##     once, as before;
##   * an RL file no rig draws any more is let go after the retention time
##     while other RL heads are still drawn, and so is a prewarmed file never
##     drawn; a file drawn again within the time is kept;
##   * the pipeline prewarm parses only the few RL files that carry every
##     shader variant and vertex format the RL files draw at High.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head_deferred_load.gd

const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const HIGH := ActorRenderQuality.Quality.HIGH

var _checks := 0
var _failures := 0
var _models: Dictionary
var _equipment: Dictionary
var _animation: Dictionary
var _next_id := 9800


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures += 1
		push_error("rl head deferred load: " + message)


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _run() -> void:
	_models = (_json("res://data/actors/models.json") as Dictionary).models
	_equipment = _json("res://data/actors/equipment.json")
	_animation = _json("res://data/animations/luminous.json")
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	_check_pipeline_files()
	await _check_deferred_build()
	await _check_file_release()
	RLHeadLibrary.deferred_loading = -1
	RLHeadLibrary.retain_seconds = RLHeadLibrary.RETAIN_SECONDS
	RLHeadLibrary.clear()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("rl head deferred load: %d checks, %d failures" % [_checks, _failures])
	print("rl head deferred load: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _spawn(sex: String, appearance: Dictionary, local := false, quality: int = HIGH) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_next_id += 1
	actor.apply_render_quality(quality, local)
	root.add_child(actor)
	var errors := actor.configure({"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": appearance, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
		_models["luminous_" + sex], _animation, _equipment)
	_expect(errors.is_empty(), "%s configures: %s" % [sex, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor


static func _rl_scenes() -> int:
	var count := 0
	for key: Variant in GlbSceneCache._scenes:
		count += 1 if str(key).contains("rl_heads") else 0
	return count


static func _cached(path: String) -> bool:
	return GlbSceneCache.missing(PackedStringArray([ProjectSettings.globalize_path(path)])).is_empty()


func _misses() -> int:
	return int(GlbSceneCache.retention_snapshot()["lookup_misses"])


func _wait(condition: Callable, seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while not bool(condition.call()) and Time.get_ticks_msec() < deadline:
		await process_frame


static func _material(material: Material) -> String:
	if material == null:
		return ""
	var parameters := {"class": material.get_class()}
	if material is ShaderMaterial:
		var shader := (material as ShaderMaterial).shader
		parameters["shader"] = shader.get_instance_id() if shader != null else 0
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
	return var_to_str(parameters).sha256_text()


## What a viewer of the actor sees, per visible mesh path.
static func _capture(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if not instance.is_visible_in_tree() or instance.is_queued_for_deletion():
			continue
		var materials: Array = []
		for surface: int in (instance.mesh.get_surface_count() if instance.mesh != null else 0):
			materials.append(_material(instance.get_active_material(surface)))
		result[str(actor.get_path_to(instance))] = {"mesh": instance.mesh.get_instance_id() if instance.mesh != null else 0,
			"materials": materials, "shadow": instance.cast_shadow, "layers": instance.layers,
			"margin": instance.extra_cull_margin}
	return result


## The chosen files carry every (shader, vertex format) pair of all RL files,
## and are a small part of them.
func _check_pipeline_files() -> void:
	var paths := RLHeadLibrary.warm_paths()
	var survey := RLHeadLibrary._survey(paths)
	_expect(survey.size() == paths.size(), "every RL file is surveyed (%d of %d)" % [survey.size(), paths.size()])
	var chosen := RLHeadLibrary._choose_pipeline_files(survey)
	var signatures := {}
	var covered := {}
	var chosen_bytes := 0
	var all_bytes := 0
	for path: String in survey:
		all_bytes += int(survey[path].size)
		if chosen.has(path):
			chosen_bytes += int(survey[path].size)
		var sex_style := RLHeadLibrary._file_sex_style(path)
		for surface: Array in survey[path].surfaces:
			var shader := RLHeadLibrary._material_shader_with(str(surface[0]), str(sex_style[0]), str(sex_style[1]),
				HIGH, surface[1] as Dictionary)
			if shader == null:
				continue
			var signature := "%d|%s" % [shader.get_instance_id(), surface[2]]
			signatures[signature] = true
			if chosen.has(path):
				covered[signature] = true
	_expect(not chosen.is_empty() and covered.size() == signatures.size(),
		"the pipeline files carry all %d shader and vertex-format pairs (%d)" % [signatures.size(), covered.size()])
	_expect(chosen.size() <= 10 and chosen_bytes * 5 < all_bytes,
		"only a few small files are parsed for the pipelines: %d of %d files, %.1f of %.1f MB"
		% [chosen.size(), paths.size(), chosen_bytes / 1e6, all_bytes / 1e6])
	print("rl head deferred load: pipeline files %s" % [chosen])
	# Every material the game draws resolves to the same Shader object the
	# survey keyed it by.
	var shared := RLHeadLibrary.material("rl_hair_card", "male", "rowan_shag", HIGH)
	_expect(shared != null and shared.shader == RLHeadLibrary.material_shader("rl_hair_card", "male", "rowan_shag", HIGH),
		"the shared material draws with material_shader's shader")
	var beard := RLHeadLibrary.material("rl_beard", "male", "moustache", HIGH)
	_expect(beard != null and beard.shader == RLHeadLibrary.material_shader("rl_beard", "male", "moustache", HIGH)
		and beard.shader.code.begins_with("#define RL_BEARD_FEATHER"), "a feathered beard keeps its variant")


func _check_deferred_build() -> void:
	RLHeadLibrary.retain_seconds = 0.0
	RLHeadLibrary.deferred_loading = 0
	var look := PRESETS.appearance("Tavi")
	# Everything but the RL files parsed once - the body, its animations,
	# equipment and the classic head's game hairstyle - by a first actor
	# taken through the same path; then no RL file.
	RLHeadLibrary.deferred_loading = 1
	var first := _spawn("male", look)
	await _wait(func() -> bool: return first.rl_head() != null, 60.0)
	first.free()
	await process_frame
	RLHeadLibrary.clear()
	await process_frame
	_expect(_rl_scenes() == 0, "no RL file is parsed to start with")
	var misses := _misses()
	var waiting := _spawn("male", look)
	var body := waiting.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	_expect(waiting.rl_head() == null and body.has_meta(HighPortraitAppearance.META) and RLHeadLibrary.warming(),
		"a remote Human whose files are not parsed draws the classic High head meanwhile")
	_expect(_misses() == misses and _rl_scenes() == 0, "and nothing was parsed on the main thread")
	await _wait(func() -> bool: return waiting.rl_head() != null, 60.0)
	_expect(waiting.rl_head() != null and not body.has_meta(HighPortraitAppearance.META),
		"the RL head takes its place once the worker parsed its files")
	_expect(_misses() == misses, "still without a main-thread parse (%d)" % (_misses() - misses))
	await process_frame
	# The same face built at once draws exactly the same.
	RLHeadLibrary.deferred_loading = 0
	var direct := _spawn("male", look)
	await process_frame
	# Both draw their finished identity bakes (shared per face).
	RLHeadIdentityBake.flush()
	await process_frame
	var a := _capture(waiting)
	var b := _capture(direct)
	var differing: Array = []
	for path: String in a:
		if path.begins_with("NativeModel") and (not b.has(path) or a[path] != b[path]):
			differing.append(path)
	for path: String in b:
		if path.begins_with("NativeModel") and not a.has(path):
			differing.append(path)
	_expect(not a.is_empty() and differing.is_empty(),
		"the swapped-in RL head matches a direct High build %s" % [differing.slice(0, 6)])
	direct.free()
	waiting.free()
	await process_frame
	await _check_switch_down_while_waiting()
	# The player's own actor (and portraits) build at once.
	RLHeadLibrary.deferred_loading = 1
	RLHeadLibrary.clear()
	await process_frame
	var local := _spawn("female", PRESETS.appearance("Mira"), true)
	_expect(local.rl_head() != null and not local._rl_head_waiting,
		"the player's own actor (and a portrait) builds its RL head at once")
	local.free()
	await process_frame
	await process_frame


## A remote Human still waiting for its RL files when the quality drops below
## High draws what a Medium build of it draws (its modern hairstyle on the
## native head), not the classic High head's game hairstyle.
func _check_switch_down_while_waiting() -> void:
	var look := PRESETS.appearance("Tavi")
	for module: int in range(2, 40):
		var candidate := look.merged({"hair_module": module}, true)
		var hair := RLHeadPortraitMap.face(candidate, "male", true).hair
		if hair != RLHeadAppearance.NONE and not hair.begins_with(RLHeadLibrary.LEGACY_PREFIX):
			look = candidate
			break
	RLHeadLibrary.deferred_loading = 1
	RLHeadLibrary.clear()
	await process_frame
	var down := _spawn("male", look)
	_expect(down._rl_head_waiting and down.rl_head() == null and down.hair_module_rig() == null,
		"a cold remote Human waits for its files with the classic High head")
	down.apply_render_quality(ActorRenderQuality.Quality.MEDIUM)
	_expect(not down._rl_head_waiting and down.hair_module_rig() != null,
		"switched to Medium meanwhile it draws its modern hairstyle at once")
	await _wait(func() -> bool: return not RLHeadLibrary.warming(), 60.0)
	await process_frame
	await process_frame
	_expect(down.rl_head() == null and down.hair_module_rig() != null,
		"and stays at Medium once its files are in")
	RLHeadLibrary.deferred_loading = 0
	var medium := _spawn("male", look, false, ActorRenderQuality.Quality.MEDIUM)
	await process_frame
	RLHeadIdentityBake.flush()
	await process_frame
	var a := _capture(down)
	var b := _capture(medium)
	var differing: Array = []
	for path: String in a:
		if path.begins_with("NativeModel") and (not b.has(path) or a[path] != b[path]):
			differing.append(path)
	for path: String in b:
		if path.begins_with("NativeModel") and not a.has(path):
			differing.append(path)
	_expect(not a.is_empty() and differing.is_empty(),
		"it matches a direct Medium build %s" % [differing.slice(0, 6)])
	down.free()
	medium.free()
	await process_frame


func _check_file_release() -> void:
	RLHeadLibrary.retain_seconds = 0.0
	RLHeadLibrary.clear()
	await process_frame
	RLHeadLibrary.deferred_loading = 0
	RLHeadLibrary.retain_seconds = 1.0
	var rowan := _spawn("male", PRESETS.appearance("Rowan"))
	# Another hairstyle module for the second head.
	var other := PRESETS.appearance("Tavi")
	var rowan_paths := RLHeadLibrary.face_paths(RLHeadPortraitMap.face(PRESETS.appearance("Rowan"), "male"))
	for module: int in range(1, 40):
		var candidate := other.merged({"hair_module": module}, true)
		var paths := RLHeadLibrary.face_paths(RLHeadPortraitMap.face(candidate, "male"))
		if paths.size() >= 2 and not rowan_paths.has(paths[1]) and paths[1].contains("/hair/"):
			other = candidate
			break
	var tavi := _spawn("male", other)
	await process_frame
	var rowan_face := rowan.rl_head().appearance if rowan.rl_head() != null else null
	var tavi_face := tavi.rl_head().appearance if tavi.rl_head() != null else null
	_expect(rowan_face != null and tavi_face != null and rowan_face.hair != tavi_face.hair,
		"two RL heads with different hairstyles")
	if rowan_face == null or tavi_face == null:
		rowan.free()
		tavi.free()
		return
	var rowan_hair := RLHeadLibrary.hair_path(rowan_face.hair, "male")
	var tavi_hair := RLHeadLibrary.hair_path(tavi_face.hair, "male")
	var head := RLHeadLibrary.head_path("male")
	_expect(RLHeadLibrary.file_users(head) == 2 and RLHeadLibrary.file_users(rowan_hair) == 1,
		"each rig holds the files it draws")
	# Short frames from here: a timer started in a long frame (the spawns
	# above) counts all of it on its first tick.
	await process_frame
	await process_frame
	rowan.free()
	await process_frame
	_expect(RLHeadLibrary.file_users(rowan_hair) == 0 and _cached(rowan_hair),
		"a file no rig draws is kept for the retention time (%d users, cached %s, %s)"
		% [RLHeadLibrary.file_users(rowan_hair), _cached(rowan_hair), rowan_hair])
	await _wait(func() -> bool: return not _cached(rowan_hair), 5.0)
	_expect(not _cached(rowan_hair) and _cached(tavi_hair) and _cached(head) and RLHeadLibrary.users() == 1,
		"then it is let go while another RL head is still drawn")
	_expect(not RLHeadLibrary._hair_info.has(rowan_hair.get_file().get_basename()),
		"its hairstyle details go with it")
	# A file drawn again within the time is kept.
	var second := _spawn("male", other)
	await process_frame
	await process_frame
	tavi.free()
	await process_frame
	await create_timer(1.5).timeout
	_expect(_cached(tavi_hair) and RLHeadLibrary.file_users(tavi_hair) == 1,
		"a file another rig still draws is kept")
	# A prewarmed file never drawn goes after the time as well.
	var beard := RLHeadLibrary.beard_path("goatee")
	RLHeadLibrary.prewarm(PackedStringArray([beard]))
	await _wait(func() -> bool: return _cached(beard), 30.0)
	_expect(_cached(beard), "a prewarmed file is published")
	await _wait(func() -> bool: return not _cached(beard), 5.0)
	_expect(not _cached(beard) and _cached(tavi_hair), "a prewarmed file no rig draws is let go after the time")
	second.free()
	await process_frame
	await create_timer(1.5).timeout
	RLHeadLibrary.retain_seconds = 0.0
	RLHeadLibrary.release_if_unused()
	await process_frame
	_expect(RLHeadLibrary.users() == 0 and _rl_scenes() == 0, "with no RL head left nothing is held")
