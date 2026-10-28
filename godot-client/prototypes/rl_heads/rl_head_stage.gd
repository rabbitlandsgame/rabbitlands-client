extends RefCounted
## The RL head lab's stage, shared by the lab, the evidence renders and the
## metrics: the game's tone curve and grade on a neutral backdrop, a three-point
## light rig, the real ReplicatedActor3D, and camera framings fixed to the Head
## bone's rest so every preset, sex and frame is shot from the same place.

const MODELS_PATH := "res://data/actors/models.json"
const ANIMATION_PATH := "res://data/animations/luminous.json"
const EQUIPMENT_PATH := "res://data/actors/equipment.json"
const BACKDROP := Color(0.17, 0.18, 0.2)
const FLOOR := Color(0.24, 0.25, 0.26)
## Headwear the lab offers, as the registry names them.
const HEADWEAR: Array = [[0, "None"], [134, "Leather Helm"], [159, "Buckled Hood"],
	[115, "Acolyte Hood"], [122, "Antler Hood"], [111, "Palesteel Circlet"], [170, "Sun Headband"]]
## A class-kit torso per sex, so the neck under a collar can be checked.
const TORSO := 209
const CAPE := 105
## Clips by the lab's names. Every one is in the luminous action map.
const CLIPS := {"Rest": "Rest_Pose", "Idle": "Idle_Subtle", "Walk": "Walk",
	"Run": "Run_Female", "Head_Nod": "Head_Nod"}
## Framings: yaw from the face's forward in degrees, positive towards the
## front view's image right (the character's left, model +X) - so a positive
## yaw turns the face towards image left; pitch in degrees above the target
## (a down-tilt); distance; the look-at offset from the Head rest (up,
## forward); and a narrow FOV, so faces keep their proportions for overlays
## on concept art. The head views frame 0.35 m, the full-body views 1.96 m.
const VIEWS := {
	"front": {"yaw": 0.0, "pitch": 0.0, "distance": 1.12, "up": 0.06, "forward": 0.02, "fov": 18.0},
	"three_quarter": {"yaw": -38.0, "pitch": 8.0, "distance": 1.12, "up": 0.06, "forward": 0.0, "fov": 18.0},
	"profile": {"yaw": 90.0, "pitch": 0.0, "distance": 1.12, "up": 0.06, "forward": 0.0, "fov": 18.0},
	"rear": {"yaw": 180.0, "pitch": 0.0, "distance": 1.12, "up": 0.06, "forward": 0.0, "fov": 18.0},
	"close": {"yaw": 12.0, "pitch": 0.0, "distance": 0.66, "up": 0.075, "forward": 0.04, "fov": 18.0},
	"eyes": {"yaw": 0.0, "pitch": 0.0, "distance": 0.4, "up": 0.07, "forward": 0.05, "fov": 18.0},
	"hair": {"yaw": 145.0, "pitch": 18.0, "distance": 1.0, "up": 0.1, "forward": -0.02, "fov": 18.0},
	"neck": {"yaw": 20.0, "pitch": -4.0, "distance": 0.6, "up": -0.075, "forward": 0.0, "fov": 18.0},
	"neck_rear": {"yaw": 160.0, "pitch": -4.0, "distance": 0.6, "up": -0.06, "forward": 0.0, "fov": 18.0},
	"bust": {"yaw": 25.0, "pitch": 2.0, "distance": 1.9, "up": -0.12, "forward": 0.0, "fov": 18.0},
	"full": {"yaw": 0.0, "pitch": 0.0, "distance": 6.2, "up": -0.62, "forward": 0.0, "fov": 18.0},
	"full_three_quarter": {"yaw": -38.0, "pitch": 8.0, "distance": 6.2, "up": -0.62, "forward": 0.0, "fov": 18.0},
	"full_profile": {"yaw": 90.0, "pitch": 0.0, "distance": 6.2, "up": -0.62, "forward": 0.0, "fov": 18.0},
	"full_rear": {"yaw": 180.0, "pitch": 0.0, "distance": 6.2, "up": -0.62, "forward": 0.0, "fov": 18.0},
}

static var _data: Dictionary = {}


static func data(key: String) -> Dictionary:
	if not _data.has(key):
		var path: String = {"models": MODELS_PATH, "animation": ANIMATION_PATH,
			"equipment": EQUIPMENT_PATH}[key]
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		_data[key] = parsed if parsed is Dictionary else {}
	return _data[key] as Dictionary


## The environment, one of three looks:
##   * "neutral" (the default): linear tone mapping under a neutral key and a
##     grey ambient, calibrated so a front-lit cheek lands on the face's chosen
##     skin colour (Mira, sRGB 237/189/158, renders 245/183/153; Rowan,
##     219/163/125, renders 214/153/118). For judging colour against concept art.
##   * "game": the game's default look, Painted ground, in which a map keeps
##     its own environment and the binder tone-maps it Filmic at exposure 1
##     (world_environment_binder.gd; white 6 here, between the maps' 1 and 9).
##     Filmic compresses and greys skin: the same cheek renders 209/177/156.
##   * "graded": the Full painted grade (LookGrade: AgX, its contrast, toe and
##     saturation, and the cool ambient), which desaturates further (207/187/176).
static func environment(look: String = "neutral") -> Environment:
	var result := Environment.new()
	result.background_mode = Environment.BG_COLOR
	result.background_color = BACKDROP
	result.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	if look == "graded":
		result.ambient_light_color = Color(0.78, 0.8, 0.84).lerp(LookProfile.AMBIENT_COOL,
			LookProfile.AMBIENT_COOL_SHARE)
		result.ambient_light_energy = 0.32
		var curve: Dictionary = LookProfile.TONEMAP_CURVES["agx"]
		var forward := RenderingServer.get_current_rendering_method() == "forward_plus"
		result.tonemap_mode = Environment.TONE_MAPPER_AGX
		result.tonemap_exposure = float(curve["exposure"])
		result.tonemap_agx_white = float(curve["agx_white"])
		result.tonemap_agx_contrast = float(curve["agx_contrast_forward"] if forward else curve["agx_contrast"])
		result.adjustment_enabled = true
		result.adjustment_contrast = LookProfile.CONTRAST
		result.adjustment_saturation = LookProfile.SATURATION_FORWARD if forward else LookProfile.SATURATION
		result.adjustment_color_correction = LookGrade.toe_curve()
	else:
		result.ambient_light_color = Color(0.66, 0.66, 0.67)
		result.ambient_light_energy = 0.45
		result.tonemap_mode = Environment.TONE_MAPPER_FILMIC if look == "game" \
			else Environment.TONE_MAPPER_LINEAR
		result.tonemap_exposure = 1.0
		result.tonemap_white = 6.0
	if RenderingServer.get_current_rendering_method() == "forward_plus" \
			and OS.get_environment("RL_STAGE_NO_SSAO") != "1":
		result.ssao_enabled = true
		result.ssao_radius = 0.4
		result.ssao_intensity = 1.0
	return result


## Backdrop, floor, environment and a key, fill and rim light, under `parent`.
## The lights are placed for an actor facing +Z, as the stage spawns it.
static func build(parent: Node3D, look: String = "neutral") -> Dictionary:
	var world := WorldEnvironment.new()
	world.name = "Environment"
	world.environment = environment(look)
	parent.add_child(world)
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_color = Color(1.0, 0.985, 0.97)
	key.light_energy = 0.95
	key.rotation_degrees = Vector3(-30.0, 32.0, 0.0)
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 12.0
	parent.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.name = "Fill"
	fill.light_color = Color(0.92, 0.94, 1.0)
	fill.light_energy = 0.25
	fill.rotation_degrees = Vector3(-10.0, -50.0, 0.0)
	parent.add_child(fill)
	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color(1.0, 0.96, 0.9)
	rim.light_energy = 0.55
	rim.rotation_degrees = Vector3(-28.0, 160.0, 0.0)
	parent.add_child(rim)
	var ground := MeshInstance3D.new()
	ground.name = "Floor"
	var plane := PlaneMesh.new()
	plane.size = Vector2(14.0, 14.0)
	ground.mesh = plane
	var material := StandardMaterial3D.new()
	material.albedo_color = FLOOR
	material.roughness = 0.95
	ground.material_override = material
	parent.add_child(ground)
	return {"environment": world, "key": key, "fill": fill, "rim": rim, "floor": ground}


## A real client actor of `sex`, posed for the stage: at the origin, facing
## +Z, its own processing off (clips are stepped by whoever drives the stage).
static func spawn(parent: Node, sex: String, appearance: Dictionary, visuals: Dictionary = {},
		quality: int = ActorRenderQuality.Quality.HIGH, actor_id: int = 9300) -> ReplicatedActor3D:
	var slug := "luminous_" + sex
	var config: Dictionary = ((data("models").get("models", {}) as Dictionary).get(slug, {})
		as Dictionary).duplicate(true)
	var actor := ReplicatedActor3D.new()
	parent.add_child(actor)
	var errors: Array = actor.configure({"actor_id": actor_id, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "", "appearance": appearance, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, data("animation"), data("equipment"))
	if not errors.is_empty():
		push_error("RL head stage: configure %s: %s" % [slug, str(errors)])
	actor.server_target = Vector3.ZERO
	actor.apply_render_quality(quality, false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI
	actor.set_process(false)
	actor.set_physics_process(false)
	for marker: Node in actor.find_children("MapDot*", "MeshInstance3D", true, false):
		(marker as MeshInstance3D).hide()
	if not visuals.is_empty():
		actor.apply_equipment_visuals(visuals)
	return actor


## Plays `clip_label` (a CLIPS key or a clip name) paused at `time` seconds.
static func pose(actor: ReplicatedActor3D, clip_label: String, time: float) -> void:
	var player := actor.animation_player
	if player == null:
		return
	var clip := str(CLIPS.get(clip_label, clip_label))
	if not player.has_animation(clip):
		return
	actor._advance_facing_offset(1.0)
	player.play(clip)
	player.seek(time, true)
	player.pause()


## The direction the face looks, flattened onto the ground.
static func face_forward(actor: ReplicatedActor3D) -> Vector3:
	var model := actor.get_node_or_null("NativeModel") as Node3D
	var forward := (model.global_basis * Vector3.BACK) if model != null else Vector3.BACK
	forward.y = 0.0
	return forward.normalized() if forward.length() > 0.001 else Vector3.BACK


## The Head bone's rest, in world space: the framing anchor.
static func head_rest(actor: ReplicatedActor3D) -> Transform3D:
	var skeleton := actor.get_skeleton()
	return skeleton.global_transform * skeleton.get_bone_global_rest(skeleton.find_bone("Head"))


## Puts `camera` at a named framing (VIEWS) of `actor`.
static func frame(camera: Camera3D, actor: ReplicatedActor3D, view: String) -> void:
	var spec: Dictionary = VIEWS.get(view, VIEWS["front"])
	var forward := face_forward(actor)
	var target := head_rest(actor).origin + Vector3.UP * float(spec["up"]) + forward * float(spec["forward"])
	var direction := forward.rotated(Vector3.UP, deg_to_rad(float(spec["yaw"])))
	direction = direction.rotated(direction.cross(Vector3.UP).normalized(), deg_to_rad(float(spec["pitch"])))
	camera.fov = float(spec["fov"])
	camera.global_position = target + direction * float(spec["distance"])
	camera.look_at(target, Vector3.UP)


## The head's landmarks (`rlHead.landmarks`, rest pose, model space) carried by
## the Head bone into the current pose, in world space.
static func landmarks(actor: ReplicatedActor3D, sex: String) -> Dictionary:
	var points: Dictionary = (RLHeadLibrary.head(sex).get("extras", {}) as Dictionary).get(
		"landmarks", {}) as Dictionary
	var skeleton := actor.get_skeleton()
	var head := skeleton.find_bone("Head")
	var carry := skeleton.global_transform * skeleton.get_bone_global_pose(head) \
		* skeleton.get_bone_global_rest(head).affine_inverse()
	var result := {}
	for name: Variant in points:
		var point: Variant = points[name]
		if point is Array and (point as Array).size() >= 3:
			result[str(name)] = carry * Vector3(float(point[0]), float(point[1]), float(point[2]))
	return result
