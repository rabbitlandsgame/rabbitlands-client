extends "res://src/app/main.gd"
## Benchmark-only instrumentation around the existing presentation pipeline.
## Nothing in the shipping client pays for these timers.

const PROFILE_GATE_SOURCE_SHA256 := "7862794be68047fbedfa356cca6e83604b13424cd367a33b36c9455d9bab1282"
var benchmark_heat_bolt: Node
var benchmark_ground_enabled := true
var benchmark_overhead_enabled := true
var benchmark_animation_enabled := true
var benchmark_attribution_enabled := false
var _benchmark_usec: Dictionary = {}
var _benchmark_calls: Dictionary = {}
var _benchmark_values: Dictionary = {}
var _benchmark_skeleton_frames: Dictionary = {}
var _benchmark_max_skeleton_updates_per_actor := 0
var _benchmark_attribution_attachment: Dictionary = {}


## Snapshots are outside timed frames. Requested environment flags are kept
## separately from instantiated native backends and completed native work.
func benchmark_runtime_snapshot() -> Dictionary:
	var cape_instances := 0
	var cape_calls := 0
	var cape_fallbacks := 0
	for raw_actor: Variant in actor_nodes.values():
		var actor := raw_actor as ReplicatedActor3D
		if not is_instance_valid(actor) or actor._cape_cloth == null:
			continue
		var stats := actor._cape_cloth.call("native_presentation_stats") as Dictionary
		cape_instances += int(bool(stats.get("active", false)))
		cape_calls += int(stats.get("nativeCalls", 0))
		cape_fallbacks += int(stats.get("fallbackCalls", 0))
	var flight_stats := preload("res://src/world/spell_flight_3d.gd").native_presentation_stats()
	var impact_stats := preload("res://src/world/world_effect_3d.gd").native_presentation_stats()
	return {
		"clientDiagnostics": benchmark_resource_diagnostics(),
		"effectiveSettings": {"quality": LookProfile.quality_name(LookProfile.quality()),
			"appearance": LookProfile.mode_name(LookProfile.mode()), "bodyCap": crowd.body_cap,
			"renderScale": main_viewport.scaling_3d_scale,
			"textureQuality": _map_texture_quality, "textureSkip": GraphicsOptions.active_texture_skip(),
			"frameCap": Engine.max_fps, "minimap": minimap_frame.visible,
			"clothBudget": crowd.cloth_bodies, "shadowsPreference": _shadows_enabled,
			"sunShadowsEnabled": world_sun.shadow_enabled,
			"particlesEnabled": _effects_enabled, "decorativeGrass": GraphicsOptions.decorative_grass,
			"nameDistanceMetres": _name_distance_metres,
			"renderer": RenderingServer.get_current_rendering_method(),
			"rootSize": [get_tree().root.size.x, get_tree().root.size.y],
			"worldViewportSize": [main_viewport.size.x, main_viewport.size.y]},
		"activeBackends": {"nativeReducer": AppState.native_crowd_reducer_active(),
			"animationTrackCompaction": NativeAnimationImporter.retention_snapshot(),
			"clientRuntime": client_runtime.snapshot(),
			"remotePresentation": (remote_presentation.snapshot() if is_instance_valid(remote_presentation) else {"backend": "legacy", "reason": "not_initialized"}),
			"remoteCoverage": remote_presentation.coverage(actor_nodes.values()),
			"resourceAdmission": benchmark_resource_admission_snapshot(),
			"rustSpellFlights": RustSpellFlights.snapshot_for(world_root),
			"mountedBatch": RustRiderPose.batch_snapshot(),
			"presentation": {"requested": OS.get_environment("ELORIA_NATIVE_PRESENTATION"),
				"nativeCapeInstances": cape_instances, "nativeCapeCalls": cape_calls,
				"capeFallbackCalls": cape_fallbacks, "flight": flight_stats, "impact": impact_stats},
			"preparedContent": preload("res://src/world/prepared_content.gd").snapshot(),
			"preparedNodePolicy": preload("res://src/world/prepared_content.gd").node_policy(),
			"mapSceneCache": {"enabled": MapSceneCache.is_enabled(), "status": str(world_loader.cache_status)}},
	}


# Keep positions, connection/authentication fields and replay actor data out of
# benchmark metadata. This is taken outside sampling, never in a per-frame timer.
func benchmark_resource_admission_snapshot() -> Dictionary:
	var service := preload("res://src/runtime/resource_admission.gd")
	var observed := resource_admission_snapshot()
	# Capture cached effective selectors, not only inherited environment text.
	observed["requested_mode"] = "rust" if service.requested() else "legacy"
	observed["requested_estimate_budget"] = service.estimate_budget()
	return observed


func benchmark_resource_diagnostics() -> Dictionary:
	var snapshot := client_diagnostic_snapshot()
	var result: Dictionary = {}
	for key: String in ["client_runtime", "spell_flights", "surface_work", "loader_work", "streaming_work",
			"resource_retention", "resource_admission", "map_cache_enabled", "map_cache_status",
			"map_load_phases_us", "chunks_resident", "chunk_resident_bytes",
			"chunk_revision", "vram_mode", "vram_formats", "static_memory_bytes",
			"video_memory_bytes"]:
		if snapshot.has(key):
			result[key] = snapshot[key]
	result["prepared_placements"] = benchmark_placement_snapshot()
	return result


func benchmark_placement_snapshot() -> Dictionary:
	var ready := bool(benchmark_readiness_snapshot().get("ready", false))
	return preload("res://tests/integration/benchmark_placement_diagnostics.gd").capture(
		world_loader, exterior_stream, loaded_server_map, ready)


func benchmark_restore_prepared_placement(map_id: String, chunk_id: String) -> Dictionary:
	var ready := bool(benchmark_readiness_snapshot().get("ready", false))
	return preload("res://tests/integration/benchmark_placement_diagnostics.gd").restore_one(
		world_loader, exterior_stream, loaded_server_map, map_id, chunk_id, ready)


func benchmark_readiness_snapshot() -> Dictionary:
	return preload("res://tests/integration/client_world_readiness.gd").snapshot(self)


## The gate with its half-rate stepping timed: the players and skeleton
## modifiers it advances every other frame, all on the same frame.
class TimedAnimationGate:
	extends AnimationGate
	var owner_main: Node

	func advance(delta: float) -> void:
		var started := Time.get_ticks_usec()
		if owner_main != null and bool(owner_main.get("benchmark_detailed_profile_enabled")):
			_profile_advance(delta)
		else:
			super.advance(delta)
		if owner_main != null:
			owner_main.call("_benchmark_add", &"half_rate_step", started)


	func _profile_advance(delta: float) -> void:
		owner_main.set("_benchmark_profile_gate_frame", Engine.get_process_frames())
		_tick += 1
		for group: Dictionary in _groups:
			group["delta"] = float(group["delta"]) + delta
			if (_tick + int(group["phase"])) % int(group["stride"]) != 0:
				continue
			var step: float = group["delta"]
			group["delta"] = 0.0
			var members: Dictionary = group["members"]
			if members.is_empty():
				continue
			var gone: Array = []
			for value: Variant in members:
				if not is_instance_valid(value):
					gone.append(value)
					continue
				var player: AnimationPlayer = value as AnimationPlayer
				if player.active and player.is_inside_tree():
					var player_started := Time.get_ticks_usec()
					player.advance(step)
					var player_usec := Time.get_ticks_usec() - player_started
					var skeleton_usec := 0
					var skeleton_called := false
					var skeleton: Variant = members[value]
					if is_instance_valid(skeleton) and (skeleton as Skeleton3D).is_inside_tree():
						var skeleton_started := Time.get_ticks_usec()
						(skeleton as Skeleton3D).advance(step)
						skeleton_usec = Time.get_ticks_usec() - skeleton_started
						skeleton_called = true
					owner_main.call("_benchmark_profile_manual_step", player, int(group["tier"]), int(group["phase"]), player_usec, skeleton_usec, skeleton_called)
			for value: Variant in gone:
				members.erase(value)
				_group_of.erase(value)


func _init() -> void:
	var timed := TimedAnimationGate.new()
	timed.owner_main = self
	animation_gate = timed


func benchmark_reset_frame() -> void:
	_benchmark_profile_metric_frames.clear()
	_benchmark_profile_signal_frames.clear()
	_benchmark_profile_manual.clear()
	_benchmark_profile_listeners.clear()
	_benchmark_profile_gate_frame = -1
	_benchmark_usec.clear()
	_benchmark_calls.clear()
	_benchmark_values.clear()
	_benchmark_max_skeleton_updates_per_actor = 0


func benchmark_take_frame() -> Dictionary:
	return {
		"profile": _benchmark_profile_snapshot() if benchmark_detailed_profile_enabled else {},
		"microseconds": _benchmark_usec.duplicate(),
		"calls": _benchmark_calls.duplicate(),
		"values": _benchmark_values.duplicate(),
		"attribution": {
			"maximumSkeletonUpdatesPerActor":
				_benchmark_max_skeleton_updates_per_actor,
		},
	}


func _benchmark_add(label: StringName, started: int) -> void:
	if benchmark_detailed_profile_enabled:
		_benchmark_profile_mark(label)
	_benchmark_usec[label] = int(_benchmark_usec.get(label, 0)) \
		+ Time.get_ticks_usec() - started
	_benchmark_calls[label] = int(_benchmark_calls.get(label, 0)) + 1


func _process(delta: float) -> void:
	var started := Time.get_ticks_usec()
	super._process(delta)
	_benchmark_add(&"main_process_inclusive", started)
	if benchmark_attribution_enabled:
		_benchmark_values[&"process_delta_milliseconds"] = delta * 1000.0


## Installs diagnostic observers only after a benchmark fixture is complete.
## Every existing connection is snapshotted before mutation. The production
## combat callback is replaced in place by rebuilding the complete ordered
## connection list, so the other callbacks retain their relative positions.
func benchmark_attach_attribution(nodes: Dictionary) -> Dictionary:
	if benchmark_detailed_profile_enabled and not (animation_gate is TimedAnimationGate):
		return {"ok": false, "error": "detailed legacy probe unsupported: Main replaced the timed gate", "actualGate": _benchmark_profile_gate_identity()}
	if benchmark_detailed_profile_enabled and not _benchmark_profile_gate_source_matches():
		return {"ok": false, "error": "diagnostic gate copy no longer matches runtime source"}
	_benchmark_skeleton_frames.clear()
	var plans: Array[Dictionary] = []
	# Preflight the complete fixture before touching any connection. A failure
	# therefore leaves production callback ordering and targets unchanged.
	for raw_id: Variant in nodes:
		var actor := nodes[raw_id] as ReplicatedActor3D
		if not is_instance_valid(actor):
			continue
		var skeleton := actor.get_skeleton()
		if skeleton == null:
			continue
		var id := int(raw_id)
		var combat := actor.combat_presentation
		var plan := {"id": id, "skeleton": skeleton, "combat": combat,
			"direct_index": -1, "originals": []}
		var connections := skeleton.skeleton_updated.get_connections()
		var originals: Array[Dictionary] = []
		for connection: Dictionary in connections:
			var callback: Callable = connection.get("callable", Callable()) as Callable
			if not callback.is_valid():
				return {"ok": false,
					"error": "actor %d has an invalid skeleton callback" % id}
			var flags := int(connection.get("flags", 0))
			if benchmark_detailed_profile_enabled and (flags & (CONNECT_DEFERRED | CONNECT_ONE_SHOT)) != 0:
				return {"ok": false, "error": "detailed synchronous frame profiling refuses deferred/one-shot listeners before mutation"}
			if (flags & CONNECT_REFERENCE_COUNTED) != 0:
				return {"ok": false,
					"error": ("actor %d has a reference-counted skeleton callback; "
						+ "connection multiplicity cannot be reconstructed") % id}
			originals.append({"callable": callback, "flags": flags})
		plan["originals"] = originals
		if combat != null:
			var direct := Callable(combat, "update_pose")
			var direct_index := -1
			for index: int in range(originals.size()):
				if originals[index].get("callable") == direct:
					if direct_index >= 0:
						return {"ok": false,
							"error": "actor %d combat callback is connected more than once" % id}
					direct_index = index
			if direct_index < 0:
				return {"ok": false,
					"error": "actor %d combat callback is not connected" % id}
			plan["direct_index"] = direct_index
		plans.append(plan)

	if benchmark_detailed_profile_enabled:
		var detailed := _benchmark_profile_attach_plans(plans)
		if bool(detailed.get("ok", false)):
			_benchmark_profile_register(nodes)
			_benchmark_profile_census() # Prime track-count cache outside warmup/timing.
		return detailed
	var combat_delegates := 0
	var passive_observers := 0
	var verified_replacements := 0
	var applied: Array[Dictionary] = []
	for plan: Dictionary in plans:
		var skeleton := plan["skeleton"] as Skeleton3D
		var id := int(plan["id"])
		var combat := plan["combat"] as CombatPresentation3D
		if combat != null:
			var delegated := Callable(self,
				"_benchmark_combat_skeleton_updated").bind(id, combat)
			var originals := plan["originals"] as Array[Dictionary]
			var replacement: Array[Dictionary] = originals.duplicate(true)
			replacement[int(plan["direct_index"])]["callable"] = delegated
			var replace_result := _benchmark_replace_connections(
				skeleton, originals, replacement)
			if not bool(replace_result.get("ok", false)):
				var rollback_errors := _benchmark_rollback_attribution(applied)
				return {"ok": false,
					"error": ("actor %d timed combat delegate failed: %s%s" % [
						id, str(replace_result.get("error", "unknown error")),
						("; rollback: " + "; ".join(rollback_errors))
						if not rollback_errors.is_empty() else ""])}
			applied.append({"kind": "replacement", "skeleton": skeleton,
				"originals": originals, "replacement": replacement})
			combat_delegates += 1
			verified_replacements += 1
		else:
			var observer := Callable(self,
				"_benchmark_skeleton_updated").bind(id)
			var connected := skeleton.skeleton_updated.connect(observer)
			if connected != OK:
				var rollback_errors := _benchmark_rollback_attribution(applied)
				return {"ok": false,
					"error": ("actor %d skeleton observer failed: %d%s" % [
						id, connected, ("; rollback: " + "; ".join(rollback_errors))
						if not rollback_errors.is_empty() else ""])}
			applied.append({"kind": "observer", "skeleton": skeleton,
				"installed": observer})
			passive_observers += 1
	_benchmark_attribution_attachment = {
		"ok": true, "actors": plans.size(),
		"combatSignalDelegates": combat_delegates,
		"passiveSkeletonObservers": passive_observers,
		"verifiedOrderedReplacements": verified_replacements,
		"allCombatReplacementOrdersVerified":
			verified_replacements == combat_delegates,
		"combatSignalOrderPolicy":
			"snapshot and rebuild every callback in original order",
	}
	return _benchmark_attribution_attachment.duplicate(true)


func _benchmark_replace_connections(skeleton: Skeleton3D,
		expected: Array[Dictionary], replacement: Array[Dictionary]) -> Dictionary:
	var current := skeleton.skeleton_updated.get_connections()
	if current.size() != expected.size():
		return {"ok": false, "error": "connection count changed after preflight"}
	for index: int in range(expected.size()):
		var live := current[index] as Dictionary
		if live.get("callable") != expected[index].get("callable") \
				or int(live.get("flags", 0)) != int(expected[index].get("flags", 0)):
			return {"ok": false,
				"error": "connection %d changed after preflight" % index}
	for descriptor: Dictionary in expected:
		skeleton.skeleton_updated.disconnect(descriptor["callable"] as Callable)
	var installed: Array[Dictionary] = []
	for descriptor: Dictionary in replacement:
		var connected := skeleton.skeleton_updated.connect(
			descriptor["callable"] as Callable, int(descriptor["flags"]))
		if connected != OK:
			for added: Dictionary in installed:
				var callback := added["callable"] as Callable
				if skeleton.skeleton_updated.is_connected(callback):
					skeleton.skeleton_updated.disconnect(callback)
			var restore_error := _benchmark_connect_descriptors(skeleton, expected)
			return {"ok": false,
				"error": "connect returned %d; restore returned %d" % [
					connected, restore_error]}
		installed.append(descriptor)
	if not _benchmark_connections_match(skeleton, replacement):
		var restore_error := _benchmark_reset_connections(skeleton, expected)
		return {"ok": false,
			"error": "replacement order/flags verification failed; restore returned %d" %
				restore_error}
	return {"ok": true, "verified": true}


func _benchmark_connections_match(skeleton: Skeleton3D,
		descriptors: Array[Dictionary]) -> bool:
	var live_connections := skeleton.skeleton_updated.get_connections()
	if live_connections.size() != descriptors.size():
		return false
	for index: int in range(descriptors.size()):
		var live := live_connections[index] as Dictionary
		if live.get("callable") != descriptors[index].get("callable") \
				or int(live.get("flags", 0)) != int(descriptors[index].get("flags", 0)):
			return false
	return true


func _benchmark_reset_connections(skeleton: Skeleton3D,
		descriptors: Array[Dictionary]) -> int:
	for connection: Dictionary in skeleton.skeleton_updated.get_connections():
		var callback: Callable = connection.get("callable", Callable()) as Callable
		if callback.is_valid():
			skeleton.skeleton_updated.disconnect(callback)
	return _benchmark_connect_descriptors(skeleton, descriptors)


func _benchmark_connect_descriptors(skeleton: Skeleton3D,
		descriptors: Array[Dictionary]) -> int:
	for descriptor: Dictionary in descriptors:
		var connected := skeleton.skeleton_updated.connect(
			descriptor["callable"] as Callable, int(descriptor["flags"]))
		if connected != OK:
			return connected
	return OK


func _benchmark_rollback_attribution(applied: Array[Dictionary]) -> Array[String]:
	var errors: Array[String] = []
	for index: int in range(applied.size() - 1, -1, -1):
		var record := applied[index]
		var skeleton := record["skeleton"] as Skeleton3D
		if str(record["kind"]) == "replacement":
			var restored := _benchmark_replace_connections(skeleton,
				record["replacement"] as Array[Dictionary],
				record["originals"] as Array[Dictionary])
			if not bool(restored.get("ok", false)):
				errors.append("actor connection restore failed: %s" %
					str(restored.get("error", "unknown error")))
		else:
			var installed := record["installed"] as Callable
			if skeleton.skeleton_updated.is_connected(installed):
				skeleton.skeleton_updated.disconnect(installed)
	return errors


func _benchmark_note_skeleton(actor_id: int) -> void:
	var frame := Engine.get_process_frames()
	var previous := _benchmark_skeleton_frames.get(actor_id, {}) as Dictionary
	var count := int(previous.get("count", 0)) + 1 \
		if int(previous.get("frame", -1)) == frame else 1
	_benchmark_skeleton_frames[actor_id] = {"frame": frame, "count": count}
	_benchmark_calls[&"skeleton_updated"] = int(
		_benchmark_calls.get(&"skeleton_updated", 0)) + 1
	if count == 1:
		_benchmark_calls[&"unique_skeletons_updated"] = int(
			_benchmark_calls.get(&"unique_skeletons_updated", 0)) + 1
	_benchmark_max_skeleton_updates_per_actor = maxi(
		_benchmark_max_skeleton_updates_per_actor, count)


func _benchmark_skeleton_updated(actor_id: int) -> void:
	_benchmark_note_skeleton(actor_id)


func _benchmark_combat_skeleton_updated(actor_id: int,
		combat: CombatPresentation3D) -> void:
	_benchmark_note_skeleton(actor_id)
	var started := Time.get_ticks_usec()
	combat.update_pose()
	_benchmark_add(&"combat_pose_from_skeleton", started)


func _benchmark_count_event(label: StringName) -> void:
	if benchmark_attribution_enabled:
		_benchmark_calls[label] = int(_benchmark_calls.get(label, 0)) + 1


func _on_missile_fired(shot: Dictionary) -> void:
	if benchmark_attribution_enabled:
		var source: Variant = actor_nodes.get(int(shot.get("source_actor_id", -1)))
		if is_instance_valid(source):
			_benchmark_count_event(&"mirrored_effect_setter_missile")
	super._on_missile_fired(shot)


func _on_ground_missile_fired(shot: Dictionary) -> void:
	if benchmark_attribution_enabled:
		var source: Variant = actor_nodes.get(int(shot.get("source_actor_id", -1)))
		if is_instance_valid(source):
			_benchmark_count_event(&"mirrored_effect_setter_ground_missile")
	super._on_ground_missile_fired(shot)


func _sync_world(changed: Variant = null) -> void:
	var started := Time.get_ticks_usec()
	super._sync_world(changed)
	_benchmark_add(&"sync_world_inclusive", started)


func _present_actor(id: Variant) -> void:
	var ground_before := int(_benchmark_usec.get(&"ground", 0))
	var started := Time.get_ticks_usec()
	super._present_actor(id)
	var actor_value: Variant = actor_nodes.get(id)
	if not benchmark_overhead_enabled:
		if is_instance_valid(actor_value):
			(actor_value as ReplicatedActor3D).set_nameplate_visible(false)
			(actor_value as ReplicatedActor3D).set_health_visible(false)
	if not benchmark_animation_enabled:
		_benchmark_freeze_actor(actor_value as ReplicatedActor3D)
	var inclusive := Time.get_ticks_usec() - started
	var ground_delta := int(_benchmark_usec.get(&"ground", 0)) - ground_before
	_benchmark_usec[&"present_inclusive"] = int(
		_benchmark_usec.get(&"present_inclusive", 0)) + inclusive
	_benchmark_usec[&"present_excluding_ground"] = int(
		_benchmark_usec.get(&"present_excluding_ground", 0)) \
		+ maxi(0, inclusive - ground_delta)
	_benchmark_calls[&"present"] = int(_benchmark_calls.get(&"present", 0)) + 1


func _place_actor_on_surface(actor: ReplicatedActor3D, force := false,
		fallback_height := NAN) -> void:
	if not benchmark_ground_enabled:
		return
	var started := Time.get_ticks_usec()
	super._place_actor_on_surface(actor, force, fallback_height)
	_benchmark_add(&"ground", started)


func _sync_overhead_health() -> void:
	if not benchmark_overhead_enabled:
		return
	var started := Time.get_ticks_usec()
	super._sync_overhead_health()
	_benchmark_add(&"overhead", started)


## The per-pass overhead answers (crowd presentation), timed with the full one.
func _sync_overhead_health_for(ids: Array) -> void:
	if not benchmark_overhead_enabled:
		return
	var started := Time.get_ticks_usec()
	super._sync_overhead_health_for(ids)
	_benchmark_add(&"overhead", started)


func _update_model_builds() -> void:
	var started := Time.get_ticks_usec()
	super._update_model_builds()
	_benchmark_add(&"model_builds", started)


func _update_map_viewports() -> void:
	var started := Time.get_ticks_usec()
	super._update_map_viewports()
	_benchmark_add(&"map_viewports", started)


func _update_animation_gate(delta: float) -> void:
	var refresh_before := _animation_gate_refresh_msec
	var started := Time.get_ticks_usec()
	super._update_animation_gate(delta)
	if not benchmark_animation_enabled and refresh_before != _animation_gate_refresh_msec:
		for actor_value: Variant in actor_nodes.values():
			if is_instance_valid(actor_value):
				_benchmark_freeze_actor(actor_value as ReplicatedActor3D)
	_benchmark_add(&"animation_gate", started)


## The crowd-wide work at the end of a gate sweep, and the overhead declutter
## inside it, timed apart from the sweep's per-actor slices.
func _finish_gate_sweep() -> void:
	var started := Time.get_ticks_usec()
	super._finish_gate_sweep()
	_benchmark_add(&"gate_sweep_end", started)


func _declutter_actor_overheads(target_id: int) -> void:
	var started := Time.get_ticks_usec()
	super._declutter_actor_overheads(target_id)
	_benchmark_add(&"declutter", started)


func _benchmark_freeze_actor(actor: ReplicatedActor3D) -> void:
	if actor != null and is_instance_valid(actor.animation_player):
		actor.animation_player.active = false


func _on_actor_animation_requested(animation: Dictionary) -> void:
	if not benchmark_attribution_enabled:
		super._on_actor_animation_requested(animation)
		if not benchmark_animation_enabled:
			_benchmark_freeze_actor(actor_nodes.get(
				int(animation.get("actor_id", -1))) as ReplicatedActor3D)
		return
	var actor_id := int(animation.get("actor_id", -1))
	var actor := actor_nodes.get(actor_id) as ReplicatedActor3D
	var accepted := is_instance_valid(actor) and not (
		str(animation.get("action", "")) == "cast_exit"
		and actor.current_action not in [&"cast_channel", &"cast_channel_enter"])
	if accepted:
		_benchmark_count_event(&"mirrored_effect_setter_animation")
	super._on_actor_animation_requested(animation)
	if accepted and animation.has("power") and actor.combat_presentation != null:
		_benchmark_count_event(&"mirrored_spell_power")
	if not benchmark_animation_enabled:
		_benchmark_freeze_actor(actor_nodes.get(
			actor_id) as ReplicatedActor3D)


func _track_effect(node: Node, kind: StringName) -> void:
	super._track_effect(node, kind)
	if kind == &"spell" and is_instance_valid(benchmark_heat_bolt):
		benchmark_heat_bolt.call("observe", node)


func _on_special_effect_requested(effect: Dictionary) -> void:
	if is_instance_valid(benchmark_heat_bolt) and int(effect.get("effect", -1)) == 2:
		# Explicit synthetic clock after decoding the real packet, identical
		# in all three family backends; never used by other cells.
		effect = effect.duplicate()
		effect["release_delay"] = 0.2
		effect["flight_duration"] = 0.4
	if not benchmark_attribution_enabled:
		super._on_special_effect_requested(effect)
		if not benchmark_animation_enabled:
			_benchmark_freeze_actor(actor_nodes.get(
				int(effect.get("actor_id", -1))) as ReplicatedActor3D)
		return
	var actor_id := int(effect.get("actor_id", -1))
	var source := actor_nodes.get(actor_id) as ReplicatedActor3D
	var action := SpellPresentation.action_for_effect(int(effect.get("effect", -1)))
	if is_instance_valid(source) and not action.is_empty():
		_benchmark_count_event(&"mirrored_effect_setter_special")
	super._on_special_effect_requested(effect)
	if _effects_enabled and is_instance_valid(source) \
			and source.combat_presentation != null \
			and super._actor_effect_position(actor_id) is Vector3 \
			and action == source.current_action:
		_benchmark_count_event(&"mirrored_spell_palette")
	if not benchmark_animation_enabled:
		_benchmark_freeze_actor(actor_nodes.get(
			actor_id) as ReplicatedActor3D)

func benchmark_remote_snapshot() -> Dictionary:
	return {"presentation": (remote_presentation.snapshot() if is_instance_valid(remote_presentation) else {"backend": "legacy", "reason": "not_initialized"}),
		"coverage": remote_presentation.coverage(actor_nodes.values())}


## Detailed diagnostic state; never reached when attribution is disabled.
var _benchmark_profile_players: Dictionary = {}
var _benchmark_profile_actor_rows: Array[Dictionary] = []
var _benchmark_profile_tracks: Dictionary = {}
var _benchmark_profile_manual: Dictionary = {}
var _benchmark_profile_listeners: Dictionary = {}
var _benchmark_profile_gate_frame := -1
var _benchmark_profile_metric_frames: Dictionary = {}
var _benchmark_profile_signal_frames: Dictionary = {}
var benchmark_detailed_profile_enabled := false
var _benchmark_profile_delegate_owners: Array[RefCounted] = []

class ProfileListenerDelegate extends RefCounted:
	var owner_main: Node
	var actor_id: int
	var label: StringName
	var callback: Callable
	var is_combat: bool
	func invoke() -> void:
		if is_instance_valid(owner_main):
			owner_main.call("_benchmark_profile_listener", actor_id, label, callback, is_combat)

func _benchmark_profile_gate_source_matches() -> bool:
	# Compiled/remapped export scripts cannot attest this copied source loop.
	if OS.has_feature("template") \
			or OS.get_environment("RABBITLANDS_CROWD_BENCH_EXECUTION_MODE") == "exported" \
			or not FileAccess.file_exists("res://src/world/animation_gate.gd"):
		return false
	var source := FileAccess.get_file_as_string("res://src/world/animation_gate.gd").replace("\r\n", "\n")
	var first := source.find("func advance(delta: float) -> void:")
	var last := source.find("## Forgets every player.", first)
	return first >= 0 and last > first and source.substr(first, last-first).sha256_text() == PROFILE_GATE_SOURCE_SHA256

func _benchmark_profile_register(nodes: Dictionary) -> void:
	for raw_id: Variant in nodes:
		var actor := nodes[raw_id] as ReplicatedActor3D
		if not is_instance_valid(actor) or actor.animation_player == null:
			continue
		var skeleton := actor.get_skeleton()
		var dto: Dictionary = AppState.actors.get(raw_id, {})
		var metadata := {"actor": actor, "actor_id": int(raw_id), "model": _model_for_actor(dto),
			"bones": skeleton.get_bone_count() if skeleton != null else 0}
		_benchmark_profile_players[actor.animation_player] = metadata
		_benchmark_profile_actor_rows.append(metadata)

func _benchmark_profile_manual_step(player: AnimationPlayer, tier: int, phase: int,
		player_usec: int, skeleton_usec: int, skeleton_called: bool) -> void:
	var metadata: Dictionary = _benchmark_profile_players.get(player, {})
	var model := str(metadata.get("model", "unregistered"))
	var key := "%s/tier%d/phase%d" % [model, tier, phase]
	var row: Dictionary = _benchmark_profile_manual.get(key, {"model": model, "tier": tier,
		"phase": phase, "players": 0, "skeleton_calls": 0, "player_usec": 0, "skeleton_usec": 0})
	row.players = int(row.players) + 1
	row.skeleton_calls = int(row.skeleton_calls) + int(skeleton_called)
	row.player_usec = int(row.player_usec) + player_usec
	row.skeleton_usec = int(row.skeleton_usec) + skeleton_usec
	_benchmark_profile_manual[key] = row
	_benchmark_usec[&"manual_player_advance"] = int(_benchmark_usec.get(&"manual_player_advance", 0)) + player_usec
	_benchmark_usec[&"manual_skeleton_advance"] = int(_benchmark_usec.get(&"manual_skeleton_advance", 0)) + skeleton_usec
	_benchmark_profile_mark(&"manual_player_advance", _benchmark_profile_gate_frame)
	if skeleton_called:
		_benchmark_profile_mark(&"manual_skeleton_advance", _benchmark_profile_gate_frame)

func _benchmark_profile_track_count(player: AnimationPlayer) -> int:
	var clip := player.assigned_animation
	if clip.is_empty() or not player.has_animation(clip):
		return 0
	var animation := player.get_animation(clip)
	var key := animation.get_instance_id()
	if not _benchmark_profile_tracks.has(key):
		_benchmark_profile_tracks[key] = animation.get_track_count()
	return int(_benchmark_profile_tracks[key])

func _benchmark_profile_census() -> Dictionary:
	var tiers := {"full": 0, "half": 0, "quarter": 0, "paused": 0}
	var models := {}
	for metadata: Dictionary in _benchmark_profile_actor_rows:
		var value: Variant = metadata.actor
		if not is_instance_valid(value):
			continue
		var actor := value as ReplicatedActor3D
		if actor == null or actor.animation_player == null:
			continue
		var tier := actor.animation_tier()
		var label := "full" if tier == AnimationGate.Tier.FULL else (
			"half" if tier == AnimationGate.Tier.HALF else (
			"quarter" if tier == AnimationGate.Tier.QUARTER else "paused"))
		tiers[label] = int(tiers[label]) + 1
		var key := "%s/%s" % [str(metadata.model), label]
		var row: Dictionary = models.get(key, {"model": metadata.model, "tier": label,
			"bodies": 0, "bones": 0, "assigned_clip_tracks": 0, "crossfade_duration_nonzero": 0})
		row.bodies = int(row.bodies) + 1
		row.bones = int(row.bones) + int(metadata.bones)
		row.assigned_clip_tracks = int(row.assigned_clip_tracks) + _benchmark_profile_track_count(actor.animation_player)
		row.crossfade_duration_nonzero = int(row.crossfade_duration_nonzero) + int(actor.action_crossfade_seconds > 0.0)
		models[key] = row
	return {"tiers": tiers, "models": models, "half_groups": animation_gate.group_sizes(AnimationGate.Tier.HALF),
		"quarter_groups": animation_gate.group_sizes(AnimationGate.Tier.QUARTER),
		"collection_engine_frame": Engine.get_process_frames(),
		"track_scope": "assigned clip only; outgoing crossfade clips are not exposed by AnimationPlayer"}

func _benchmark_profile_mark(label: StringName, origin_frame := -1) -> void:
	var execution := Engine.get_process_frames()
	var origin := execution if origin_frame < 0 else origin_frame
	var row: Dictionary = _benchmark_profile_metric_frames.get(label, {"origin": [], "execution": []})
	if (row.origin as Array).is_empty() or (row.origin as Array)[-1] != origin:
		(row.origin as Array).append(origin)
	if (row.execution as Array).is_empty() or (row.execution as Array)[-1] != execution:
		(row.execution as Array).append(execution)
	_benchmark_profile_metric_frames[label] = row

func _benchmark_profile_signal_started(actor_id: int) -> void:
	var frame := Engine.get_process_frames()
	_benchmark_profile_signal_frames[actor_id] = frame
	_benchmark_profile_mark(&"skeleton_signal_dispatch", frame)
	_benchmark_note_skeleton(actor_id)

func _benchmark_profile_listener(actor_id: int, label: StringName, callback: Callable, is_combat: bool) -> void:
	if not callback.is_valid():
		return # Original target has been freed; its original signal would not run.
	var origin := int(_benchmark_profile_signal_frames.get(actor_id, -1))
	var started := Time.get_ticks_usec()
	callback.call()
	var elapsed := Time.get_ticks_usec() - started
	_benchmark_profile_mark(label, origin)
	_benchmark_usec[&"skeleton_listener_total"] = int(_benchmark_usec.get(&"skeleton_listener_total", 0)) + elapsed
	if is_combat:
		_benchmark_usec[&"combat_pose_from_skeleton"] = int(_benchmark_usec.get(&"combat_pose_from_skeleton", 0)) + elapsed
	var row: Dictionary = _benchmark_profile_listeners.get(label, {"calls": 0, "usec": 0})
	row.calls = int(row.calls) + 1
	row.usec = int(row.usec) + elapsed
	_benchmark_profile_listeners[label] = row

func _benchmark_profile_snapshot() -> Dictionary:
	return {"gate_engine_frame": _benchmark_profile_gate_frame,
		"metric_frames": _benchmark_profile_metric_frames.duplicate(true),
		"origin_scope": "synchronous timer call or skeleton signal dispatch; native pose evaluation origin is not exposed",
		"manual": _benchmark_profile_manual.duplicate(true),
		"listeners": _benchmark_profile_listeners.duplicate(true),
		"census": _benchmark_profile_census(),
		"gate_source_sha256": PROFILE_GATE_SOURCE_SHA256}

func _benchmark_profile_attach_plans(plans: Array[Dictionary]) -> Dictionary:
	var applied: Array[Dictionary] = []
	var listener_count := 0
	var delegates: Array[RefCounted] = []
	for plan: Dictionary in plans:
		var skeleton := plan.skeleton as Skeleton3D
		var actor_id := int(plan.id)
		var originals := plan.originals as Array[Dictionary]
		var replacement: Array[Dictionary] = [{"callable": Callable(self, "_benchmark_profile_signal_started").bind(actor_id), "flags": 0}]
		var combat := plan.combat as CombatPresentation3D
		for index: int in range(originals.size()):
			var original := originals[index]["callable"] as Callable
			var target := original.get_object()
			var label := StringName("%s.%s" % [target.get_class() if target != null else "static", original.get_method()])
			var is_combat := index == int(plan.direct_index) and combat != null
			label = StringName("%s/%s" % [_model_for_actor(AppState.actors.get(actor_id, {})), label])
			var descriptor := originals[index].duplicate()
			var delegate := ProfileListenerDelegate.new()
			delegate.owner_main = self
			delegate.actor_id = actor_id
			delegate.label = label
			delegate.callback = original
			delegate.is_combat = is_combat
			delegates.append(delegate)
			descriptor["callable"] = Callable(delegate, "invoke")
			replacement.append(descriptor)
			listener_count += 1
		var result := _benchmark_replace_connections(skeleton, originals, replacement)
		if not bool(result.get("ok", false)):
			var rollback_errors := _benchmark_rollback_attribution(applied)
			return {"ok": false, "error": "detailed listener attachment failed: %s; rollback: %s" % [result, rollback_errors]}
		applied.append({"kind": "replacement", "skeleton": skeleton, "originals": originals, "replacement": replacement})
	_benchmark_profile_delegate_owners.append_array(delegates)
	_benchmark_attribution_attachment = {"ok": true, "detailed": true, "actors": plans.size(),
		"timedListeners": listener_count, "originalListenerOrderAndFlagsVerified": true,
		"fullAnimationClock": "Godot AnimationPlayer idle path unchanged", "gateSourceHash": PROFILE_GATE_SOURCE_SHA256,
		"actualGate": _benchmark_profile_gate_identity(),
		"actualGateFamily": "TimedAnimationGate", "nativeRemoteBackendClaim": false}
	return _benchmark_attribution_attachment.duplicate(true)

func _benchmark_profile_gate_identity() -> Dictionary:
	var script := animation_gate.get_script() as Script
	return {"class": animation_gate.get_class(), "script": script.resource_path if script != null else "",
		"isTimedLegacyProbe": animation_gate is TimedAnimationGate,
		"runtime": _benchmark_profile_backend_snapshot("client_runtime"),
		"remote": _benchmark_profile_backend_snapshot("remote_presentation")}

func _benchmark_profile_backend_snapshot(property: String) -> Dictionary:
	var backend: Variant = get(property)
	if is_instance_valid(backend) and backend.has_method("snapshot"):
		return backend.call("snapshot") as Dictionary
	return {"available": false, "reason": "not_initialized"}
