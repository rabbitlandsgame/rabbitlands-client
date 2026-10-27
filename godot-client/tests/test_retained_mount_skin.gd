extends SceneTree
const Retained := preload("res://src/mounts/retained_mount_skin.gd")
var failures := 0
var checks := 0

func _init() -> void: run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func make_mesh(joint: int) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK,Vector3.BACK,Vector3.BACK])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.DOWN])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([joint,0,0,0,joint,0,0,0,joint,0,0,0])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1,0,0,0,1,0,0,0,1,0,0,0])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	mesh.surface_set_material(0,StandardMaterial3D.new())
	return mesh

func run() -> void:
	var skeleton := Skeleton3D.new()
	skeleton.add_bone("Root"); skeleton.add_bone("Shell")
	var skin := Skin.new()
	skin.add_named_bind("Root",Transform3D.IDENTITY)
	skin.add_named_bind("Shell",Transform3D.IDENTITY)
	var original := make_mesh(1)
	var source := make_mesh(0)
	var before := RenderingServer.mesh_get_surface(source.get_rid(),0)
	var original_bytes: PackedByteArray = RenderingServer.mesh_get_surface(original.get_rid(),0).skin_data
	var record := {"layout":Retained.LAYOUT,"bind_names":["Root","Shell"],"skin_hex":original_bytes.hex_encode()}
	source.set_meta("extras",{Retained.KEY:record,"rabbitlands_coat_pattern_height":3.5})
	check(Retained.for_mount(original,null,null).mesh == original,"unmarked meshes pass through unchanged")
	var result := Retained.for_mount(source,skin,skeleton)
	check(result.errors.is_empty(),"valid retained skin restores")
	if result.errors.is_empty():
		var restored := result.mesh as ArrayMesh
		check(restored != source,"restoration owns a private mesh")
		var after := RenderingServer.mesh_get_surface(restored.get_rid(),0)
		check(after.skin_data == original_bytes,"restored packed skin is exact")
		check(after.bone_aabbs == RenderingServer.mesh_get_surface(original.get_rid(),0).bone_aabbs,"culling bounds follow restored influences")
		for key: String in ["vertex_data","attribute_data","index_data","format","vertex_count","index_count"]:
			check(before.get(key) == after.get(key),"encoded geometry retained: " + key)
		check(restored.surface_get_arrays(0)[Mesh.ARRAY_BONES] == original.surface_get_arrays(0)[Mesh.ARRAY_BONES],"CPU skin arrays see the restoration")
		check(restored.surface_get_material(0) == source.surface_get_material(0),"materials remain shared")
		check(restored.get_meta("extras") == source.get_meta("extras"),"coat scale metadata survives restoration")
		check(Retained.for_mount(restored,skin,skeleton).mesh == restored,"restoration is idempotent")
	check(RenderingServer.mesh_get_surface(source.get_rid(),0).skin_data == before.skin_data,"cached wild mesh remains untouched")
	for change: String in ["layout","binding","length","joint","influences"]:
		var bad := record.duplicate(true)
		if change == "layout": bad.layout = "other-version"
		if change == "binding": bad.bind_names[1] = "OtherBone"
		if change == "length": bad.skin_hex = "00"
		if change == "joint": bad.skin_hex = "ffff" + str(bad.skin_hex).substr(4)
		if change == "influences": bad.bind_names = ["Root"]
		source.set_meta("extras",{Retained.KEY:bad})
		check(not Retained.for_mount(source,skin,skeleton).errors.is_empty(),"invalid record rejected: " + change)
	skeleton.free()
	print("RETAINED_MOUNT_SKIN ",checks," checks; failures=",failures)
	quit(1 if failures else 0)
