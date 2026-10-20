extends SceneTree

var failures := 0
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0})

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func actor_fixture() -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var body := MeshInstance3D.new()
	body.name = "Body"
	body.mesh = BoxMesh.new()
	actor.add_child(body)
	actor.resolver = AnimationResolver.new({"actions": {"idle": "Idle", "death": "Death"},
		"serverCommands": {"3": "death", "7": "idle", "19": "idle"}})
	var player := AnimationPlayer.new()
	actor.add_child(player)
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var library := AnimationLibrary.new()
	var death := Animation.new()
	death.length = 2.0
	var track := death.add_track(Animation.TYPE_VALUE)
	death.track_set_path(track, "Body:rotation")
	death.track_insert_key(track, 0.0, Vector3.ZERO)
	death.track_insert_key(track, 2.0, Vector3(0.0, 0.0, PI / 2.0))
	library.add_animation("Death", death)
	var idle := Animation.new()
	idle.length = 1.0
	idle.loop_mode = Animation.LOOP_LINEAR
	library.add_animation("Idle", idle)
	player.add_animation_library("", library)
	actor.animation_player = player
	player.animation_finished.connect(actor._on_animation_finished)
	return actor

func dead_state(temporary := false, elapsed := 0.0) -> Dictionary:
	return {"x": 0, "y": 0, "rotation": 0, "health": 0, "alive": false, "command": 3,
		"death_presentation": {"temporary": temporary, "elapsed": elapsed,
			"animation_seconds": 3.0, "hold_seconds": 10.0, "fade_seconds": 10.0,
			"received_msec": Time.get_ticks_msec()}}

func run() -> void:
	var actor := actor_fixture()
	var dead := dead_state()
	actor.apply_server_state(dead, adapter)
	expect(actor.current_action == &"death" and actor.animation_player.is_playing(),
		"zero health starts the full death clip")
	actor.animation_player.advance(3.01)
	actor._process(3.01)
	var body := actor.get_node("Body") as MeshInstance3D
	expect(actor.death_animation_finished() and is_equal_approx(body.rotation.z, PI / 2.0),
		"death holds the exact final pose")
	actor.apply_server_state(dead, adapter)
	actor.play_action(&"death", true)
	actor.play_action(&"idle")
	expect(actor.current_action == &"death" and not actor.animation_player.is_playing()
		and is_equal_approx(body.rotation.z, PI / 2.0), "snapshots and late combat commands never restart a corpse")
	actor._process(600.0)
	expect(is_zero_approx(body.transparency), "normal corpses remain fully visible until respawn")
	var fallen_yaw := actor.rotation.y
	var stale_turn := dead.duplicate(true)
	stale_turn["rotation"] = 20000
	stale_turn["facing_command"] = 42
	actor.apply_server_state(stale_turn, adapter)
	actor._physics_process(1.0)
	expect(is_equal_approx(actor.rotation.y, fallen_yaw), "late turn packets cannot rotate a fallen body")
	actor.apply_server_state({"x": 0, "y": 0, "rotation": 0, "health": 17,
		"alive": true, "command": 7}, adapter)
	expect(actor.current_action == &"idle" and actor.animation_player.is_playing(),
		"authoritative healing releases the death pose")
	actor.free()

	actor = actor_fixture()
	actor.set("_is_creature", true)
	var ordinary_dead := dead_state(false)
	ordinary_dead.death_presentation.hold_seconds = 3.0
	ordinary_dead.death_presentation.fade_seconds = 4.0
	actor.apply_server_state(ordinary_dead, adapter)
	actor._process(10.0)
	expect(is_equal_approx(actor.get_node("Body").transparency, 1.0), "ordinary creature corpses also clear after the held pose and fade")
	actor.apply_server_state({"x":0,"y":0,"rotation":0,"health":20,"alive":true,"command":7},adapter)
	expect(is_zero_approx(actor.get_node("Body").transparency), "respawning restores a faded ordinary creature")
	actor.free()

	actor = actor_fixture()
	actor.apply_server_state(dead_state(true, 8.0), adapter)
	body = actor.get_node("Body") as MeshInstance3D
	expect(actor.death_animation_finished() and is_equal_approx(body.rotation.z, PI / 2.0),
		"a late viewer sees the corpse's final pose immediately")
	actor._process(4.9)
	expect(is_zero_approx(body.transparency), "temporary corpses hold for ten seconds after the clip")
	actor._process(5.1)
	expect(absf(body.transparency - 0.5) < 0.01, "temporary corpses fade halfway over the next ten seconds")
	actor._process(5.0)
	expect(is_equal_approx(body.transparency, 1.0),
		"the body disappears after the fade")
	actor.free()
	await process_frame
	_test_creature_dissolve()

	var state := root.get_node("AppState")
	state.actors[9] = {"health": 0, "max_health": 100, "alive": false, "command": 3,
		"death_presentation": {"temporary": false}}
	state._apply_actor_health_delta(9, 25)
	expect(state.actors[9].alive and state.actors[9].command == 7
		and not state.actors[9].has("death_presentation"), "healing clears stale death commands in replicated state")

	actor = actor_fixture()
	actor.apply_server_state(dead_state(), adapter)
	var panel := preload("res://src/ui/death_panel.gd").new()
	panel.actor_for_player = func() -> Variant: return actor
	root.add_child(panel)
	state.authenticated = true
	state.death = {"dead": true, "ready": false, "remaining": 30.0,
		"received_msec": Time.get_ticks_msec()}
	panel._process(0.0)
	expect(panel.visible and not panel.respawn.visible, "Respawn Now stays hidden during the server timer")
	state.death.ready = true
	panel._process(0.0)
	expect(not panel.respawn.visible, "Respawn Now waits for the death clip to finish too")
	actor._process(3.1)
	panel._process(0.0)
	expect(panel.respawn.visible and panel.respawn.text == "Respawn Now", "Respawn Now appears when both waits finish")
	state.death = {"dead": false}
	panel._process(0.0)
	expect(not panel.visible, "revival closes the death controls")
	panel.free()
	actor.free()
	state._on_connection_state_changed("disconnected")

	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	state.local_actor_id = 9
	state.actors[10] = {"kind": 1, "health": 0, "alive": false}
	var heal_id := -1
	var harm_id := -1
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json"))
	for spell: Dictionary in catalog.spells:
		if spell.scope == "target" and spell.effect == "heal": heal_id = int(spell.id)
		if spell.scope == "target" and spell.effect == "harm": harm_id = int(spell.id)
	expect(main._spell_target_candidate(heal_id, 10), "targeted healing can select a fallen player")
	expect(not main._spell_target_candidate(harm_id, 10), "hostile spells cannot select a fallen player")
	state.actors[10].kind = 3
	expect(not main._spell_target_candidate(heal_id, 10), "targeted healing cannot revive dead creatures")
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	for model_name: String in ["red_fox", "mossback_boar"]:
		actor = ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models.models[model_name]
		# Import the shipped source directly; lean checkouts need no editor cache.
		var model_path := ProjectSettings.globalize_path(str(config.scene))
		GlbSceneCache.install_prepared({model_path: GlbSceneCache._build_raw(model_path)})
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
		var dto := dead_state()
		dto.merge({"actor_id": 30, "kind": 3, "name": "", "appearance": {}, "equipment_visuals": {}})
		var errors := actor.configure(dto, adapter, config, animations)
		expect(errors.is_empty(), model_name + " imports its shipped death animation: " + ", ".join(errors))
		actor.apply_server_state(dto, adapter)
		if actor.animation_player != null:
			actor.animation_player.advance(3.01)
			actor._process(3.01)
			expect(actor.death_animation_finished(), model_name + " finishes its death clip and holds")
			var clip := actor.resolver.clip_for_action(&"death")
			expect(actor.animation_player.has_animation(clip)
				and is_equal_approx(actor.animation_player.current_animation_position,
					actor.animation_player.get_animation(clip).length), model_name + " freezes at the last authored key")
		actor.free()
	NativeAnimationImporter.clear()
	main.queue_free()
	state._on_connection_state_changed("disconnected")
	await process_frame
	print("DEATH PRESENTATION: ", failures, " failures")
	quit(failures)

func _test_creature_dissolve() -> void:
	var actor := actor_fixture()
	actor.set("_is_creature", true)
	var body := actor.get_node("Body") as MeshInstance3D
	var original := StandardMaterial3D.new()
	original.albedo_color = Color("6c553c")
	body.material_override = original
	# Another creature shares the mesh and material, as the runtime cache does.
	var neighbor := MeshInstance3D.new()
	neighbor.mesh = body.mesh
	neighbor.material_override = original
	root.add_child(neighbor)
	var dead := dead_state(true, 0.0)
	dead.death_presentation.hold_seconds = 3.0
	dead.death_presentation.fade_seconds = 4.0
	actor.apply_server_state(dead, adapter)
	actor._process(3.0)
	expect(actor.death_animation_finished() and actor.get("_corpse_dissolve") == null,
		"temporary creature finishes its death clip before the dissolve delay begins")
	actor._process(1.99)
	expect(actor.get("_corpse_dissolve") == null, "temporary creature holds its full body for two seconds after the death clip")
	actor._process(0.02)
	var material := body.get_active_material(0) as ShaderMaterial
	expect(material != null and float(material.get_shader_parameter("dissolve_progress")) > 0.0
		and float(material.get_shader_parameter("dissolve_progress")) < 0.01,
		"dissolve starts immediately after the two-second hold despite the longer server cleanup hold")
	actor._process(1.19)
	var effect: RefCounted = actor.get("_corpse_dissolve")
	expect(effect != null and material != null and is_zero_approx(body.transparency),
		"temporary creatures break into opaque patches instead of fading the whole body")
	expect(material != null and absf(float(material.get_shader_parameter("dissolve_progress")) - 0.3) < 0.01,
		"dissolve keeps its four-second duration after the two-second hold")
	var ash := actor.get_node_or_null("DissolveAsh") as MultiMeshInstance3D
	expect(ash != null and ash.multimesh.instance_count > 0 and ash.multimesh.instance_count <= 512 and ash.layers == 2,
		"surface dust uses one bounded batch excluded from map cameras")
	expect(neighbor.get_active_material(0) == original and body.mesh.surface_get_material(0) == null,
		"dissolving never changes another creature's shared mesh or material")
	actor.apply_server_state(dead, adapter)
	expect(actor.get("_corpse_dissolve") == effect, "restated death snapshots keep the existing dissolve")
	actor._process(3.0)
	expect(is_equal_approx(body.transparency, 1.0) and not ash.visible,
		"body and drifting fragments finish before server cleanup")
	actor.apply_server_state({"x": 0, "y": 0, "rotation": 0, "health": 20, "alive": true, "command": 7}, adapter)
	expect(body.material_override == original and is_zero_approx(body.transparency)
		and actor.get_node_or_null("DissolveAsh") == null, "revival restores original materials and removes all dust")
	actor.free()
	neighbor.free()
	actor = actor_fixture()
	actor.set("_is_creature", true)
	dead.death_presentation.elapsed = 7.0
	dead.death_presentation.received_msec = Time.get_ticks_msec()
	actor.apply_server_state(dead, adapter)
	material = (actor.get_node("Body") as MeshInstance3D).get_active_material(0) as ShaderMaterial
	expect(material != null and absf(float(material.get_shader_parameter("dissolve_progress")) - 0.5) < 0.02,
		"a late viewer joins the dissolve halfway through without replaying it")
	actor.free()
	actor = actor_fixture()
	actor.set("_is_creature", true)
	dead.death_presentation.elapsed = 20.0
	dead.death_presentation.received_msec = Time.get_ticks_msec()
	actor.apply_server_state(dead, adapter)
	expect(actor.get("_corpse_dissolve") == null and actor.get_node_or_null("DissolveAsh") == null,
		"already expired corpses allocate no dissolve or particle resources")
	actor.free()
