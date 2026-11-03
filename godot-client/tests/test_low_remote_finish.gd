extends SceneTree
## Low actor tier, remote finishing skip (LAT-L4, owner decision 2026-11-02:
## "skip per-vertex body finishing for remote actors" at Low/Performance only).
##
## On the real ReplicatedActor3D, built the way Main builds it (configure under
## the player's quality, then apply_render_quality(level, is_local)):
##   * a remote Human at LOW keeps its source body and face: no mesh carries
##     CharacterProportions' BODY_RESULT_META or RESULT_META, and its meshes are
##     exactly a neutral-faced Human's, beard included (the groom runs on the
##     neutral face the actor draws, even from a fresh groom cache);
##   * repeating the LOW pass does no work (the beard node is the same node);
##   * MEDIUM, HIGH and the local player at LOW finish it, to the same meshes
##     as a body built there; going back to remote LOW restores the exact
##     unfinished actor; a wardrobe or appearance change at LOW stays
##     unfinished, and garments are refined once the quality rises;
##   * MEDIUM and HIGH remote builds finish as before (Medium/High unchanged);
##   * the build profile records the skipped stages for a remote LOW build.
##
##   Godot --headless --path godot-client --script res://tests/test_low_remote_finish.gd

const FIT := preload("res://src/actors/character_proportions.gd")
const GROOM := preload("res://src/actors/portrait_groom.gd")
const LOW := ActorRenderQuality.Quality.LOW
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const HIGH := ActorRenderQuality.Quality.HIGH
## A face far from neutral on every sculpt control the beard coverage reads.
const FACE := {"jaw": 92, "cheekbones": 85, "nose": 18, "face_length": 80, "eye_size": 75,
	"eye_tilt": 30, "eye_spacing": 70, "nose_width": 25, "lip_fullness": 80, "brow_depth": 85}

var _checks := 0
var _failures := 0
var _models: Dictionary
var _equipment: Dictionary
var _animation: Dictionary
var _next_id := 9900


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		print("PASS: ", message)
	else:
		_failures += 1
		push_error("low remote finish: " + message)


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _run() -> void:
	_models = (_json("res://data/actors/models.json") as Dictionary).models
	_equipment = _json("res://data/actors/equipment.json")
	_animation = _json("res://data/animations/luminous.json")
	var had_override := OS.has_environment(LookProfile.QUALITY_VARIABLE)
	var old_override := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	var old_profile := OS.get_environment("ELORIA_ACTOR_BUILD_PROFILE")
	var old_quality := LookProfile.player_quality()
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	_check_policy()
	for sex: String in ["male", "female"]:
		await _check_round_trip(sex)
	await _check_beard_follows_drawn_face()
	await _check_wardrobe_and_appearance()
	await _check_medium_high_unchanged()
	await _check_local_paths()
	await _check_other_races()
	await _check_build_profile()
	LookProfile.set_player_quality(old_quality)
	if had_override:
		OS.set_environment(LookProfile.QUALITY_VARIABLE, old_override)
	else:
		OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	OS.set_environment("ELORIA_ACTOR_BUILD_PROFILE", old_profile)
	# The session cleanup a real exit runs: animation sources own detached
	# Nodes, and the shape caches hold meshes built from the freed actors.
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	FIT.clear()
	GROOM.clear()
	print("low remote finish: %d checks, %d failures" % [_checks, _failures])
	quit(1 if _failures > 0 else 0)


## Main's two creation seams: the local player is marked local before
## configure; every other actor configures under the player's quality and is
## told its role right after (main.gd `_spawn_actor` / `_revive_actor`).
func _spawn(slug: String, appearance: Dictionary, equipment: Dictionary, quality: int,
		local := false) -> ReplicatedActor3D:
	LookProfile.set_player_quality(quality)
	var actor := ReplicatedActor3D.new()
	_next_id += 1
	if local:
		actor.apply_render_quality(quality, true)
	root.add_child(actor)
	var errors := actor.configure({"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": appearance, "equipment_visuals": equipment},
		CoordinateAdapter.new({"walkingHeight": 0.0}), _models[slug], _animation, _equipment)
	_expect(errors.is_empty(), "%s configures: %s" % [slug, errors])
	actor.apply_render_quality(quality, local)
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor


func _human(sex: String, beard := true) -> Dictionary:
	var look := FACE.duplicate()
	look["hair"] = AppearanceVariants.pack_hair(2, 0)
	look["facial_hair"] = 3 if sex == "male" and beard else 0
	look["skin"] = 2
	return look


func _neutral(look: Dictionary) -> Dictionary:
	var neutral := look.duplicate()
	for key: String in FIT.FACE_FIELDS:
		neutral.erase(key)
	return neutral


## Meshes carrying a body-refinement or face-sculpt result under NativeModel.
func _finished(actor: ReplicatedActor3D) -> Dictionary:
	var result := {"body": 0, "face": 0, "equipment_body": 0}
	var native := actor.get_node_or_null("NativeModel") as Node3D
	if native == null:
		return result
	for node: Node in native.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if instance.has_meta(FIT.BODY_RESULT_META) and instance.mesh == instance.get_meta(FIT.BODY_RESULT_META):
			result.body += 1
			if instance.has_meta("native_equipment"):
				result.equipment_body += 1
		if instance.has_meta(FIT.RESULT_META) and instance.mesh == instance.get_meta(FIT.RESULT_META):
			result.face += 1
	return result


func _unfinished(actor: ReplicatedActor3D) -> bool:
	var native := actor.get_node_or_null("NativeModel") as Node3D
	if native == null:
		return false
	for node: Node in native.find_children("*", "MeshInstance3D", true, false):
		for meta: StringName in [FIT.BODY_RESULT_META, FIT.BODY_SOURCE_META, FIT.RESULT_META, FIT.SOURCE_META]:
			if node.has_meta(meta):
				return false
	return true


static func _sha(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	var bytes := var_to_bytes(value)
	if not bytes.is_empty():
		context.update(bytes)
	return context.finish().hex_encode().left(20)


func _mesh(mesh: Mesh) -> String:
	if mesh == null:
		return ""
	var parts: Array = []
	for surface: int in mesh.get_surface_count():
		parts.append(_sha(mesh.surface_get_arrays(surface)))
		parts.append(_sha(mesh.surface_get_blend_shape_arrays(surface)))
	return _sha(parts)


## The meshes the Human shape finish can touch. RLHeadRig's own head, beard
## and hair meshes (RLHeadRig.MESH_META) are left out: refinement, sculpt and
## groom never touch them, and the rig swaps them on its own clock (identity
## bakes after RLHeadIdentityBake.BAKE_DELAY_MSEC, LOD bands ranked every few
## frames), so they would compare timing, not finishing.
func _finish_meshes(actor: ReplicatedActor3D) -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if not instance.is_visible_in_tree() or instance.is_queued_for_deletion() \
				or instance.has_meta(RLHeadRig.MESH_META):
			continue
		result.append(instance)
	return result


## What a viewer sees of the actor's geometry, per visible mesh path. Mesh
## content, not identity, so a rebuilt cache entry compares equal.
func _geometry(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for instance: MeshInstance3D in _finish_meshes(actor):
		result[str(actor.get_path_to(instance))] = {"mesh": _mesh(instance.mesh),
			"shadow": instance.cast_shadow, "lod_bias": instance.lod_bias}
	return result


## The same plus the identity of every mesh resource and material: proves a
## round trip hands back the very resources, not equal copies.
func _resources(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for instance: MeshInstance3D in _finish_meshes(actor):
		var materials: Array = []
		for surface: int in (instance.mesh.get_surface_count() if instance.mesh != null else 0):
			var material := instance.get_active_material(surface)
			materials.append(material.get_instance_id() if material != null else 0)
		result[str(actor.get_path_to(instance))] = {
			"mesh": instance.mesh.get_instance_id() if instance.mesh != null else 0,
			"materials": materials, "shadow": instance.cast_shadow, "lod_bias": instance.lod_bias,
			"visible": instance.visible}
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


func _beard(actor: ReplicatedActor3D) -> MeshInstance3D:
	return actor.get_node_or_null("NativeModel/PortraitFacialHair") as MeshInstance3D


func _free(actors: Array) -> void:
	for actor: Variant in actors:
		if is_instance_valid(actor):
			(actor as Node).free()
	await process_frame


func _check_policy() -> void:
	_expect(not ActorRenderQuality.remote_body_finish(LOW)
		and ActorRenderQuality.remote_body_finish(MEDIUM)
		and ActorRenderQuality.remote_body_finish(HIGH),
		"the policy skips remote finishing at LOW only")


func _check_round_trip(sex: String) -> void:
	var slug := "luminous_" + sex
	var look := _human(sex)
	var actor := _spawn(slug, look, {}, LOW)
	await process_frame
	_expect(_unfinished(actor), "%s: a remote Human at LOW keeps its source body and face meshes" % sex)
	_expect(actor._human_shape_finish == ReplicatedActor3D.HumanShapeFinish.UNFINISHED,
		"%s: the actor records the unfinished shape" % sex)
	if sex == "male":
		_expect(_beard(actor) != null, "male: the beard shell is still groomed at LOW")
	var low_geometry := _geometry(actor)
	var low_resources := _resources(actor)
	var beard_before := _beard(actor)
	# Main reapplies the quality on revival and on every quality pass: no work.
	actor.apply_render_quality(LOW, false)
	actor.apply_render_quality(LOW, false)
	_expect(_beard(actor) == beard_before and _differences(low_resources, _resources(actor)).is_empty(),
		"%s: repeating remote LOW regrooms nothing and changes no resource" % sex)

	# A neutral-faced remote Human at LOW is the reference for the shape a
	# sculpted one draws there: the same source body and face, the same beard.
	var neutral_low := _spawn(slug, _neutral(look), {}, LOW)
	await process_frame
	var diff := _differences(low_geometry, _geometry(neutral_low))
	_expect(diff.is_empty(), "%s: remote LOW draws exactly a neutral-faced Human's geometry %s" % [sex, diff.slice(0, 6)])

	var medium := _spawn(slug, look, {}, MEDIUM)
	await process_frame
	var medium_finished := _finished(medium)
	_expect(medium_finished.body > 0 and medium_finished.face > 0,
		"%s: a remote Human built at MEDIUM is refined and sculpted (%s)" % [sex, medium_finished])

	actor.apply_render_quality(MEDIUM, false)
	await process_frame
	var raised := _finished(actor)
	_expect(raised.body > 0 and raised.face > 0, "%s: raising LOW to MEDIUM finishes the remote body (%s)" % [sex, raised])
	diff = _differences(_geometry(medium), _geometry(actor))
	_expect(diff.is_empty(), "%s: finished later equals finished at build %s" % [sex, diff.slice(0, 6)])

	actor.apply_render_quality(LOW, false)
	await process_frame
	_expect(_unfinished(actor), "%s: back to remote LOW gives the derived meshes back" % sex)
	diff = _differences(low_geometry, _geometry(actor))
	var beard_ok := sex != "male" or _beard(actor) != null
	_expect(diff.is_empty() and beard_ok,
		"%s: MEDIUM -> LOW restores the exact unfinished geometry %s" % [sex, diff.slice(0, 6)])
	# Source meshes come back by identity (only the regroomed beard is a new node
	# on the cached mesh).
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var low_body: Dictionary = low_resources.get(str(actor.get_path_to(body)), {})
	_expect(body != null and int(low_body.get("mesh", -1)) == body.mesh.get_instance_id(),
		"%s: the body is the very source mesh again" % sex)

	actor.apply_render_quality(LOW, true)
	await process_frame
	var local := _finished(actor)
	_expect(local.body > 0 and local.face > 0, "%s: becoming the local player at LOW finishes it (%s)" % [sex, local])
	var local_low := _spawn(slug, look, {}, LOW, true)
	await process_frame
	diff = _differences(_geometry(local_low), _geometry(actor))
	_expect(diff.is_empty(), "%s: equals a local player built at LOW %s" % [sex, diff.slice(0, 6)])
	actor.apply_render_quality(LOW, false)
	await process_frame
	diff = _differences(low_geometry, _geometry(actor))
	_expect(_unfinished(actor) and diff.is_empty(),
		"%s: the local role given up at LOW unfinishes it again (unfinished %s) %s" % [sex, _unfinished(actor), diff.slice(0, 6)])
	await _free([actor, neutral_low, medium, local_low])


## The groom fits the beard to the face drawn. With fresh groom caches, the
## beard of a sculpted face kept unfinished at LOW is the neutral face's beard;
## grooming it with the player's face would give a different shell (so the
## neutral appearance is load-bearing, not a coincidence of caching).
func _check_beard_follows_drawn_face() -> void:
	var look := _human("male")
	GROOM.clear()
	var sculpted := _spawn("luminous_male", look, {}, LOW)
	await process_frame
	var sculpted_beard := _beard(sculpted)
	var sculpted_hash := _mesh(sculpted_beard.mesh) if sculpted_beard != null else ""
	GROOM.clear()
	var neutral := _spawn("luminous_male", _neutral(look), {}, LOW)
	await process_frame
	var neutral_beard := _beard(neutral)
	_expect(sculpted_beard != null and neutral_beard != null
		and sculpted_hash == _mesh(neutral_beard.mesh),
		"a sculpted face's LOW beard is built for the neutral face it draws (fresh caches)")
	# What grooming with the face choices would build on the same source body.
	GROOM.clear()
	GROOM.apply(sculpted.get_node("NativeModel") as Node3D, sculpted.get_skeleton(), look, _models["luminous_male"])
	var face_aware := _beard(sculpted)
	_expect(face_aware != null and _mesh(face_aware.mesh) != sculpted_hash,
		"the face choices would shape a different beard on the source body (the neutral groom matters)")
	GROOM.clear()
	await _free([sculpted, neutral])


func _check_wardrobe_and_appearance() -> void:
	var look := _human("male")
	var loadout := CreationArchetypes.loadout_at(1)
	var actor := _spawn("luminous_male", look, {}, LOW)
	await process_frame
	actor.apply_equipment_visuals(loadout)
	await process_frame
	var garments := 0
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		if node.has_meta("native_equipment"):
			garments += 1
	_expect(garments > 0 and _unfinished(actor), "a wardrobe change at remote LOW stays unfinished (%d garments)" % garments)
	var dressed := _spawn("luminous_male", look, loadout, LOW)
	await process_frame
	var diff := _differences(_geometry(dressed), _geometry(actor))
	_expect(diff.is_empty(), "dressing at LOW equals a Human built dressed at LOW %s" % [diff.slice(0, 6)])
	actor.apply_render_quality(MEDIUM, false)
	await process_frame
	var raised := _finished(actor)
	_expect(raised.equipment_body > 0 and raised.face > 0,
		"raising the quality refines the worn garments with the body (%s)" % raised)
	actor.apply_render_quality(LOW, false)
	await process_frame
	diff = _differences(_geometry(dressed), _geometry(actor))
	_expect(_unfinished(actor) and diff.is_empty(),
		"and LOW gives every garment's source mesh back (unfinished %s) %s" % [_unfinished(actor), diff.slice(0, 6)])
	var changed := look.duplicate()
	changed["jaw"] = 10
	changed["facial_hair"] = 4
	actor.apply_appearance_variants(changed)
	await process_frame
	_expect(_unfinished(actor) and _beard(actor) != null,
		"an appearance change at remote LOW stays unfinished and regrooms the beard")
	await _free([actor, dressed])


func _check_medium_high_unchanged() -> void:
	for quality: int in [MEDIUM, HIGH]:
		for sex: String in ["male", "female"]:
			var actor := _spawn("luminous_" + sex, _human(sex), {}, quality)
			await process_frame
			var finished := _finished(actor)
			var rl := actor.rl_head() != null
			# With the RL head (High), the body's own head is hidden and left
			# unsculpted, as before; the body is refined to the cut mesh.
			_expect(finished.body > 0 and (rl or finished.face > 0),
				"%s %s: a remote build is finished as before (%s, rl head %s)" % [
					ActorRenderQuality.quality_name(quality), sex, finished, rl])
			_expect(actor._human_shape_finish == ReplicatedActor3D.HumanShapeFinish.FULL,
				"%s %s: the actor records the full shape" % [ActorRenderQuality.quality_name(quality), sex])
			if quality == HIGH:
				# High -> Low -> High in place: the remote body goes unfinished at
				# Low (with or without the RL head) and is finished again.
				actor.apply_render_quality(LOW, false)
				await process_frame
				_expect(_unfinished(actor) and actor.rl_head() == null,
					"high %s: switching a remote Human down to LOW unfinishes it" % sex)
				actor.apply_render_quality(HIGH, false)
				await process_frame
				var again := _finished(actor)
				_expect(again.body > 0 and (actor.rl_head() != null) == rl and (rl or again.face > 0),
					"high %s: and back to HIGH finishes it as built (%s)" % [sex, again])
			await _free([actor])


func _check_local_paths() -> void:
	# Main's local seam: marked local before configure, finished during it.
	var local := _spawn("luminous_female", _human("female"), {}, LOW, true)
	await process_frame
	var finished := _finished(local)
	_expect(finished.body > 0 and finished.face > 0, "the local player built at LOW is finished (%s)" % finished)
	# The campaign replay / leaderboard seam: configured first, then marked local.
	LookProfile.set_player_quality(LOW)
	var replay := ReplicatedActor3D.new()
	_next_id += 1
	root.add_child(replay)
	var errors := replay.configure({"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": _human("female"), "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), _models["luminous_female"], _animation, _equipment)
	_expect(errors.is_empty(), "the replay seam configures: %s" % [errors])
	_expect(_unfinished(replay), "configured at LOW without a role it is unfinished")
	replay.apply_render_quality(LOW, true)
	await process_frame
	var diff := _differences(_geometry(local), _geometry(replay))
	_expect(_finished(replay).face > 0 and diff.is_empty(),
		"marked local afterwards it is finished once, as the local build %s" % [diff.slice(0, 6)])
	await _free([local, replay])


func _check_other_races() -> void:
	# Body refinement and face sculpt are the Human's only; other races on the
	# Human body never enter either path.
	var orun := _spawn("orun_male", {"jaw": 90, "facial_hair": 3}, {}, LOW)
	await process_frame
	_expect(_unfinished(orun) and orun._human_shape_finish == ReplicatedActor3D.HumanShapeFinish.NONE,
		"an Orun at remote LOW is untouched by the Human finish")
	orun.apply_render_quality(HIGH, false)
	orun.apply_render_quality(LOW, false)
	_expect(orun._human_shape_finish == ReplicatedActor3D.HumanShapeFinish.NONE,
		"quality changes leave a non-Human's finish state alone")
	await _free([orun])


func _check_build_profile() -> void:
	OS.set_environment("ELORIA_ACTOR_BUILD_PROFILE", "1")
	# The ranger, not the arcanist: a finished arcanist Human makes the headless
	# engine crash at exit, on the wave-1 code as well (independent of this test).
	var remote := _spawn("luminous_male", _human("male"), CreationArchetypes.loadout_at(1), LOW)
	await process_frame
	var medium := _spawn("luminous_male", _human("male"), CreationArchetypes.loadout_at(1), MEDIUM)
	await process_frame
	OS.set_environment("ELORIA_ACTOR_BUILD_PROFILE", "")
	var remote_timings := remote.configuration_timings_usec()
	var medium_timings := medium.configuration_timings_usec()
	var skipped := true
	var restored := false
	for key: String in remote_timings:
		if key.ends_with("finish.body_refinement") or key.ends_with("finish.face_proportions"):
			skipped = false
		if key.ends_with("finish.unfinished_restore"):
			restored = true
	_expect(skipped and restored, "a remote LOW build profiles no refinement or sculpt stage")
	var refined := false
	for key: String in medium_timings:
		if key.ends_with("finish.body_refinement"):
			refined = true
	_expect(refined, "a MEDIUM build still profiles its refinement stage")
	print("finish profile remote LOW: ", _finish_usec(remote_timings), " MEDIUM: ", _finish_usec(medium_timings))
	await _free([remote, medium])


func _finish_usec(timings: Dictionary) -> Dictionary:
	var result := {}
	for key: String in timings:
		if key.contains(".finish"):
			result[key] = timings[key]
	return result
