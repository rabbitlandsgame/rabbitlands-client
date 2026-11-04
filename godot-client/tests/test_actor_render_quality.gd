extends SceneTree
## Contract for the actor-only graphics-quality policy.  These are structural
## tests: they use real MeshInstance3D properties but need no rendered frame.

const Policy := preload("res://src/actors/actor_render_quality.gd")
const Look := preload("res://src/world/look/look_profile.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_presets()
	_check_low_actor_tier()
	_check_mesh_application()
	_check_actor_tree()
	_check_far_presentation()
	_check_far_ranks()
	_check_capes()
	_check_runtime_actor()
	_check_main_wiring()
	print("actor render quality: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _check_presets() -> void:
	_expect(Policy.Quality.LOW == Look.Quality.LOW
		and Policy.Quality.MEDIUM == Look.Quality.MEDIUM
		and Policy.Quality.HIGH == Look.Quality.HIGH,
		"actor and frame qualities share one numeric contract")
	_expect(Policy.QUALITY_PRESETS.size() == Policy.QUALITY_NAMES.size(),
		"every named quality has a preset")
	var high: Dictionary = Policy.QUALITY_PRESETS[Policy.Quality.HIGH]
	for level: int in Policy.QUALITY_NAMES.size():
		var row: Dictionary = Policy.QUALITY_PRESETS[level]
		_expect(row.keys() == high.keys(),
			"%s has HIGH's policy fields" % Policy.quality_name(level))
		for key: String in high:
			_expect(typeof(row[key]) == typeof(high[key]),
				"%s.%s keeps HIGH's value type" % [Policy.quality_name(level), key])
	_expect(Policy.lod_bias_scale(Policy.Quality.LOW)
		< Policy.lod_bias_scale(Policy.Quality.MEDIUM)
		and Policy.lod_bias_scale(Policy.Quality.MEDIUM)
		< Policy.lod_bias_scale(Policy.Quality.HIGH),
		"lower qualities select imported LODs earlier")
	_expect(not Policy.casts_shadows(Policy.Quality.LOW)
		and Policy.casts_shadows(Policy.Quality.MEDIUM)
		and Policy.casts_shadows(Policy.Quality.HIGH),
		"only LOW gives up actor shadows")
	_expect(Policy.normalized_quality(-1) == Policy.Quality.HIGH
		and Policy.normalized_quality(99) == Policy.Quality.HIGH
		and Policy.quality_name(99) == "high",
		"an unknown quality safely uses HIGH")


## The Low actor tier's table (wave 2 LAT-L0). MEDIUM and HIGH must stay what
## every consumer used before the tier: their rows are compared as text, so a
## changed value, type or key order fails, and each neutral value is checked
## against the constant its consumer still owns. LOW carries the approved
## values. The LOD biases stay 0.35 / 0.65 / 1.0 (schedule 1.1 #5).
func _check_low_actor_tier() -> void:
	var golden := {
		Policy.Quality.LOW: {
			"lod_bias_scale": 0.35, "cast_shadows": false, "non_local_cape": false,
			"body_cap_default": 60, "full_rate_metres": 35.0,
			"hand_detail_metres": 12.0, "hand_detail_release_metres": 15.0,
			"combat_cues_full_rate_only": true, "effect_scale": 0.25,
			"overhead_cap": 24, "local_cape_step_hz": 30,
			"remote_body_finish": false, "frame_driven_motion": true,
		},
		Policy.Quality.MEDIUM: {
			"lod_bias_scale": 0.65, "cast_shadows": true, "non_local_cape": false,
			"body_cap_default": 160, "full_rate_metres": 45.0,
			"hand_detail_metres": INF, "hand_detail_release_metres": INF,
			"combat_cues_full_rate_only": false, "effect_scale": 0.75,
			"overhead_cap": 0, "local_cape_step_hz": 60,
			"remote_body_finish": true, "frame_driven_motion": false,
		},
		Policy.Quality.HIGH: {
			"lod_bias_scale": 1.0, "cast_shadows": true, "non_local_cape": true,
			"body_cap_default": 160, "full_rate_metres": 45.0,
			"hand_detail_metres": INF, "hand_detail_release_metres": INF,
			"combat_cues_full_rate_only": false, "effect_scale": 1.0,
			"overhead_cap": 0, "local_cape_step_hz": 60,
			"remote_body_finish": true, "frame_driven_motion": false,
		},
	}
	for level: int in golden:
		_expect(var_to_str(Policy.QUALITY_PRESETS[level]) == var_to_str(golden[level]),
			"the %s row is exactly the approved table: %s" % [Policy.quality_name(level),
				var_to_str(Policy.QUALITY_PRESETS[level]).replace("\n", " ")])
	_expect(Policy.lod_bias_scale(Policy.Quality.LOW) == 0.35
		and Policy.lod_bias_scale(Policy.Quality.MEDIUM) == 0.65
		and Policy.lod_bias_scale(Policy.Quality.HIGH) == 1.0,
		"the actor LOD biases stay 0.35 / 0.65 / 1.0")

	# Every accessor reads its own column, for every level.
	for level: int in golden:
		var row: Dictionary = golden[level]
		var name := Policy.quality_name(level)
		_expect(Policy.body_cap_default(level) == row.body_cap_default
			and Policy.full_rate_metres(level) == row.full_rate_metres
			and Policy.hand_detail_metres(level) == row.hand_detail_metres
			and Policy.hand_detail_release_metres(level) == row.hand_detail_release_metres
			and Policy.combat_cues_full_rate_only(level) == row.combat_cues_full_rate_only
			and Policy.effect_scale(level) == row.effect_scale
			and Policy.overhead_cap(level) == row.overhead_cap
			and Policy.local_cape_step_hz(level) == row.local_cape_step_hz
			and Policy.remote_body_finish(level) == row.remote_body_finish
			and Policy.frame_driven_motion(level) == row.frame_driven_motion,
			"the %s accessors return the %s row" % [name, name])
		_expect(Policy.hand_detail_release_metres(level) >= Policy.hand_detail_metres(level),
			"%s releases finger detail no nearer than it grants it" % name)
	_expect(Policy.body_cap_default(99) == 160 and Policy.effect_scale(-1) == 1.0
		and not Policy.frame_driven_motion(99),
		"an unknown quality reads HIGH's tier values")

	# MEDIUM and HIGH equal what the consuming code does today, read from that
	# code where it still owns a constant (a literal stands in once a later
	# chunk moves the constant into this table).
	var body_cap := int(_constant("res://src/world/crowd_presentation.gd", "BODY_CAP_DEFAULT", 160))
	var half_rate := float(_constant("res://src/world/animation_gate.gd", "HALF_RATE_METRES", 45.0))
	var cape_step := float(_constant("res://src/actors/cape_cloth.gd", "FIXED_STEP", 1.0 / 60.0))
	for level: int in [Policy.Quality.MEDIUM, Policy.Quality.HIGH]:
		var name := Policy.quality_name(level)
		_expect(body_cap == 160 and Policy.body_cap_default(level) == body_cap,
			"%s keeps the crowd's 160-body default" % name)
		_expect(half_rate == 45.0 and Policy.full_rate_metres(level) == half_rate,
			"%s keeps the 45 m full-rate distance" % name)
		_expect(Policy.local_cape_step_hz(level) == 60
			and Policy.local_cape_step_hz(level) == roundi(1.0 / cape_step),
			"%s keeps the local cape on its 60 Hz step" % name)
		_expect(is_inf(Policy.hand_detail_metres(level))
			and not Policy.combat_cues_full_rate_only(level)
			and Policy.overhead_cap(level) == 0
			and Policy.remote_body_finish(level)
			and not Policy.frame_driven_motion(level),
			"%s keeps fingers, cues, banners, remote finishing and physics-tick motion" % name)
	var budget_script := load("res://src/world/live_effect_budget.gd") as Script
	_expect(budget_script != null, "the live-effect budget loads")
	if budget_script != null:
		var budget: RefCounted = budget_script.new()
		var limits: Dictionary = budget_script.get_script_constant_map().get("LIMITS", {})
		var same := not limits.is_empty()
		for level: int in [Policy.Quality.MEDIUM, Policy.Quality.HIGH]:
			budget.set("quality", level)
			for kind: StringName in limits:
				same = same and int(budget.call("limit", kind)) \
					== maxi(1, int(int(limits[kind]) * Policy.effect_scale(level)))
		_expect(same, "MEDIUM and HIGH effect scales give today's live-effect limits")

	# LOW is the approved tier.
	var low := Policy.Quality.LOW
	_expect(Policy.body_cap_default(low) == 60 and Policy.full_rate_metres(low) == 35.0
		and Policy.hand_detail_metres(low) == 12.0 and Policy.hand_detail_release_metres(low) == 15.0
		and Policy.combat_cues_full_rate_only(low) and Policy.effect_scale(low) == 0.25
		and Policy.overhead_cap(low) == 24 and Policy.local_cape_step_hz(low) == 30
		and not Policy.remote_body_finish(low) and Policy.frame_driven_motion(low),
		"LOW returns the Low actor tier: 60 bodies, 35 m, fingers within 12-15 m, cues at full rate, "
		+ "0.25 effects, 24 banners, 30 Hz local cape, no remote finishing, frame-driven motion")


## `name` in the script at `path`, or `fallback` when the script no longer has it.
func _constant(path: String, name: String, fallback: Variant) -> Variant:
	var script := load(path) as Script
	if script == null:
		_expect(false, "%s loads" % path)
		return fallback
	return script.get_script_constant_map().get(name, fallback)


func _check_mesh_application() -> void:
	var mesh := MeshInstance3D.new()
	var geometry := BoxMesh.new()
	var authored := StandardMaterial3D.new()
	var override := StandardMaterial3D.new()
	var surface_override := StandardMaterial3D.new()
	geometry.material = authored
	mesh.mesh = geometry
	mesh.material_override = override
	mesh.set_surface_override_material(0, surface_override)
	mesh.lod_bias = 2.0
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED

	Policy.apply_mesh(mesh, Policy.Quality.LOW)
	_expect(is_equal_approx(mesh.lod_bias, 0.7)
		and mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"LOW advances LODs and disables shadow casting")
	_expect(mesh.mesh == geometry and geometry.material == authored
		and mesh.material_override == override
		and mesh.get_surface_override_material(0) == surface_override,
		"quality changes preserve mesh and material resource identity")

	Policy.apply_mesh(mesh, Policy.Quality.MEDIUM)
	_expect(is_equal_approx(mesh.lod_bias, 1.3)
		and mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED,
		"MEDIUM derives from authored values and restores authored shadows")
	Policy.apply_mesh(mesh, Policy.Quality.HIGH)
	_expect(is_equal_approx(mesh.lod_bias, 2.0)
		and mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED,
		"HIGH restores authored LOD and shadow behavior")

	# An intentionally shadowless helper must not start casting at a quality
	# that allows shadows.
	var shadowless := MeshInstance3D.new()
	shadowless.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	Policy.apply_mesh(shadowless, Policy.Quality.HIGH)
	_expect(shadowless.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"HIGH preserves intentionally shadowless geometry")

	Policy.apply_mesh(mesh, Policy.Quality.LOW)
	Policy.restore_mesh(mesh)
	_expect(is_equal_approx(mesh.lod_bias, 2.0)
		and mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED,
		"restore_mesh returns both authored properties")
	# After restore, a changed authored value becomes the next baseline.
	mesh.lod_bias = 3.0
	Policy.apply_mesh(mesh, Policy.Quality.MEDIUM)
	_expect(is_equal_approx(mesh.lod_bias, 1.95),
		"restoring forgets the old baseline")

	mesh.free()
	shadowless.free()


func _check_actor_tree() -> void:
	var actor := Node3D.new()
	var body := MeshInstance3D.new()
	var equipment_root := Node3D.new()
	var equipment := MeshInstance3D.new()
	body.lod_bias = 1.0
	equipment.lod_bias = 1.5
	actor.add_child(body)
	actor.add_child(equipment_root)
	equipment_root.add_child(equipment)
	Policy.apply_actor(actor, Policy.Quality.LOW)
	_expect(is_equal_approx(body.lod_bias, 0.35)
		and is_equal_approx(equipment.lod_bias, 0.525),
		"apply_actor reaches body and runtime equipment descendants")
	Policy.restore_actor(actor)
	_expect(is_equal_approx(body.lod_bias, 1.0)
		and is_equal_approx(equipment.lod_bias, 1.5),
		"restore_actor restores every descendant")
	actor.free()


## The far overlay (actor LODs C5): the coarsest chain level and no shadow at
## every quality, without touching resources, and the quality's own values
## back as soon as the body is no longer far - from the authored baseline, so
## toggling never compounds and the default (far false) path is today's.
func _check_far_presentation() -> void:
	_expect(Policy.FAR_LOD_BIAS == Policy.MIN_LOD_BIAS,
		"far presentation selects the coarsest level any bias can")
	var double := GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED
	var off := GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for level: int in Policy.QUALITY_NAMES.size():
		var name := Policy.quality_name(level)
		var mesh := MeshInstance3D.new()
		var geometry := BoxMesh.new()
		var override := StandardMaterial3D.new()
		mesh.mesh = geometry
		mesh.material_override = override
		mesh.lod_bias = 2.0
		mesh.cast_shadow = double
		# Today's path, then the explicit far = false path: the same values.
		Policy.apply_mesh(mesh, level)
		var plain_bias := mesh.lod_bias
		var plain_shadow := mesh.cast_shadow
		Policy.apply_mesh(mesh, level, false)
		_expect(mesh.lod_bias == plain_bias and mesh.cast_shadow == plain_shadow
			and is_equal_approx(plain_bias, 2.0 * Policy.lod_bias_scale(level)),
			"%s without far draws exactly what the quality draws" % name)
		for pass_index: int in 3:
			Policy.apply_mesh(mesh, level, true)
			_expect(is_equal_approx(mesh.lod_bias, Policy.FAR_LOD_BIAS) and mesh.cast_shadow == off,
				"%s far draws the coarsest level without a shadow (pass %d)" % [name, pass_index])
			Policy.apply_mesh(mesh, level)
			_expect(mesh.lod_bias == plain_bias and mesh.cast_shadow == plain_shadow,
				"%s leaving far restores the quality's bias and shadow (pass %d)" % [name, pass_index])
		_expect(mesh.mesh == geometry and mesh.material_override == override,
			"%s far keeps mesh and material identity" % name)
		# Far first, before any quality: the authored values are still the
		# baseline the quality and restore_mesh() return to.
		var fresh := MeshInstance3D.new()
		fresh.lod_bias = 1.5
		fresh.cast_shadow = double
		Policy.apply_mesh(fresh, level, true)
		Policy.apply_mesh(fresh, level)
		_expect(is_equal_approx(fresh.lod_bias, 1.5 * Policy.lod_bias_scale(level))
			and fresh.cast_shadow == (double if Policy.casts_shadows(level) else off),
			"%s far applied first keeps the authored baseline" % name)
		Policy.apply_mesh(fresh, level, true)
		Policy.restore_mesh(fresh)
		_expect(is_equal_approx(fresh.lod_bias, 1.5) and fresh.cast_shadow == double,
			"%s restore_mesh after far returns the authored values" % name)
		mesh.free()
		fresh.free()

	# Intentionally shadowless geometry stays shadowless after far.
	var shadowless := MeshInstance3D.new()
	shadowless.cast_shadow = off
	Policy.apply_mesh(shadowless, Policy.Quality.HIGH, true)
	Policy.apply_mesh(shadowless, Policy.Quality.HIGH)
	_expect(shadowless.cast_shadow == off, "far then HIGH keeps shadowless geometry shadowless")
	shadowless.free()

	# The tree walk passes far to every descendant, and back.
	var actor := Node3D.new()
	var body := MeshInstance3D.new()
	var holder := Node3D.new()
	var equipment := MeshInstance3D.new()
	body.lod_bias = 1.0
	equipment.lod_bias = 1.5
	actor.add_child(body)
	actor.add_child(holder)
	holder.add_child(equipment)
	Policy.apply_actor(actor, Policy.Quality.MEDIUM, true)
	_expect(is_equal_approx(body.lod_bias, Policy.FAR_LOD_BIAS)
		and is_equal_approx(equipment.lod_bias, Policy.FAR_LOD_BIAS)
		and body.cast_shadow == off and equipment.cast_shadow == off,
		"apply_actor far reaches body and runtime equipment descendants")
	Policy.apply_actor(actor, Policy.Quality.MEDIUM)
	_expect(is_equal_approx(body.lod_bias, 0.65) and is_equal_approx(equipment.lod_bias, 0.975)
		and body.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON,
		"apply_actor without far gives every descendant MEDIUM back")
	actor.free()


## The far tier's size per quality (actor-lod.md 3(e): 24 / 20 / 16 detail
## bodies, 4 of hysteresis) and the rank rule C7 applies.
func _check_far_ranks() -> void:
	_expect(Policy.FAR_DETAIL_BODIES.size() == Policy.QUALITY_NAMES.size(),
		"every named quality has a far tier size")
	_expect(Policy.far_detail_bodies(Policy.Quality.LOW) == 16
		and Policy.far_detail_bodies(Policy.Quality.MEDIUM) == 20
		and Policy.far_detail_bodies(Policy.Quality.HIGH) == 24
		and Policy.FAR_HYSTERESIS_BODIES == 4,
		"the far tier keeps 16 / 20 / 24 bodies in full, with 4 of hysteresis")
	_expect(Policy.far_detail_bodies(-1) == 24 and Policy.far_detail_bodies(99) == 24,
		"an unknown quality uses HIGH's far tier size")
	for level: int in Policy.QUALITY_NAMES.size():
		var name := Policy.quality_name(level)
		var detail := Policy.far_detail_bodies(level)
		var enter := detail + Policy.FAR_HYSTERESIS_BODIES
		_expect(not Policy.far_by_rank(-1, level, false) and not Policy.far_by_rank(-1, level, true),
			"%s never draws an unranked (priority or out-of-view) body far" % name)
		_expect(not Policy.far_by_rank(0, level, true) and not Policy.far_by_rank(detail - 1, level, true),
			"%s brings a far body back inside the nearest %d" % [name, detail])
		_expect(Policy.far_by_rank(detail, level, true) and Policy.far_by_rank(enter, level, true),
			"%s keeps a far body far from rank %d" % [name, detail])
		_expect(not Policy.far_by_rank(detail, level, false)
			and not Policy.far_by_rank(enter - 1, level, false)
			and Policy.far_by_rank(enter, level, false),
			"%s sends a full body far only from rank %d" % [name, enter])
		# A crowd that walks out and back in flips each body at most once per
		# crossing: no rank changes the answer of both states.
		var flips := 0
		var far := false
		for rank: int in [detail - 2, detail, detail + 2, enter, detail + 2, detail, detail - 2]:
			var next := Policy.far_by_rank(rank, level, far)
			flips += int(next != far)
			far = next
		_expect(flips == 2, "%s flips a body twice over one walk out and back (%d)" % [name, flips])


func _check_capes() -> void:
	for level: int in Policy.QUALITY_NAMES.size():
		_expect(Policy.cape_enabled(level, true),
			"the local player's cape remains enabled at %s" % Policy.quality_name(level))
	_expect(not Policy.cape_enabled(Policy.Quality.LOW, false)
		and not Policy.cape_enabled(Policy.Quality.MEDIUM, false)
		and Policy.cape_enabled(Policy.Quality.HIGH, false),
		"only HIGH enables cape simulation for non-local actors")


## The policy above is deliberately standalone; this proves the actor owns its
## current answer, applies it only to body presentation, and reapplies it to
## hair and equipment created after the setting changed.
func _check_runtime_actor() -> void:
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json")) as Dictionary
	var model: Dictionary = (registry.get("models", {}) as Dictionary).get(
		"luminous_male", {}).duplicate(true) as Dictionary
	# The face mask is a generated PNG that is intentionally absent from this
	# checkout's lean test assets; it is unrelated to mesh-quality behavior.
	model.erase("faceAppearance")
	var equipment := {
		"parts": {"3": {"attachment": "head", "fallback": "head"}},
		"models": {},
		"sockets": {"3": {"bone": "Head", "offset": [0, 0, 0],
			"rotationDegrees": [0, 0, 0]}},
	}
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({
		"actor_id": 901,
		"x": 0,
		"y": 0,
		"rotation": 0,
		"kind": 1,
		"name": "quality",
		"appearance": {"hair": AppearanceVariants.pack_hair(1, 0)},
		"equipment_visuals": {},
	}, CoordinateAdapter.new({"walkingHeight": 0.0}), model, {
		"fallbackAction": "idle",
		"actions": {"idle": "Idle_A"},
		"loopingClips": ["Idle_A"],
	}, equipment)
	_expect(errors.is_empty(),
		"a real actor configures for quality integration: " + ",".join(errors))
	var body := actor.find_child("body", true, false) as MeshInstance3D
	var selection := actor.get("_selection_ring") as MeshInstance3D
	_expect(body != null, "the quality fixture has a body mesh")
	if body == null:
		actor.free()
		NativeAnimationImporter.clear()
		return
	var body_bias := body.lod_bias
	var selection_bias := selection.lod_bias
	var selection_shadow := selection.cast_shadow
	actor.apply_render_quality(Policy.Quality.LOW)
	_expect(is_equal_approx(body.lod_bias,
		body_bias * Policy.lod_bias_scale(Policy.Quality.LOW))
		and body.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"the actor applies LOW to its loaded body")
	_expect(is_equal_approx(selection.lod_bias, selection_bias)
		and selection.cast_shadow == selection_shadow,
		"actor quality leaves its selection UI outside the mesh walk")

	# Appearance replaces the old hair holder after LOW is already active. A
	# Human's hairstyle is drawn by the RL hair-only rig (RLHeadRig.HAIR_NODE_NAME)
	# where its style has RL hair, otherwise by an AppearanceHair_<style>
	# holder; either way the meshes are new nodes and must take LOW.
	var hair_before := {}
	for mesh: MeshInstance3D in _hair_meshes(actor):
		hair_before[mesh.get_instance_id()] = true
	actor.apply_appearance_variants({
		"hair": AppearanceVariants.pack_hair(2, 0),
	})
	var hair_meshes := _hair_meshes(actor)
	var hair_new := not hair_meshes.is_empty()
	for mesh: MeshInstance3D in hair_meshes:
		hair_new = hair_new and not hair_before.has(mesh.get_instance_id())
	_expect(hair_new and _all_low(hair_meshes),
		"hair created after the quality change inherits LOW (%d new meshes)" % hair_meshes.size())

	# A missing registry model exercises the actor's normal fallback-equipment
	# path without adding a test asset.
	actor.apply_equipment_visuals({3: 999}, [3])
	var fallback := actor.find_child(
		"MissingNativeEquipmentFallback", true, false) as MeshInstance3D
	_expect(fallback != null and is_equal_approx(fallback.lod_bias,
		Policy.lod_bias_scale(Policy.Quality.LOW))
		and fallback.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"equipment created after the quality change inherits LOW")

	# The real cape modifier proves quality is combined with worn and animation
	# state, rather than being overwritten by either path later.
	var cloth := actor.get("_cape_cloth") as SkeletonModifier3D
	_expect(cloth != null, "the quality fixture carries the cape modifier")
	if cloth != null:
		actor.call("_set_cape_cloth_active", true)
		_expect(not cloth.active,
			"LOW keeps a worn non-local cape solver asleep")
		actor.apply_render_quality(Policy.Quality.HIGH)
		_expect(cloth.active,
			"HIGH wakes a worn non-local cape solver")
		actor.apply_render_quality(Policy.Quality.LOW, true)
		_expect(cloth.active,
			"the local actor keeps its worn cape solver at LOW")
		actor.set("_animation_tier", AnimationGate.Tier.PAUSED)
		actor.apply_render_quality(Policy.Quality.HIGH, true)
		_expect(not cloth.active,
			"a paused animation tier still sleeps a local HIGH cape")

	actor.free()
	NativeAnimationImporter.clear()


## The meshes of the hairstyle the actor draws now: its legacy
## AppearanceHair_<style> holder and the RL hair-only rig alike.
func _hair_meshes(actor: Node) -> Array[MeshInstance3D]:
	var meshes: Array[MeshInstance3D] = []
	for holder: Node in actor.find_children("AppearanceHair_*", "", true, false):
		meshes.append_array(_meshes_below(holder))
	return meshes


func _meshes_below(parent: Node) -> Array[MeshInstance3D]:
	var meshes: Array[MeshInstance3D] = []
	if parent == null:
		return meshes
	if parent is MeshInstance3D:
		meshes.append(parent as MeshInstance3D)
	for node: Node in parent.find_children("*", "MeshInstance3D", true, false):
		meshes.append(node as MeshInstance3D)
	return meshes


func _all_low(meshes: Array[MeshInstance3D]) -> bool:
	for mesh: MeshInstance3D in meshes:
		if not is_equal_approx(mesh.lod_bias,
				Policy.lod_bias_scale(Policy.Quality.LOW)) \
				or mesh.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:
			return false
	return true


## Keep the two creation seams and the live update loop explicit. Runtime actor
## coverage above owns their behavior; these assertions keep a later spawn-path
## refactor from silently omitting the call. The source is compared with LF line
## endings, because a Windows checkout with core.autocrlf writes main.gd as CRLF
## and the multi-line needles below would then never match.
func _check_main_wiring() -> void:
	var source := FileAccess.get_file_as_string("res://src/app/main.gd").replace("\r\n", "\n")
	_expect(source.contains(
		"preview_actor.apply_render_quality(LookProfile.quality(), true)"),
		"new creation previews receive the resolved quality")
	_expect(source.contains(
		"node.apply_render_quality(LookProfile.quality(), int(id) == AppState.local_actor_id)"),
		"new world actors receive quality with local identity")
	var graphics_start := source.find("func _apply_graphics_quality() -> void:")
	var graphics_end := source.find("\nfunc ", graphics_start + 1)
	var graphics_body := source.substr(graphics_start, graphics_end - graphics_start)
	_expect(graphics_start >= 0 and graphics_end > graphics_start
		and source.contains("func _apply_actor_render_quality() -> void:")
		and graphics_body.contains("\t_apply_actor_render_quality()"),
		"a live graphics-quality change updates existing actors")
	_expect(source.contains("&\"local_actor\":")
		and source.contains("&\"local_actor\":\n")
		and source.contains("\t\t\t_apply_actor_render_quality()\n\t\t\t_queue_world_sync()"),
		"late local-player identity refreshes actor quality roles")
	var load_start := source.find("func _load_look_settings(config: ConfigFile) -> void:")
	var load_end := source.find("func _apply_look_switch() -> void:", load_start)
	var load_body := source.substr(load_start, load_end - load_start)
	_expect(load_start >= 0 and load_end > load_start
		and load_body.contains("LookProfile.set_player_quality(")
		and load_body.contains("\t_apply_graphics_quality()")
		and not load_body.contains("if quality_changed:"),
		"settings reload reapplies the resolved actor quality")


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS ", message)
	else:
		_failures += 1
		push_error("actor render quality: " + message)
