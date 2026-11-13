extends SceneTree
## Companion eligibility, campaign-only refreshes and the real overhead vitals.
const Rescue := preload("res://tests/test_campaign_rescue.gd")
var checks := 0
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func make_actor(id: int, app: Node, main: Node) -> ReplicatedActor3D:
	var dto := {"actor_id": id, "kind": 2, "name": "Companion %d" % id,
		"x": 0, "y": 0, "rotation": 0, "health": 70, "max_health": 70}
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	expect(actor.configure(dto, CoordinateAdapter.new({}), {}, {}, {}, false).is_empty(),
		"the real banner configures without loading a body")
	actor.set_process(false)
	actor.set_physics_process(false)
	app.actors[id] = dto
	main.actor_nodes[id] = actor
	return actor

func run() -> void:
	var app := root.get_node("AppState")
	var main = (load("res://src/app/main.gd") as Script).new()
	app.authenticated = true
	app.current_map = "landfall"
	app.local_actor_id = 1
	app.combat_state = {"active": false, "target_id": -1}
	app.actors = {}
	app.campaign = {}
	var mother := make_actor(20, app, main)
	var villager := make_actor(21, app, main)
	main._sync_overhead_health()
	expect(not mother._health_bar_background.visible and not villager._health_bar_background.visible,
		"ordinary NPCs keep their name-only banners")
	app.campaign = Rescue.snapshot()
	main._on_state_changed(&"campaign")
	expect(mother._health_bar_background.visible and mother._health_bar_fill.visible
		and mother._health_label.visible and mother._health_label.text == "70/70",
		"a companion joining shows health immediately without selection, combat or an actor packet")
	expect(not villager._health_bar_background.visible, "nearby villagers remain name-only")
	main._sync_overhead_health_for([20])
	expect(mother._health_label.visible, "incremental actor refreshes retain companion health")
	mother.apply_vitals(18, 70)
	expect(mother._health_label.text == "18/70" and mother._health_bar_fill.visible
		and is_equal_approx((mother._health_bar_fill.mesh as QuadMesh).size.x,
		ReplicatedActor3D.HEALTH_BAR_WIDTH * 18.0 / 70.0 * ReplicatedActor3D.OVERHEAD_PIXEL),
		"damage updates the same current/max label and proportional bar as other actors")
	mother.apply_vitals(0, 70)
	expect(mother._health_bar_background.visible and mother._health_label.visible
		and mother._health_label.text == "0/70" and not mother._health_bar_fill.visible,
		"a downed companion retains an empty health banner for healing")
	mother.apply_vitals(30, 70)
	expect(mother._health_label.text == "30/70" and mother._health_bar_fill.visible,
		"healing restores the companion's health fill")
	mother.set_banner_parts({"health_bar": false, "health_numbers": true})
	expect(not mother._health_bar_background.visible and mother._health_label.visible,
		"the existing health display options still apply")
	mother.set_banner_parts({})
	mother.set_nameplate_visible(false)
	expect(not mother._health_bar_background.visible and not mother._health_label.visible,
		"hiding the overhead banner also hides companion health")
	mother.set_nameplate_visible(true)
	app.current_map = "landfall_insides"
	main._on_state_changed(&"campaign")
	expect(not mother._health_bar_background.visible, "a stale campaign from another map hides health")
	app.campaign.map = "landfall_insides"
	main._on_state_changed(&"campaign")
	expect(mother._health_bar_background.visible, "the companion's banner works in the mine too")
	app.campaign.actors.mother = 21
	main._on_state_changed(&"campaign")
	expect(not mother._health_bar_background.visible and villager._health_bar_background.visible,
		"replacing a companion refreshes both old and new actor banners")
	app.campaign.active = false
	main._on_state_changed(&"campaign")
	expect(not villager._health_bar_background.visible, "ending the campaign hides health immediately")
	app.campaign.active = true
	main._on_state_changed(&"campaign")
	app.campaign = {}
	main._on_state_changed(&"campaign")
	expect(not villager._health_bar_background.visible, "clearing the campaign removes the former companion's bar")
	expect(main._overhead_health_for(21, app.actors[21], 21), "targeted NPC health remains visible")
	expect(main._overhead_health_for(30, {"kind": 1}, -1)
		and main._overhead_health_for(31, {"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND}, -1),
		"players and creatures keep their health banners")
	main.actor_nodes.clear()
	app.actors = {}
	app.campaign = {}
	app.authenticated = false
	mother.free()
	villager.free()
	var disposed := {}
	for property: Dictionary in main.get_property_list():
		if (int(property.get("usage", 0)) & PROPERTY_USAGE_SCRIPT_VARIABLE) == 0:
			continue
		var value: Variant = main.get(str(property.name))
		if value is Node and is_instance_valid(value) and value != main:
			var node := value as Node
			if node.get_parent() == null and not disposed.has(node.get_instance_id()):
				disposed[node.get_instance_id()] = true
				node.free()
	main.free()
	print("NPC_COMPANION_BANNER checks=%d failures=%d" % [checks, failures])
	quit(1 if failures else 0)
