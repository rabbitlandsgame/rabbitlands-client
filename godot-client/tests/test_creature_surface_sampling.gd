extends SceneTree
## CPU sampling is checked headlessly. Run with Forward+ for MultiMesh readback.
## --legacy=res://path/to/immutable/original/creature_dissolve.gd strengthens
## the renderer check by comparing the pre-partition implementation directly.
const Dissolve := preload("res://src/actors/creature_dissolve.gd")
const Sampling := preload("res://src/actors/creature_surface_sampling.gd")
var checks := 0
var failures: Array[String] = []
var gpu_cases := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func input_arrays() -> Array:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	var points := PackedVector3Array()
	var normals := PackedVector3Array()
	var uv := PackedVector2Array()
	for triangle in 4:
		for point: Vector3 in [Vector3(triangle*.3,triangle*.07,0),Vector3(triangle*.3+.18,triangle*.07,.11),Vector3(triangle*.3+.04,triangle*.07+.21,.03)]:
			points.append(point); normals.append(Vector3.UP); uv.append(Vector2(point.x,point.y))
	arrays[Mesh.ARRAY_VERTEX] = points
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array(range(12))
	return arrays

func weighted_arrays(slots: int) -> Array:
	var arrays := input_arrays()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	var profile := [.13729,.20381,.31457,.34433] if slots == 4 else [.09123,.17381,.22157,.14433,.08767,.06419,.10231,.11489]
	for vertex in 12:
		for slot in slots:
			bones.append(slot)
			weights.append(float(profile[(slot+vertex)%slots]))
	arrays[Mesh.ARRAY_BONES] = bones; arrays[Mesh.ARRAY_WEIGHTS] = weights
	return arrays

func subset(arrays: Array, ids: PackedInt32Array, slots: int, rigid: bool) -> Array:
	var result := []
	result.resize(Mesh.ARRAY_MAX)
	var points := PackedVector3Array(); var normals := PackedVector3Array(); var uv := PackedVector2Array()
	var bones := PackedInt32Array(); var weights := PackedFloat32Array()
	for vertex in ids:
		points.append(arrays[Mesh.ARRAY_VERTEX][vertex]); normals.append(arrays[Mesh.ARRAY_NORMAL][vertex]); uv.append(arrays[Mesh.ARRAY_TEX_UV][vertex])
		for slot in (4 if rigid else slots):
			bones.append(0 if rigid else int(arrays[Mesh.ARRAY_BONES][vertex*slots+slot]))
			weights.append((1.0 if slot == 0 else 0.0) if rigid else float(arrays[Mesh.ARRAY_WEIGHTS][vertex*slots+slot]))
	result[Mesh.ARRAY_VERTEX] = points; result[Mesh.ARRAY_NORMAL] = normals; result[Mesh.ARRAY_TEX_UV] = uv
	result[Mesh.ARRAY_BONES] = bones; result[Mesh.ARRAY_WEIGHTS] = weights
	result[Mesh.ARRAY_INDEX] = PackedInt32Array(range(ids.size()))
	return result

func make_mesh(arrays: Array, material: Material, slots: int) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{},Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS if slots == 8 else 0)
	mesh.surface_set_material(0,material)
	return mesh

func add_part(skeleton: Skeleton3D, resource: Mesh, skin: Skin, label: String) -> MeshInstance3D:
	var node := MeshInstance3D.new(); node.name = label; node.mesh = resource; node.skin = skin
	node.skeleton = NodePath(".."); skeleton.add_child(node)
	return node

func make_fixture(split: bool, slots: int, pose: float, several := false) -> Dictionary:
	var actor := Node3D.new(); root.add_child(actor)
	actor.transform = Transform3D(Basis.from_euler(Vector3(.11,.37,-.13)).scaled(Vector3(1.2,.8,1.1)),Vector3(2,-1,3))
	var skeleton := Skeleton3D.new(); actor.add_child(skeleton)
	skeleton.transform = Transform3D(Basis.from_euler(Vector3(-.07,.12,.03)),Vector3(.17,.23,-.19))
	var skin := Skin.new(); var names := []
	for bone in slots:
		var label := "Joint"+str(bone)
		skeleton.add_bone(label); skin.add_named_bind(label,Transform3D.IDENTITY); names.append(label)
		skeleton.set_bone_pose_position(bone,Vector3(sin(bone+.3)*pose*.12,cos(bone+.7)*pose*.09,bone*pose*.013))
		skeleton.set_bone_pose_rotation(bone,Quaternion.from_euler(Vector3(.04*bone*pose,-.03*bone*pose,.02*bone*pose)))
	skeleton.force_update_all_bone_transforms()
	var material := StandardMaterial3D.new(); material.albedo_color = Color(.23,.61,.37,.91); material.roughness = .43; material.metallic = .17
	var original_arrays := weighted_arrays(slots)
	var original_mesh := make_mesh(original_arrays,material,slots)
	var original_skin: PackedByteArray = RenderingServer.mesh_get_surface(original_mesh.get_rid(),0).skin_data
	var parts: Array[MeshInstance3D] = []
	var remainder: MeshInstance3D
	if split:
		remainder = add_part(skeleton,make_mesh(subset(original_arrays,PackedInt32Array([0,1,2,6,7,8]),slots,false),material,slots),skin,"Remainder")
		remainder.mesh.set_meta("extras",{Sampling.KEY:{"group":"fixture","role":"remainder","surface":0,"source_vertices":12,"source_triangles":4,"selected_triangles":[1,3]}})
		parts.append(remainder)
	else:
		parts.append(add_part(skeleton,original_mesh,skin,"Original"))
	# Deliberately put an unrelated surface between remainder and selected parts.
	# Grouping at the first selected part would change its original RNG window.
	var other_arrays := input_arrays()
	other_arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-.4,.2,.1),Vector3(-.2,.2,.1),Vector3(-.3,.4,.2)])
	other_arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP])
	other_arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.DOWN])
	other_arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	var other_material := StandardMaterial3D.new(); other_material.albedo_color = Color(.7,.19,.12)
	parts.append(add_part(skeleton,make_mesh(other_arrays,other_material,4),null,"Unrelated"))
	if split:
		var selections := [PackedInt32Array([3,4,5]),PackedInt32Array([9,10,11])] if several else [PackedInt32Array([3,4,5,9,10,11])]
		for group_index in selections.size():
			var ids: PackedInt32Array = selections[group_index]
			var reference := PackedByteArray()
			for vertex in ids: reference.append_array(original_skin.slice(vertex*slots*4,(vertex+1)*slots*4))
			var resource := make_mesh(subset(original_arrays,ids,slots,true),material,4)
			resource.set_meta("extras",{Sampling.KEY:{"group":"fixture","role":"selected","surface":0,"source_vertices":12,"source_triangles":4,"selected_triangles":[1+group_index*2] if several else [1,3],"reference_skin":{"layout":"godot-eight-influences-u16-v1" if slots == 8 else "godot-four-influences-u16-v1","bind_names":names,"skin_hex":reference.hex_encode()}}})
			parts.append(add_part(skeleton,resource,skin,"Selected"+str(group_index)))
	return {"actor":actor,"skeleton":skeleton,"parts":parts,"original_skin":original_skin,"original_mesh":original_mesh}

func collect(actor: Node3D, effect: RefCounted) -> Array[Dictionary]:
	var surfaces: Array[Dictionary] = []
	for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		for surface in mesh.mesh.get_surface_count():
			surfaces.append({"mesh":mesh,"surface":surface,"arrays":mesh.mesh.surface_get_arrays(surface),"skin":effect._skin_transforms(mesh),"material":mesh.get_active_material(surface)})
	return surfaces

func snapshot_resources(fixture: Dictionary) -> Array:
	var rows := []
	for node: MeshInstance3D in fixture.parts:
		rows.append({"node":node,"mesh":node.mesh,"skin":node.skin,"override":node.material_override,"surface_override":node.get_surface_override_material(0),"material":node.mesh.surface_get_material(0),"raw":RenderingServer.mesh_get_surface(node.mesh.get_rid(),0)})
	return rows

func verify_resources(saved: Array) -> void:
	for row: Dictionary in saved:
		expect(row.node.mesh == row.mesh and row.node.skin == row.skin,"shared mesh and skin identities retained")
		expect(row.node.material_override == row.override and row.node.get_surface_override_material(0) == row.surface_override,"original instance overrides restored")
		expect(row.node.mesh.surface_get_material(0) == row.material,"shared base material retained")
		var raw := RenderingServer.mesh_get_surface(row.mesh.get_rid(),0)
		for key: String in ["vertex_data","attribute_data","skin_data","index_data"]:
			expect(raw.get(key) == row.raw.get(key),"encoded source bytes unchanged: "+key)

func compare_uniforms(a: ShaderMaterial, b: ShaderMaterial) -> void:
	for uniform: Dictionary in a.shader.get_shader_uniform_list():
		var name: StringName = uniform.name
		expect(a.get_shader_parameter(name) == b.get_shader_parameter(name),"dissolve uniform preserved: "+str(name))

func metadata_guards() -> void:
	var effect := Dissolve.new()
	var a := make_fixture(true,8,.4)
	var anchor: MeshInstance3D = a.parts[0]
	var resource := anchor.mesh as ArrayMesh
	resource.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,resource.surface_get_arrays(0),[],{},Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
	resource.surface_set_material(1,resource.surface_get_material(0))
	var record: Dictionary = resource.get_meta("extras")[Sampling.KEY]
	record.surface = 1
	var sampling := Sampling.virtual_surfaces(collect(a.actor,effect))
	expect(sampling.errors.is_empty(),"surface metadata applies only to its declared primitive")
	expect(sampling.surfaces.size() == 3 and not sampling.surfaces[0].has("partition") and sampling.surfaces[1].has("partition"),"unmodified sibling primitive retains its original order")
	var b := make_fixture(true,8,.4)
	var all: Array[Dictionary] = collect(a.actor,effect)
	all.append_array(collect(b.actor,effect))
	var repeated := Sampling.virtual_surfaces(all)
	expect(repeated.errors.is_empty(),"same partition ID in separate skeleton instances is scoped independently")
	var groups := 0
	for surface: Dictionary in repeated.surfaces:
		if surface.has("partition"): groups += 1
	expect(groups == 2,"both imported instances retain their own virtual original surface")
	var selected: MeshInstance3D = b.parts[-1]
	var metadata: Dictionary = selected.mesh.get_meta("extras")[Sampling.KEY]
	var good := metadata.duplicate(true)
	for mutation: String in ["duplicate","union","counts","surface","layout","skin_length","bindings"]:
		var bad := good.duplicate(true)
		if mutation == "duplicate": bad.selected_triangles = [1,1]
		if mutation == "union": bad.selected_triangles = [0,3]
		if mutation == "counts": bad.source_vertices = 12.5
		if mutation == "surface": bad.surface = "0"
		if mutation == "layout": bad.reference_skin.layout = "unknown"
		if mutation == "skin_length": bad.reference_skin.skin_hex = "00"
		if mutation == "bindings": bad.reference_skin.bind_names[0] = "MissingJoint"
		selected.mesh.set_meta("extras",{Sampling.KEY:bad})
		expect(not Sampling.virtual_surfaces(collect(b.actor,effect)).errors.is_empty(),"invalid partition record rejected: "+mutation)
	selected.mesh.set_meta("extras",{Sampling.KEY:good})
	a.actor.free(); b.actor.free()

func run() -> void:
	var legacy: Script = Dissolve
	var report_path := ""
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--legacy="): legacy = load(argument.trim_prefix("--legacy=")) as Script
		if argument.begins_with("--report="): report_path = argument.trim_prefix("--report=")
	var gpu := DisplayServer.get_name() != "headless"
	metadata_guards()
	for slots in [4,8]:
		for pose in [0.0,.67,1.0]:
			for seed_value in [0,1,77,193]:
				var a := make_fixture(false,slots,pose)
				var b := make_fixture(true,slots,pose,seed_value == 193)
				var saved_a := snapshot_resources(a); var saved_b := snapshot_resources(b)
				var control := Dissolve.new(); var effect := Dissolve.new()
				control._actor = a.actor; effect._actor = b.actor
				var original := Sampling.virtual_surfaces(collect(a.actor,control))
				var partitioned := Sampling.virtual_surfaces(collect(b.actor,effect))
				expect(original.errors.is_empty() and partitioned.errors.is_empty(),"partition records validate")
				expect(original.total_vertices == partitioned.total_vertices,"original surface vertex weighting restored")
				if not partitioned.errors.is_empty(): a.actor.free(); b.actor.free(); continue
				var first := RandomNumberGenerator.new(); first.seed = seed_value
				var second := RandomNumberGenerator.new(); second.seed = seed_value
				var old_points := control._sample_fragments(original.surfaces,original.total_vertices,first)
				var new_points := effect._sample_fragments(partitioned.surfaces,partitioned.total_vertices,second)
				expect(old_points.points == new_points.points,"all seeded fragment points preserved")
				expect(old_points.colors == new_points.colors,"all seeded fragment colors preserved")
				expect(first.state == second.state,"sampling consumes exactly the original RNG sequence")
				var baseline: RefCounted = legacy.new()
				baseline.begin(a.actor,2.0,seed_value); effect.begin(b.actor,2.0,seed_value)
				baseline.update(.42); effect.update(.42)
				expect(baseline._ash != null and effect._ash != null,"fragment batches created")
				if baseline._ash != null and effect._ash != null:
					compare_uniforms(baseline._materials[0],effect._materials[0])
					compare_uniforms(baseline._materials[1],effect._materials[1])
					for index in range(2,effect._materials.size()-1): compare_uniforms(baseline._materials[0],effect._materials[index])
					compare_uniforms(baseline._ash.material_override,effect._ash.material_override)
					expect(baseline._ash.custom_aabb == effect._ash.custom_aabb,"fragment bounds preserved")
					if gpu:
						await process_frame
						await RenderingServer.frame_post_draw
						var before: PackedFloat32Array = baseline._ash.multimesh.buffer
						var after: PackedFloat32Array = effect._ash.multimesh.buffer
						expect(not before.is_empty() and before == after,"GPU fragment transforms/colors/custom-data preserved")
						gpu_cases += 1
				baseline.update(1.0); effect.update(1.0)
				expect(not baseline._ash.visible and not effect._ash.visible,"completion visibility preserved")
				baseline.reset(); effect.reset()
				verify_resources(saved_a); verify_resources(saved_b)
				expect(baseline._ash == null and effect._ash == null,"revival removes fragment batches")
				a.actor.free(); b.actor.free()
	var report := {"passed":failures.is_empty(),"checks":checks,"failures":failures,"gpu_cases":gpu_cases,"legacy_reference_supplied":legacy != Dissolve}
	if not report_path.is_empty(): FileAccess.open(report_path,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	print("CREATURE_SURFACE_SAMPLING ",JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
