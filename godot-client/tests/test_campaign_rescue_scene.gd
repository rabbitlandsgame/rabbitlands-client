extends SceneTree
## Verify native escort motion, capture attachment, branch dialogue and replay
## against the shared controller, without supplying any gameplay proof.
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Actor extends Node3D:
	var staged := 0
	var released := 0
	var last_action: StringName
	func set_cinematic_presentation(point: Vector3, yaw: float, action: StringName, _speed: float) -> void:
		staged += 1
		last_action = action
		global_position = point
		rotation.y = yaw
	func end_cinematic_presentation() -> void: released += 1

class Rig extends Node3D:
	var camera: Camera3D
	var focus := Vector3.ZERO
	var distance := 26.0
	var pitch_degrees := -60.0
	var yaw_degrees := 0.0

func _init() -> void: run.call_deferred()
func expect(value: bool, detail: String) -> void:
	checks += 1
	if value: print("PASS: ", detail)
	else:
		failures += 1
		push_error(detail)

func run() -> void:
	var scene := Scene.new()
	root.add_child(scene)
	var mother := Actor.new()
	var daughter := Actor.new()
	var carrier := Actor.new()
	for actor: Actor in [mother, daughter, carrier]: root.add_child(actor)
	carrier.position = Vector3(4, 0, 3)
	carrier.rotation.y = PI/2
	mother.position = Vector3(9, 0, 1)
	scene._actors = {"mother":mother,"daughter":daughter,"abductor":carrier}
	scene._posts = {"mother":mother.global_transform,"daughter":daughter.global_transform,"abductor":carrier.global_transform}
	scene._origin = Vector3.ZERO
	scene._definition = {"duration":40,"native_roles":["mother"],"cues":[
		{"at":0,"actor":"mother","offset":[100,0,0],"action":"walk"},
		{"at":0,"actor":"daughter","attach_to":"abductor","offset":[0.4,0.9,0.2],"face":"post"},
		{"at":8,"actor":"daughter","offset":[1,0,2],"visible":false,"when":"watch"}],
		"events":[{"id":"rescue_burn","type":"dissolve","at":20,"until":24,"request":true,"when":"watch"}]}
	scene._choice_state = {"selected":"watch"}
	scene.elapsed = 2
	scene._apply_actors()
	expect(mother.staged == 0 and mother.position == Vector3(9,0,1), "native mother movement remains under the server during the escort film")
	expect(daughter.global_position.is_equal_approx(carrier.global_transform*Vector3(0.4,0.9,0.2)), "the captive stays beside a turning carrier in the carrier's local frame")
	scene._definition.cues[1].ground_attachment = true
	scene._surface_sample = func(_point: Vector3) -> float: return 6.0
	scene._apply_actors()
	expect(is_equal_approx(daughter.global_position.y, 6.0), "a captive forced along uneven ground stays on the sampled terrain")
	scene._surface_sample = Callable()
	mother.position = Vector3(10,0,2)
	scene._apply_actors()
	expect(mother.position == Vector3(10,0,2), "a later authoritative escort step cannot be pulled back to an authored post")
	scene.elapsed = 10
	scene._apply_actors()
	expect(not daughter.visible and daughter.position == Vector3(1,0,2), "a later ordinary cue releases the capture attachment and can hide an offscreen role")
	scene._replaying = true
	scene._apply_actors()
	expect(mother.staged == 1, "read-only replay reconstructs the escort without issuing a native route")
	scene._replaying = false
	scene.playing = true
	scene.elapsed = 21
	var requests: Array[String] = []
	scene.event_requested.connect(func(id: String) -> void: requests.append(id))
	scene._request_scene_events()
	scene._request_scene_events()
	expect(requests == ["rescue_burn"], "an authorized presentation event requests its server action once")
	scene._event_emitted.clear()
	scene._replaying = true
	scene._request_scene_events()
	expect(requests.size() == 1, "replay can never request the corpse burn again")
	scene._choice_state.selected = "help"
	expect(scene.presentation_state().events.is_empty(), "the unselected branch cannot request a presentation event")
	var definitions := Scene.scene_definitions()
	for id: String in ["abduction","injured","commitment","descent","boss","captive","resolved","shadow"]:
		expect(definitions.has("measure.rescue."+id), "the authored rescue includes "+id)
	var snapshot := {"active":true,"kind":"rescue","run_id":"cache-run","map":"landfall_insides",
		"scene":{"id":"measure.rescue.shadow","actors":{"goblin_boss":20}}}
	var dtos := {20:{"actor_id":20,"name":"Goblin captor","health":0,"x":83,"y":62}}
	scene.remember_replay_cast(snapshot,dtos)
	dtos[20].name = "A later unrelated actor"
	snapshot.scene.actors.clear()
	scene._definition = {"cast_roles":["goblin_boss"]}
	scene._replaying = true
	var builds: Array[Dictionary] = []
	scene.configure_replay_actor_factory(func(dto: Dictionary, parent: Node3D, _adapter: CoordinateAdapter, _sample: Callable) -> Node3D:
		builds.append(dto)
		var visual := Actor.new()
		parent.add_child(visual)
		return visual)
	var live := {20:carrier}
	var replay := scene._replay_view_nodes(snapshot,live)
	expect(builds.size() == 1 and builds[0].name == "Goblin captor", "replay keeps an immutable copy of the real removed cast member")
	expect(replay[20] != carrier and live[20] == carrier, "a recycled live actor ID is never mistaken for the removed boss or overwritten")
	expect(scene._scene_bindings(snapshot.scene,snapshot).get("goblin_boss") == 20, "the final film can bind its removed boss for read-only replay")
	scene._replay_view_nodes(snapshot,live)
	expect(builds.size() == 1, "a replay reuses its scoped visual instead of creating one each frame")
	scene.remember_replay_cast({}, {})
	expect(scene._replay_visuals.is_empty() and scene._cast_templates.is_empty(), "leaving the active run releases all replay-only cast state")
	snapshot.scene.actors = {"goblin_boss":20}
	snapshot.scene.corpse_template = {"actor_id":20,"name":"Goblin captor","health":0,"x":83,"y":62}
	scene.remember_replay_cast(snapshot,{})
	scene._replaying = false
	scene._scene_id = "measure.rescue.shadow"
	var cutaway := scene._replay_view_nodes(snapshot,{})
	expect(cutaway.has(20) and builds.size() == 2, "a fresh client can show the authorized dead boss outside creature interest")
	scene.remember_replay_cast(snapshot,{20:{"actor_id":20,"name":"A new lich","health":20,"actor_type":671,"kind":2}})
	expect(scene._replay_view_nodes(snapshot,{20:carrier})[20] != carrier,
		"a reused actor ID cannot substitute a live lich for the recorded dead goblin")
	snapshot.scene.corpse_template.actor_type = 624
	snapshot.scene.corpse_template.kind = 5
	scene.remember_replay_cast(snapshot,{20:{"actor_id":20,"health":0,"actor_type":624,"kind":5,
		"death_presentation":{"hold_for_scene":false,"temporary":true,"elapsed":10}}})
	expect(scene._replay_view_nodes(snapshot,{20:carrier})[20] != carrier,
		"a fully dissolved native corpse cannot make the final replay body invisible")
	scene.remember_replay_cast(snapshot,{20:{"actor_id":20,"health":0,"actor_type":624,"kind":5,
		"death_presentation":{"hold_for_scene":true,"temporary":false,"elapsed":3}}})
	expect(scene._replay_view_nodes(snapshot,{20:carrier})[20] == carrier,
		"a real visible held boss is reused rather than duplicated during its live cutaway")
	expect(scene._replay_view_nodes(snapshot,{}).get(20) == cutaway[20], "the distant corpse visual remains scoped and stable during the cutaway")
	scene._scene_id = "measure.rescue.boss"
	expect(scene._replay_view_nodes(snapshot,{}).is_empty(), "the corpse fallback never creates a live combat target or substitutes the boss confrontation")
	scene.remember_replay_cast({}, {})
	scene._definition = {"duration":50,"events":[{"type":"fade","at":40,"until":50,"from":0,"to":1,"handoff":true,"when":"accept"}]}
	scene._choice_state = {"selected":"accept"}
	scene.elapsed = 28
	scene.playing = true
	scene._last_playback_replay = false
	expect(not scene.presentation_state().handoff_fade, "the accepted answer does not black out the remaining spoken follow-up")
	scene._returning = true
	scene._return_reason = "skipped"
	expect(scene.presentation_state().handoff_fade, "rapid Skip retains an authored accepted-transfer fade before the timed fade event")
	scene._replaying = true
	expect(not scene.presentation_state().handoff_fade, "replay never reserves a travel fade or narrative transfer")
	scene._replaying = false
	scene._returning = false
	scene.playing = false
	scene._last_return_reason = "finished"
	expect(scene.presentation_state().handoff_fade, "a completed live film retains the fade through the server handoff gap")
	scene._last_return_reason = "actor_lost"
	scene.elapsed = 50
	expect(not scene.presentation_state().handoff_fade, "an interrupted presentation cannot leave the world black")
	scene._definition.response_speakers = {"accept":"Elen Reed","defer":"Woman"}
	scene._choice_state.selected = "defer"
	expect(scene._response_speaker() == "Woman", "declining the rescue keeps the unnamed woman's caption")
	scene._choice_state.selected = "accept"
	expect(scene._response_speaker() == "Elen Reed", "agreeing introduces Elen in the emphasized speaker space")
	scene.playing = false
	scene.queue_free()
	for actor: Actor in [mother,daughter,carrier]: actor.queue_free()
	check_rescue_readiness()
	check_manual_rescue_dialogue()
	check_carry_and_native_handoff()
	print("Rescue scene checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)

func check_rescue_readiness() -> void:
	var scene := Scene.new()
	root.add_child(scene)
	scene._scene_id = "measure.rescue.abduction"
	scene._definition = {"anchor":"ramp","shots":[{"anchor":"ramp"}],
		"cues":[{"from":"ramp","destination":"damage","face":"speaker_post"}]}
	scene._anchors = {"ramp":Vector3.ZERO,"damage":Vector3(1,0,0),
		"speaker_post":Vector3(2,0,0),"mine_entry":Vector3(100,0,0)}
	scene._surface_sample = func(point: Vector3) -> float: return NAN if point.x > 10.0 else 3.0
	expect(scene._anchors_ready(), "unloaded distant mine terrain cannot hold the ramp film before its dialogue")
	scene._surface_sample = func(point: Vector3) -> float: return NAN if point.x > 0.5 else 3.0
	expect(not scene._anchors_ready(), "a missing surface used by the current staging still waits")
	scene._definition.cues = [{"face":"speaker_post"}]
	expect(not scene._anchors_ready(), "a facing point used by the current conversation also needs its surface")
	scene._scene_id = "measure.ferry.opening"
	scene._surface_sample = func(point: Vector3) -> float: return NAN if point.x > 10.0 else 3.0
	expect(not scene._anchors_ready(), "legacy scenes preserve their existing full-anchor readiness")
	scene._scene_id = "measure.rescue.commitment"
	scene._variant = "returned"
	scene._definition = (Scene.scene_definitions()[scene._scene_id] as Dictionary).duplicate(true)
	scene._apply_scene_variant()
	scene._anchors = {"entrance_focus":Vector3.ZERO,"mother_intercept":Vector3(100,0,0)}
	expect(scene._definition.anchor == "entrance_focus" and scene._anchors_ready(),
		"returning to the mine uses its effective entrance shots and origin without waiting for ramp terrain")
	scene._surface_sample = func(_point: Vector3) -> float: return NAN
	expect(not scene._anchors_ready(), "the returned mine conversation still waits for its actual entrance surface")
	scene.queue_free()

func check_manual_rescue_dialogue() -> void:
	var definitions := Scene.scene_definitions()
	for id: String in definitions:
		if not id.begins_with("measure.rescue."): continue
		var definition: Dictionary = definitions[id]
		var lines: Array = definition.get("lines", [])
		var holds: Array = definition.get("dialogue_holds", [])
		expect(lines.is_empty() or holds.is_empty() or float(holds[0]) > float(lines[0].at),
			id + " lets its first caption appear before the first reading pause")
	var scene := Scene.new()
	root.add_child(scene)
	scene.set_auto_dialogue(false, false)
	var rig := Rig.new()
	root.add_child(rig)
	rig.camera = Camera3D.new()
	rig.add_child(rig.camera)
	rig.camera.position = Vector3(0,5,10)
	rig.camera.look_at(Vector3.ZERO)
	var bindings := {}
	var nodes := {}
	var id := 1
	for role: String in definitions["measure.rescue.abduction"].required_actors:
		var actor := Actor.new()
		root.add_child(actor)
		bindings[role] = id
		nodes[id] = actor
		id += 1
	var anchors := {}
	for key: String in ["entry","mother_post","daughter_start","family_turn","mother_intercept",
		"daughter_trip","capture","escort_post","guard_post","player_help","player_watch",
		"ramp_top","ramp_middle","ramp_toe","recovery","mother_turn","guard_strike",
		"escape_turn","escape_turn_2","guard_combat"]:
		anchors[key] = [anchors.size(),0]
	anchors.mine_entry = [100,0]
	anchors.entrance_focus = [100,0]
	var snapshot := {"active":true,"kind":"rescue","run_id":"manual-ramp","map":"landfall",
		"anchors":anchors,"scene":{"id":"measure.rescue.abduction","token":"manual-ramp:abduction","actors":bindings}}
	var adapter := CoordinateAdapter.new()
	var sample := func(point: Vector3) -> float: return NAN if point.x >= 100.0 else 0.0
	var local_id := int(bindings.protagonist)
	scene.update(2.1,snapshot,rig,nodes,local_id,"landfall",true,adapter,sample)
	expect(scene.playing and scene._layer.visible and not scene._caption.text.is_empty(),
		"manual ramp playback shows its first caption while distant mine terrain remains unloaded")
	expect(scene._line_continue.visible and scene.continue_dialogue(),
		"Continue is immediately available on the first actual rescue caption")
	scene.update(0.0,snapshot,rig,nodes,local_id,"landfall",true,adapter,sample)
	expect(scene._dialogue.speaker_label.text == "Girl" and scene._caption.text == "Mum! My foot—"
		and scene._dialogue._actor.get_ref() == nodes[bindings.daughter],
		"one Continue advances to the next speaker and binds her portrait without an empty pause or extra click")
	scene.cancel("test_complete")
	scene.queue_free()
	rig.queue_free()
	for actor: Actor in nodes.values(): actor.queue_free()

func check_carry_and_native_handoff() -> void:
	var scene := Scene.new()
	root.add_child(scene)
	var hero := Actor.new()
	var carrier := Actor.new()
	var child := Actor.new()
	for actor: Actor in [hero,carrier,child]: root.add_child(actor)
	carrier.position = Vector3(4,0,3)
	carrier.rotation.y = PI/2
	var skeleton := Skeleton3D.new()
	carrier.add_child(skeleton)
	skeleton.scale = Vector3.ONE * 0.676024
	skeleton.rotation.z = 0.5
	skeleton.add_bone("spine_3")
	skeleton.set_bone_rest(0,Transform3D(Basis.IDENTITY,Vector3(0,1.4,0)))
	skeleton.force_update_all_bone_transforms()
	scene._actors = {"protagonist":hero,"abductor":carrier,"daughter":child}
	for role: String in scene._actors: scene._posts[role] = scene._actors[role].global_transform
	scene._anchors = {"downramp":Vector3(0,0,-5)}
	scene._definition = {"duration":68,"cues":[
		{"at":0,"actor":"protagonist","action":"idle","face":"downramp"},
		{"at":16,"actor":"daughter","action":"injury_pinned","attach_to":"abductor",
			"attach_bone":"spine_3","attach_yaw_degrees":90,"offset":[-.25,.10,.10]}]}
	scene.elapsed = 20
	scene._apply_actors()
	var shoulder := (skeleton.global_transform * skeleton.get_bone_global_pose(0)).origin
	var offset := carrier.global_basis.orthonormalized() * Vector3(-.25,.10,.10)
	expect(child.global_position.is_equal_approx(shoulder+offset),"a carried child follows the real shoulder without inheriting the imported skeleton's roll or scale")
	expect(child.last_action == &"injury_pinned" and is_equal_approx(child.rotation.y,PI),"the captive lies across the carrier instead of running beside him")
	var center := (hero.global_position+carrier.global_position)/2
	expect(scene._shot_anchor({"anchor_actors":["protagonist","abductor"]}).is_equal_approx(center),"the departure camera follows the actual pair's midpoint")
	var stages := hero.staged
	scene.elapsed = 42
	scene._apply_actors()
	scene._apply_actors()
	expect(hero.released == 0 and hero.staged == stages+2,"the player remains staged through the Help choreography until the film hands off to native combat")
	scene._replaying = true
	scene._apply_actors()
	expect(hero.staged == stages+3,"read-only replay retains the same authored choreography without native combat movement")
	scene._choice_state = {"selected":"accept"}
	scene._variant = "returned"
	expect(not scene._beat_matches({"when":"accept","unless_variant":"returned"}),"returning at the mine cannot replay the earlier departure or its fade")
	scene._variant = ""
	expect(scene._beat_matches({"when":"accept","unless_variant":"returned"}),"the original accepted rescue retains its departure")
	scene.queue_free()
	for actor: Actor in [hero,carrier,child]: actor.queue_free()
