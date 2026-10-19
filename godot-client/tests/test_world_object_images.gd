extends SceneTree
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Images := preload("res://src/world/world_object_images.gd")
var failures := 0

func _init() -> void:
	Quantization.ensure_registered()
	# Actor/map imports omit this opt-in. An unset Variant must skip safely,
	# without trying bool(null) or changing the engine's ordinary decoder.
	var extension := Images.new()
	for opt_in in [null, false, "true"]:
		var state := GLTFState.new()
		if opt_in != null: state.set_additional_data(Images.ENABLED, opt_in)
		if extension._import_preflight(state, PackedStringArray()) != ERR_SKIP:
			push_error("Unselected imports must keep their ordinary image decoder")
			failures += 1
	for name in ["crystal_arch", "cave_mouth", "mine_rail"]:
		var document := GLTFDocument.new()
		var state := GLTFState.new()
		state.set_additional_data(Images.ENABLED, true)
		if document.append_from_file(ProjectSettings.globalize_path("res://assets/world/underground/"+name+".glb"),state) != OK:
			push_error(name+" failed to import")
			failures += 1
			continue
		if int(state.get_additional_data(Images.PREPARED)) != state.get_images().size():
			push_error(name+" did not prepare every embedded image before upload")
			failures += 1
		for texture: Texture2D in state.get_images():
			if not texture.get_image().has_mipmaps():
				push_error(name+" lost its mip chain")
				failures += 1
	print("WORLD_OBJECT_IMAGES_COMPLETE failures=",failures)
	quit(failures)
