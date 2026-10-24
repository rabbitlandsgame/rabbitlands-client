extends SceneTree
## A shot/channel can replace the last walk command before interpolation ends.
## No idle packet is required for the animal to stop after that final step.
class TimedActor extends ReplicatedActor3D:
	var clock_msec := 100000
	func _movement_time_msec() -> int: return clock_msec

const Profiles := preload("res://src/mounts/mount_profiles.gd")
const ACTIONS := [&"ranged_draw", &"ranged_hold", &"ranged_attack", &"cast",
	&"cast_aggressive", &"cast_defensive", &"heal", &"cast_channel_enter", &"cast_channel", &"cast_exit"]
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func advance(actor: TimedActor, seconds: float) -> void:
	actor.clock_msec += roundi(seconds*1000.0)
	actor._physics_process(seconds)

func finish_step(actor: TimedActor) -> void:
	advance(actor, actor._segment_duration + actor.movement_coast_seconds + 1.0)
	expect(actor._segment_duration == 0.0 and actor.global_position == actor.server_target,"final tile really arrived")

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"walkingHeight":0.0})
	var ids: Array = Profiles.PATHS.keys()
	if "--pony" in OS.get_cmdline_user_args(): ids = ["moor_pony"]
	for id: String in ids:
		var actor := TimedActor.new()
		root.add_child(actor)
		expect(actor.configure({"actor_id":42,"x":0,"y":0,"rotation":0,"kind":1,"name":""},adapter,models.luminous_male,mapping).is_empty(),"rider loads")
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.apply_server_state({"x":0,"y":0,"rotation":0,"command":7},adapter,true)
		var tile := 0
		for gait: String in ["cruise","burst"]:
			actor.set_mount_state({"mode":"mounted","mount_id":id,"gait":gait,"step_us":100000 if gait == "burst" else 133333},models)
			var visual: Variant = actor._mount_visual
			visual.set_process(false)
			for requested: StringName in ACTIONS:
				actor.play_action(&"idle")
				for frame: int in 4: visual._process(1.0)
				tile += 1
				actor.apply_server_state({"x":tile,"y":0,"rotation":0,"command":22},adapter)
				advance(actor,actor._segment_duration * .5)
				actor.play_action(requested,true)
				visual._process(.01)
				expect(visual.action == ("gallop" if gait == "burst" else "trot"),"attack keeps movement while a real step is active")
				finish_step(actor)
				var stopped := actor.global_transform
				visual._process(.01)
				expect(visual.action == "idle",id+" "+str(requested)+" stops without an idle command")
				expect(visual.pony.animation_player.assigned_animation == visual.profile.clips.idle,"animal plays its native idle")
				expect(visual.upper.ground_action == &"idle","no stale walk/run survives the attack")
				expect(not visual.upper.action.is_empty() and not visual.upper._returning,"arrival preserves the shot or channel")
				expect(actor.global_transform.is_equal_approx(stopped) and actor._mount_visual == visual,"stationary action stays seated in place")
				# Starting another step while aiming must resume locomotion without
				# cancelling the upper-body action, including the selected fast gait.
				tile += 1
				actor.apply_server_state({"x":tile,"y":0,"rotation":0,"command":22},adapter)
				visual._process(.01)
				expect(visual.action == ("gallop" if gait == "burst" else "trot") and not visual.upper.action.is_empty(),"moving again resumes the selected gait during the action")
				finish_step(actor)
				for frame: int in 6: visual._process(.5)
				expect(visual.action == "idle","held and completed actions cannot restart a stopped mount")
				if requested in [&"ranged_draw", &"ranged_hold", &"cast_channel_enter", &"cast_channel"]:
					expect(not visual.upper.action.is_empty() and not visual.upper._returning,"idle mount preserves held aim/channel")
			actor.set_mount_state({},models)
		actor.free()
	print("MOUNTED_STATIONARY_ACTION_CHECKS ",checks," failures=",failures)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
