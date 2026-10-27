extends SceneTree
## Real Human equipment/action integration. The optional native binary is not
## required: its thin choose_action wrapper is exercised with controlled native
## outputs and the real actor sink, including the once-only swing counter.
const POLISH := preload("res://src/actors/human_locomotion_polish.gd")
const Remote := preload("res://src/runtime/remote_presentation.gd")
var checks := 0
var failures := 0
var adapter := CoordinateAdapter.new({"walkingHeight":0.0})
var models: Dictionary
var equipment: Dictionary
var animations: Dictionary
var starts: Array[StringName] = []
var metrics: Array = []
var previous_pair_pattern: Array[StringName] = []

class NativeActionOutput extends Remote:
	var selected := -1
	var restart := false
	func owns(_node) -> bool: return true
	func _event(node, operation: int, values: PackedFloat64Array, _width := 5) -> Dictionary:
		if operation == 7 and selected >= 0 and bool(values[3]) and bool(values[5]):
			# The native decision already advances the occurrence counter before
			# the real wrapper chooses the Human shuffle's presentation alias.
			node._swing_index += 1
		return {"meta":PackedInt64Array([0,0,0,0,0,selected,int(restart)])}

func _init() -> void: run.call_deferred()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func make_actor(slug: String, id: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new(); actor.apply_render_quality(1,true); root.add_child(actor)
	var errors := actor.configure({"actor_id":id,"actor_type":0 if slug=="luminous_female" else 1,
		"x":0,"y":0,"rotation":0,"kind":1,"name":"","health":100,"max_health":100,
		"appearance":{},"equipment_visuals":{},"command":7,"command_sequence":0},
		adapter,models[slug],animations,equipment)
	expect(errors.is_empty(), slug+" native rig configures")
	actor.set_process(false); actor.set_physics_process(false)
	actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	actor.animation_player.animation_started.connect(func(clip: StringName) -> void: starts.append(clip))
	return actor

func expected_melee(actor: ReplicatedActor3D, clips: PackedStringArray, guard: StringName, run: StringName, label: String) -> void:
	expect(actor.resolver.clip_for_action(&"attack_primary") == StringName(clips[0]) and actor.resolver.clip_for_action(&"attack_secondary") == StringName(clips[1]), label+" selects the correct two attack clips")
	expect(actor.resolver.clip_for_action(&"combat_idle") == guard, label+" selects the correct combat guard")
	expect(actor.resolver.clip_for_action(&"run") == run, label+" selects the actual held-hand running mask")

func protected_pose(actor: ReplicatedActor3D) -> Array:
	var rig := actor.get_skeleton(); var values: Array = []
	# Held weapon aiming can turn the wrist. Its origin and all upstream body
	# motion remain fixed while only the grip animation variant changes.
	for name: String in ["pelvis","spine_01","spine_03","thigh_l","thigh_r","calf_l","calf_r","foot_l","foot_r","upperarm_l","upperarm_r","lowerarm_l","lowerarm_r"]:
		values.append(rig.get_bone_global_pose(rig.find_bone(name)))
	for side: String in ["l","r"]:
		values.append(rig.get_bone_global_pose(rig.find_bone("hand_"+side)).origin)
	return values

func run_swap(actor: ReplicatedActor3D, gear: Dictionary, expected: StringName, label: String) -> void:
	var player := actor.animation_player
	actor._in_combat = false; actor._segment_duration = 0.0; actor._movement_coast_remaining = 0.0; actor._presentation_speed = 5.0
	actor.play_action(&"run",true); player.advance(0.2)
	player.seek(player.current_animation_length*0.37,true); actor.get_skeleton().force_update_all_bone_transforms()
	var phase := player.current_animation_position/player.current_animation_length
	var speed := player.speed_scale; var before := protected_pose(actor)
	actor.apply_equipment_visuals(gear)
	player.advance(0.0); actor.get_skeleton().force_update_all_bone_transforms()
	expect(actor.current_action == &"run" and player.current_animation == expected, label+" keeps the semantic run and updates its grip clip")
	expect(absf(player.current_animation_position/player.current_animation_length-phase)<0.000001, label+" preserves the stride phase")
	expect(is_equal_approx(player.speed_scale,speed), label+" preserves the accepted stride speed")
	expect(protected_pose(actor) == before, label+" preserves accepted nonfinger body motion and wrist positions")

func equipment_cases(actor: ReplicatedActor3D, label: String) -> void:
	var unarmed := PackedStringArray(["Fighting_Left_Jab","Fighting_Right_Jab"])
	var right := POLISH.ATTACKS.normal_clips("r"); var left := POLISH.ATTACKS.normal_clips("l")
	expected_melee(actor,unarmed,&"Fighting_Idle",&"Run_Female",label+" initially empty")
	run_swap(actor,{0:114},&"Human_Run_Hold_R",label+" draw main sword")
	expected_melee(actor,right,POLISH.ATTACKS.guard_clip(),&"Human_Run_Hold_R",label+" main sword")
	run_swap(actor,{},&"Run_Female",label+" remove main sword")
	expected_melee(actor,unarmed,&"Fighting_Idle",&"Run_Female",label+" empty again")
	run_swap(actor,{1:160},&"Human_Run_Hold_L",label+" offhand blade")
	expected_melee(actor,left,POLISH.ATTACKS.guard_clip(),&"Human_Run_Hold_L",label+" offhand blade")
	run_swap(actor,{1:106},&"Human_Run_Hold_L",label+" shield only")
	expected_melee(actor,unarmed,&"Fighting_Idle",&"Human_Run_Hold_L",label+" shield only")
	run_swap(actor,{0:164},&"Human_Run_Hold_L",label+" starter bow")
	var carry = actor._weapon_carry
	expect(carry != null, label+" bow has its actual carry modifier")
	if carry != null:
		var hands: Array = carry.get("_hands")
		expect(hands.size() == 1 and str(hands[0].get("side","")) == "l" and bool(hands[0].get("finger_only",false)), label+" starter bow owns only the live left hand, not the hidden right prop")
	run_swap(actor,{0:114,1:160},&"Human_Run_Hold_Both",label+" dual blades")
	expected_melee(actor,right,POLISH.ATTACKS.guard_clip(),&"Human_Run_Hold_Both",label+" dual blades")
	run_swap(actor,{},&"Run_Female",label+" remove both hands")

func shuffle_properties(actor: ReplicatedActor3D, label: String) -> void:
	var pattern: Array[StringName] = []
	var before := actor._swing_index
	for pair: int in range(64):
		var first := actor._melee_action_at(pair*2)
		var second := actor._melee_action_at(pair*2+1)
		pattern.append(first)
		expect(first != second and first in [&"attack_primary",&"attack_secondary"] and second in [&"attack_primary",&"attack_secondary"], label+" every shuffled pair contains opposing first/second directions")
		expect(first == actor._melee_action_at(pair*2) and second == actor._melee_action_at(pair*2+1), label+" the same actor/occurrence counter repeats the same selection")
	expect(pattern.has(&"attack_primary") and pattern.has(&"attack_secondary"), label+" both first directions occur across64pairs")
	expect(actor._swing_index == before, label+" looking up a shuffle never consumes an occurrence")
	if not previous_pair_pattern.is_empty(): expect(pattern != previous_pair_pattern, "different Human actor IDs produce different direction sequences")
	previous_pair_pattern=pattern

func server_strikes(actor: ReplicatedActor3D, label: String, human := true) -> void:
	actor.apply_equipment_visuals({0:114}); actor._segment_duration=0.0; actor._movement_coast_remaining=0.0; actor._in_combat=true
	actor.play_action(&"combat_idle",true); actor.animation_player.advance(0.2)
	actor._swing_index=0; actor._last_command_sequence=100
	var pair: Array[StringName] = []
	for index: int in range(8):
		var dto := {"x":0,"y":0,"rotation":0,"command":46,"command_sequence":101+index,
			"health":100,"alive":true,"in_combat":true,"equipment_visuals":{0:114}}
		var before := actor._swing_index
		actor.apply_server_state(dto,adapter)
		expect(actor._swing_index == before+1, label+" a fresh server attack advances one occurrence")
		expect(actor.current_action == actor._melee_action_at(before), label+" selects the occurrence's ordered/shuffled action")
		if not human: expect(actor.current_action == (&"attack_primary" if index%2==0 else &"attack_secondary"), "nonHuman retains original alternating attacks")
		pair.append(actor.current_action)
		if pair.size() == 2:
			expect(pair.has(&"attack_primary") and pair.has(&"attack_secondary"), label+" each pair contains both opposing strikes")
			pair.clear()
		var player := actor.animation_player
		expect(player.get_animation(player.current_animation) == player.get_animation(actor.resolver.clip_for_action(actor.current_action)), label+" selected cut or restart alias uses the intended shared resource")
		player.advance(0.08)
		var time := player.current_animation_position; var started := starts.size(); var action := actor.current_action
		actor.apply_server_state(dto,adapter)
		expect(actor._swing_index == before+1 and actor.current_action == action, label+" a replayed state never consumes another strike")
		expect(starts.size() == started and is_equal_approx(player.current_animation_position,time), label+" a replayed attack never restarts its clip clock")

func finish_actions(actor: ReplicatedActor3D, label: String) -> void:
	for armed: bool in [false,true]:
		actor.apply_equipment_visuals({0:114} if armed else {})
		for combat: bool in [false,true]:
			actor._in_combat=combat; actor._segment_duration=0.0; actor._movement_coast_remaining=0.0
			for action: StringName in [&"attack_primary",&"attack_secondary",&"attack_flurry",&"attack_flurry_secondary"]:
				actor.play_action(action,true)
				var player := actor.animation_player
				expect(actor.current_action == action, label+" normal/flurry starts "+str(action))
				player.advance(player.current_animation_length/maxf(absf(player.speed_scale),0.01)+0.2)
				expect(actor.current_action == (&"combat_idle" if combat else &"idle"), label+" one-shot returns to combat guard or standing idle")
				var expected := POLISH.ATTACKS.guard_clip() if armed and combat else &"Fighting_Idle" if combat else actor.resolver.clip_for_action(&"idle")
				expect(player.get_animation(player.current_animation) == player.get_animation(expected), label+" recovery uses fitted armed guard/raw empty guard/standing idle")

func transient_updates(actor: ReplicatedActor3D, label: String) -> void:
	actor.apply_equipment_visuals({})
	# Legacy records omit occurrence IDs. Modern records can restate the same
	# command while updating combat state. Neither is a new swing/idle request.
	for native_fallback: bool in [false,true]:
		for legacy: bool in [true,false]:
			for action: StringName in [&"attack_primary",&"attack_flurry",&"attack_flurry_secondary"]:
				actor._in_combat=false; actor._segment_duration=0.0; actor._movement_coast_remaining=0.0
				actor._last_command_sequence=-1 if legacy else 100
				actor.play_action(action,true); actor.animation_player.advance(0.1)
				var clock := actor.animation_player.current_animation_position
				var started := starts.size(); var occurrence := actor._swing_index
				var dto: Dictionary = {"x":0,"y":0,"rotation":0,"command":7,"in_combat":not legacy,"health":100,"alive":true,"equipment_visuals":{}}
				if not legacy: dto.command_sequence=100
				if native_fallback: actor._apply_server_state_native(dto,adapter)
				else: actor.apply_server_state(dto,adapter)
				expect(actor.current_action == action, label+" existing normal/flurry one-shot survives legacy or same-sequence combat state updates")
				expect(starts.size() == started and is_equal_approx(actor.animation_player.current_animation_position,clock), label+" state-only update does not restart or replace an active flurry")
				expect(actor._swing_index == occurrence, label+" state-only update consumes no extra attack occurrence")

func native_wrapper(actor: ReplicatedActor3D, label: String, human := true) -> void:
	var service := NativeActionOutput.new(); root.add_child(service)
	actor._swing_index=0; actor._in_combat=true; actor._segment_duration=0.0; actor._movement_coast_remaining=0.0
	for index: int in range(4):
		service.selected=Remote.ACTIONS.find(&"attack_secondary"); service.restart=true
		var before := actor._swing_index
		expect(service.choose_action(actor,&"attack_primary",false,false,true,201+index,true), label+" real native wrapper handles a controlled native decision")
		expect(actor._swing_index == before+1, label+" wrapper consumes the already-advanced native occurrence only once")
		var expected := actor._melee_action_at(index) if human else &"attack_secondary"
		expect(actor.current_action == expected, label+" wrapper preserves Human shuffle/nonHuman native selection parity")
		actor.animation_player.advance(0.08)
		var clock := actor.animation_player.current_animation_position; var started := starts.size(); var action := actor.current_action
		service.selected=-1; service.restart=false
		expect(service.choose_action(actor,&"attack_primary",false,false,false,201+index,true), label+" replayed native output is handled")
		expect(actor._swing_index == before+1 and actor.current_action == action and starts.size() == started and is_equal_approx(actor.animation_player.current_animation_position,clock), label+" no native replay increments or restarts")
	service.free()

func run() -> void:
	models=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	equipment=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	animations=JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for slug: String in ["luminous_male","luminous_female"]:
		var actor := make_actor(slug,9100 if slug=="luminous_male" else 9101)
		shuffle_properties(actor,slug)
		equipment_cases(actor,slug)
		server_strikes(actor,slug)
		finish_actions(actor,slug)
		transient_updates(actor,slug)
		native_wrapper(actor,slug)
		metrics.append({"model":slug,"normal_clips":POLISH.ATTACKS.normal_clips(),"held_runs":POLISH.HELD_RUN_CLIPS})
		actor.free(); await process_frame
	var control := make_actor("orun_male",9190)
	expect(control.resolver.clip_for_action(&"run") == &"Run_Female", "nonHuman retains original run mapping")
	control.apply_equipment_visuals({0:114})
	expect(control.resolver.clip_for_action(&"attack_primary") == StringName(animations.actions.attack_primary) and control.resolver.clip_for_action(&"attack_secondary") == StringName(animations.actions.attack_secondary), "nonHuman retains original armed animation mappings")
	server_strikes(control,"orun_male",false)
	native_wrapper(control,"orun_male",false)
	control.free()
	var destination := OS.get_environment("RL_HUMAN_ANIMATION_METRICS")
	if not destination.is_empty(): FileAccess.open(destination,FileAccess.WRITE).store_string(JSON.stringify({"checks":checks,"failures":failures,"native_binary_executed":false,"native_choose_action_wrapper_executed":true,"models":metrics},"  "))
	print("Human animation integration: %d checks, %d failures; optional native binary absent, real wrapper with controlled outputs tested" % [checks,failures])
	quit(1 if failures else 0)
