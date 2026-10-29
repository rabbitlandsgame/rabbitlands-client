extends SceneTree
## Exercise the live Main selector and native constructor, not the cinematic
## preview's direct model lookup. Native NPC kind 2/type 0 is the rescue family.
const Retired := preload("res://src/actors/archived_model_policy.gd")
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

func family(name: String, id: int, child := false) -> Dictionary:
	# Current server campaign_rescue.json approach rows; age is represented by
	# the daughter's native 0.65 scale, with her own saved clothes and hair.
	return {"actor_id":id,"actor_type":0,"kind":2,"name":name,
		"x":263,"y":135 if child else 137,"rotation":0,"command":7,
		"command_sequence":0,"health":70,"max_health":70,"alive":true,
		"scale":0.65 if child else 1.0,"equipment_visuals":{},
		"appearance":{"skin":1,"hair":205 if child else 107,
			"shirt":7 if child else 5,"pants":6 if child else 4,
			"boots":0 if child else 1,"head":0,"eyes":2}}

func native_actor(main, raw: Dictionary) -> ReplicatedActor3D:
	var before := raw.duplicate(true)
	var model_id: String = main._model_for_actor(raw)
	expect(model_id == main.actor_type_models["0"], str(raw.name) + " uses the current female registry entry")
	var model: Dictionary = main.models.get(model_id, {})
	expect(str(model.get("gender", "")) == "female", str(raw.name) + " keeps the female body")
	expect(not Retired.is_retired_path(str(model.get("scene", ""))), str(raw.name) + " uses an approved native model")
	var presented: Dictionary = main._presentation_dto(raw)
	expect(presented.appearance == raw.appearance and presented.scale == raw.scale,
		str(raw.name) + " preserves native appearance and child scale")
	var actor := ReplicatedActor3D.new()
	actor.apply_render_quality(1, true)
	root.add_child(actor)
	var errors := actor.configure(presented, main.adapter, model,
		main._animation_for_model(model), main.equipment_config)
	actor.set_process(false)
	actor.set_physics_process(false)
	expect(errors.is_empty(), str(raw.name) + " native constructor succeeds: " + str(errors))
	expect(not actor.is_model_deferred() and actor.get_node_or_null("StandIn") == null,
		str(raw.name) + " is a built body rather than a deferred cylinder")
	expect(actor.get_node_or_null("MissingModelFallback") == null,
		str(raw.name) + " has no missing-model cylinder")
	var body := actor.get_node_or_null("NativeModel") as Node3D
	var skeleton := actor.get_skeleton()
	var skinned := false
	if body != null:
		for node: Node in body.find_children("*", "MeshInstance3D", true, false):
			var mesh := node as MeshInstance3D
			if mesh.mesh != null and mesh.skin != null:
				skinned = true
	expect(body != null and skeleton != null and skeleton.get_bone_count() > 20 and skinned,
		str(raw.name) + " contains actual skinned native geometry and skeleton")
	expect(actor.animation_player != null and actor.resolver.action_to_clip.has("walk")
		and actor.animation_player.has_animation(actor.resolver.clip_for_action(&"walk")),
		str(raw.name) + " has native movement animations")
	expect(is_equal_approx(actor.server_scale, float(raw.scale)), str(raw.name) + " retains authoritative scale")
	var head = actor._rl_head_face(presented.appearance)
	expect(head != null and head.sex == "female", str(raw.name) + " maps its current RL head to the female body")
	expect(raw == before, str(raw.name) + " model construction never rewrites the authoritative DTO")
	return actor

func dispose_main(main) -> void:
	# Main is intentionally not entered into the tree: no networking, world or
	# gameplay startup. Free any Node-valued initializer it owns before it exits.
	var disposed: Dictionary = {}
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

func run() -> void:
	var registry := json("res://data/actors/models.json")
	var main = (load("res://src/app/main.gd") as Script).new()
	main.models = registry.models
	main.actor_type_models = registry.actorTypes
	main.npc_looks = registry.get("npcLooks", {})
	main.npc_characters = json("res://data/actors/npc_characters.json")
	main.equipment_config = json("res://data/actors/equipment.json")
	var app := root.get_node("AppState")
	var actors_before: Dictionary = app.get("actors").duplicate(true)
	var mother := native_actor(main, family("Elen Reed", 98001))
	var daughter := native_actor(main, family("Liora Reed", 98002, true))
	expect(is_equal_approx(daughter.head_height() / mother.head_height(), 0.65),
		"Liora's native body is visibly child-sized rather than adult scale")
	var injured := family("Injured woman", 98003)
	expect(main._model_for_actor(injured) == registry.actorTypes["0"],
		"injured-woman alias still gets the same female model")
	var customized := family("Unlisted female NPC", 98004)
	customized.appearance.merge({"height":62,"build":46,"jaw":73,"eyelid":65,"ear_size":38})
	var presented: Dictionary = main._presentation_dto(customized)
	expect(presented.appearance == customized.appearance,
		"current PC3/RL head appearance fields pass unchanged through live NPC presentation")
	expect(main._model_for_actor({"kind":2,"actor_type":1,"name":"Unknown legacy NPC"}) == "",
		"ambiguous legacy male NPC byte remains rejected")
	expect(main._model_for_actor({"kind":1,"actor_type":0}) == registry.actorTypes["0"]
		and main._model_for_actor({"kind":4,"actor_type":1}) == registry.actorTypes["1"],
		"player mappings remain unchanged")
	expect(main._model_for_actor({"kind":3,"actor_type":624}) == registry.actorTypes["624"],
		"native goblin mapping remains unchanged")
	var named: Dictionary = main.npc_characters.npcs.values()[0]
	expect(main._model_for_actor({"kind":2,"actor_type":named.actorType,"name":named.name}) == named.model,
		"named NPC model lookup still takes precedence")
	var retired_type := int((json(Retired.INDEX).retiredActorTypes as Array)[0])
	var retired_dto := family("Retired identity", 98005)
	retired_dto.actor_type = retired_type
	var retired_actor := ReplicatedActor3D.new()
	root.add_child(retired_actor)
	var retired_errors := retired_actor.configure(retired_dto, main.adapter,
		registry.models[registry.actorTypes["0"]], {}, {})
	expect(retired_errors.is_empty() and retired_actor.has_meta("retired_model")
		and retired_actor.get_node_or_null("NativeModel") == null
		and retired_actor.get_node_or_null("MissingModelFallback") == null,
		"retired native identities still cannot build a replacement body")
	expect(app.get("actors") == actors_before, "model selection/build never registers or replaces authoritative actors")
	retired_actor.free()
	daughter.free()
	mother.free()
	dispose_main(main)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	CharacterProportions.clear()
	print("Rescue native NPC models: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
