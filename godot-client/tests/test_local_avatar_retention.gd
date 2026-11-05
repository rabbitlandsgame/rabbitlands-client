extends SceneTree
## AW-02: the player's own body is kept across a map change that is not a
## seamless crossing and worn again for the ADD that follows.
##
## On Main's real pipeline (main.tscn, a recorded transport, a finite floor),
## with a real Human built the way Main builds the player:
##   * KILL_ALL_ACTORS (stale removal) and CHANGE_MAP's teardown both hold the
##     player's body: off the table, hidden, paused, not pickable, still in the
##     tree, the old map's presentation state dropped;
##   * the YOU_ARE + ADD that follows adopts the same node instance on the new
##     map: metres per tile, footprint, position and tier are the new map's,
##     no build is recorded, the cape solver restarts at the new place, and a
##     changed wardrobe or appearance is applied on the kept body;
##   * the adopted body matches a freshly built one (visible meshes, their
##     geometry, presentation state);
##   * another person, another model, the 15 s expiry, a changed player id,
##     session end and client close free it; a death, a staged scene, the
##     intro, a held portrait and a seamless crossing are not held; remote
##     bodies are never held.
## The LocalAvatarHold bookkeeping is checked on its own first.
##
##   Godot --headless --path godot-client --script res://tests/test_local_avatar_retention.gd

const HOLD := preload("res://src/actors/local_avatar_hold.gd")
const MEDIUM := ActorRenderQuality.Quality.MEDIUM
const LOCAL := 1
const CAPE_LOADOUT := {"0": 114, "1": 106, "2": 1, "3": 117, "4": 171, "5": 184, "6": 192}

var checks := 0
var failures := 0
var main: Node
var app: Node
var network: Node
## Main's `_spawn_actor` time for the last build or adoption (headless CPU).
var last_spawn_usec := 0


func _init() -> void:
	run.call_deferred()


func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("local avatar retention: " + message)


func run() -> void:
	create_timer(300).timeout.connect(func() -> void:
		push_error("local avatar retention timed out")
		quit(1))
	_check_hold_bookkeeping()
	await _setup_main()
	var old_quality := LookProfile.player_quality()
	LookProfile.set_player_quality(MEDIUM)
	await _check_kill_all_then_add()
	await _check_teardown_then_changed_wardrobe()
	await _check_matches_fresh_build()
	await _check_mounted()
	await _check_rl_hair_springs()
	await _check_harvest_glitter()
	await _check_mismatches()
	await _check_releases()
	await _check_refusals()
	await _check_seamless_and_remote()
	await _check_session_end()
	LookProfile.set_player_quality(old_quality)
	await _cleanup()
	print("local avatar retention: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)


# --- LocalAvatarHold on its own ---------------------------------------------

func _check_hold_bookkeeping() -> void:
	var hold = HOLD.new()
	var body := StaticBody3D.new()
	body.collision_layer = 2
	root.add_child(body)
	expect(not hold.holding() and hold.held_id() == -1 and hold.node() == null,
		"an empty hold holds nothing")
	expect(hold.hold(body, 7, "k", "m", 1000) and hold.holding() and hold.held_id() == 7
		and not body.visible and body.process_mode == Node.PROCESS_MODE_DISABLED
		and body.collision_layer == 0 and body.get_parent() == root,
		"a held body is hidden, not processing and not pickable, and stays in the tree")
	expect(hold.matches(7, "k", "m") and not hold.matches(8, "k", "m")
		and not hold.matches(7, "other", "m") and not hold.matches(7, "k", "other"),
		"only the same actor id, identity and model match")
	expect(not hold.expire(1000 + HOLD.HOLD_MSEC - 1, 7), "it waits HOLD_MSEC for its ADD")
	expect(hold.take(7, "k", "m") == body and not hold.holding() and body.visible
		and body.process_mode == Node.PROCESS_MODE_INHERIT and hold.adoptions == 1
		and not body.is_queued_for_deletion(),
		"take gives the same body back, visible and processing")
	expect(hold.take(7, "k", "m") == null, "nothing is taken twice")
	expect(hold.hold(body, 7, "k", "m", 2000) and hold.take(7, "k", "other") == null
		and body.is_queued_for_deletion() and int(hold.releases.get("mismatch", 0)) == 1,
		"a mismatching ADD frees the held body")
	var second := Node3D.new()
	root.add_child(second)
	var third := Node3D.new()
	root.add_child(third)
	hold.hold(second, 7, "k", "m", 3000)
	expect(hold.expire(3000 + HOLD.HOLD_MSEC, 7) and second.is_queued_for_deletion()
		and int(hold.releases.get("expired", 0)) == 1, "HOLD_MSEC later it is freed")
	hold.hold(third, 7, "k", "m", 4000)
	expect(hold.expire(4001, 9) and third.is_queued_for_deletion()
		and int(hold.releases.get("actor_changed", 0)) == 1,
		"a different player id frees it at once")
	var fourth := Node3D.new()
	root.add_child(fourth)
	var fifth := Node3D.new()
	root.add_child(fifth)
	hold.hold(fourth, 7, "k", "m", 5000)
	hold.hold(fifth, 7, "k", "m", 5000)
	expect(fourth.is_queued_for_deletion() and hold.node() == fifth
		and int(hold.releases.get("replaced", 0)) == 1, "one player: a second hold replaces the first")
	hold.release("session")
	expect(fifth.is_queued_for_deletion() and not hold.holding()
		and int(hold.releases.get("session", 0)) == 1, "release frees it and counts the reason")
	hold.refuse("dead")
	var snapshot: Dictionary = hold.snapshot(6000)
	expect(int(snapshot.holds) == 6 and int(snapshot.adoptions) == 1 and not bool(snapshot.held)
		and int((snapshot.refusals as Dictionary).get("dead", 0)) == 1,
		"the snapshot counts holds, adoptions, releases and refusals: %s" % snapshot)
	var gone := Node3D.new()
	root.add_child(gone)
	hold.hold(gone, 7, "k", "m", 7000)
	gone.free()
	expect(hold.take(7, "k", "m") == null and not hold.holding()
		and int(hold.releases.get("lost", 0)) == 1, "a body freed by someone else is forgotten")
	expect(not hold.hold(null, 7, "k", "m", 0), "nothing to hold is not held")


# --- Main ---------------------------------------------------------------------

func _setup_main() -> void:
	root.size = Vector2i(1280, 720)
	app = root.get_node("AppState")
	network = root.get_node("Network")
	# Actual Network validation and Main's signal wiring; only the final
	# socket write is replaced, so this process cannot contact a service.
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the isolated final-write recorder compiles")
	network.set_script(recorder)
	network.call("block_for_hud_preview")
	app.authenticated = false
	app.current_map = ""
	app.actors = {}
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.set_physics_process(false)
	await process_frame
	var floor := StaticBody3D.new()
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	floor.collision_mask = 0
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600, 0.1, 600)
	collision.shape = box
	collision.position.y = -0.05
	floor.add_child(collision)
	main.world_root.add_child(floor)
	await physics_frame
	app.authenticated = true
	app.death = {}
	app.local_actor_id = LOCAL
	app.selected_actor_id = -1
	app.combat_state = {}
	app.campaign = {}
	app.current_map = "landfall"
	main.adapter = CoordinateAdapter.new({"walkingHeight": 0.025, "invertServerY": true})


func _record(x: int, y: int, equipment: Dictionary = CAPE_LOADOUT, name := "Holder",
		actor_type := 1) -> Dictionary:
	return {"actor_id": LOCAL, "actor_type": actor_type, "kind": 1, "name": name,
		"x": x, "y": y, "rotation": 0, "health": 20, "max_health": 20, "alive": true,
		"appearance": {"skin": 2, "hair": AppearanceVariants.pack_hair(2, 0)},
		"equipment_visuals": equipment.duplicate(), "equipment_fallback_parts": []}


func _local() -> ReplicatedActor3D:
	var value: Variant = main.actor_nodes.get(LOCAL)
	return value as ReplicatedActor3D if is_instance_valid(value) else null


func _builds() -> int:
	var budget: Dictionary = main.call("actor_creation_budget_snapshot")
	return int((budget.totals as Dictionary).builds)


func _hold_snapshot() -> Dictionary:
	return main.get("_local_avatar_hold").snapshot()


## The player built fresh by Main from `record`, on the current adapter.
func _spawn_fresh(record: Dictionary) -> ReplicatedActor3D:
	if _local() != null:
		await _discard_local()
	app.actors = {LOCAL: record}
	# Each build in its own creation frame: under this SceneTree script the
	# process frame count Main's per-frame allowance reads does not advance.
	main.set("_actor_creation_frame", -1)
	var started := Time.get_ticks_usec()
	var built := bool(main.call("_spawn_actor", LOCAL, true))
	last_spawn_usec = Time.get_ticks_usec() - started
	expect(built, "Main builds the player")
	await physics_frame
	return _local()


## KILL_ALL_ACTORS ahead of a map change: AppState empties its table and the
## next world sync removes what it no longer has.
func _kill_all() -> void:
	app.actors = {}
	app.actor_roster_generation += 1
	main.call("_remove_stale_actor_nodes", null)


## Main's CHANGE_MAP teardown (`_load_server_map`), with the record still there.
func _change_map_teardown() -> void:
	main.set("_continuous_map_handoff", false)
	main.set("_retained_traveller", -1)
	main.call("_clear_actor_nodes_for_map_change")


## YOU_ARE (the same id: it is per character) and the player's ADD on a map
## of `metres` per tile.
## `probe` runs right after the ADD, before any frame has stepped the body.
func _arrive(record: Dictionary, metres := 1.0, probe := Callable()) -> ReplicatedActor3D:
	main.adapter = CoordinateAdapter.new({"walkingHeight": 0.025, "invertServerY": true,
		"metresPerTile": metres})
	app.local_actor_id = LOCAL
	app.actors = {LOCAL: record}
	main.set("_actor_creation_frame", -1)
	var started := Time.get_ticks_usec()
	var presented := bool(main.call("_spawn_actor", LOCAL, true))
	last_spawn_usec = Time.get_ticks_usec() - started
	expect(presented, "Main presents the arriving player")
	if probe.is_valid():
		probe.call(_local())
	await physics_frame
	return _local()


func _dirty(actor: ReplicatedActor3D) -> void:
	# What a body walking through a door carries from the map it leaves.
	actor.play_action(&"walk")
	actor.set("_pace_histories", {1: PackedFloat32Array([0.31, 0.29])})
	actor.set("_segment_duration", 0.4)
	actor.set("_schedule_due", 12.5)
	actor.set("_jitter_allowance", 0.2)
	actor.set("_last_command_sequence", 77)
	actor.set("_in_combat", true)
	actor.predict_turn(PI / 4.0)
	actor.set_selected(true)
	actor.set_combat_target(true)
	actor.show_speech_bubble("leaving", 30000)
	actor.set("_surface_target_up", Vector3(0.2, 1.0, 0.0).normalized())


func _check_kill_all_then_add() -> void:
	var actor := await _spawn_fresh(_record(3, 4))
	expect(actor != null and not actor.is_model_deferred() and str(actor.get_meta(&"model_id", "")) == "luminous_male",
		"the player is built with its model id recorded")
	if actor == null:
		return
	await physics_frame
	_dirty(actor)
	# Shrunk as on one of the small lesson maps (main.gd _fit_lantern_map_marker).
	var dot := actor.get_node_or_null("MapDot") as Node3D
	if dot != null:
		dot.scale = Vector3(0.18, 1.0, 0.18)
	var bodies_before: int = int(main.get("_built_bodies"))
	var builds_before := _builds()
	var old_position := actor.global_position
	_kill_all()
	var held: Dictionary = _hold_snapshot()
	expect(not main.actor_nodes.has(LOCAL) and is_instance_valid(actor) and not actor.is_queued_for_deletion()
		and actor.get_parent() == main.world_root and bool(held.held)
		and main.get("_local_avatar_hold").held_id() == LOCAL and not held.has("actorId"),
		"KILL_ALL_ACTORS holds the player's body off the table, still under world_root "
		+ "(its actor id stays out of the diagnostics row)")
	expect(not actor.visible and actor.process_mode == Node.PROCESS_MODE_DISABLED and actor.collision_layer == 0
		and actor.animation_tier() == AnimationGate.Tier.PAUSED,
		"the held body is hidden, paused and not pickable")
	expect((actor.get("_pace_histories") as Dictionary).is_empty() and float(actor.get("_segment_duration")) == 0.0
		and float(actor.get("_schedule_due")) < 0.0 and float(actor.get("_jitter_allowance")) == 0.0
		and int(actor.get("_last_command_sequence")) == -1 and not bool(actor.get("_in_combat"))
		and not bool(actor.get("_predicted_turn_pending")) and not bool(actor.get("_selected"))
		and not bool(actor.get("_combat_target")) and actor.current_action == &"idle"
		and (actor.get("_surface_target_up") as Vector3) == Vector3.UP and bool(actor.get("_snap_pending")),
		"the old map's motion, prediction, selection, target, lean and clip are dropped")
	var bubble := actor.get_node_or_null("SpeechBubble") as Node3D
	expect(bubble == null or not bubble.visible, "the speech bubble from the old map is gone")
	expect(int(main.get("_built_bodies")) == bodies_before - 1, "the hold takes the body out of the built count")
	expect((main.call("_kept_body_ids") as Array).has(LOCAL), "the browser asset prune keeps the held body's files")
	# CHANGE_MAP's teardown finds nothing more to free; YOU_ARE then the ADD.
	_change_map_teardown()
	var cloth := actor.find_child("CapeCloth", true, false)
	var cape := {}
	var arrived := await _arrive(_record(40, 52), 2.0, func(body: ReplicatedActor3D) -> void:
		var skeleton := body.get_skeleton() if body != null else null
		if cloth != null and skeleton != null and cloth.get("_last_translation") is Vector3:
			cape["solver"] = cloth.get("_last_translation")
			cape["body"] = skeleton.global_transform.origin)
	expect(arrived == actor, "the ADD after YOU_ARE adopts the same node instance")
	expect(is_equal_approx(float(actor.get("_metres_per_tile")), 2.0)
		and actor.server_target.x == main.adapter.footprint_center(40, 52, Vector2i.ONE).x
		and actor.global_position.distance_to(old_position) > 50.0,
		"the adopted body stands on the new map's tile at its metres per tile")
	expect(actor.visible and actor.collision_layer == 2 and actor.process_mode == Node.PROCESS_MODE_INHERIT
		and actor.animation_tier() == AnimationGate.Tier.FULL and actor.is_drawn(),
		"it is visible, pickable, processing and at full rate")
	expect(_builds() == builds_before, "no actor build is recorded for the adoption")
	expect(int(main.get("_built_bodies")) == bodies_before, "the adoption counts the body as built again")
	expect(main.get("_grounded_actors").has(LOCAL), "the adopted body is put on the new ground")
	expect(dot != null and dot.scale == Vector3.ONE, "the map dot is full size again off the lesson maps")
	var after: Dictionary = _hold_snapshot()
	expect(not bool(after.held) and int(after.adoptions) == 1 and int(after.lastWaitMsec) >= 0,
		"the hold is empty again and counts one adoption")
	if cape.has("solver"):
		expect((cape.solver as Vector3).distance_to(cape.body as Vector3) < 0.01,
			"the cape solver restarted where the body now stands, before any step: %s" % cape)
	else:
		print("NOTE: cape solver state not readable; cape reset not checked")


func _check_teardown_then_changed_wardrobe() -> void:
	var actor := _local()
	expect(actor != null, "the player from the previous case is on the table")
	if actor == null:
		return
	var builds_before := _builds()
	_change_map_teardown()
	expect(not main.actor_nodes.has(LOCAL) and bool(_hold_snapshot().held) and not actor.is_queued_for_deletion(),
		"CHANGE_MAP's teardown holds the player's body")
	_kill_all()
	expect(bool(_hold_snapshot().held), "KILL_ALL_ACTORS after the teardown keeps the hold")
	# rebind_map reads the map and record as configure does.
	var odd := CoordinateAdapter.new({"walkingHeight": 7.5, "metresPerTile": 3.0, "invertServerY": true})
	actor.rebind_map(odd, {"x": 2, "y": 3, "rotation": 2, "scale": 1.5, "footprint": Vector2i(2, 2)})
	expect(actor.server_target == odd.footprint_center(2, 3, Vector2i(2, 2)) and actor.position == actor.server_target
		and is_equal_approx(actor.server_target.y, 7.5) and actor.footprint == Vector2i(2, 2)
		and is_equal_approx(actor.server_scale, 1.5) and is_equal_approx(float(actor.get("_metres_per_tile")), 3.0)
		and is_equal_approx(actor.rotation.y, odd.rotation_to_godot(2)),
		"rebind_map takes the tile, the map's own height, the facing, footprint, scale and metres per tile")
	# The gear changed while the map loaded: no cape, other boots.
	var changed := CAPE_LOADOUT.duplicate()
	changed.erase("5")
	changed["6"] = 205
	var record := _record(8, 9, changed)
	record.appearance = {"skin": 4, "hair": AppearanceVariants.pack_hair(3, 1)}
	var arrived := await _arrive(record, 1.0)
	var diagnostics: Dictionary = arrived.equipment_diagnostics() if arrived != null else {}
	expect(arrived == actor and _builds() == builds_before, "the same body is adopted without a build")
	expect(diagnostics.get("visuals", {}) == _int_keys(changed),
		"the changed wardrobe is applied on the kept body: %s" % diagnostics.get("visuals", {}))
	expect(arrived != null and arrived.get("_appearance") == record.appearance,
		"the changed appearance is applied on the kept body")
	expect(arrived != null and is_equal_approx(float(arrived.get("_metres_per_tile")), 1.0)
		and arrived.footprint == Vector2i.ONE and is_equal_approx(arrived.server_scale, 1.0),
		"the metres per tile follow the map again, and a record without footprint or scale gets 1")


static func _int_keys(visuals: Dictionary) -> Dictionary:
	var result := {}
	for key: Variant in visuals:
		result[int(key)] = int(visuals[key])
	return result


## Visible mesh paths of the body, their geometry and render state.
func _picture(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		if not instance.is_visible_in_tree() or instance.is_queued_for_deletion():
			continue
		result[str(actor.get_path_to(instance))] = {"mesh": _mesh_hash(instance.mesh),
			"shadow": instance.cast_shadow, "layers": instance.layers,
			"override": instance.material_override != null}
	return result


static func _mesh_hash(mesh: Mesh) -> String:
	if mesh == null:
		return ""
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	for surface: int in mesh.get_surface_count():
		var bytes := var_to_bytes(mesh.surface_get_arrays(surface))
		if not bytes.is_empty():
			context.update(bytes)
	return context.finish().hex_encode().left(20)


func _state(actor: ReplicatedActor3D) -> Dictionary:
	return {"position": actor.global_position.snapped(Vector3.ONE * 0.001),
		"yaw": snappedf(actor.rotation.y, 0.0001), "target": actor.server_target.snapped(Vector3.ONE * 0.001),
		"action": actor.current_action, "segment": actor.get("_segment_duration"),
		"paces": actor.get("_pace_histories"), "metres": actor.get("_metres_per_tile"),
		"footprint": actor.footprint, "scale": actor.server_scale, "tier": actor.animation_tier(),
		"visible": actor.visible, "collision": actor.collision_layer, "drawn": actor.is_drawn(),
		"selected": actor.get("_selected"), "combat": actor.get("_in_combat"),
		"quality": actor.render_quality(), "local": actor.render_quality_is_local(),
		"visuals": actor.equipment_diagnostics().visuals}


## Takes the player's node off the table and frees it, outside Main's paths.
func _gone(node: Variant) -> bool:
	return not is_instance_valid(node) or (node as Node).is_queued_for_deletion()


func _discard_local() -> void:
	var actor := _local()
	main.actor_nodes.erase(LOCAL)
	if actor != null:
		actor.queue_free()
	await process_frame


func _check_matches_fresh_build() -> void:
	var record := _record(12, 14)
	# Built with this wardrobe on one map, held and adopted on another ...
	await _discard_local()
	var first := await _spawn_fresh(_record(3, 3))
	for _frame: int in 3:
		await physics_frame
		await process_frame
	_dirty(first)
	_kill_all()
	var adopted := await _arrive(record.duplicate(true), 1.0)
	expect(adopted == first, "the body built on the first map is the one adopted")
	expect(adopted != null, "the kept body is adopted for the comparison")
	if adopted == null:
		return
	for _frame: int in 3:
		await physics_frame
		await process_frame
	var adopt_usec := last_spawn_usec
	var kept_state := _state(adopted)
	var kept_picture := _picture(adopted)
	# ... against the same record built fresh in its place.
	await _discard_local()
	var fresh := await _spawn_fresh(record.duplicate(true))
	# Measured, not asserted: what the adoption saves against a warm rebuild.
	print("TIMING local avatar: adopt %.2f ms, warm rebuild %.2f ms (headless)"
		% [adopt_usec / 1000.0, last_spawn_usec / 1000.0])
	for _frame: int in 3:
		await physics_frame
		await process_frame
	var fresh_state := _state(fresh)
	var fresh_picture := _picture(fresh)
	expect(kept_state == fresh_state, "the adopted body's presentation state is a fresh build's:\n kept  %s\n fresh %s"
		% [kept_state, fresh_state])
	expect(kept_picture.keys() == fresh_picture.keys(), "the same meshes are visible on both: kept %d, fresh %d"
		% [kept_picture.size(), fresh_picture.size()])
	var same_geometry := true
	for path: String in fresh_picture:
		if kept_picture.get(path) != fresh_picture[path]:
			same_geometry = false
			print("differs: ", path, " kept ", kept_picture.get(path), " fresh ", fresh_picture[path])
	expect(same_geometry and not fresh_picture.is_empty(), "every visible mesh has the same geometry and render state")


func _mount_row(mode := "mounted") -> Dictionary:
	return {"schema_version": 1, "actor_id": LOCAL, "mode": mode, "gait": "cruise",
		"mount_id": "moor_pony" if mode == "mounted" else "", "selected_mount_id": "moor_pony",
		"step_us": 133333, "endurance_ms": 5000, "summon_remaining_ms": 0, "combat_remaining_ms": 0,
		"can_summon": false, "blocked_reason": "", "map": "", "owner": "Holder"}


## A mounted teleport: the rider is held with its mount and adopted on it.
func _check_mounted() -> void:
	var actor := await _spawn_fresh(_record(10, 10))
	app.actor_mounts = {LOCAL: _mount_row()}
	main.call("_apply_actor_mount", LOCAL)
	await process_frame
	var visual: Variant = actor.get("_mount_visual")
	expect(is_instance_valid(visual), "the player rides (fixture)")
	if not is_instance_valid(visual):
		app.actor_mounts = {}
		return
	var visual_id := (visual as Node).get_instance_id()
	_kill_all()
	expect(bool(_hold_snapshot().held) and bool((visual as Node).get("_parked")),
		"a rider is held with its mount parked")
	var arrived := await _arrive(_record(30, 31), 1.0)
	var after: Variant = arrived.get("_mount_visual") if arrived != null else null
	expect(arrived == actor and is_instance_valid(after) and (after as Node).get_instance_id() == visual_id
		and not bool((after as Node).get("_parked")) and arrived.visible
		and arrived.server_target.x == main.adapter.footprint_center(30, 31, Vector2i.ONE).x,
		"the rider is adopted on the same mount, unparked, on the new tile")
	app.actor_mounts = {}
	main.call("_apply_actor_mount", LOCAL)
	await process_frame
	expect(arrived != null and not is_instance_valid(arrived.get("_mount_visual")), "fixture: on foot again")


## The camera close to the player, as the follow camera zoomed in has it, so
## the RL hair springs run (RLHairMotion.RANGE_METRES), for `frames` frames.
func _near_camera_frames(actor: ReplicatedActor3D, frames: int) -> void:
	var rig: IsometricCameraController = main.camera_rig
	rig.distance = 3.0
	for _frame: int in frames:
		if is_instance_valid(actor):
			rig.set_focus(actor.global_position)
		await process_frame


## Starts recording, at every step of `motion`'s springs, how far its furthest
## hair bone is from rest, in millimetres (a modifier's pose holds only while
## its skeleton updates, so it is read when the simulator reports).
## `_stop_hair_record` returns the series.
func _start_hair_record(motion: RLHairMotion) -> Array:
	var series: Array = []
	var skeleton: Skeleton3D = motion._skeleton
	var probe := func() -> void:
		var here := 0.0
		for bone: int in skeleton.get_bone_count():
			here = maxf(here, skeleton.get_bone_global_pose(bone).origin.distance_to(
				skeleton.get_bone_global_rest(bone).origin))
		series.append(snappedf(here * 1000.0, 0.1))
	motion._simulator.modification_processed.connect(probe)
	return [series, probe]


func _stop_hair_record(motion: RLHairMotion, recording: Array) -> Array:
	motion._simulator.modification_processed.disconnect(recording[1] as Callable)
	return recording[0] as Array


## The largest of the first `count` values of `series` (0 when it is empty).
static func _first_peak(series: Array, count: int) -> float:
	var peak := 0.0
	for index: int in mini(count, series.size()):
		peak = maxf(peak, float(series[index]))
	return peak


func _hair_motion_of(actor: ReplicatedActor3D) -> RLHairMotion:
	var rig: RLHeadRig = actor.hair_module_rig() if actor != null else null
	return rig.hair_motion() if rig != null else null


## High with an RL head: the hair springs, like the cape, work in world space,
## so a kept body's locks wake from rest at the new place, as a new body's do,
## rather than swinging in from where the body stood on the old map.
func _check_rl_hair_springs() -> void:
	var camera_distance: float = main.camera_rig.distance
	LookProfile.set_player_quality(ActorRenderQuality.Quality.HIGH)
	var record := _record(20, 20, {})
	# Rowan's shag (PC/3 hair module 2) is a hairstyle that declares springs.
	record.appearance = HumanPortraitPresets.appearance("Rowan").merged({"hair_module": 2}, true)
	var actor := await _spawn_fresh(record)
	var motion := _hair_motion_of(actor)
	if motion == null or not motion.has_springs():
		print("NOTE: no RL hair springs on this fixture's player; hair reset not checked")
		LookProfile.set_player_quality(MEDIUM)
		return
	await _near_camera_frames(actor, 4)
	expect(motion.is_running(), "the player's RL hair springs run at High near the camera (fixture)")
	_kill_all()
	var far := record.duplicate(true)
	far.x = 140
	far.y = 160
	# Recorded from before the ADD, so the first step the adopted body's
	# springs take is in the series whichever frame it falls on.
	var kept_recording := _start_hair_record(motion)
	var arrived := await _arrive(far, 1.0)
	expect(arrived == actor and _hair_motion_of(arrived) == motion,
		"the body with its RL head and hair springs is adopted")
	await _near_camera_frames(arrived, 3)
	var kept_series := _stop_hair_record(motion, kept_recording)
	await _discard_local()
	var fresh := await _spawn_fresh(far.duplicate(true))
	var fresh_motion := _hair_motion_of(fresh)
	var fresh_series: Array = []
	if fresh_motion != null:
		var fresh_recording := _start_hair_record(fresh_motion)
		await _near_camera_frames(fresh, 3)
		fresh_series = _stop_hair_record(fresh_motion, fresh_recording)
	var kept_peak := _first_peak(kept_series, 3)
	var fresh_peak := _first_peak(fresh_series, 3)
	expect(not kept_series.is_empty() and not fresh_series.is_empty() and kept_peak <= fresh_peak + 5.0,
		"the kept body's hair springs wake from rest at the new place as a new body's do: "
		+ "tips off rest per step %s mm, a fresh build %s mm" % [kept_series, fresh_series])
	await _discard_local()
	main.camera_rig.distance = camera_distance
	LookProfile.set_player_quality(MEDIUM)


## What follows the body goes with it, as when it was freed: the harvest glitter.
func _check_harvest_glitter() -> void:
	var actor := await _spawn_fresh(_record(11, 11))
	var saved: Dictionary = app.harvest
	app.harvest = {"active": true, "resource": "Reed"}
	main.call("_sync_harvest_sparkle")
	var glitter: Variant = main.get("harvest_sparkle")
	if not is_instance_valid(glitter):
		print("NOTE: no harvest glitter in this fixture (effects off); glitter not checked")
		app.harvest = saved
		return
	expect((glitter as HarvestSparkle3D).is_following(actor), "the player glitters while harvesting (fixture)")
	_kill_all()
	expect((glitter as HarvestSparkle3D).is_stopping() and main.get("harvest_sparkle") == null,
		"the harvest glitter stops with the held body, as with a freed one")
	var arrived := await _arrive(_record(12, 12), 1.0)
	var again: Variant = main.get("harvest_sparkle")
	expect(arrived == actor and is_instance_valid(again) and again != glitter
		and (again as HarvestSparkle3D).is_following(actor),
		"a run still going glitters around the adopted body")
	app.harvest = saved
	main.call("_sync_harvest_sparkle")


func _check_mismatches() -> void:
	var actor := _local()
	_kill_all()
	var renamed := await _arrive(_record(5, 5, CAPE_LOADOUT, "Someone Else"), 1.0)
	expect(renamed != null and renamed != actor and _gone(actor)
		and int((_hold_snapshot().releases as Dictionary).get("mismatch", 0)) == 1,
		"another person under the id frees the held body and builds a new one")
	await process_frame
	actor = _local()
	_kill_all()
	var other_model := await _arrive(_record(5, 5, CAPE_LOADOUT, "Someone Else", 0), 1.0)
	expect(other_model != null and other_model != actor and _gone(actor)
		and str(other_model.get_meta(&"model_id", "")) == "luminous_female"
		and int((_hold_snapshot().releases as Dictionary).get("mismatch", 0)) == 2,
		"another actor type (another model) frees the held body and builds the new one")
	await process_frame


func _check_releases() -> void:
	var hold = main.get("_local_avatar_hold")
	var actor := _local()
	_kill_all()
	main.call("_expire_held_local_avatar", Time.get_ticks_msec() + HOLD.HOLD_MSEC - 1000)
	expect(bool(_hold_snapshot().held), "the held body waits through its window")
	main.call("_expire_held_local_avatar", Time.get_ticks_msec() + HOLD.HOLD_MSEC + 1)
	expect(not hold.holding() and actor.is_queued_for_deletion()
		and int(hold.releases.get("expired", 0)) == 1, "15 s without its ADD frees the held body")
	await process_frame
	actor = await _spawn_fresh(_record(5, 5))
	_kill_all()
	app.local_actor_id = 2
	main.call("_expire_held_local_avatar", Time.get_ticks_msec())
	expect(not hold.holding() and actor.is_queued_for_deletion()
		and int(hold.releases.get("actor_changed", 0)) == 1, "a different player id frees it")
	app.local_actor_id = LOCAL
	await process_frame


func _check_session_end() -> void:
	var hold = main.get("_local_avatar_hold")
	var actor := await _spawn_fresh(_record(5, 5))
	_kill_all()
	expect(hold.holding(), "held before the session ends")
	main.call("_clear_world_presentation")
	expect(not hold.holding() and actor.is_queued_for_deletion()
		and int(hold.releases.get("session", 0)) == 1, "session end (logout, disconnect) frees it")
	await process_frame


func _refused(reason: String, setup: Callable, teardown: Callable) -> void:
	var hold = main.get("_local_avatar_hold")
	var actor := await _spawn_fresh(_record(6, 6))
	var before := int(hold.refusals.get(reason, 0))
	setup.call(actor)
	_kill_all()
	expect(not hold.holding() and is_instance_valid(actor) and actor.is_queued_for_deletion()
		and int(hold.refusals.get(reason, 0)) == before + 1, "%s: not held, freed as before" % reason)
	teardown.call(actor)
	await process_frame


func _check_refusals() -> void:
	await _refused("dead", func(_actor: ReplicatedActor3D) -> void: app.death = {"dead": true},
		func(_actor: ReplicatedActor3D) -> void: app.death = {})
	await _refused("dead", func(actor: ReplicatedActor3D) -> void: actor.current_action = &"death",
		func(_actor: ReplicatedActor3D) -> void: pass)
	var campaign: Node = main.get("campaign_scene")
	await _refused("campaign", func(_actor: ReplicatedActor3D) -> void: campaign.set("pending", true),
		func(_actor: ReplicatedActor3D) -> void: campaign.set("pending", false))
	var intro: Node = main.get("character_intro")
	await _refused("intro", func(_actor: ReplicatedActor3D) -> void: intro.set("pending", true),
		func(_actor: ReplicatedActor3D) -> void: intro.set("pending", false))
	var holder := RefCounted.new()
	await _refused("portrait", func(actor: ReplicatedActor3D) -> void: actor.hold_portrait_pose(holder),
		func(_actor: ReplicatedActor3D) -> void: pass)
	await _refused("cinematic", func(actor: ReplicatedActor3D) -> void: actor.set("_cinematic_active", true),
		func(_actor: ReplicatedActor3D) -> void: pass)


func _check_seamless_and_remote() -> void:
	var hold = main.get("_local_avatar_hold")
	var actor := await _spawn_fresh(_record(7, 7))
	main.set("_continuous_map_handoff", true)
	main.call("_clear_actor_nodes_for_map_change")
	expect(main.actor_nodes.get(LOCAL) == actor and not hold.holding() and actor.visible,
		"a seamless crossing keeps every node on the table and holds nothing")
	main.set("_continuous_map_handoff", false)
	var remote := {"actor_id": 30, "actor_type": 1, "kind": 1, "name": "Passer", "x": 9, "y": 9,
		"rotation": 0, "health": 20, "max_health": 20, "alive": true, "appearance": {},
		"equipment_visuals": {}, "equipment_fallback_parts": []}
	app.actors = {LOCAL: _record(7, 7), 30: remote}
	main.set("_actor_creation_frame", -1)
	expect(bool(main.call("_spawn_actor", 30, true)), "Main builds a remote actor")
	var passer: Variant = main.actor_nodes.get(30)
	app.actors = {LOCAL: _record(7, 7)}
	app.actor_roster_generation += 1
	main.call("_remove_stale_actor_nodes", null)
	expect(not hold.holding() and not main.actor_nodes.has(30)
		and (not is_instance_valid(passer) or (passer as Node3D).is_queued_for_deletion()
			or main.crowd.parked_actor_ids().has(30)),
		"a remote body is parked or freed as before, never held")
	await process_frame


func _cleanup() -> void:
	app.authenticated = false
	main.call("_clear_world_presentation")
	expect(not main.get("_local_avatar_hold").holding(), "nothing is held at the end")
	expect(await ContinentChunkStream.drain_workers(self, 30000), "the test drains every owned resource worker")
	main.queue_free()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
