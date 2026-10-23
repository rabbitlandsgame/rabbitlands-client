extends SceneTree
## Synthetic skeletons, the real actor handoff and the real mounted scheduler.
## Model/seat fitting is covered by test_mount_quality_and_scheduling.
const Mounted := preload("res://src/mounts/mounted_player_visual.gd")
var failures := 0

class RecordingGate extends AnimationGate:
	var apply_calls := 0
	func apply(player: AnimationPlayer, tier: AnimationGate.Tier,
			skeleton: Skeleton3D = null) -> void:
		apply_calls += 1
		super.apply(player, tier, skeleton)

class CountingModifier extends SkeletonModifier3D:
	var counts: Dictionary = {}
	func _process_modification_with_delta(_delta: float) -> void:
		counts.calls = int(counts.get("calls", 0)) + 1

func _init() -> void:
	call_deferred("_run")

func _body(parent: Node) -> Dictionary:
	var actor := ReplicatedActor3D.new()
	parent.add_child(actor)
	actor.set_process(false)
	actor.set_physics_process(false)
	var model := Node3D.new()
	model.name = "NativeModel"
	actor.add_child(model)
	var skeleton := Skeleton3D.new()
	skeleton.add_bone("Root")
	model.add_child(skeleton)
	var counts := {"calls": 0}
	var modifier := CountingModifier.new()
	modifier.counts = counts
	skeleton.add_child(modifier)
	var player := AnimationPlayer.new()
	model.add_child(player)
	var clip := Animation.new()
	clip.length = 4.0
	clip.loop_mode = Animation.LOOP_LINEAR
	var track := clip.add_track(Animation.TYPE_VALUE)
	clip.track_set_path(track, NodePath("..:position"))
	clip.track_insert_key(track, 0.0, Vector3.ZERO)
	clip.track_insert_key(track, 4.0, Vector3.RIGHT)
	var library := AnimationLibrary.new()
	library.add_animation("slide", clip)
	player.add_animation_library("", library)
	player.play("slide")
	actor._native_model = model
	actor._native_skeleton = skeleton
	actor.animation_player = player
	return {"actor": actor, "skeleton": skeleton, "player": player, "counts": counts}

func _run() -> void:
	var rider := _body(root)
	var actor := rider.actor as ReplicatedActor3D
	var gate := RecordingGate.new()
	actor.set_animation_tier(AnimationGate.Tier.HALF, gate)
	_expect(gate.apply_calls == 1 and gate.half_rate_count() == 1,
		"the ordinary rider positively enters the real animation gate")
	gate.advance(0.05)
	gate.advance(0.05)
	await _drain()
	_expect(int(rider.counts.calls) > 0 and (rider.player as AnimationPlayer).current_animation_position > 0.0,
		"ordinary gate stepping positively drives the real skeleton modifier and player")
	var visual := Mounted.new()
	actor.add_child(visual)
	visual.set_process(false)
	# These are owned children in the normal configure path, which intentionally
	# is not used by this asset-free ownership fixture.
	visual.add_child(visual.reins)
	var mount := _body(visual)
	visual.actor = actor
	visual.pony = mount.actor
	actor._mount_visual = visual
	(rider.skeleton as Skeleton3D).modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	(mount.skeleton as Skeleton3D).modifier_callback_mode_process = Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
	(mount.skeleton as Skeleton3D).advance(0.01)
	await _drain()
	_expect(int(mount.counts.calls) > 0, "the mount's real modifier also has a positive control")
	var player := rider.player as AnimationPlayer
	var position := player.current_animation_position
	var applied := gate.apply_calls
	var rider_calls := int(rider.counts.calls)
	var mount_calls := int(mount.counts.calls)
	for tier: int in [AnimationGate.Tier.FULL, AnimationGate.Tier.HALF,
			AnimationGate.Tier.QUARTER, AnimationGate.Tier.PAUSED]:
		actor.set_animation_tier(tier, gate)
		visual.set_process(false)
		_expect(gate.apply_calls == applied and gate.half_rate_count() == 0 and gate.quarter_rate_count() == 0,
			"mounted tier changes use membership-only discard, never ordinary pause/apply")
		_expect(not player.active and player.callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL,
			"the mounted player's clock remains inactive and manual")
		_expect((rider.skeleton as Skeleton3D).modifier_callback_mode_process == Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL
			and (mount.skeleton as Skeleton3D).modifier_callback_mode_process == Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL,
			"rider and mount modifiers remain on the manual owner")
		gate.advance(0.1)
		_expect(is_equal_approx(player.current_animation_position, position),
			"the ordinary gate cannot advance the mounted player")
	await _drain()
	_expect(int(rider.counts.calls) == rider_calls and int(mount.counts.calls) == mount_calls,
		"tier and gate changes queue no new automatic real modifier passes")
	gate.gate_skeletons = false
	actor.set_animation_tier(AnimationGate.Tier.PAUSED, gate)
	visual.set_process(false)
	_expect(actor.animation_tier() == AnimationGate.Tier.FULL and actor.model_processing()
		and (mount.actor as ReplicatedActor3D).model_processing(),
		"disabling gate-skeleton policy keeps mounted presentation full rate")
	actor.pause_for_parking(gate)
	_expect(actor.animation_tier() == AnimationGate.Tier.PAUSED and not actor.model_processing()
		and not (mount.actor as ReplicatedActor3D).model_processing() and gate.apply_calls == applied,
		"parking overrides that policy without returning either callback to idle")
	actor.set_animation_tier(AnimationGate.Tier.HALF, gate)
	visual.set_process(false)
	_expect(actor.animation_tier() == AnimationGate.Tier.FULL, "revival retains the disabled-gate policy")
	gate.gate_skeletons = true
	actor._selected = true
	actor.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	visual.set_process(false)
	_expect(actor.animation_tier() == AnimationGate.Tier.FULL, "selected mounted presentation retains priority")
	actor._selected = false
	actor._combat_target = true
	actor.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	visual.set_process(false)
	_expect(actor.animation_tier() == AnimationGate.Tier.FULL, "combat-target mounted presentation retains priority")
	actor._combat_target = false
	actor._render_quality_local_actor = true
	actor.set_animation_tier(AnimationGate.Tier.QUARTER, gate)
	visual.set_process(false)
	_expect(actor.animation_tier() == AnimationGate.Tier.FULL, "local mounted presentation retains priority")
	actor._render_quality_local_actor = false
	actor.set_animation_tier(AnimationGate.Tier.HALF, gate)
	visual.set_process(false)
	actor.set_mount_state({}, {})
	_expect(not is_instance_valid(actor._mount_visual) and gate.apply_calls == applied + 1
		and gate.half_rate_count() == 1 and player.active,
		"dismount positively returns the same rider to ordinary stepped ownership once")
	var before_dismount := int(rider.counts.calls)
	gate.advance(0.05)
	gate.advance(0.05)
	await _drain()
	_expect(int(rider.counts.calls) > before_dismount and player.current_animation_position > position,
		"ordinary player and real modifier processing resume after dismount")
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	gate.reset(false)
	await _drain()
	actor.queue_free()
	await _drain()
	print("mounted gate ownership: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame

func _expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
