extends SceneTree
## Verify native escort motion, capture attachment, branch dialogue and replay
## against the shared controller, without supplying any gameplay proof.
const Scene := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Actor extends Node3D:
	var staged := 0
	func set_cinematic_presentation(point: Vector3, yaw: float, _action: StringName, _speed: float) -> void:
		staged += 1
		global_position = point
		rotation.y = yaw

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
	print("Rescue scene checks: ", checks, "; failures: ", failures)
	quit(1 if failures else 0)
