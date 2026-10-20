extends SceneTree
## Deliver real packets on separate frames, through AppState and Main's mount
## binding, so a transient on-foot frame cannot hide inside one packet batch.
const Op := EloriaProtocol.ServerMessage
var checks := 0
var failures := 0
var main: Node
var state: Node
var actor: ReplicatedActor3D
var mount_id := "moor_pony"
var gait := "cruise"

func _init() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

static func u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 255, (value >> 8) & 255])

func spawn_payload(owner := "Traveller") -> PackedByteArray:
	var payload := PackedByteArray()
	for value: int in [42, 3, 4, 0, 0]: payload.append_array(u16(value))
	payload.append_array(PackedByteArray([1, 0]))
	payload.append_array(u16(20))
	payload.append_array(u16(20))
	payload.append(1)
	payload.append_array(owner.to_ascii_buffer())
	payload.append(0)
	return payload

func snapshot(map_name: String, mode := "mounted", owner := "Traveller") -> PackedByteArray:
	var row := {"schema_version": 1, "actor_id": 42, "mode": mode, "gait": gait if mode == "mounted" else "on_foot",
		"mount_id": mount_id if mode == "mounted" else "", "selected_mount_id": mount_id,
		"step_us": 100000 if gait == "burst" else 133333, "endurance_ms": 5000,
		"summon_remaining_ms": 0, "combat_remaining_ms": 0, "can_summon": false,
		"blocked_reason": "", "map": map_name, "owner": owner}
	return JSON.stringify({"schema_version": 1, "map": map_name, "states": [row]}).to_utf8_buffer()

func deliver(op: int, payload: PackedByteArray) -> void:
	state.call("_on_packet", op, payload)
	main.call("_apply_actor_mount", 42)
	await process_frame

func same_mount(visual_id: int, message: String) -> void:
	check(is_instance_valid(actor._mount_visual) and actor._mount_visual.get_instance_id() == visual_id, mount_id + ": " + message)
	check(actor.mount_state.get("gait") == gait, "crossing preserves gait")
	check(actor.mount_state.get("endurance_ms") == 5000, "crossing preserves endurance")

func run() -> void:
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	state = root.get_node("AppState")
	state.set("authenticated", false) # Keep terrain loading out of this packet-order regression.
	var models: Dictionary = main.get("models")
	var config: Dictionary = models.luminous_male
	actor = ReplicatedActor3D.new()
	root.add_child(actor)
	check(actor.configure({"actor_id": 42, "x": 3, "y": 4, "rotation": 0,
		"kind": 1, "name": "Traveller"}, CoordinateAdapter.new({}), config,
		JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))).is_empty(), "rider loads")
	actor.set_process(false)
	actor.set_physics_process(false)
	(main.get("actor_nodes") as Dictionary)[42] = actor
	for selected: String in preload("res://src/mounts/mount_profiles.gd").PATHS:
		mount_id = selected
		for pace: String in ["cruise", "burst"]:
			gait = pace
			for mount_first: bool in [false, true]:
				await deliver(Op.KILL_ALL_ACTORS, PackedByteArray())
				await deliver(Op.CHANGE_MAP, "landfall".to_ascii_buffer() + PackedByteArray([0]))
				await deliver(Op.ADD_NEW_ACTOR, spawn_payload())
				await deliver(Op.ELORIA_MOUNT_STATES, snapshot("landfall"))
				var visual: Node3D = actor._mount_visual
				check(is_instance_valid(visual), "mount loads")
				if not is_instance_valid(visual): continue
				visual.set_process(false)
				var visual_id := visual.get_instance_id()
				# Back-to-back crossings must not cancel a still-pending handoff.
				for destination: String in ["warrenmead", "landfall", "warrenmead"]:
					await deliver(Op.CHANGE_MAP, destination.to_ascii_buffer() + PackedByteArray([0]))
					same_mount(visual_id, "map notification keeps the same visual")
					await deliver(Op.YOU_ARE, u16(42))
					same_mount(visual_id, "local actor refresh keeps the same visual")
					if mount_first:
						await deliver(Op.ELORIA_MOUNT_STATES, snapshot(destination))
					else:
						await deliver(Op.ADD_NEW_ACTOR, spawn_payload())
						same_mount(visual_id, "actor-first arrival keeps the same visual")
					if mount_first:
						same_mount(visual_id, "mount-first arrival keeps the same visual")
						await deliver(Op.ADD_NEW_ACTOR, spawn_payload())
					else:
						await deliver(Op.ELORIA_MOUNT_STATES, snapshot(destination))
					same_mount(visual_id, "completed arrival keeps the same visual")
				await deliver(Op.CHANGE_MAP, "landfall".to_ascii_buffer() + PackedByteArray([0]))
				await deliver(Op.ELORIA_MOUNT_STATES, snapshot("landfall", "on_foot"))
				check(not is_instance_valid(actor._mount_visual), "authoritative dismount wins during handoff")
	# Clear/removal/logout and recycled actor IDs cannot inherit a pending mount.
	for ending: int in [Op.REMOVE_ACTOR, Op.KILL_ALL_ACTORS, -1, Op.ADD_NEW_ACTOR]:
		await deliver(Op.KILL_ALL_ACTORS, PackedByteArray())
		await deliver(Op.CHANGE_MAP, "landfall".to_ascii_buffer() + PackedByteArray([0]))
		await deliver(Op.ADD_NEW_ACTOR, spawn_payload())
		await deliver(Op.ELORIA_MOUNT_STATES, snapshot("landfall"))
		await deliver(Op.CHANGE_MAP, "warrenmead".to_ascii_buffer() + PackedByteArray([0]))
		if ending == -1:
			state.call("_on_connection_state_changed", "disconnected")
			main.call("_apply_actor_mount", 42)
		else:
			await deliver(ending, spawn_payload("SomeoneElse") if ending == Op.ADD_NEW_ACTOR else u16(42))
		check(not is_instance_valid(actor._mount_visual), "actor identity/lifetime ends the handoff")
		await deliver(Op.ADD_NEW_ACTOR, spawn_payload("SomeoneElse"))
		check(not is_instance_valid(actor._mount_visual), "recycled ID never inherits a mount")
	# New mount states can arrive before a teleport's first actor is spawned.
	await deliver(Op.KILL_ALL_ACTORS, PackedByteArray())
	await deliver(Op.CHANGE_MAP, "landfall".to_ascii_buffer() + PackedByteArray([0]))
	await deliver(Op.ELORIA_MOUNT_STATES, snapshot("landfall"))
	await deliver(Op.ADD_NEW_ACTOR, spawn_payload())
	check(is_instance_valid(actor._mount_visual), "teleport arrival binds already-received mount state")
	await deliver(Op.CHANGE_MAP, "warrenmead".to_ascii_buffer() + PackedByteArray([0]))
	await deliver(Op.ELORIA_MOUNT_STATES, JSON.stringify({"schema_version": 1,
		"map": "warrenmead", "states": []}).to_utf8_buffer())
	check(not is_instance_valid(actor._mount_visual), "authoritative empty snapshot ends the handoff")
	(main.get("actor_nodes") as Dictionary).clear()
	actor.free()
	main.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOUNT_MAP_HANDOFF_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
