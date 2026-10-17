extends SceneTree
## Production presentation from real server packets, plus all named NPC outfits.
## ELORIA_NPC_PACKETS accepts the live server roster's captured spawn frames.
## ELORIA_NPC_PREVIEWS saves front/side/walking views for a representative cast.

const SHOWCASE := ["Aven", "Mara Venn", "Sella", "Brannic", "Rowan Vale", "Ilyra",
	"Captain Tor", "Pell", "Tamsin Quill", "Vestra", "Lens-Master Corvine Ast",
	"Orrery Keeper Sabel Roon", "Quarry Foreman Hesk", "Salvage Mistress Gero Lund",
	"Sunken Court Diver Teth-Sa", "Gate Warden Ilyon", "Nash", "Hemmen",
	"Bettany Orl", "Tessa", "Rellan", "Banner-Rider Ashaia", "Snowline Ranger Kestrel Vane", "Ione Brass",
	"Caravan Doctor Nesrin", "Motherroot Voice Sillow", "Canopy Rigger",
	"Bog-Iron Smith Nella Doust", "Captain Iven", "Tessara", "Hatchery Keeper Nuu-Sesh",
	"Old Pyke", "Widow Carrow", "Grinder Vell", "Ammet Sorrel",
	"Ostrid Hollin", "Marta Quell", "Tavi Unhar", "Odo Fenn"]

var failures := 0
var checks := 0
var stage: Node3D
var camera: Camera3D
var output := ""

func _init() -> void:
	call_deferred("run")

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func run() -> void:
	output = OS.get_environment("ELORIA_NPC_PREVIEWS")
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(480, 640)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.hide()
	var catalogue: Dictionary = main.get("npc_characters") as Dictionary
	var models: Dictionary = main.get("models") as Dictionary
	var player := {"kind": 1, "actor_type": 1, "name": "Mara Venn",
		"appearance": {"shirt": 5, "pants": 9, "hair": 101}, "equipment_visuals": {5: 209}}
	var player_look: Dictionary = main.call("_presentation_dto", player)
	expect(player_look["appearance"] == player["appearance"] and
		player_look["equipment_visuals"] == player["equipment_visuals"] and
		main.call("_model_for_actor", player) == "luminous_male",
		"production player presentation keeps the player's own choices under an NPC name")
	expect(str(main.call("_model_for_actor", {"kind": 2, "actor_type": 1,
		"name": "Mara Venn"})).is_empty(), "another NPC type cannot borrow a named model")
	var packets := {}
	var packet_file := OS.get_environment("ELORIA_NPC_PACKETS")
	if not packet_file.is_empty():
		packets = JSON.parse_string(FileAccess.get_file_as_string(packet_file))
		expect(packets.size() == catalogue["npcs"].size(), "live roster and authored cast have equal coverage")
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color(.13, .16, .19)
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color.WHITE
	world.environment.ambient_light_energy = .55
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -30, 0)
	light.light_energy = .75
	stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 2.75
	camera.current = true
	stage.add_child(camera)
	camera.position = Vector3(0, 1.1, 4)
	camera.look_at(Vector3(0, 1.1, 0))
	var count := 0
	var selected := OS.get_environment("ELORIA_NPC_NAMES").split(",", false)
	for key: String in catalogue["npcs"]:
		var person: Dictionary = catalogue["npcs"][key]
		if not selected.is_empty() and str(person["name"]) not in selected:
			continue
		var dto := {"actor_id": 30000 + count, "x": 0, "y": 0, "rotation": 0,
			"kind": 2, "actor_type": person["actorType"], "name": person["name"]}
		if not packets.is_empty():
			expect(packets.has(key), key + " exists in the real server roster")
			if not packets.has(key):
				continue
			var packet: Dictionary = packets[key]
			dto = EloriaProtocol.decode_server(int(packet["opcode"]), str(packet["payload"]).hex_decode())
			expect(dto.get("type", "") == "actor_spawn", key + " actual packet decodes")
		var presented: Dictionary = main.call("_presentation_dto", dto)
		var slug: String = main.call("_model_for_actor", dto)
		expect(slug == person["model"], key + " model matches its story")
		expect(presented["appearance"] == person["appearance"], key + " production appearance")
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure(presented, CoordinateAdapter.new({"walkingHeight": 0.0}),
			models[slug], main.call("_animation_for_model", models[slug]), main.get("equipment_config"))
		expect(errors.is_empty(), key + " loads: " + str(errors))
		var wanted := {}
		for part: String in person["equipmentVisuals"]:
			wanted[int(part)] = int(person["equipmentVisuals"][part])
		var diagnostics := actor.equipment_diagnostics()
		expect(diagnostics["visuals"] == wanted and diagnostics["fallback"] == 0,
			key + " every outfit piece uses native equipment")
		if not wanted.has(5):
			var shirt := actor.find_child("wardrobe_shirt", true, false) as MeshInstance3D
			expect(shirt != null and shirt.get_meta("wardrobe_color") == AppearanceVariants.wardrobe_color(
				models[slug]["culture"], 5, int(person["appearance"]["shirt"])), key + " actual fabric dye")
		for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
			if str(node.name).begins_with("EquipmentSkin") and (node as MeshInstance3D).visible:
				expect((node as MeshInstance3D).skin != null, key + " clothing has a skeleton binding")
		if not output.is_empty() and str(person["name"]) in SHOWCASE:
			await capture(actor, key, 0, "Idle_Subtle")
			await capture(actor, key + "-side", PI / 2, "Idle_Subtle")
			await capture(actor, key + "-walk", PI / 3, "Walk")
		actor.free()
		await process_frame
		count += 1
		if count % 32 == 0:
			print("NPC CAST: ", count, "/", catalogue["npcs"].size(), ", ", failures, " failures")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	print("NPC CAST: ", count, " NPCs, ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)

func capture(actor: ReplicatedActor3D, key: String, angle: float, clip: String) -> void:
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.global_position = Vector3.ZERO
	actor.rotation.y = PI + angle
	actor._advance_facing_offset(1.0)
	actor.set_nameplate_visible(false)
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		if (node as MeshInstance3D).mesh is QuadMesh:
			(node as MeshInstance3D).hide()
	actor.animation_player.play(clip)
	actor.animation_player.advance(.35)
	actor.animation_player.pause()
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var filename := key.validate_filename().replace(" ", "_") + ".png"
	expect(root.get_texture().get_image().save_png(output.path_join(filename)) == OK, key + " preview saved")
