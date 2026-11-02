extends SceneTree
## Run in the isolated browser staging project with its editor cape extension.
const Warmup := preload("res://src/platform/browser_mount_warmup.gd")

class Visual extends Node3D:
	var owner_actor: ReplicatedActor3D
	var stepped := false
	func _step_visual(_delta: float) -> void:
		assert(owner_actor.is_drawn() and owner_actor.is_visible_in_tree())
		stepped = true

class Actor extends ReplicatedActor3D:
	var rig := Skeleton3D.new()
	func _ready() -> void: pass
	func get_skeleton() -> Skeleton3D: return rig
	func set_mount_state(state: Dictionary, _models: Dictionary) -> void:
		mount_state = state.duplicate(true)
		if is_instance_valid(_mount_visual): _mount_visual.free()
		_mount_visual = null
		if state.get("mode") == "mounted":
			var visual := Visual.new()
			visual.owner_actor = self
			add_child(visual)
			_mount_visual = visual

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	assert(ClassDB.class_exists("RabbitLandsCapeProjector"), "Requires the staged editor cape module")
	var actor := Actor.new()
	root.add_child(actor)
	actor.set_process(false)
	actor.visible = false
	actor.set_drawn(false)
	var original := {"mode":"on_foot", "selected_mount_id":"moor_pony", "owned_mount_ids":["moor_pony"]}
	var models := {"moor_pony":{}}
	actor.mount_state = original.duplicate(true)
	var warmup := Warmup.new()
	# An early incomplete server row must not consume the later valid warmup.
	assert(not warmup.advance(actor, models, {}))
	assert(warmup.advance(actor, models, original))
	assert(actor._mount_visual.stepped)
	assert(actor._mount_visual.process_mode == Node.PROCESS_MODE_DISABLED)
	# A server update received between the two frames wins over the old state.
	var latest := original.duplicate(true)
	latest["blocked_reason"] = "combat"
	assert(warmup.advance(actor, models, latest))
	assert(actor.mount_state == latest and actor._mount_visual == null)
	assert(not actor.visible and not actor.is_drawn())
	assert(not warmup.advance(actor, models, latest))
	# Cancellation restores the original state and both presentation gates.
	warmup = Warmup.new()
	assert(warmup.advance(actor, models, latest))
	warmup.cancel(models)
	assert(actor.mount_state == latest and actor._mount_visual == null)
	assert(not actor.visible and not actor.is_drawn())
	# An arrival already riding prepares that server-selected gait and coat.
	warmup = Warmup.new()
	var riding := latest.duplicate(true)
	riding.merge({"mode":"mounted", "mount_id":"moor_pony", "gait":"cruise", "coat_id":"test"}, true)
	actor.set_mount_state(riding, models)
	assert(warmup.advance(actor, models, riding))
	assert(actor.mount_state == riding and actor._mount_visual.stepped)
	assert(warmup.advance(actor, models, riding))
	assert(actor.mount_state == riding and actor._mount_visual != null)
	actor.rig.free()
	actor.free()
	print("browser mount warmup lifecycle passed")
	quit()
