extends SceneTree
const REST = preload("res://src/actors/mesh_rest_coordinates.gd")
const HIGH = preload("res://src/actors/high_portrait_appearance.gd")
const Stage = preload("res://prototypes/rl_heads/rl_head_stage.gd")
var checks := 0
var failures := 0
func _initialize() -> void:
	call_deferred("run")
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
func synthetic() -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, 1.4, 0), Vector3(.1, 1.5, 0), Vector3(0, 1.5, .1), Vector3(.1, 1.6, .1)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2.RIGHT, Vector2.DOWN, Vector2.ONE])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color.RED, Color.BLUE, Color.GREEN, Color.WHITE])
	arrays[Mesh.ARRAY_CUSTOM1] = PackedFloat32Array([1,2,3,4, 5,6,7,8, 9,10,11,12, 13,14,15,16])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([0,1,2,3, 0,1,2,3, 0,1,2,3, 0,1,2,3])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([.1,.2,.3,.4, .2,.3,.4,.1, .3,.4,.1,.2, .4,.1,.2,.3])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2, 2,1,3])
	var shape := []
	shape.resize(Mesh.ARRAY_MAX)
	shape[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3(.001,0,0), Vector3.ZERO, Vector3.ZERO])
	shape[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
	var source := ArrayMesh.new()
	source.custom_aabb = AABB(Vector3(-1, -1, -1), Vector3(2, 3, 4))
	source.add_blend_shape("identity")
	source.blend_shape_mode = Mesh.BLEND_SHAPE_MODE_RELATIVE
	var material := StandardMaterial3D.new()
	material.resource_name = "rl_bodypatch"
	var format := Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT
	source.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [shape], {.1: PackedInt32Array([0,1,3])}, format)
	source.surface_set_material(0, material)
	source.surface_set_name(0, "Body patch")
	var other := StandardMaterial3D.new()
	other.resource_name = "untouched_face"
	source.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [shape], {}, format)
	source.surface_set_material(1, other)
	source.surface_set_name(1, "Untouched face")
	var before := source.surface_get_arrays(0)
	var before_bytes := var_to_bytes(before)
	var target := REST.for_material(source, "rl_bodypatch")
	var after := target.surface_get_arrays(0)
	expect(var_to_bytes(source.surface_get_arrays(0)) == before_bytes, "source arrays remain immutable")
	for slot: int in Mesh.ARRAY_MAX:
		if slot != Mesh.ARRAY_CUSTOM0:
			expect(var_to_bytes(before[slot]) == var_to_bytes(after[slot]), "existing channel remains exact: " + str(slot))
	expect(target.surface_get_material(0) == material, "material reference retained")
	expect((target as ArrayMesh).custom_aabb == source.custom_aabb and (target as ArrayMesh).shadow_mesh == source.shadow_mesh, "mesh culling and shadow references retained")
	expect(target.surface_get_name(0) == "Body patch", "surface name retained")
	expect(target.get_blend_shape_name(0) == "identity", "morph name retained")
	expect(var_to_bytes(target.surface_get_blend_shape_arrays(0)) == var_to_bytes(source.surface_get_blend_shape_arrays(0)), "all morph arrays, including generated tangents, remain byte exact")
	check_packed(source, target, "synthetic")
	expect(WardrobeShirtFit._surface_lods(target, 0) == WardrobeShirtFit._surface_lods(source, 0), "LOD indices retained")
	var coordinates: PackedFloat32Array = after[Mesh.ARRAY_CUSTOM0]
	for vertex: int in 4:
		for axis: int in 3:
			expect(coordinates[vertex * 3 + axis] == before[Mesh.ARRAY_VERTEX][vertex][axis], "carrier stores exact source position")
	expect(((target.surface_get_format(0) >> Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT) & 7) == Mesh.ARRAY_CUSTOM_RGB_FLOAT, "CUSTOM0 format is full precision XYZ")
	expect(((target.surface_get_format(0) >> Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT) & 7) == Mesh.ARRAY_CUSTOM_RGBA_FLOAT, "existing CUSTOM1 format retained")
	expect(RLHeadIdentityBake._surface_bytes(after, 1, {}) - RLHeadIdentityBake._surface_bytes(before, 1, {}) == 4 * 12, "identity bake budget includes the added carrier bytes")
	var midpoint := after.duplicate(true)
	HIGH._append_midpoint(midpoint, 0, 1)
	expect(midpoint[Mesh.ARRAY_CUSTOM0].size() == 15, "classic High adds all three carrier components")
	expect(midpoint[Mesh.ARRAY_CUSTOM1].size() == 20, "classic High preserves all four existing custom components")
	for axis: int in 3:
		expect(absf(midpoint[Mesh.ARRAY_CUSTOM0][12 + axis] - (coordinates[axis] + coordinates[3 + axis]) * .5) < .0000001, "classic High interpolates the rest carrier within float32 precision")
func check_packed(source: Mesh, target: Mesh, label: String) -> void:
	var before: Array = source.get("_surfaces")
	var after: Array = target.get("_surfaces")
	expect(before.size() == after.size(), label + " surface count retained")
	for surface: int in before.size():
		var material := source.surface_get_material(surface)
		if material == null or material.resource_name != "rl_bodypatch":
			expect(var_to_bytes(before[surface]) == var_to_bytes(after[surface]), label + " non-consuming primitive remains entirely byte exact")
		else:
			for key: String in before[surface]:
				if key not in ["format", "attribute_data"]:
					expect(var_to_bytes(before[surface][key]) == var_to_bytes(after[surface][key]), label + " consumer preserves packed " + key)
			expect(var_to_bytes(source.surface_get_blend_shape_arrays(surface)) == var_to_bytes(target.surface_get_blend_shape_arrays(surface)), label + " consumer preserves all decoded morph channels")
func real_heads() -> void:
	var source := GlbSceneCache.instantiate(RLHeadLibrary.head_path("female"))
	for node: Node in source.find_children("*", "MeshInstance3D", true, false):
		var head := node as MeshInstance3D
		var original: Array = head.mesh.get("_surfaces")
		var before := var_to_bytes(original)
		var target := REST.for_material(head.mesh, RLHeadLibrary.BODY_PATCH_MATERIAL)
		check_packed(head.mesh, target, str(head.name))
		expect(var_to_bytes(head.mesh.get("_surfaces")) == before, "source head packed surfaces remain immutable")
		expect(target.get_blend_shape_count() == head.mesh.get_blend_shape_count(), "head morph count retained")
		expect((target as ArrayMesh).blend_shape_mode == (head.mesh as ArrayMesh).blend_shape_mode, "head morph mode retained")
	source.free()
func check_body(actor: ReplicatedActor3D, label: String) -> void:
	var body := actor.find_child("body", true, false) as MeshInstance3D
	var a := body.mesh.surface_get_arrays(0)
	expect(a[Mesh.ARRAY_CUSTOM0] is PackedFloat32Array and a[Mesh.ARRAY_CUSTOM0].size() == a[Mesh.ARRAY_VERTEX].size() * 3, label + " body retains its rest carrier")
	expect(((body.mesh.surface_get_format(0) >> Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT) & 7) == Mesh.ARRAY_CUSTOM_RGB_FLOAT, label + " body carrier format retained")
	var material := body.get_active_material(0) as ShaderMaterial
	expect(material != null and material.get_shader_parameter("smooth_shirt_neckline") == true, label + " default shirt mask active")
func run() -> void:
	synthetic()
	real_heads()
	var stage := Node3D.new()
	root.add_child(stage)
	Stage.build(stage, "neutral")
	var look := {"hair": AppearanceVariants.pack_hair(3, 1), "hair_module": 3, "skin": 2, "eyes": 2}
	var actor := Stage.spawn(stage, "female", look)
	var camera := Camera3D.new()
	stage.add_child(camera)
	camera.global_position = Stage.head_rest(actor).origin + Stage.face_forward(actor) * 1.1
	camera.look_at(Stage.head_rest(actor).origin, Vector3.UP)
	camera.current = true
	actor.hold_portrait_pose(self)
	for frame: int in 8:await process_frame
	for quality: int in [2, 1, 0, 1, 2]:
		actor.apply_render_quality(quality)
		for frame: int in 2:await process_frame
		check_body(actor, "quality " + str(quality))
		if quality == 2:
			var rig := actor.rl_head()
			expect(rig != null, "High keeps the RL head")
			for level: Array in rig.mesh_nodes().head:
				for head: MeshInstance3D in level:
					for surface: int in head.mesh.get_surface_count():
						var material := head.mesh.surface_get_material(surface)
						if material != null and material.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL:
							var a := head.mesh.surface_get_arrays(surface)
							expect(a[Mesh.ARRAY_CUSTOM0] is PackedFloat32Array and a[Mesh.ARRAY_CUSTOM0].size() == a[Mesh.ARRAY_VERTEX].size() * 3, "every head LOD body patch retains the carrier")
	actor.apply_render_quality(1)
	var medium := (actor.find_child("body", true, false) as MeshInstance3D).mesh
	var canonical_coordinates: PackedFloat32Array = medium.surface_get_arrays(0)[Mesh.ARRAY_CUSTOM0]
	var shaped := look.duplicate()
	shaped.height = 75
	shaped.build = 25
	actor.apply_appearance_variants(shaped)
	expect((actor.find_child("body", true, false) as MeshInstance3D).mesh.surface_get_arrays(0)[Mesh.ARRAY_CUSTOM0] == canonical_coordinates, "non-neutral body proportions retain canonical carrier coordinates")
	actor.apply_appearance_variants(look)
	medium = (actor.find_child("body", true, false) as MeshInstance3D).mesh
	var previous_switch := OS.get_environment("RL_HEADS")
	OS.set_environment("RL_HEADS", "classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	actor.apply_render_quality(2)
	for frame: int in 2:await process_frame
	check_body(actor, "classic High fallback")
	actor.apply_render_quality(1)
	expect((actor.find_child("body", true, false) as MeshInstance3D).mesh == medium, "return from classic High restores the exact cached Medium mesh")
	OS.set_environment("RL_HEADS", previous_switch)
	ReplicatedActor3D.reload_rl_heads_switch()
	actor.apply_render_quality(2)
	actor.apply_equipment_visuals({5: Stage.TORSO})
	var body := actor.find_child("body", true, false) as MeshInstance3D
	expect((body.get_active_material(0) as ShaderMaterial).get_shader_parameter("smooth_shirt_neckline") == false, "equipped torso retains its own opening")
	actor.apply_equipment_visuals({})
	check_body(actor, "unequipped default shirt")
	actor.queue_free()
	stage.queue_free()
	for frame: int in 8:await process_frame
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	print("Mesh rest coordinates: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
