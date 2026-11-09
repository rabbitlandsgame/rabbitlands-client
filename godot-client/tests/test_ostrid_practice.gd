extends SceneTree
var checks := 0
var failures := 0

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary

func run() -> void:
	var registry := json("res://data/actors/models.json")
	var main = (load("res://src/app/main.gd") as Script).new()
	main.models = registry.models
	main.actor_type_models = registry.actorTypes
	main.npc_looks = registry.get("npcLooks", {})
	main.npc_characters = json("res://data/actors/npc_characters.json")
	main.equipment_config = json("res://data/actors/equipment.json")
	var raw := {"public":{"actor_id":90,"kind":2,"actor_type":315,"name":"Ostrid Hollin","appearance":{},"health":20,"max_health":20},
		"practice":{"actor_id":91,"kind":2,"actor_type":0,"name":"Ostrid Hollin","health":200,"max_health":200,
			"appearance":{"skin":2,"hair":6,"shirt":3,"pants":0,"boots":3,"head":0,"eyes":0}}}
	var evidence := OS.get_environment("RL_OSTRID_EVIDENCE")
	if not evidence.is_empty():raw = json(evidence)
	var original := raw.duplicate(true)
	var actors: Array[ReplicatedActor3D] = []
	var presented: Array[Dictionary] = []
	for role: String in ["public", "practice"]:
		var model_id: String = main._model_for_actor(raw[role])
		expect(model_id == registry.actorTypes["0"], role + " uses the existing practice Human model")
		var dto: Dictionary = main._presentation_dto(raw[role])
		expect(dto.equipment_visuals.is_empty(), role + " has the practice clothes without the old outfit override")
		presented.append(dto)
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(1, true);root.add_child(actor)
		var errors := actor.configure(dto, main.adapter, registry.models[model_id],
			main._animation_for_model(registry.models[model_id]), main.equipment_config)
		expect(errors.is_empty() and actor.get_node_or_null("NativeModel") != null
			and actor.get_skeleton() != null and actor.get_node_or_null("MissingModelFallback") == null,
			role + " constructs the actual animated native body")
		actors.append(actor)
	var world_look: Dictionary = presented[0].appearance
	var practice_look: Dictionary = presented[1].appearance
	for part: String in ["skin", "shirt", "pants", "boots", "head", "eyes"]:
		expect(world_look[part] == practice_look[part], "same " + part + " in public and practice")
	expect(AppearanceVariants.hair_style(world_look.hair) == AppearanceVariants.hair_style(practice_look.hair)
		and AppearanceVariants.hair_color_index(world_look.hair) == AppearanceVariants.hair_color_index(practice_look.hair),
		"packed authored hair preserves the practice style and color")
	expect(actors[0]._rl_head_face(world_look).to_dict() == actors[1]._rl_head_face(practice_look).to_dict(),
		"the head and portrait resolve to the same face and hair")
	var app := root.get_node("AppState")
	app.authenticated = true;app.current_map = "landfall_town";app.combat_state = {"active":false,"target_id":-1}
	var mentor := int(raw.practice.actor_id)
	app.actors = {mentor:raw.practice}
	main.actor_nodes[mentor] = actors[1]
	app.campaign = {"kind":"shelves","active":true,"run_id":"private-spar","map":"landfall_town",
		"actors":{"mentor":mentor},"shelves":{"private_practice":true,"sparring":true}}
	main._on_state_changed(&"campaign")
	expect(actors[1]._health_bar_background.visible and actors[1]._health_maximum == 200,
		"the instructor shows a 200-health bar before the player selects her")
	expect(not main._overhead_health_for(int(raw.public.actor_id),raw.public,-1), "the public instructor keeps the normal peaceful NPC banner")
	app.campaign.shelves.sparring = false
	main._on_state_changed(&"campaign")
	expect(not actors[1]._health_bar_background.visible, "ending the bout hides the health bar without waiting for actor packets")
	app.campaign.shelves.sparring = true;app.current_map = "landfall"
	main._on_state_changed(&"campaign")
	expect(not actors[1]._health_bar_background.visible, "a stale practice state cannot reveal a public NPC health bar")
	expect(raw == original, "appearance presentation preserves authoritative actors")
	main.actor_nodes.clear();app.actors = {};app.campaign = {};app.authenticated = false
	for actor: ReplicatedActor3D in actors:actor.free()
	var disposed: Dictionary = {}
	for property: Dictionary in main.get_property_list():
		if (int(property.get("usage", 0)) & PROPERTY_USAGE_SCRIPT_VARIABLE) == 0:continue
		var value: Variant = main.get(str(property.name))
		if value is Node and is_instance_valid(value) and value != main:
			var node := value as Node
			if node.get_parent() == null and not disposed.has(node.get_instance_id()):
				disposed[node.get_instance_id()] = true;node.free()
	main.free()
	NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Ostrid practice: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
