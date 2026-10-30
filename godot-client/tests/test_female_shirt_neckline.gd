extends SceneTree
const Stage = preload("res://prototypes/rl_heads/rl_head_stage.gd")
const Repair = preload("res://src/actors/female_shirt_neckline.gd")
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, label: String) -> void:
	print(("PASS " if ok else "FAIL ") + label)
	if not ok:
		failures += 1

func run() -> void:
	var model := GlbSceneCache.instantiate(Repair.BODY)
	var shirt := model.find_child("wardrobe_shirt", true, false) as MeshInstance3D
	var body := model.find_child("body", true, false) as MeshInstance3D
	var source_body := body.mesh
	var source_skin := shirt.skin
	Repair.apply(model, Repair.BODY)
	check(body.mesh == source_body and shirt.skin == source_skin, "canonical body and shirt binds retained")
	check(shirt.mesh.get_surface_count() == 2, "repaired collar and original fabric both present")
	var arrays := shirt.mesh.surface_get_arrays(1)
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var used := {}
	for i: int in indices:
		used[i] = true
	var rim := PackedVector3Array()
	for i: int in used:
		var p := points[i]
		var angle := atan2(p.x, p.z + .030)
		var y := 1.50 + .010 * pow(sin(angle), 2) - .075 * pow(maxf(cos(angle), 0), 4)
		if absf(p.y-y) < .00001:
			rim.append(p)
	check(rim.size() == 192, "complete smooth collar rim")
	var mirror_error := 0.0
	for p: Vector3 in rim:
		var mirrored := Vector3(-p.x,p.y,p.z)
		var nearest := INF
		for q: Vector3 in rim:
			nearest = minf(nearest,q.distance_to(mirrored))
		mirror_error = maxf(mirror_error,nearest)
	check(mirror_error < .00001, "both sides mirror within 0.01 mm (%.6f mm)" % (mirror_error*1000))
	model.free()
	var stage := Node3D.new()
	root.add_child(stage)
	var library: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/rl_head_archetypes.json"))
	var appearance: Dictionary = {}
	for row: Dictionary in library.archetypes:
		if row.id == "human_01":
			appearance = row.appearance_pc3.duplicate(true)
	var presets: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/rl_head_presets.json")).presets
	appearance.rl_head = presets.human_01
	var actor: ReplicatedActor3D = Stage.spawn(stage,"female",appearance)
	actor.hold_portrait_pose(self)
	for i: int in 6:
		await process_frame
	var actor_shirt := actor.find_child("wardrobe_shirt",true,false) as MeshInstance3D
	var actor_body := actor.find_child("body",true,false) as MeshInstance3D
	check(actor_shirt.mesh.get_surface_count() == 2, "normal actor route installs the repaired collar")
	var material := actor_body.get_active_material(0) as ShaderMaterial
	check(material != null and material.get_shader_parameter("smooth_shirt_neckline") == true, "source skin stays under the default collar")
	actor.apply_equipment_visuals({5:Stage.TORSO})
	check(material.get_shader_parameter("smooth_shirt_neckline") == false, "equipped torso keeps its own neckline")
	actor.apply_equipment_visuals({})
	check(material.get_shader_parameter("smooth_shirt_neckline") == true, "default collar restored after unequipping")
	actor.queue_free()
	stage.queue_free()
	for i: int in 8:
		await process_frame
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	RLHeadLibrary.clear()
	GlbSceneCache.clear()
	print("female shirt neckline: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)
