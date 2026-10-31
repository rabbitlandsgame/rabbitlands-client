extends SceneTree
const NECK := preload("res://src/actors/rl_head/rl_head_neck_normals.gd")
const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
var checks := 0
var failures := 0
func expect(ok: bool,label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
func _initialize() -> void:call_deferred("run")
func masked_normals(data: PackedByteArray,rows: Array,offset: int,stride: int,frame_bytes: int,frames: int) -> PackedByteArray:
	var result := data.duplicate()
	for frame: int in frames:
		for row: int in rows:
			for byte: int in 4:result[frame * frame_bytes + offset + stride * row + byte] = 0
	return result
func altered(source: ArrayMesh,key: String,morph: bool = false) -> ArrayMesh:
	var result := source.duplicate() as ArrayMesh
	var surfaces: Array = result.get("_surfaces")
	for surface: int in result.get_surface_count():
		if result.surface_get_material(surface).resource_name != "rl_bodypatch":continue
		var packed: Dictionary = surfaces[surface].duplicate()
		var bytes: PackedByteArray = packed[key].duplicate()
		var count: int = packed.vertex_count
		var offset := RenderingServer.mesh_surface_get_format_offset(packed.format,count,Mesh.ARRAY_NORMAL)
		var stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(packed.format,count)
		var at := offset + stride * 40 + (count * 20 if morph else 0)
		bytes[at] = (bytes[at] + 10) % 256
		packed[key] = bytes
		surfaces[surface] = packed
	result.set("_surfaces",surfaces)
	return result
func unsupported_checks(source: ArrayMesh) -> void:
	var targets := NECK.plan(source)
	var relative := source.duplicate() as ArrayMesh
	relative.blend_shape_mode = Mesh.BLEND_SHAPE_MODE_RELATIVE
	expect(NECK.plan(relative).is_empty() and NECK.patch(relative,targets) == relative,"unsupported morph mode leaves head unchanged and emits no body targets")
	var changed := altered(source,"vertex_data")
	expect(NECK.plan(changed).is_empty() and NECK.patch(changed,targets) == changed,"unreviewed source normal fails closed")
	var morph := altered(source,"blend_shapes",true)
	expect(NECK.plan(morph).is_empty() and NECK.patch(morph,targets) == morph,"nonzero target normal delta fails closed")
	var sparse := ArrayMesh.new()
	var minimal := []
	minimal.resize(Mesh.ARRAY_MAX)
	minimal[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO,Vector3.RIGHT,Vector3.UP])
	minimal[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.FORWARD,Vector3.FORWARD,Vector3.FORWARD])
	for i: int in 75:sparse.add_blend_shape("shape%d" % i)
	var shapes: Array[Array] = []
	for i: int in 75:shapes.append(minimal)
	sparse.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,minimal,shapes)
	var material := StandardMaterial3D.new()
	material.resource_name = "rl_bodypatch"
	sparse.surface_set_material(0,material)
	expect(NECK.plan(sparse).is_empty() and NECK.patch(sparse,targets) == sparse,"unreviewed vertex/normal format leaves source unchanged")
	var normalless := ArrayMesh.new()
	minimal[Mesh.ARRAY_NORMAL] = null
	shapes.clear()
	for i: int in 75:
		normalless.add_blend_shape("shape%d" % i)
		shapes.append(minimal)
	normalless.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,minimal,shapes)
	normalless.surface_set_material(0,material)
	expect(NECK.plan(normalless).is_empty() and NECK.patch(normalless,targets) == normalless,"missing normals fail closed before any typed array assignment")
	var lods: Array = [[{"mesh":source}],[{"mesh":source}],[{"mesh":relative}]]
	NECK.prepare_lods(lods,"res://assets/actors/native/races/luminous_male.glb")
	for level: Array in lods:
		expect(not level[0].has("neck_normals"),"one unsupported LOD suppresses all head/body targets")
	expect(lods[0][0].mesh == source and lods[2][0].mesh == relative,"no earlier LOD is partially corrected")
	lods = [[{"mesh":source}],[{"mesh":source}],[{"mesh":source}]]
	NECK.prepare_lods(lods,RLHeadLibrary.head_path("male"))
	expect(not lods[0][0].has("neck_normals") and lods[0][0].mesh == source,"unreviewed body identity suppresses head/body correction together")
func source_checks() -> void:
	var imported := GlbSceneCache.instantiate(RLHeadLibrary.head_path("male"))
	for node: Node in imported.find_children("*","MeshInstance3D",true,false):
		var mesh := (node as MeshInstance3D).mesh as ArrayMesh
		if node.name == &"rl_head_lod0":unsupported_checks(mesh)
		var source_bytes := var_to_bytes(mesh.get("_surfaces"))
		var targets := NECK.plan(mesh)
		expect(targets.size() == 7,"only seven reviewed neck groups")
		var result := NECK.patch(mesh,targets)
		expect(var_to_bytes(mesh.get("_surfaces")) == source_bytes,"imported source remains immutable")
		expect(result.blend_shape_mode == mesh.blend_shape_mode and result.get_blend_shape_count() == 75,"all target names/count/mode retained")
		var original: Array = mesh.get("_surfaces")
		var modified: Array = result.get("_surfaces")
		for surface: int in mesh.get_surface_count():
			var material := mesh.surface_get_material(surface)
			if material.resource_name != "rl_bodypatch":
				expect(var_to_bytes(original[surface]) == var_to_bytes(modified[surface]),"face/eye/other primitive remains entirely packed-exact")
				continue
			var rows: Array = []
			for target: Dictionary in targets:rows.append_array(target.rows)
			expect(rows.size() == 15,"exact fifteen patch normal rows")
			var packed: Dictionary = original[surface]
			var count: int = packed.vertex_count
			var offset := RenderingServer.mesh_surface_get_format_offset(packed.format,count,Mesh.ARRAY_NORMAL)
			var stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(packed.format,count)
			for key: String in packed:
				if key not in ["vertex_data","blend_shapes"]:
					expect(var_to_bytes(packed[key]) == var_to_bytes(modified[surface][key]),"non-normal payload unchanged:" + key)
			expect(masked_normals(packed.vertex_data,rows,offset,stride,count*20,1) == masked_normals(modified[surface].vertex_data,rows,offset,stride,count*20,1),"all base bytes outside selected normals exact")
			expect(masked_normals(packed.blend_shapes,rows,offset,stride,count*20,75) == masked_normals(modified[surface].blend_shapes,rows,offset,stride,count*20,75),"all75 target bytes outside selected normals exact")
			var a := result.surface_get_arrays(surface)
			for target: Dictionary in targets:
				for row: int in target.rows:
					expect(a[Mesh.ARRAY_NORMAL][row].distance_to(target.normal) < .0002,"corrected patch normal matches the unique-normal average")
			var shapes := result.surface_get_blend_shape_arrays(surface)
			for shape: Array in shapes:
				var correct := true
				for row: int in rows:correct = correct and shape[Mesh.ARRAY_NORMAL][row] == a[Mesh.ARRAY_NORMAL][row]
				expect(correct,"NORMALIZED target keeps zero normal delta")
	imported.free()
func check_runtime(actor: ReplicatedActor3D,label: String) -> void:
	var info := RLHeadLibrary.head("male")
	var body := actor.find_child("body",true,false) as MeshInstance3D
	var a := body.mesh.surface_get_arrays(0)
	var points: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
	var matched_groups := 0
	for target: Dictionary in info.neck_normals:
		var matched := false
		for row: int in points.size():
			if points[row].distance_to(target.position) <= NECK.TOLERANCE:
				matched = true
				expect(normals[row].distance_to(target.normal) < .0002,label+" retained body normal matches patch")
		if matched:matched_groups += 1
	expect(matched_groups == 3,label+" only three lower canonical body groups match")
func run() -> void:
	var previous_retain := RLHeadLibrary.retain_seconds
	RLHeadLibrary.retain_seconds = 0.0
	source_checks()
	var stage := Node3D.new()
	root.add_child(stage)
	var look := {"hair":0,"hair_module":1,"skin":2}
	var actor := Stage.spawn(stage,"male",look,{},ActorRenderQuality.Quality.MEDIUM)
	for frame: int in 8:await process_frame
	var body := actor.find_child("body",true,false) as MeshInstance3D
	var medium := body.mesh
	actor.apply_render_quality(0)
	var low := body.mesh
	actor.apply_render_quality(2)
	for frame: int in 4:await process_frame
	check_runtime(actor,"neutral")
	var high_body := body.mesh
	var cached_head: Mesh = RLHeadLibrary.head("male").lods[0][0].mesh
	var second := Stage.spawn(stage,"male",look,{},ActorRenderQuality.Quality.HIGH)
	for frame: int in 4:await process_frame
	expect((second.find_child("body",true,false) as MeshInstance3D).mesh == high_body,"equivalent High actors reuse the body-cut derivative")
	expect(RLHeadLibrary.head("male").lods[0][0].mesh == cached_head,"equivalent actors reuse the derived source head")
	var shaped := look.duplicate()
	shaped.height = 75
	shaped.build = 25
	actor.apply_appearance_variants(shaped)
	for frame: int in 4:await process_frame
	check_runtime(actor,"non-neutral proportions")
	actor.apply_appearance_variants(look)
	actor.apply_render_quality(0)
	expect(body.mesh == low,"original cached Low resource restored exactly")
	actor.apply_render_quality(1)
	expect(body.mesh == medium,"original cached Medium resource restored exactly")
	actor.apply_render_quality(2)
	for frame: int in 4:await process_frame
	expect(body.mesh == high_body and RLHeadLibrary.head("male").lods[0][0].mesh == cached_head,"repeated High reuses derivatives while another user holds them")
	actor.queue_free()
	second.queue_free()
	stage.queue_free()
	for frame: int in 8:await process_frame
	expect(RLHeadLibrary.users() == 0 and not RLHeadLibrary.is_loaded(),"last actor releases the shared head resources")
	expect(RLHeadBodyCut._cuts.is_empty() and RLHeadBodyCut._plans.is_empty(),"last actor releases derived body-cut caches")
	RLHeadLibrary.retain_seconds = previous_retain
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	print("RL head neck normals: %d checks,%d failures" % [checks,failures])
	quit(1 if failures else 0)
