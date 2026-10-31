extends SceneTree
## Greying must reach every legacy quality/finish path without changing saved dye.
const STAGE := preload("res://prototypes/rl_heads/rl_head_stage.gd")
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func colours(actor: ReplicatedActor3D) -> Array:
	var result: Array = []
	for hair: MeshInstance3D in HighHairAppearance._hair_nodes(actor.get_node("NativeModel")):
		if hair.is_queued_for_deletion() or not hair.visible: continue
		for index: int in hair.mesh.get_surface_count():
			var material := hair.get_active_material(index)
			if material is ShaderMaterial:
				result.append((material as ShaderMaterial).get_shader_parameter("hair_color"))
			elif material is BaseMaterial3D:
				result.append((material as BaseMaterial3D).albedo_color)
	return result

func _run() -> void:
	for sex: String in ["female", "male"]:
		for quality: int in [0, 1, 2]:
			for finish: int in [0, 63]:
				var base := {"skin": 2, "hair": AppearanceVariants.pack_hair(1, 1), "eyes": 2,
					"hair_module": 1, "hair_finish": finish, "facial_hair": 4}
				var actor := STAGE.spawn(root, sex, base, {}, quality)
				var other := STAGE.spawn(root, sex, base, {}, quality, 9301)
				await process_frame
				var original := colours(actor)
				var isolated := colours(other)
				check(not original.is_empty(), "legacy material colours available")
				actor.apply_appearance_variants(base.merged({"hair_grey": 100}, true))
				await process_frame
				check(colours(actor) != original, "%s quality%d finish%d greys visible legacy materials" % [sex, quality, finish])
				check(colours(other) == isolated, "another actor retains its dye")
				check(int(actor._appearance.hair) == int(base.hair), "saved base hair choice remains unchanged")
				actor.apply_appearance_variants(base)
				await process_frame
				check(colours(actor) == original, "legacy neutral restores exact dye")
				actor.free()
				other.free()
				await process_frame
	# The offline fit/head lab stores normalized values in an explicit rl_head.
	var face := RLHeadAppearance.from_preset("rowan")
	face.hair = RLHeadLibrary.legacy_hair_styles("male")[0]
	var lab := STAGE.spawn(root, "male", {"rl_head": face.to_dict()})
	await process_frame
	var before := colours(lab)
	face.hair_grey = 1.0
	lab.apply_appearance_variants({"rl_head": face.to_dict()})
	await process_frame
	check(not before.is_empty() and colours(lab) != before, "offline lab legacy hair receives normalized greying")
	lab.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("Character age legacy: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
