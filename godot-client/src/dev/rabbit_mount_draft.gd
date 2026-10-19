extends RefCounted
## Offline fitting only; this draft does not add an owned/live mount ID.
const Visual := preload("res://src/mounts/mounted_player_visual.gd")
const PROFILE := "res://data/mounts/drafts/meadow_rabbit.json"

static func attach(actor: ReplicatedActor3D, models: Dictionary) -> Array[String]:
	actor.set_mount_state({}, models)
	var visual := Visual.new()
	actor.add_child(visual)
	var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PROFILE))
	var errors := visual.configure(actor, models, "rabbit", profile)
	if not errors.is_empty():
		visual.restore()
		visual.free()
		return errors
	actor._mount_visual = visual
	visual.name = "RabbitMountDraft"
	actor.mount_state = {"mode":"mounted", "mount_id":"rabbit", "gait":"walk"}
	visual.state = actor.mount_state
	actor.current_action = &"idle"
	return []

static func pace(actor: ReplicatedActor3D, gait: String) -> void:
	actor.mount_state["gait"] = gait
	actor._mount_visual.state = actor.mount_state
