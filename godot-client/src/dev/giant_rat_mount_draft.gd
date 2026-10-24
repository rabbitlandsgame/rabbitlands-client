extends RefCounted
## Offline draft: use the production rider, tack, reins and cape components
## without registering an unapproved mount with the normal server catalogue.
const Visual := preload("res://src/mounts/mounted_player_visual.gd")
const PROFILE := "res://data/mounts/drafts/giant_rat.json"

static func add_model(models: Dictionary) -> void:
	models["giant_rat"] = {
		"scene":"res://assets/actors/native/mounts/giant_rat.glb",
		"animationLibrary":"res://assets/actors/native/mounts/giant_rat.glb",
		"animationMap":"res://data/animations/mounts/giant_rat.json",
		"import":{"scale":1.0,"rotationDegreesX":0,"rotationDegreesY":0,
			"rotationDegreesZ":0,"forwardAxisCorrectionDegreesY":180},
		"attachments":{"head":"head","body":"hips","neck":"head"}}

static func attach(actor: ReplicatedActor3D, models: Dictionary) -> Array[String]:
	add_model(models)
	var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PROFILE))
	var visual := Visual.new()
	actor.add_child(visual)
	var errors := visual.configure(actor, models, "giant_rat", profile)
	if not errors.is_empty():
		visual.restore()
		visual.free()
		return errors
	actor._mount_visual = visual
	visual.name = "GiantRatMountDraft"
	actor.mount_state = {"mode":"mounted","mount_id":"giant_rat","gait":"cruise"}
	visual.state = actor.mount_state
	actor.current_action = &"idle"
	return []

static func pace(actor: ReplicatedActor3D, gait: String) -> void:
	actor.mount_state["gait"] = gait
	actor._mount_visual.state = actor.mount_state

static func detach(actor: ReplicatedActor3D) -> void:
	var visual := actor._mount_visual
	actor._mount_visual = null
	actor.mount_state = {}
	if is_instance_valid(visual):
		visual.restore()
		visual.free()
