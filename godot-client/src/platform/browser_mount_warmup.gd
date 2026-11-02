extends RefCounted
## Prepare the selected mount while the arrival curtain still covers the scene.
## Only presentation changes: no mount request or authoritative state is sent.
const Profiles := preload("res://src/mounts/mount_profiles.gd")
const Diagnostics := preload("res://src/diagnostics/client_diagnostics.gd")
var _actor: WeakRef
var _original: Dictionary = {}
var _completed := 0
var _was_drawn := true
var _was_visible := true

func _restore(actor: ReplicatedActor3D, state: Dictionary, models: Dictionary) -> void:
	var visual := actor.get("_mount_visual") as Node
	if is_instance_valid(visual): visual.process_mode = Node.PROCESS_MODE_INHERIT
	actor.set_mount_state(state, models)
	actor.set_drawn(_was_drawn)
	actor.visible = _was_visible

func advance(actor: ReplicatedActor3D, models: Dictionary, server_state: Dictionary) -> bool:
	if _actor != null:
		var previous := _actor.get_ref() as ReplicatedActor3D
		if is_instance_valid(previous):
			_restore(previous, server_state if previous == actor else _original, models)
			Diagnostics.record("browser_mount_warmup_finished", {"mount": str(_original.get("selected_mount_id", ""))})
		if previous == actor: _completed = actor.get_instance_id()
		_actor = null
		_original = {}
		if previous == actor: return true
	if _completed == actor.get_instance_id() or actor.get_skeleton() == null \
			or not ClassDB.class_exists("RabbitLandsCapeProjector"):
		return false
	var mounted: bool = server_state.get("mode") == "mounted"
	var mount_id := str(server_state.get("mount_id" if mounted else "selected_mount_id", ""))
	if not Profiles.supports(mount_id) \
			or not models.has(mount_id) or mount_id not in server_state.get("owned_mount_ids", []):
		return false
	_original = actor.mount_state.duplicate(true)
	_was_drawn = actor.is_drawn()
	_was_visible = actor.visible
	# Arrival range/visibility gates normally suppress this work. The opaque
	# curtain owns input and presentation throughout both preparation frames.
	actor.visible = true
	actor.set_drawn(true)
	var started := Time.get_ticks_usec()
	var preparation := server_state.duplicate(true)
	preparation.merge({"mode":"mounted", "mount_id":mount_id}, true)
	if not mounted: preparation["gait"] = "walk"
	actor.set_mount_state(preparation, models)
	var visual := actor.get("_mount_visual") as Node
	if not is_instance_valid(visual):
		_restore(actor, _original, models)
		_original = {}
		return false
	_actor = weakref(actor)
	_completed = actor.get_instance_id()
	# Render one posed frame beneath the curtain to prepare its shader too.
	visual.process_mode = Node.PROCESS_MODE_DISABLED
	visual.call("_step_visual", 1.0 / 30.0)
	Diagnostics.record("browser_mount_warmup_started", {"mount": mount_id,
		"msec": (Time.get_ticks_usec() - started) / 1000.0})
	return true

func cancel(models: Dictionary) -> void:
	var actor := _actor.get_ref() as ReplicatedActor3D if _actor != null else null
	if is_instance_valid(actor):
		_restore(actor, _original, models)
	_actor = null
	_original = {}
