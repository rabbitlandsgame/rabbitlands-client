extends SceneTree
## Saved-copy state, icon silhouettes, and the equipment secondary pass.
const Glow := preload("res://src/ui/item_glow.gd")
const EquipmentGlow := preload("res://src/actors/equipment_glow.gd")
const EffectIcons := preload("res://src/ui/item_effect_icons.gd")
var failures := 0
var checks := 0

func _init() -> void: _run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func packet(state: Node, data: Dictionary) -> void:
	state.call("_on_packet", EloriaProtocol.ServerMessage.ELORIA_MAGIC_STATE, JSON.stringify(data).to_utf8_buffer())

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	for effect: String in EffectIcons.PATHS:
		expect(Glow.STYLES.has(effect), "saved effect has a glow style: " + effect)
	var fire := {"tier": "magic", "image_id": 182, "effects": ["Emberstrike"]}
	var frost := {"tier": "rare", "image_id": 182, "effects": ["Frostbind", "Renewal", "Runebound"]}
	expect(Glow.profile({}).is_empty(), "ordinary equipment has no glow")
	expect(Glow.profile(fire).colors[0] != Glow.profile(frost).colors[0], "effects determine the palette")
	var reversed := frost.duplicate(true)
	reversed.effects.reverse()
	expect(Glow.profile(frost) == Glow.profile(reversed), "saved roll order does not change the style")
	var rare := fire.duplicate(true)
	rare.tier = "rare"
	expect(Glow.profile(rare).strength > Glow.profile(fire).strength, "rare pieces glow more strongly")
	var bad := Glow.validated({"0": {"tier": "magic", "image_id": 182, "effects": [42]},
		"-1": fire, "44": frost, "1": fire}, 43)
	expect(bad.keys() == ["1"], "malformed and out-of-range descriptors are ignored")
	var state := root.get_node("AppState")
	packet(state, {"kind": "item_glows", "slots": {"0": fire, "1": frost}})
	expect(state.get("item_glows").size() == 2, "inventory receives each exact copy's saved effects")
	packet(state, {"kind": "item_glows", "slots": {"1": frost}})
	expect(not state.get("item_glows").has("0"), "replacing a copy with plain gear clears its glow")
	state.set("actors", {901: {"actor_id": 901}})
	packet(state, {"kind": "actor_status", "actor_id": 901, "effects": [], "equipment_glows": {"0": frost}})
	expect(state.get("actors")[901].equipment_glows["0"].tier == "rare", "actor status carries worn-piece glow")
	packet(state, {"kind": "actor_status", "actor_id": 901, "effects": [], "equipment_glows": {}})
	expect(state.get("actors")[901].equipment_glows.is_empty(), "unequipping clears the actor's glow")

	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	var plain := atlas.icon_for(182)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.item_atlas = atlas
	state.set("inventory", {0: {"image_id": 182, "quantity": 1}, 1: {"image_id": 182, "quantity": 1}})
	packet(state, {"kind": "item_glows", "slots": {"0": fire}})
	expect(main._slot_icon(182, 0) != main._slot_icon(182, 1), "production slots distinguish plain and magic copies with the same artwork")
	expect(main._slot_icon(183, 0) == atlas.icon_for(183), "late metadata cannot decorate different artwork")
	packet(state, {"kind": "item_glows", "slots": {}})
	expect(main._slot_icon(182, 0) == plain, "the production slot immediately clears a removed glow")
	main.free()
	expect(Glow.icon(plain, {}) == plain, "normal icons use their original artwork")
	var lit := Glow.icon(plain, fire)
	expect(lit != plain and lit.get_size() == Vector2(64, 64), "enchanted artwork has a bounded halo texture")
	expect(Glow.icon(plain, fire) == lit, "glow artwork is cached across inventory refreshes")
	expect(lit.get_image().get_pixel(3, 3).a == 0.0, "opaque painted backgrounds do not become glowing square frames")
	var worn := atlas.worn_icon_for(182)
	expect(Glow.icon(worn, fire) != lit, "worn artwork retains its independent mirrored treatment")
	var synthetic := Image.create(32, 32, false, Image.FORMAT_RGBA8)
	synthetic.fill_rect(Rect2i(14, 5, 4, 23), Color.WHITE)
	var synthetic_icon := ImageTexture.create_from_image(synthetic)
	var halo := Glow.icon(synthetic_icon, fire).get_image()
	var original_pixels := synthetic_icon.get_image().get_data()
	expect(halo.get_pixel(26, 32).a > 0.0 and halo.get_pixel(0, 0).a == 0.0,
		"the halo follows the item silhouette without filling its cell")
	expect(synthetic_icon.get_image().get_data() == original_pixels, "shared source artwork stays untouched")

	var stage := Node3D.new()
	root.add_child(stage)
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	stage.add_child(mesh)
	var authored := StandardMaterial3D.new()
	mesh.material_override = authored
	var overlay := StandardMaterial3D.new()
	mesh.material_overlay = overlay
	var controller := EquipmentGlow.new()
	controller.sync({0: [mesh]}, {"0": fire}, null)
	expect(mesh.get_child_count() == 1, "a saved effect adds one secondary draw per mesh")
	var clone := mesh.get_child(0) as MeshInstance3D
	expect(clone.layers == 2 and clone.mesh == mesh.mesh, "the glow reuses geometry only on the gameplay layer")
	expect(mesh.material_override == authored and mesh.material_overlay == overlay, "the glow preserves materials and the visibility silhouette")
	controller.sync({0: [mesh]}, {"0": fire}, null)
	expect(mesh.get_child_count() == 1, "a movement refresh does not duplicate glow meshes")
	controller.sync({0: [mesh]}, {"0": frost}, null)
	await process_frame
	expect(mesh.get_child_count() == 1, "swapping same-artwork copies replaces their glow")
	controller.sync({0: [mesh]}, {}, null)
	await process_frame
	expect(mesh.get_child_count() == 0, "a plain replacement removes the secondary pass")
	stage.queue_free()
	await process_frame
	print("Item glows: %d checks, %d failures" % [checks, failures])
	quit(failures)
