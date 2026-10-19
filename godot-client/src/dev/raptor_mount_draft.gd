extends RefCounted
## Offline fitting only; this draft does not add an owned/live mount ID.
const Visual := preload("res://src/mounts/mounted_player_visual.gd")
const PROFILE := "res://data/mounts/drafts/jadefeather_raptor.json"

static func attach(actor: ReplicatedActor3D, models: Dictionary) -> Array[String]:
	actor.set_mount_state({}, models)
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(PROFILE))
	if not value is Dictionary:
		return ["Raptor riding draft profile missing"]
	var profile: Dictionary = value
	var visual := Visual.new()
	actor.add_child(visual)
	var errors := visual.configure(actor, models, "jadefeather_raptor", profile)
	if not errors.is_empty():
		visual.restore()
		visual.free()
		return errors
	var offset: Array = profile.visualOffsetMetres
	visual.pony.position = Vector3(offset[0],offset[1],offset[2])
	actor._mount_visual = visual
	visual.name = "RaptorMountDraft"
	actor.mount_state = {"mode":"mounted", "mount_id":"jadefeather_raptor", "gait":"cruise"}
	visual.state = actor.mount_state
	actor.current_action = &"idle"
	return []

static func pace(actor: ReplicatedActor3D, gait: String) -> void:
	actor.mount_state["gait"] = gait
	actor._mount_visual.state = actor.mount_state
	var profile: Dictionary = actor._mount_visual.profile
	profile.pelvisLeanDegrees = float(profile.gallopPelvisLeanDegrees if gait == "burst" else profile.normalPelvisLeanDegrees)
