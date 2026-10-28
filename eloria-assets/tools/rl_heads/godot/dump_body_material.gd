extends SceneTree
const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
func _init() -> void:
	call_deferred("_run")
func _run() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	Stage.build(stage, "neutral")
	var face := RLHeadAppearance.from_preset("rowan")
	var actor := Stage.spawn(stage, face.sex, {"rl_head": face.to_dict()}, {}, 2)
	for i in 10:
		await process_frame
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var m := body.get_active_material(0) as ShaderMaterial
	print("BODY material ", m, " override ", body.material_override)
	for p in ["recolor_skin", "skin_color", "skin_reference", "skin_tint", "base_color", "roughness", "use_regions"]:
		print("BODY ", p, " = ", m.get_shader_parameter(p))
	print("RL appearance skin ", actor.rl_head().appearance.skin)
	for n: MeshInstance3D in actor.rl_head().mesh_nodes()["head"][0]:
		print("HEAD node ", n.name, " skin_color instance ", n.get_instance_shader_parameter("skin_color"))
		for s in n.mesh.get_surface_count():
			var sm := n.get_active_material(s)
			print("  surface ", s, " ", sm.resource_name if sm else "null", " ", (sm as ShaderMaterial).shader.resource_path if sm is ShaderMaterial else "")
	quit(0)
