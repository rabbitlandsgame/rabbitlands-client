extends SceneTree
## Render the production icon palette and subtle particles on the native sword.
const Glow := preload("res://src/ui/item_glow.gd")
const EquipmentGlow := preload("res://src/actors/equipment_glow.gd")
const ARTIFACTS := "res://test-artifacts/item-glows"
const EFFECTS := ["Emberstrike", "Frostbind", "Runebound", "Renewal", "Soulreave", "Irradiated", "Second Wind", "Stoneward"]
var controllers: Array[RefCounted] = []
var failures := 0

func _init() -> void: _run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 800)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ARTIFACTS))
	var stage := Node3D.new()
	root.add_child(stage)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	world_environment.environment.background_mode = Environment.BG_COLOR
	world_environment.environment.background_color = Color("151b25")
	world_environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world_environment.environment.ambient_light_color = Color("b3c0dc")
	world_environment.environment.ambient_light_energy = 0.65
	stage.add_child(world_environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-35, -25, 0)
	sun.light_energy = 1.4
	stage.add_child(sun)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 5.8
	camera.cull_mask = 3
	stage.add_child(camera)
	camera.look_at_from_position(Vector3(0, 0.4, 7), Vector3(0, 0.4, 0))
	camera.current = true
	var canvas := CanvasLayer.new()
	root.add_child(canvas)
	var title := Label.new()
	title.text = "SUBTLE ITEM PARTICLES"
	title.position = Vector2(28, 18)
	title.add_theme_font_size_override("font_size", 25)
	canvas.add_child(title)
	var subtitle := Label.new()
	subtitle.text = "Inventory: normal / magic / rare                 Equipped: sparse rare particles on the native arming sword"
	subtitle.position = Vector2(28, 54)
	canvas.add_child(subtitle)
	var atlas := ItemAtlas.new()
	atlas.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/items/atlases.json")))
	for index: int in EFFECTS.size():
		var label := Label.new()
		label.text = EFFECTS[index]
		label.position = Vector2(25 + index * 157, 95)
		label.add_theme_font_size_override("font_size", 17)
		canvas.add_child(label)
		for tier_index: int in 3:
			var icon := TextureRect.new()
			icon.position = Vector2(23 + index * 157 + tier_index * 47, 128)
			icon.size = Vector2(46, 46)
			icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			icon.texture = Glow.icon(atlas.icon_for(182), {"tier": ["normal", "magic", "rare"][tier_index], "effects": [EFFECTS[index]]})
			canvas.add_child(icon)
		var model := GlbSceneCache.instantiate("res://assets/actors/native/equipment/militia_arming_sword.glb")
		expect(model != null, "native sword loads")
		if model == null: continue
		stage.add_child(model)
		model.position = Vector3((index - 3.5) * 1.13, -0.75, 0)
		model.scale = Vector3.ONE * 1.9
		model.rotation_degrees.y = 18
		var controller := EquipmentGlow.new()
		controller.sync({0: [model]}, {"0": {"tier": "rare", "effects": [EFFECTS[index]]}}, null)
		controllers.append(controller)
	var footer := Label.new()
	footer.text = "Fire embers  /  Ice flecks  /  Arcane motes  /  Life sparks  /  Soul wisps  /  Radiation  /  Wind streaks  /  Metallic glints"
	footer.position = Vector2(28, 755)
	canvas.add_child(footer)
	for frame: int in 12: await process_frame
	var clones := stage.find_children("ItemMotes", "MultiMeshInstance3D", true, false)
	expect(clones.size() >= 8, "each sword has its particle emitter attached")
	for clone: Node3D in clones: clone.hide()
	var plain := await capture("plain")
	for clone: Node3D in clones: clone.show()
	var lit := await capture("effects")
	await create_timer(0.7).timeout
	var animated := await capture("animated")
	var visible_pixels := changed(plain, lit)
	var moving_pixels := changed(lit, animated)
	print("Particle pixels: ", visible_pixels, " visible; ", moving_pixels, " animated")
	expect(visible_pixels > 8 and visible_pixels < 900, "particles are visible but leave almost all equipment pixels untouched")
	expect(moving_pixels > 8, "the sparse motes animate")
	print("Rendered item glows: %d failures" % failures)
	quit(failures)

func capture(label: String) -> Image:
	await process_frame
	await RenderingServer.frame_post_draw
	var result := root.get_texture().get_image()
	result.save_png(ARTIFACTS + "/" + label + ".png")
	return result

func changed(a: Image, b: Image) -> int:
	var count := 0
	for y: int in range(200, 740):
		for x: int in range(1280):
			var left := a.get_pixel(x, y)
			var right := b.get_pixel(x, y)
			if absf(left.r - right.r) + absf(left.g - right.g) + absf(left.b - right.b) > 0.035: count += 1
	return count
