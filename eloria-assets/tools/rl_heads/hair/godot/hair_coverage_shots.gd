extends SceneTree
## Coverage shots of an installed RL hairstyle in the real client actor (the lab's
## stage), from the back, both back three-quarters, above the crown and below the
## nape, at several hair_detail levels. Run from outside the project:
##   Godot --path <godot-client> --resolution 640x720 -s <this file>
## with RL_SHOT_DIR (output folder), RL_SHOT_PRESET (default rowan) and
## RL_SHOT_DETAILS (default 0,50,100) in the environment. Writes only RL_SHOT_DIR.

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const VIEWS := {"back": [180.0, 5.0], "back_tq_l": [145.0, 10.0], "back_tq_r": [-145.0, 10.0],
	"top_back": [180.0, 52.0], "low_back": [180.0, -22.0]}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var out_dir := OS.get_environment("RL_SHOT_DIR")
	var preset := OS.get_environment("RL_SHOT_PRESET")
	if preset.is_empty():
		preset = "rowan"
	var details_env := OS.get_environment("RL_SHOT_DETAILS")
	var details: Array = []
	for part in (details_env if not details_env.is_empty() else "0,50,100").split(","):
		details.append(int(part))
	DirAccess.make_dir_recursive_absolute(out_dir)
	var stage := Node3D.new()
	root.add_child(stage)
	Stage.build(stage, "neutral")
	var cam := Camera3D.new()
	cam.near = 0.02
	cam.fov = 24.0
	cam.cull_mask = 1
	stage.add_child(cam)
	cam.current = true
	for detail: int in details:
		var face := RLHeadAppearance.from_preset(preset)
		face.hair_detail = detail
		var actor := Stage.spawn(stage, face.sex, {"rl_head": face.to_dict()}, {}, ActorRenderQuality.Quality.HIGH)
		var rig := actor.rl_head()
		if rig != null:
			rig.set_hair_motion_allowed(false)
		for i in 40:
			await process_frame
		var rest: Transform3D = Stage.head_rest(actor)
		var fwd: Vector3 = Stage.face_forward(actor)
		var target := rest.origin + Vector3.UP * 0.07
		for view: String in VIEWS:
			var az: float = deg_to_rad(VIEWS[view][0])
			var el: float = deg_to_rad(VIEWS[view][1])
			var d := fwd.rotated(Vector3.UP, az) * cos(el) + Vector3.UP * sin(el)
			cam.global_position = target + d.normalized() * 1.05
			cam.look_at(target, Vector3.UP if absf(el) < 1.2 else fwd)
			for i in 4:
				await process_frame
			var img := root.get_texture().get_image()
			img.save_png(out_dir.path_join("%s_detail%d_%s.png" % [preset, detail, view]))
		actor.queue_free()
		for i in 3:
			await process_frame
	print("RL_SHOTS_DONE ", out_dir)
	quit(0)
