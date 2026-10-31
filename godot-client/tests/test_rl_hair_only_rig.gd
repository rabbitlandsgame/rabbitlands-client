extends SceneTree
## Hair keeps its modern contract on a native head without loading RL skin.
const Rig := preload("res://src/actors/rl_head/rl_head_rig.gd")
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
var checks := 0
var failures := 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _initialize() -> void:
	OS.set_environment("RL_HEAD_BAKE", "0")
	OS.set_environment("RL_HEAD_STILL", "0")
	run.call_deferred()

func run() -> void:
	check_native_fit_shape()
	for sex: String in ["female", "male"]:
		for quality: int in [0, 1, 2]:
			Library.clear()
			var skeleton := Skeleton3D.new()
			skeleton.add_bone("Head")
			skeleton.set_bone_rest(0, Transform3D(Basis.IDENTITY, Vector3(0, 1.65, 0)))
			root.add_child(skeleton)
			var face := RLHeadAppearance.new()
			face.sex = sex
			face.hair = "mira_bun" if sex == "female" else "rowan_shag"
			face.beard = "full_beard"
			face.controls = {"ear_size": 0.3}
			var rig := Rig.attach_hair_only(skeleton, face, quality)
			check(rig != null, "%s quality%d attaches modern hair" % [sex, quality])
			if rig == null:
				skeleton.queue_free()
				await process_frame
				continue
			check(Library._heads.is_empty(), "hair-only attachment never loads the head mesh")
			check(rig.head_info().is_empty() and rig._head_lods.is_empty()
				and rig._beard_lods.is_empty() and rig.expression() == null,
				"native head/beard stay independent of the hair rig")
			check(not rig.draws_expressions(), "hair does not consume a live-face budget slot")
			check(rig._hair_lods.size() == quality + 1, "quality keeps only its required hair LODs")
			var nodes := rig.all_meshes()
			check(not nodes.is_empty(), "hair has real render meshes")
			var first := nodes[0]
			var ear_shape := first.find_blend_shape_by_name("id_ear_size_p")
			check(ear_shape >= 0 and is_zero_approx(first.get_blend_shape_value(ear_shape)),
				"native hair does not sculpt the fixed skull with High identity shapes")
			check(is_zero_approx(float(rig._baked_weights(first).get("id_ear_size_p", -1.0))),
				"baked native hair also excludes High identity shapes")
			check(is_equal_approx(face.control("ear_size"), 0.3), "native drawing does not mutate the saved face")
			check(int(first.get_meta(Rig.LOD_LEVEL_META)) == 2 - quality,
				"Low/Medium/High start at authored LOD2/1/0")
			face.hair_length = 0.4
			face.hair_volume = -0.3
			face.hair_detail = 80
			face.hair_grey = 0.5
			check(rig.apply_appearance(face), "live grooming and greying are accepted")
			check(rig.all_meshes()[0] == first, "grooming keeps the active mesh instance")
			for pair: Array in [["hl_length_p", 0.4], ["hl_volume_n", 0.3]]:
				var index := first.find_blend_shape_by_name(pair[0])
				check(index >= 0 and is_equal_approx(first.get_blend_shape_value(index), pair[1]),
					"real grooming shape is driven: " + str(pair[0]))
			check(is_equal_approx(rig.hair_detail_uniform(), 0.8), "messiness reaches the hair shader")
			check(Library._heads.is_empty(), "edits do not load the hidden RL head")
			rig.teardown()
			skeleton.queue_free()
			await process_frame
			await process_frame
	Library.clear()
	GlbSceneCache.clear()
	print("RL hair-only rig: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func check_native_fit_shape() -> void:
	var source := ArrayMesh.new()
	source.blend_shape_mode = Mesh.BLEND_SHAPE_MODE_RELATIVE
	source.add_blend_shape("hl_native_fit")
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK])
	var delta := []
	delta.resize(Mesh.ARRAY_MAX)
	delta[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.RIGHT * .003, Vector3.RIGHT * .003, Vector3.RIGHT * .003])
	delta[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
	source.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [delta])
	var mesh := MeshInstance3D.new()
	mesh.mesh = source
	var rig := Rig.new()
	rig.appearance = RLHeadAppearance.new()
	rig._hair_lods = [[mesh]]
	rig._hair_only = true
	rig._apply_hair_shapes()
	check(is_equal_approx(mesh.get_blend_shape_value(0), 1.0), "native mode activates its optional fitted offset")
	var native_key := RLHeadIdentityBake.key(source, rig._baked_weights(mesh))
	rig._hair_only = false
	rig._apply_hair_shapes()
	check(is_zero_approx(mesh.get_blend_shape_value(0)), "High mode preserves the original fitted baseline")
	check(native_key != RLHeadIdentityBake.key(source, rig._baked_weights(mesh)),
		"native fitted geometry has a separate bake key")
	var plain := ArrayMesh.new()
	plain.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	check(RLHeadIdentityBake.key(plain, {"hl_native_fit": 1}) == RLHeadIdentityBake.key(plain, {}),
		"a source without native fitting keeps its original bake key")
	rig.free()
	mesh.free()
