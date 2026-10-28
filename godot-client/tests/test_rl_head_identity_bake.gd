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
##     last RL head.
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
