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
static var _registration_mutex := Mutex.new()
static var _registration_ready := false


## Only the main thread may mutate GLTFDocument's process-wide extension
## vector. Main and standalone prewarm/load entry points finish registration
## before starting any import worker. A worker-first call fails explicitly;
## callers must not continue a raw parse when this returns false.
static func ensure_registered() -> bool:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return is_registered()
	if _registration_ready:
		return true
	_registration_mutex.lock()
	var quantization: GLTFDocumentExtension = new()
	var world_images: GLTFDocumentExtension = preload("res://src/world/world_object_images.gd").new()
	GLTFDocument.register_gltf_document_extension(quantization)
	GLTFDocument.register_gltf_document_extension(world_images)
	_registered = quantization
	_world_images = world_images
	# Publish completion only after BOTH global registrations. The mutex
	# protects a defensive worker-first observation, never a parse or mesh.
	_registration_ready = true
	_registration_mutex.unlock()
	return true


static func is_registered() -> bool:
	_registration_mutex.lock()
	var ready := _registration_ready
	_registration_mutex.unlock()
	return ready


func _get_supported_extensions() -> PackedStringArray:
	return PackedStringArray(["KHR_mesh_quantization"])
