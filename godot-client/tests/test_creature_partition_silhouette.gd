extends SceneTree
const Effect := preload("res://src/actors/occluded_silhouette.gd")
var failures := 0
func _init() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok: failures += 1; push_error(message)
func make_mesh(joint: int) -> ArrayMesh:
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([joint,0,0,0,joint,0,0,0,joint,0,0,0])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1,0,0,0,1,0,0,0,1,0,0,0])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2])
	var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	return mesh
func run() -> void:
	var actor := Node3D.new(); root.add_child(actor)
	var skeleton := Skeleton3D.new(); actor.add_child(skeleton)
	skeleton.add_bone("Root"); skeleton.add_bone("Eyes")
	var skin := Skin.new(); skin.add_named_bind("Root",Transform3D.IDENTITY); skin.add_named_bind("Eyes",Transform3D.IDENTITY)
	var original := make_mesh(1); var corrected := make_mesh(0)
	var old_data: PackedByteArray = RenderingServer.mesh_get_surface(original.get_rid(),0).skin_data
	corrected.set_meta("extras",{"rabbitlands_surface_partition_v1":{"reference_skin":{
		"layout":"godot-four-influences-u16-v1","skin_hex":old_data.hex_encode(),"bind_names":["Root","Eyes"]}}})
	var source := MeshInstance3D.new(); source.mesh = corrected; source.skin = skin
	skeleton.add_child(source); source.skeleton = NodePath("..")
	var before: PackedByteArray = RenderingServer.mesh_get_surface(corrected.get_rid(),0).skin_data
	var effect := Effect.new(actor,skeleton); effect.set_enabled(true)
	check(effect._pairs.size() == 1,"one silhouette clone")
	if effect._pairs.size() == 1:
		var clone: MeshInstance3D = effect._pairs[0].clone
		check(clone.mesh != corrected,"clone owns restored skin mesh")
		check(RenderingServer.mesh_get_surface(clone.mesh.get_rid(),0).skin_data == old_data,"silhouette keeps original pre-correction skin")
		check(RenderingServer.mesh_get_surface(corrected.get_rid(),0).skin_data == before,"visible/shared corrected mesh remains untouched")
		source.visible = false; effect.sync(); check(not clone.visible,"visibility mirrors source")
	effect.set_enabled(false)
	check(source.material_overlay == null,"marker overlay restored")
	await process_frame
	actor.free()
	print("CREATURE_PARTITION_SILHOUETTE failures=",failures)
	quit(1 if failures else 0)
