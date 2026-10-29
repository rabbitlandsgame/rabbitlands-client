extends SceneTree
## Headless checks for RLHeadIdentityBake, the RL head's per-face identity bake:
##   * for every head, beard and hairstyle level and a spread of faces (the
##     Rowan/Mira presets, the all-50 default face, both extremes, Tavi), the
##     baked mesh reproduces the live blend-shape result: every vertex within
##     1e-5 m, with no expression and with blink, smile and jaw weights on the
##     kept shapes; normals within 1e-3 with no expression;
##   * a baked mesh keeps only the `ex_` shapes, the source's surfaces,
##     materials, names, index arrays, generated LODs, UVs and skin;
##   * one mesh per distinct face (shared, counted), idle entries reused and
##     bounded, and a spent budget falls back to the live source mesh;
##   * on the real ReplicatedActor3D at High: the shown levels draw baked meshes
##     shared by actors with the same face, expressions still drive the kept
##     shapes, `set_control` goes live, RL_HEAD_BAKE=0 draws live, the bakes
##     done on the WorkerThreadPool arrive, and the cache empties with the
##     last RL head;
##   * a still bake (RLHeadIdentityBake.still_enabled) keeps no live shapes
##     and leaves the mouth out, with the same identity vertices; on the actor
##     a far level draws it with every surface's material found again by name,
##     and the near level keeps its expressions;
##   * the expressive budget (RLHeadRig.MAX_EXPRESSIVE): with a camera, only
##     the nearest faces within the range draw their expressions; every other
##     face, and every hairstyle, draws still bakes at the first level too and
##     its expression node rests, until the camera comes close;
##   * material values (the Compatibility renderer's per-face materials,
##     forced with RL_HEAD_VALUES=material): each surface draws a copy of its
##     shared material carrying the face's values, compiled with
##     RL_MATERIAL_VALUES, shared by identical faces, and nothing is set as an
##     instance uniform.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head_identity_bake.gd

const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const BAKE := preload("res://src/actors/rl_head/rl_head_identity_bake.gd")
const HIGH := ActorRenderQuality.Quality.HIGH
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const TOLERANCE := 1e-5

var _checks := 0
var _failures := 0
var _models: Dictionary
var _equipment: Dictionary
var _animation: Dictionary
var _next_id := 9800
var _worst := 0.0


func _init() -> void:
	call_deferred("_run")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures += 1
		push_error("rl head identity bake: " + message)


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _run() -> void:
	_models = (_json("res://data/actors/models.json") as Dictionary).models
	_equipment = _json("res://data/actors/equipment.json")
	_animation = _json("res://data/animations/luminous.json")
	OS.set_environment("RL_HEADS", "")
	# The cache checks below expect the caches to go with the last RL head.
	RLHeadLibrary.retain_seconds = 0.0
	# Headless runs report no renderer: switch the bake on explicitly.
	OS.set_environment("RL_HEAD_BAKE", "1")
	ReplicatedActor3D.reload_rl_heads_switch()
	BAKE.reload_switch()
	RLHeadLibrary.acquire()
	BAKE.synchronous = true
	_check_math()
	_check_cache()
	RLHeadLibrary.release()
	await _check_actors()
	await _check_still()
	await _check_expressive()
	await _check_material_values()
	await _check_async_and_switch()
	print("rl head identity bake: worst vertex difference %s m" % String.num_scientific(_worst))
	print("rl head identity bake: %d checks, %d failures" % [_checks, _failures])
	print("rl head identity bake: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


static func _all(value: int) -> Dictionary:
	var result := {}
	for field: String in PortraitCustomization.FIELDS:
		result[field] = mini(value, PortraitCustomization.maximum(field))
	return result


## Faces by name for one sex, as RLHeadAppearance.
func _faces(sex: String) -> Dictionary:
	var preset := "Rowan" if sex == "male" else "Mira"
	var faces := {}
	for entry: Array in [[preset, PRESETS.appearance(preset)], ["all-50", {}], ["all-0", _all(0)],
			["all-100", _all(100)], ["Tavi", PRESETS.appearance("Tavi")]]:
		faces[entry[0]] = RLHeadPortraitMap.face(entry[1] as Dictionary, sex)
	return faces


## Identity weights of a face for a source mesh, plus synthetic hair-shape
## weights (the hairstyles carry no hl_ shapes yet; any they gain are baked).
static func _weights(face: RLHeadAppearance, names: PackedStringArray) -> Dictionary:
	var weights := {}
	for control: String in names:
		var amount := face.control(control)
		weights["id_%s_p" % control] = maxf(amount, 0.0)
		weights["id_%s_n" % control] = maxf(-amount, 0.0)
	weights["hl_length_p"] = 0.3
	weights["hl_volume_n"] = 0.45
	return weights


## Every source mesh: head levels by sex, beard and hairstyle levels.
func _sources() -> Array:
	var sources: Array = []
	for sex: String in ["male", "female"]:
		var info := RLHeadLibrary.head(sex)
		for level: int in (info["lods"] as Array).size():
			for piece: Dictionary in (info["lods"] as Array)[level]:
				sources.append({"name": "head %s lod%d" % [sex, level], "sex": sex, "mesh": piece["mesh"],
					"names": info["control_names"]})
	var male_names: PackedStringArray = RLHeadLibrary.head("male")["control_names"]
	for style: String in RLHeadLibrary.beard_styles():
		var lods := RLHeadLibrary.beard(style)
		for level: int in lods.size():
			for piece: Dictionary in lods[level]:
				sources.append({"name": "beard %s lod%d" % [style, level], "sex": "male", "mesh": piece["mesh"],
					"names": male_names})
	for style: String in RLHeadLibrary.hair_styles():
		var instance := RLHeadLibrary.instantiate_hair(style)
		if instance == null:
			continue
		var sex := "female" if style.begins_with("mira") else "male"
		for node: Node in instance.find_children("*", "MeshInstance3D", true, false):
			sources.append({"name": "hair %s %s" % [style, node.name], "sex": sex,
				"mesh": (node as MeshInstance3D).mesh, "names": RLHeadLibrary.head(sex)["control_names"]})
		instance.free()
	return sources


## The live result: base + sum of weight * (shape - base) over every shape.
static func _live(mesh: Mesh, surface: int, weights: Dictionary) -> Array:
	var arrays := mesh.surface_get_arrays(surface)
	var shapes := mesh.surface_get_blend_shape_arrays(surface)
	var v: PackedVector3Array = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).duplicate()
	var base_v: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var has_n := arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array
	var n: PackedVector3Array = (arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array).duplicate() if has_n \
		else PackedVector3Array()
	for index: int in mesh.get_blend_shape_count():
		var w := float(weights.get(str(mesh.get_blend_shape_name(index)), 0.0))
		if w == 0.0:
			continue
		var sv: PackedVector3Array = (shapes[index] as Array)[Mesh.ARRAY_VERTEX]
		for i: int in v.size():
			v[i] += (sv[i] - base_v[i]) * w
		if has_n:
			var sn: PackedVector3Array = (shapes[index] as Array)[Mesh.ARRAY_NORMAL]
			var base_n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			for i: int in n.size():
				n[i] += (sn[i] - base_n[i]) * w
	return [v, n]


func _check_math() -> void:
	var expression := {"ex_blink_l": 0.7, "ex_blink_r": 0.7, "ex_smile": 0.4, "ex_jaw_open": 0.25}
	var faces_by_sex := {"male": _faces("male"), "female": _faces("female")}
	for source: Dictionary in _sources():
		var mesh := source["mesh"] as ArrayMesh
		var label := str(source["name"])
		var faces: Dictionary = faces_by_sex[source["sex"]]
		var first := true
		for face_name: String in faces:
			var face: RLHeadAppearance = faces[face_name]
			var weights := _weights(face, source["names"] as PackedStringArray)
			var baked := BAKE.acquire(mesh, weights)
			_expect(baked != null, "%s %s baked synchronously" % [label, face_name])
			if baked == null:
				continue
			if first:
				first = false
				_check_structure(label, mesh, baked)
			var worst := 0.0
			var worst_expr := 0.0
			var worst_normal := 0.0
			for surface: int in mesh.get_surface_count():
				var live := _live(mesh, surface, weights)
				var live_expr := _live(mesh, surface, weights.merged(expression))
				var mine := _live(baked, surface, {})
				var mine_expr := _live(baked, surface, expression)
				for i: int in (live[0] as PackedVector3Array).size():
					worst = maxf(worst, ((live[0] as PackedVector3Array)[i] - (mine[0] as PackedVector3Array)[i]).length())
					worst_expr = maxf(worst_expr, ((live_expr[0] as PackedVector3Array)[i]
						- (mine_expr[0] as PackedVector3Array)[i]).length())
				for i: int in (live[1] as PackedVector3Array).size():
					var a := (live[1] as PackedVector3Array)[i]
					var b := (mine[1] as PackedVector3Array)[i]
					if a.length() > 1e-6 and b.length() > 1e-6:
						worst_normal = maxf(worst_normal, (a.normalized() - b.normalized()).length())
			_worst = maxf(_worst, maxf(worst, worst_expr))
			_expect(worst <= TOLERANCE, "%s %s: baked vertices match the live identity (%s m)" % [label, face_name, String.num_scientific(worst)])
			_expect(worst_expr <= TOLERANCE, "%s %s: kept shapes on the baked face match live (%s m)"
				% [label, face_name, String.num_scientific(worst_expr)])
			_expect(worst_normal <= 1e-3, "%s %s: baked normals match (%s)" % [label, face_name, String.num_scientific(worst_normal)])
			BAKE.release(BAKE.key(mesh, weights))


func _check_structure(label: String, source: ArrayMesh, baked: ArrayMesh) -> void:
	var kept := PackedStringArray()
	for index: int in source.get_blend_shape_count():
		var shape := str(source.get_blend_shape_name(index))
		if not BAKE.is_baked_shape(shape):
			kept.append(shape)
	var names := PackedStringArray()
	for index: int in baked.get_blend_shape_count():
		names.append(str(baked.get_blend_shape_name(index)))
	_expect(names == kept, "%s keeps exactly the live shapes %s" % [label, names])
	_expect(baked.get_surface_count() == source.get_surface_count() and baked.blend_shape_mode == source.blend_shape_mode,
		"%s keeps its surfaces and blend mode" % label)
	for surface: int in mini(baked.get_surface_count(), source.get_surface_count()):
		var a := source.surface_get_arrays(surface)
		var b := baked.surface_get_arrays(surface)
		var same := baked.surface_get_material(surface) == source.surface_get_material(surface) \
			and baked.surface_get_name(surface) == source.surface_get_name(surface) \
			and baked.surface_get_primitive_type(surface) == source.surface_get_primitive_type(surface)
		for slot: int in [Mesh.ARRAY_INDEX, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2, Mesh.ARRAY_COLOR,
				Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS]:
			same = same and a[slot] == b[slot]
		var lods_a: Array = RenderingServer.mesh_get_surface(source.get_rid(), surface).get("lods", [])
		var lods_b: Array = RenderingServer.mesh_get_surface(baked.get_rid(), surface).get("lods", [])
		_expect(same and lods_a.size() == lods_b.size(),
			"%s surface %d keeps material, name, indices, UVs, colours, skin and %d LODs (%d)"
			% [label, surface, lods_a.size(), lods_b.size()])


func _check_cache() -> void:
	var info := RLHeadLibrary.head("male")
	var mesh: ArrayMesh = ((info["lods"] as Array)[1] as Array)[0]["mesh"]
	var names: PackedStringArray = info["control_names"]
	var faces := _faces("male")
	var a := _weights(faces["all-50"], names)
	var b := _weights(faces["all-100"], names)
	var first := BAKE.acquire(mesh, a)
	var again := BAKE.acquire(mesh, a)
	var other := BAKE.acquire(mesh, b)
	_expect(first != null and first == again and other != null and other != first,
		"one shared mesh per distinct face")
	var near := a.duplicate()
	near["id_%s_p" % names[0]] = float(near["id_%s_p" % names[0]]) + BAKE.QUANTUM * 0.2
	_expect(BAKE.key(mesh, near) == BAKE.key(mesh, a), "faces within the quantum share a key")
	_expect(BAKE.key(mesh, b) != BAKE.key(mesh, a), "different faces differ in key")
	for key: String in [BAKE.key(mesh, a), BAKE.key(mesh, a), BAKE.key(mesh, b)]:
		BAKE.release(key)
	var state := BAKE.describe()
	_expect(int(state["users"]) == 0 and int(state["idle"]) >= 2, "released entries stay idle for reuse %s" % state)
	_expect(BAKE.acquire(mesh, a) == first, "an idle entry is reused")
	BAKE.release(BAKE.key(mesh, a))
	# Idle entries are bounded.
	for index: int in BAKE.IDLE_KEEP + 6:
		var w := a.duplicate()
		w["id_%s_p" % names[1]] = 0.01 * (index + 1)
		w["id_%s_n" % names[1]] = 0.0
		BAKE.acquire(mesh, w)
		BAKE.release(BAKE.key(mesh, w))
	_expect(int(BAKE.describe()["idle"]) <= BAKE.IDLE_KEEP, "idle entries kept within IDLE_KEEP %s" % BAKE.describe())
	# A spent budget falls back to live, without an entry.
	var held := BAKE.acquire(mesh, b)
	BAKE.budget_bytes = 1
	var w2 := a.duplicate()
	w2["id_%s_p" % names[2]] = 0.77
	_expect(BAKE.acquire(mesh, w2) == null and not BAKE.holds(BAKE.key(mesh, w2)),
		"no new bake once the budget is spent by meshes in use")
	BAKE.budget_bytes = BAKE.BUDGET_BYTES
	_expect(held != null, "meshes in use survive the budget")
	BAKE.release(BAKE.key(mesh, b))


func _spawn(sex: String, appearance: Dictionary, quality: int = HIGH) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_next_id += 1
	actor.apply_render_quality(quality, false)
	root.add_child(actor)
	var errors := actor.configure({"actor_id": _next_id, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": appearance, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
		_models["luminous_" + sex], _animation, _equipment)
	_expect(errors.is_empty(), "%s configures: %s" % [sex, errors])
	actor.set_process(false)
	return actor


## The shown nodes of a rig and whether each draws a baked mesh.
static func _shown(rig: RLHeadRig) -> Array[MeshInstance3D]:
	var shown: Array[MeshInstance3D] = []
	for node: MeshInstance3D in rig.all_meshes():
		if node.visible:
			shown.append(node)
	return shown


func _check_actors() -> void:
	BAKE.synchronous = true
	var tavi := PRESETS.appearance("Tavi")
	var one := _spawn("male", tavi)
	var two := _spawn("male", tavi)
	var other := _spawn("male", _all(100).merged({"facial_hair": 5, "hair": AppearanceVariants.pack_hair(1, 2)}, true))
	await process_frame
	var rig := one.rl_head()
	_expect(rig != null and two.rl_head() != null and other.rl_head() != null, "RL heads built at High")
	if rig == null:
		return
	var shown := _shown(rig)
	var parts := {}
	for node: MeshInstance3D in shown:
		parts[str(node.name).get_slice("_", 0)] = true
		_expect(rig.is_baked(node), "%s draws its baked mesh" % node.name)
		var identity := 0
		for index: int in node.mesh.get_blend_shape_count():
			identity += 1 if BAKE.is_baked_shape(str(node.mesh.get_blend_shape_name(index))) else 0
		_expect(identity == 0, "%s carries no identity shapes once baked" % node.name)
	_expect(parts.has("RLHead") and parts.has("RLBeard") and parts.has("RLHair"),
		"head, beard and hair are all baked %s" % [parts.keys()])
	for node: MeshInstance3D in rig.all_meshes():
		if not node.visible:
			_expect(not rig.is_baked(node), "hidden level %s keeps its live source" % node.name)
	var shown_two := _shown(two.rl_head())
	var shared := shown.size() == shown_two.size()
	for index: int in mini(shown.size(), shown_two.size()):
		shared = shared and shown[index].mesh == shown_two[index].mesh
	_expect(shared, "actors with the same face share the baked meshes")
	var shown_other := _shown(other.rl_head())
	_expect(not shown_other.is_empty() and shown_other[0].mesh != shown[0].mesh,
		"a different face has its own baked meshes")
	# Expressions still drive the kept shapes on the baked head.
	var expression := rig.expression()
	expression.always_update = true
	expression.blink()
	expression.advance(0.1)
	var head := shown[0]
	var blink := RLHeadRig.shape_index(head, "ex_blink_l")
	_expect(blink >= 0 and head.get_blend_shape_value(blink) > 0.3, "a blink drives the baked head's kept shape")
	# The portrait pose shows (and bakes) the first level.
	one.hold_portrait_pose(self)
	var first_level: Array = rig.mesh_nodes()["head"][0]
	_expect(rig.is_baked(first_level[0] as MeshInstance3D), "the portrait pose's first level is baked")
	one.release_portrait_pose(self)
	# set_control goes live for good.
	var names: PackedStringArray = rig.head_info()["control_names"]
	rig.set_control(names[0], 0.5)
	var live := true
	for node: MeshInstance3D in rig.all_meshes():
		live = live and not rig.is_baked(node)
	var index := RLHeadRig.shape_index(head, "id_%s_p" % names[0])
	_expect(live and index >= 0 and is_equal_approx(head.get_blend_shape_value(index), 0.5),
		"set_control draws every level live with its weight")
	one.apply_appearance_variants(tavi)
	await process_frame
	live = true
	for node: MeshInstance3D in one.rl_head().all_meshes():
		live = live and not one.rl_head().is_baked(node)
	_expect(live, "a face edited control by control stays live")
	# Down to Medium and the actors gone: the cache empties.
	for actor: ReplicatedActor3D in [one, two, other]:
		actor.apply_render_quality(MEDIUM, false)
	await process_frame
	_expect(int(BAKE.describe()["users"]) == 0, "switching down releases every bake %s" % BAKE.describe())
	for actor: ReplicatedActor3D in [one, two, other]:
		actor.free()
	await process_frame
	await process_frame
	_expect(RLHeadLibrary.users() == 0 and int(BAKE.describe()["entries"]) == 0,
		"the cache empties with the last RL head %s" % BAKE.describe())


## Still bakes: the far levels of a head, beard and hair, directly and on an actor.
func _check_still() -> void:
	BAKE.synchronous = true
	RLHeadLibrary.acquire()
	var face: RLHeadAppearance = _faces("male")["Tavi"]
	var info := RLHeadLibrary.head("male")
	for level: int in range(1, (info["lods"] as Array).size()):
		var source: ArrayMesh = ((info["lods"] as Array)[level] as Array)[0]["mesh"]
		var weights := _weights(face, info["control_names"])
		var full := BAKE.acquire(source, weights)
		var still := BAKE.acquire(source, weights, Callable(), true)
		_expect(still != null and full != null and still != full and BAKE.key(source, weights, true) != BAKE.key(source, weights),
			"lod%d: a still bake is its own entry" % level)
		if still == null or full == null:
			continue
		_expect(still.get_blend_shape_count() == 0, "lod%d: a still bake keeps no live shapes" % level)
		var kept := PackedStringArray()
		for surface: int in source.get_surface_count():
			var material := source.surface_get_material(surface)
			if material == null or not BAKE.STILL_DROPPED_MATERIALS.has(material.resource_name):
				kept.append(source.surface_get_name(surface))
		var names := PackedStringArray()
		for surface: int in still.get_surface_count():
			names.append(still.surface_get_name(surface))
		_expect(names == kept, "lod%d: a still bake draws every surface but the mouth %s" % [level, names])
		var worst := 0.0
		for surface: int in still.get_surface_count():
			var at := -1
			for index: int in full.get_surface_count():
				if full.surface_get_name(index) == still.surface_get_name(surface):
					at = index
			var a: PackedVector3Array = still.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			var b: PackedVector3Array = full.surface_get_arrays(at)[Mesh.ARRAY_VERTEX]
			for i: int in mini(a.size(), b.size()):
				worst = maxf(worst, a[i].distance_to(b[i]))
			_expect(a.size() == b.size() and still.surface_get_material(surface) == full.surface_get_material(at),
				"lod%d %s: same vertices and material as the full bake" % [level, still.surface_get_name(surface)])
		_expect(worst <= 1e-6, "lod%d: the still bake carries the same identity (%s m)" % [level, String.num_scientific(worst)])
		BAKE.release(BAKE.key(source, weights))
		BAKE.release(BAKE.key(source, weights, true))
	RLHeadLibrary.release()
	# On the actor: a far band draws still meshes, the near band its expressions.
	var actor := _spawn("male", PRESETS.appearance("Tavi"))
	await process_frame
	var rig := actor.rl_head()
	_expect(rig != null and BAKE.still_enabled(), "Tavi's RL head built, far levels still")
	if rig == null:
		actor.free()
		return
	rig.update_lod(18.0)
	_expect(rig.lod_band() == 1, "18 m shows the second level")
	for node: MeshInstance3D in _shown(rig):
		_expect(rig.is_baked(node) and node.mesh.get_blend_shape_count() == 0,
			"%s draws a still bake at 18 m" % node.name)
		for surface: int in node.mesh.get_surface_count():
			var imported := node.mesh.surface_get_material(surface)
			var drawn := node.get_active_material(surface)
			_expect(imported != null and drawn != null and (drawn.resource_name == imported.resource_name
				or imported.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL),
				"%s surface %d draws its own material (%s)" % [node.name, surface,
					drawn.resource_name if drawn != null else "none"])
	rig.update_lod(2.0)
	_expect(rig.lod_band() == 0, "2 m shows the first level")
	var head := _shown(rig)[0]
	_expect(rig.is_baked(head) and RLHeadRig.shape_index(head, "ex_blink_l") >= 0,
		"the near level keeps its expression shapes")
	_expect(head.mesh.get_surface_count() == RLHeadRig.source_mesh(head).get_surface_count(),
		"the near level draws every surface")
	actor.free()
	await process_frame
	await process_frame


## The expressive budget: one camera, max_expressive lowered to 1.
func _check_expressive() -> void:
	BAKE.synchronous = true
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.position = Vector3(0.0, 1.6, 6.0)
	camera.current = true
	RLHeadRig.max_expressive = 1
	var tavi := PRESETS.appearance("Tavi")
	var nearest := _spawn("male", tavi)
	var second := _spawn("male", tavi)
	var beyond := _spawn("male", tavi)
	# Placed by hand: their movement (physics) would walk them back to their tile.
	for placed: Array in [[nearest, Vector3.ZERO], [second, Vector3(1.2, 0.0, 0.0)], [beyond, Vector3(0.0, 0.0, -3.0)]]:
		(placed[0] as ReplicatedActor3D).set_physics_process(false)
		(placed[0] as ReplicatedActor3D).position = placed[1]
	for _i: int in RLHeadRig.LOD_CHECK_FRAMES * 3:
		await process_frame
	var rigs: Array[RLHeadRig] = [nearest.rl_head(), second.rl_head(), beyond.rl_head()]
	_expect(rigs.all(func(rig: RLHeadRig) -> bool: return rig != null and rig.lod_band() == 0),
		"three faces within 10 m show their first level")
	if not rigs.all(func(rig: RLHeadRig) -> bool: return rig != null):
		for actor: ReplicatedActor3D in [nearest, second, beyond]:
			actor.free()
		camera.free()
		RLHeadRig.max_expressive = RLHeadRig.MAX_EXPRESSIVE
		return
	_expect(rigs[0].draws_expressions() and not rigs[1].draws_expressions() and not rigs[2].draws_expressions(),
		"only the nearest face within %.0f m draws its expressions" % RLHeadRig.expressive_range)
	_expect(RLHeadRig.shape_index(_shown(rigs[0])[0], "ex_blink_l") >= 0 and rigs[0].expression().is_processing(),
		"the expressive face keeps its expression shapes and runs its expression")
	for index: int in [1, 2]:
		var head := _shown(rigs[index])[0]
		var mouth := false
		for surface: int in head.mesh.get_surface_count():
			var material := head.mesh.surface_get_material(surface)
			mouth = mouth or (material != null and material.resource_name == "rl_mouth")
		_expect(rigs[index].is_baked(head) and head.mesh.get_blend_shape_count() == 0 and not mouth
			and not rigs[index].expression().is_processing(),
			"face %d draws a still first level without its mouth, its expression resting" % index)
	for rig: RLHeadRig in rigs:
		for node: MeshInstance3D in _shown(rig):
			if str(node.name).begins_with("RLHair"):
				_expect(rig.is_baked(node) and node.mesh.get_blend_shape_count() == 0,
					"%s: the hair is drawn still" % node.name)
	# The camera beside the second face: it takes the expressive place.
	camera.position = Vector3(1.2, 1.6, 1.5)
	for _i: int in RLHeadRig.LOD_CHECK_FRAMES * 3:
		await process_frame
	var head_two := _shown(rigs[1])[0]
	_expect(rigs[1].draws_expressions() and not rigs[0].draws_expressions()
		and RLHeadRig.shape_index(head_two, "ex_blink_l") >= 0 and rigs[1].expression().is_processing(),
		"coming close, the second face draws its expressions and the first goes still")
	_expect(_shown(rigs[0])[0].mesh.get_blend_shape_count() == 0 and not rigs[0].expression().is_processing(),
		"the face left behind draws still")
	# A held portrait pose keeps its expressions whatever the ranking.
	beyond.hold_portrait_pose(self)
	_expect(rigs[2].draws_expressions() and RLHeadRig.shape_index(_shown(rigs[2])[0], "ex_blink_l") >= 0,
		"a held portrait pose draws its expression shapes")
	beyond.release_portrait_pose(self)
	for _i: int in RLHeadRig.LOD_CHECK_FRAMES * 2:
		await process_frame
	_expect(not rigs[2].draws_expressions() and _shown(rigs[2])[0].mesh.get_blend_shape_count() == 0,
		"released, it is ranked still again")
	RLHeadRig.max_expressive = RLHeadRig.MAX_EXPRESSIVE
	camera.free()
	for _i: int in RLHeadRig.LOD_CHECK_FRAMES * 2:
		await process_frame
	_expect(rigs.all(func(rig: RLHeadRig) -> bool: return rig.draws_expressions()),
		"without a camera every face keeps its expressions")
	for actor: ReplicatedActor3D in [nearest, second, beyond]:
		actor.free()
	await process_frame
	await process_frame


## Material values: per-face material copies instead of instance uniforms.
func _check_material_values() -> void:
	BAKE.synchronous = true
	OS.set_environment("RL_HEAD_VALUES", "material")
	RLHeadLibrary.reload_values_switch()
	_expect(RLHeadLibrary.material_values(), "RL_HEAD_VALUES=material switches material values on")
	var mira := PRESETS.appearance("Mira")
	var one := _spawn("female", mira)
	var two := _spawn("female", mira)
	var other := _spawn("female", mira.merged({"skin": (int(mira.get("skin", 0)) + 3) % 10}, true))
	await process_frame
	var rig := one.rl_head()
	_expect(rig != null and two.rl_head() != null and other.rl_head() != null, "three female RL heads")
	if rig != null:
		var skin_seen := false
		for node: MeshInstance3D in rig.all_meshes():
			for surface: int in node.mesh.get_surface_count():
				var imported := node.mesh.surface_get_material(surface)
				var drawn := node.get_surface_override_material(surface) as ShaderMaterial
				if imported == null or imported.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL or drawn == null:
					continue
				var shared := RLHeadLibrary.material(imported.resource_name, "female", rig.appearance.hair
					if RLHeadRig.HAIR_NODE_NAME in str(node.get_path()) else "", rig.quality)
				if not shared.shader.code.contains(RLHeadLibrary.INSTANCE_INCLUDE):
					_expect(drawn == shared, "%s keeps its shared material (no values included)" % imported.resource_name)
					continue
				# Every surface whose shader includes the values, read or not,
				# draws an RL_MATERIAL_VALUES compile: no instance uniform is
				# declared on any RL mesh instance.
				_expect(drawn != shared and drawn.shader != shared.shader
					and drawn.shader.code.contains("#define RL_MATERIAL_VALUES"),
					"%s draws a copy compiled with RL_MATERIAL_VALUES" % imported.resource_name)
				if RLHeadLibrary.shader_values(shared).is_empty():
					_expect(RLHeadLibrary.face_material(shared, {}) == drawn,
						"%s reads no values: one copy for every face" % imported.resource_name)
					continue
				if imported.resource_name == "rl_skin":
					skin_seen = true
					_expect(drawn.get_shader_parameter("skin_color") == rig.appearance.skin,
						"the skin copy carries the face's skin colour")
					_expect(drawn.get_shader_parameter("albedo_texture") == shared.get_shader_parameter("albedo_texture"),
						"the skin copy keeps the shared maps")
		_expect(skin_seen, "the head's skin draws a per-face copy")
		var shown_one := _shown(rig)
		var shown_two := _shown(two.rl_head())
		_expect(not shown_one.is_empty() and shown_one[0].get_surface_override_material(0) == shown_two[0].get_surface_override_material(0),
			"identical faces share their material copies")
		_expect(_shown(other.rl_head())[0].get_surface_override_material(0) != shown_one[0].get_surface_override_material(0),
			"another skin colour draws another copy")
	for actor: ReplicatedActor3D in [one, two, other]:
		actor.free()
	OS.set_environment("RL_HEAD_VALUES", "")
	RLHeadLibrary.reload_values_switch()
	await process_frame
	await process_frame


func _check_async_and_switch() -> void:
	BAKE.synchronous = false
	var actor := _spawn("female", PRESETS.appearance("Mira").merged({"jaw": 80}, true))
	var rig := actor.rl_head()
	_expect(rig != null, "female RL head built")
	if rig == null:
		return
	var head := _shown(rig)[0]
	_expect(not rig.is_baked(head), "a fresh face draws live while its bake waits")
	var began := Time.get_ticks_msec()
	while not rig.is_baked(head) and Time.get_ticks_msec() - began < 10000:
		await process_frame
	_expect(rig.is_baked(head), "the WorkerThreadPool bake arrives (%d ms)" % (Time.get_ticks_msec() - began))
	# A face replaced before its bake starts never bakes.
	var before := int(BAKE.describe()["baked_total"])
	var transient := PRESETS.appearance("Mira").merged({"jaw": 10}, true)
	var transient_key := BAKE.key(RLHeadRig.source_mesh(head),
		_weights(RLHeadPortraitMap.face(transient, "female"), rig.head_info()["control_names"]))
	actor.apply_appearance_variants(transient)
	_expect(BAKE.holds(transient_key), "the first edit asks for its bake")
	actor.apply_appearance_variants(PRESETS.appearance("Mira").merged({"jaw": 90}, true))
	began = Time.get_ticks_msec()
	while not rig.is_baked(_shown(rig)[0]) and Time.get_ticks_msec() - began < 10000:
		await process_frame
	var parts := _shown(rig).size()
	var made := int(BAKE.describe()["baked_total"]) - before
	_expect(rig.is_baked(_shown(rig)[0]) and not BAKE.holds(transient_key) and made >= 1 and made <= parts,
		"only the last of two quick edits bakes (%d new meshes, %d parts shown)" % [made, parts])
	actor.free()
	await process_frame
	await process_frame
	OS.set_environment("RL_HEAD_BAKE", "0")
	BAKE.reload_switch()
	var plain := _spawn("female", PRESETS.appearance("Mira"))
	await process_frame
	var any_baked := false
	for node: MeshInstance3D in plain.rl_head().all_meshes():
		any_baked = any_baked or plain.rl_head().is_baked(node)
	_expect(not any_baked, "RL_HEAD_BAKE=0 draws every level live")
	plain.free()
	OS.set_environment("RL_HEAD_BAKE", "")
	BAKE.reload_switch()
	_expect(not BAKE.enabled() or RenderingServer.get_current_rendering_method() == "gl_compatibility",
		"unset, RL_HEAD_BAKE bakes only in the Compatibility renderer")
	await process_frame
