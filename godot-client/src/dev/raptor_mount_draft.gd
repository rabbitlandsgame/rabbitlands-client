extends RefCounted
## Offline review helper using the same registered mount path as normal play.

static func attach(actor: ReplicatedActor3D, models: Dictionary) -> Array[String]:
	actor.set_mount_state({"mode":"mounted", "mount_id":"jadefeather_raptor", "gait":"cruise"}, models)
	if not is_instance_valid(actor._mount_visual):
		return ["Raptor mount could not be configured"]
	actor._mount_visual.name = "RaptorMountDraft"
	actor.current_action = &"idle"
	return []

static func pace(actor: ReplicatedActor3D, gait: String) -> void:
	actor.mount_state["gait"] = gait
	actor._mount_visual.state = actor.mount_state
