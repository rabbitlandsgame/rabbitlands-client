extends GLTFDocumentExtension

## Lets this client read the packages' quantised vertex data.
##
## `tools/quantise_geometry.py` stores normals and tangents as normalized
## signed bytes and a morph target's position deltas as normalized signed
## shorts, which is KHR_mesh_quantization. Godot 4.7.2 decodes all of that
## correctly - a normal comes back within 0.37 degrees of the float it
## replaced, a position bit-identical - but `GLTFDocument` refuses a file that
## declares the extension in `extensionsRequired` unless something says it is
## supported, which is all this extension does.
##
## Writing the file without that declaration would load today and is off-spec:
## every other tool that reads these packages (Blender, the validator, the
## pipeline's own readers) is entitled to refuse data it was not told about.
##
## Registration is a no-op after the first and must happen before any package
## is parsed, so every site that builds a GLTFDocument calls it:
## world_loader.gd, external_mesh_pool.gd, glb_scene_cache.gd and
## native_animation_importer.gd.

static var _registered: GLTFDocumentExtension = null
static var _world_images: GLTFDocumentExtension = null


static func ensure_registered() -> void:
	if _registered != null:
		return
	_registered = new()
	GLTFDocument.register_gltf_document_extension(_registered)
	_world_images = preload("res://src/world/world_object_images.gd").new()
	GLTFDocument.register_gltf_document_extension(_world_images)


func _get_supported_extensions() -> PackedStringArray:
	return PackedStringArray(["KHR_mesh_quantization"])
