extends SceneTree
## Keeps the cape off the body through an attack.
##
## Two failures this guards, both only visible under real momentum -- a static
## seek settles the overshoot away, so the actor walks and then swings while
## the cloth is measured every frame:
##   - the cape swinging forward onto the chest, when the torso leans and twists
##     (measured against the spine's own forward, not the arms', which swing);
##   - the hem whipping up into a spike over the shoulder, when a fast lunge
##     lands on an already-moving cape (measured as height above the anchor).
## The worst frame of each is photographed from a three-quarter front so a
## borderline reading can be looked at. This is a floor, not a ceiling: the
## live game drives the cape from network poses and blended clips this harness
## cannot fully stage, so a clean run here means the sim keeps the cape behind
## under the motion it CAN stage, not that no pose anywhere spikes.

const ATTACKS := ["Sword_Attack", "Attack_Ground_Pound", "Punch_Cross"]
const CAPE_VISUAL := 5
const BODY_VISUAL := 184
## The cape may reach this far ahead of the spine plane (the plane runs down the
## middle of the torso, so a little is still inside the body) and this far above
## the anchor (a trail reaches shoulder height; more is a spike).
const AHEAD_TOLERANCE := 0.04
const RISE_TOLERANCE := 0.14

var _failures := 0
var _artifacts := ""
var _main: Control
var _stage: Node3D
var _camera: Camera3D
var _adapter: CoordinateAdapter
var _model_config: Dictionary
var _animation_config: Dictionary
var _equipment_config: Dictionary
var _forward_local := Vector3.ZERO

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/cape-clipping")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = Vector2i(560, 720)
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	await process_frame
	var models: Dictionary = _main.get("models") as Dictionary
	_equipment_config = _main.get("equipment_config") as Dictionary
	_model_config = models.get("luminous_male", {}) as Dictionary
	_animation_config = _main.call("_animation_for_model", _model_config) as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})

	_stage = Node3D.new()
	root.add_child(_stage)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.85, 0.87, 0.9)
	env.environment.ambient_light_energy = 1.2
	_stage.add_child(env)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-30.0, 165.0, 0.0)
	_stage.add_child(key)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.cull_mask = 3
	_stage.add_child(_camera)

	var actor := _spawn({str(2): CAPE_VISUAL, str(5): BODY_VISUAL})
	await _settle(actor)
	var skeleton: Skeleton3D = _skeleton_of(actor)
	var cape_bones: PackedInt32Array = _cape_bones(skeleton)
	_detect_forward(skeleton)
	var player: AnimationPlayer = actor.get("animation_player") as AnimationPlayer

	for clip: String in ATTACKS:
		if not player.has_animation(clip):
			continue
		# Walk, then swing: the cape is already moving when the lunge lands,
		# which is what stresses both the forward wrap and the upward whip.
		actor.play_action(&"walk")
		var travel := 3.0
		actor.server_target = Vector3(0, 0, travel)
		for _f: int in range(10):
			travel += 0.05
			actor.server_target = Vector3(0, 0, travel)
			await process_frame
		player.play(clip)
		var worst_ahead := -1.0
		var worst_rise := 0.0
		var ahead_frame := 0
		var rise_frame := 0
		for frame: int in range(48):
			travel += 0.05
			actor.server_target = Vector3(0, 0, travel)
			await process_frame
			var m: Vector2 = _measure(skeleton, cape_bones)
			if m.x > worst_ahead:
				worst_ahead = m.x
				ahead_frame = frame
			if m.y > worst_rise:
				worst_rise = m.y
				rise_frame = frame
			if not player.is_playing():
				player.play(clip)
		# Photograph both worst frames by replaying to them.
		await _replay_to(actor, player, clip, maxi(ahead_frame, rise_frame))
		await _capture(actor, "cape-%s.png" % clip.to_lower())
		var why := PackedStringArray()
		if worst_ahead > AHEAD_TOLERANCE:
			why.append("forward %.3f" % worst_ahead)
		if worst_rise > RISE_TOLERANCE:
			why.append("spike %.3f above anchor" % worst_rise)
		var verdict: String = "ok" if why.is_empty() else "CLIPS (%s)" % ", ".join(why)
		print("  %-22s worst ahead %+.3f, worst rise %.3f  %s"
			% [clip, worst_ahead, worst_rise, verdict])
		if not why.is_empty():
			_failures += 1

	print("rendered cape clipping: ", "PASS" if _failures == 0
		else "FAIL (%d)" % _failures)
	_main.queue_free()
	await process_frame
	quit(_failures)

func _replay_to(actor: ReplicatedActor3D, player: AnimationPlayer,
		clip: String, frame: int) -> void:
	actor.play_action(&"walk")
	var travel := 3.0
	actor.server_target = Vector3(0, 0, travel)
	for _f: int in range(10):
		travel += 0.05
		actor.server_target = Vector3(0, 0, travel)
		await process_frame
	player.play(clip)
	for f: int in range(frame + 1):
		travel += 0.05
		actor.server_target = Vector3(0, 0, travel)
		await process_frame

func _capture(actor: ReplicatedActor3D, name: String) -> void:
	var skeleton: Skeleton3D = _skeleton_of(actor)
	var chest: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(
		skeleton.find_bone("spine_03")).origin
	# Three-quarter front: a side-front fling or an over-head spike both show.
	_camera.global_position = chest + Vector3(-1.1, 0.2, -1.7)
	_camera.look_at(chest, Vector3.UP)
	for _f: int in range(2):
		await process_frame
	root.get_texture().get_image().save_png(_artifacts.path_join(name))

## Ahead of the spine plane (any cape joint), and how high the HEM rises above
## the anchor -- both in metres. The hem, not the whole cape: the collar links
## sit high by design at the neck, so only the hanging tips flying up is a
## spike.
func _measure(skeleton: Skeleton3D, cape_bones: PackedInt32Array) -> Vector2:
	var to_world: Transform3D = skeleton.global_transform
	var anchor: int = skeleton.find_bone("spine_03")
	var anchor_pos: Vector3 = to_world * skeleton.get_bone_global_pose(anchor).origin
	var forward: Vector3 = (to_world.basis
		* skeleton.get_bone_global_pose(anchor).basis * _forward_local).normalized()
	var plane: float = anchor_pos.dot(forward)
	var ahead := -1.0
	for bone: int in cape_bones:
		var pos: Vector3 = to_world * skeleton.get_bone_global_pose(bone).origin
		ahead = maxf(ahead, pos.dot(forward) - plane)
	var rise := -2.0
	for chain: String in ["l", "c", "r"]:
		var hem: int = skeleton.find_bone("cape_%s_04" % chain)
		if hem >= 0:
			rise = maxf(rise, (to_world * skeleton.get_bone_global_pose(hem).origin).y
				- anchor_pos.y)
	return Vector2(ahead, rise)

## The spine bone's local axis at the chest, the way the sim finds it: from the
## CENTRE chain, whose rest offset is purely backward. A side chain's is mostly
## lateral and would name a sideways axis "forward".
func _detect_forward(skeleton: Skeleton3D) -> void:
	var anchor: int = skeleton.find_bone("spine_03")
	var neck: int = skeleton.find_bone("neck_01")
	var centre: int = skeleton.find_bone("cape_c_02")
	if anchor < 0 or centre < 0:
		return
	var anchor_rest: Transform3D = skeleton.get_bone_global_rest(anchor)
	var up: Vector3 = Vector3.UP
	if neck >= 0:
		up = (skeleton.get_bone_global_rest(neck).origin - anchor_rest.origin).normalized()
	var hang: Vector3 = skeleton.get_bone_global_rest(centre).origin - anchor_rest.origin
	hang -= up * hang.dot(up)
	if hang.length_squared() < 1e-9:
		return
	hang = hang.normalized()
	var best := -2.0
	for local: Vector3 in [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN,
			Vector3.FORWARD, Vector3.BACK]:
		var world: Vector3 = (anchor_rest.basis * local).normalized()
		var flat: Vector3 = world - up * world.dot(up)
		if flat.length_squared() < 1e-4:
			continue
		var score: float = flat.normalized().dot(-hang)
		if score > best:
			best = score
			_forward_local = local

func _cape_bones(skeleton: Skeleton3D) -> PackedInt32Array:
	var bones := PackedInt32Array()
	for chain: String in ["l", "c", "r"]:
		for link: int in range(1, 5):
			var bone: int = skeleton.find_bone("cape_%s_%02d" % [chain, link])
			if bone >= 0:
				bones.append(bone)
	return bones

func _skeleton_of(actor: ReplicatedActor3D) -> Skeleton3D:
	var model: Node = actor.get_node_or_null("NativeModel")
	for node_value: Node in model.find_children("*", "Skeleton3D", true, false):
		return node_value as Skeleton3D
	return null

func _spawn(visuals: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	actor.configure({
		"actor_id": 8100, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "cape", "appearance": {}, "equipment_visuals": visuals,
	}, _adapter, _model_config, _animation_config, _equipment_config)
	actor.server_target = Vector3.ZERO
	actor.global_position = Vector3.ZERO
	actor.rotation.y = 0.0
	return actor

func _settle(actor: ReplicatedActor3D) -> void:
	actor.play_action(&"idle")
	for _f: int in range(20):
		await process_frame
