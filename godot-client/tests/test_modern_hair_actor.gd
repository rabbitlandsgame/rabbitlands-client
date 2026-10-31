extends SceneTree
## Real actor transitions keep modern hair, the native head and wardrobe apart.
const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")
const Library := preload("res://src/actors/rl_head/rl_head_library.gd")
var checks := 0
var failures := 0
var capture_dir := ""
var camera: Camera3D
var captured := {}

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _initialize() -> void:
	OS.set_environment("RL_HEADS", "all")
	OS.set_environment("RL_HEAD_BAKE", "0")
	OS.set_environment("RL_HEAD_STILL", "0")
	ReplicatedActor3D.reload_rl_heads_switch()
	run.call_deferred()

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	capture_dir = OS.get_environment("RL_HAIR_ACTOR_CAPTURE")
	if not capture_dir.is_empty():
		root.size = Vector2i(640, 640)
		DirAccess.make_dir_recursive_absolute(capture_dir)
		Stage.build(world)
		camera = Camera3D.new()
		world.add_child(camera)
		camera.current = true
	for sex: String in ["female", "male"]:
		var module := 3 if sex == "female" else 2
		var style := 3 if sex == "female" else 1
		var app := {"skin": 2, "hair": AppearanceVariants.pack_hair(style, 1),
			"eyes": 2, "hair_module": module, "facial_hair": 0}
		var actor := Stage.spawn(world, sex, app, {}, 0)
		await process_frame
		if sex == "female":
			check(Library._heads.is_empty(), "initial Low actor loads hair without loading a modern head")
		for quality: int in [0, 1, 2, 1, 0, 2]:
			actor.apply_appearance_variants(app)
			actor.apply_render_quality(quality)
			await process_frame
			var rig := actor.hair_module_rig()
			check(rig != null and rig.draws_module_hair(), "%s quality%d draws modern hair" % [sex, quality])
			check(actor._legacy_hair_style_drawn() == 0, "retired native hair is not built behind the module")
			check((actor.rl_head() != null) == (quality == 2), "quality changes the head independently of hair")
			check((actor._rl_hair != null) == (quality < 2), "native-head tiers use the hair-only rig")
			if rig != null:
				check(int(rig.all_meshes()[0].get_meta(RLHeadRig.LOD_LEVEL_META)) == 2 - quality,
					"actor uses the quality's authored hair LOD")
			await capture(actor, sex, quality)
			var before := actor._appearance.duplicate(true)
			actor.apply_appearance_variants(app.merged({"hair_length": 80, "hair_volume": 25, "hair_grey": 50}, true))
			await process_frame
			check(actor.hair_module_rig() != null and actor._legacy_hair_style_drawn() == 0,
				"live groom edits keep the module and no legacy mesh")
			check(int(actor._appearance.hair) == int(before.hair)
				and int(actor._appearance.hair_module) == module, "rendering preserves saved hairstyle bytes")
		actor.apply_appearance_variants(app.merged({"hair": 0}, true))
		await process_frame
		check(actor.hair_module_rig() == null and actor._legacy_hair_style_drawn() == 0,
			"Bald clears both modern and native hair")
		actor.apply_appearance_variants(app)
		actor.apply_render_quality(0)
		await process_frame
		actor._hidden_body_surfaces["hair"] = true
		actor._refresh_body_surface_visibility()
		var attachment := actor.get_skeleton().get_node_or_null(RLHeadRig.HAIR_NODE_NAME) as Node3D
		check(attachment != null and not attachment.visible, "closed headwear hides modern hair on the native head")
		actor._hidden_body_surfaces.erase("hair")
		actor._refresh_body_surface_visibility()
		check(attachment != null and attachment.visible, "removing headwear restores the same hair")
		actor.queue_free()
		await process_frame
		await process_frame
	check(Library.users() == 0, "freeing both actors releases every head and hair library lease")
	Library.clear()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("Modern hair actor: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func capture(actor: ReplicatedActor3D, sex: String, quality: int) -> void:
	var key := "%s-quality%d" % [sex, quality]
	if capture_dir.is_empty() or captured.has(key):
		return
	captured[key] = true
	Stage.pose(actor, "Rest", 0.0)
	actor.get_skeleton().force_update_all_bone_transforms()
	for view: String in ["front", "profile"]:
		Stage.frame(camera, actor, view)
		for frame: int in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		var image := root.get_texture().get_image()
		check(image != null and not image.is_empty(), key + " " + view + " renders")
		if image != null:
			check(image.save_png(capture_dir.path_join(key + "-" + view + ".png")) == OK,
				key + " " + view + " capture saved")
