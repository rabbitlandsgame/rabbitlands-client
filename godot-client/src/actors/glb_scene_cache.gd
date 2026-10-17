class_name GlbSceneCache

extends RefCounted
## Loads each glTF scene exactly once and hands out instances of the cached
## result.
##
## In-project actor assets prefer Godot's imported PackedScene. Besides avoiding
## a runtime parse, that path retains the importer's generated mesh LODs, shadow
## meshes, compression and texture mip chains. External authoring/test files and
## lean checkouts without an import cache keep the raw GLTFDocument fallback.
##
## Instances share their mesh, skin and material resources, which also removes
## the duplicate GPU uploads the per-actor parse produced. Per-actor tinting
## goes through `material_override`, so sharing the source materials cannot leak
## one actor's appearance into another.
##
## Threads: parse an equipment glTF on the main thread only, or on a worker the
## main thread never waits on. A packaged client imports the textures the
## equipment glTFs name by URI (tools/package_client.py), and GLTFDocument
## takes such a texture through ResourceLoader and then reads it back with
## get_image(). Outside the editor that is a RenderingServer texture read: on
## the main thread it stalls the GPU once per image, and on a worker it waits
## for the main thread to serve it, so a main thread that joins the worker
## (wait_to_finish) never returns. Today only the main thread parses equipment:
## `prepare` runs on a map preloader's worker for the exterior links'
## visualScenes, which name no actor file, and the packaging tests hold them
## and the prewarmed animation libraries to that.

## World objects (harvest nodes, interactives) also come through here, and
## GLTFDocument builds their textures at runtime with no mip chain. Seen from the
## gameplay camera a node's 256-512 px texture is minified several times over, so
## without mips it aliases and swims as the camera moves - the reason
## world_loader rebuilds the chains of every map chunk. Models under this root
## get the same chains and the same anisotropic filter as the map around them.
## Actors are left as they were: their load time is why this cache exists.
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const GltfAnimationFidelity := preload("res://src/actors/gltf_animation_fidelity.gd")
const ArchivedModelPolicy := preload("res://src/actors/archived_model_policy.gd")
const WORLD_ASSET_ROOT := "res://assets/world/"

static var _scenes: Dictionary = {}
static var _failed: Dictionary = {}

static func missing(paths: PackedStringArray) -> PackedStringArray:
	var out := PackedStringArray()
	for path: String in paths:
		path = _canonical_path(path)
		if not _scenes.has(path) and not _failed.has(path):
			out.append(path)
	return out

static func prepare(paths: PackedStringArray) -> Dictionary:
	# Worker-owned resources. The main thread publishes them only on arrival.
	# Never an equipment glTF: see "Threads" above.
	var result: Dictionary = {}
	for path: String in paths:
		path = _canonical_path(path)
		var scene := _build(path)
		if scene != null:
			result[path] = scene
	return result

static func install_prepared(scenes: Dictionary) -> void:
	for path: String in scenes:
		if not _scenes.has(path):
			_scenes[path] = scenes[path]

## Returns a fresh instance of `path`, or null when the file cannot be imported.
static func instantiate(path: String) -> Node3D:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	path = _canonical_path(path)
	if path.is_empty() or _failed.has(path):
		return null
	var packed: PackedScene = _scenes.get(path) as PackedScene
	if packed == null:
		packed = _build(path)
		if packed == null:
			_failed[path] = true
			return null
		_scenes[path] = packed
	return packed.instantiate() as Node3D

## Drops every cached scene. Call when leaving a session so the next map is not
## charged for models it no longer uses.
static func clear() -> void:
	_scenes.clear()
	_failed.clear()

static func cached_scene_count() -> int:
	return _scenes.size()

static func _canonical_path(path: String) -> String:
	return ProjectSettings.globalize_path(path) if path.begins_with("res://") else path

static func _build(path: String) -> PackedScene:
	if ArchivedModelPolicy.is_retired_path(path):
		return null
	var imported := _imported_actor_scene(path)
	if imported != null:
		return imported
	return _build_raw(path)

## ResourceLoader resolves the `.import` remap in an editor checkout and the
## equivalent remap in an exported PCK. Restricting this preference to actor
## assets leaves the world-authoring cache's external-file semantics unchanged.
static func _imported_actor_scene(path: String) -> PackedScene:
	var resource_path := ProjectSettings.localize_path(path)
	if not resource_path.begins_with("res://assets/actors/"):
		return null
	var extension := resource_path.get_extension().to_lower()
	if extension != "glb" and extension != "gltf":
		return null
	if not ResourceLoader.exists(resource_path, "PackedScene"):
		return null
	return ResourceLoader.load(resource_path, "PackedScene",
		ResourceLoader.CACHE_MODE_REUSE) as PackedScene

static func _build_raw(path: String) -> PackedScene:
	GltfQuantization.ensure_registered()
	var document: GLTFDocument = GLTFDocument.new()
	var state: GLTFState = GLTFState.new()
	if document.append_from_file(path, state) != OK:
		return null
	var world_asset := is_world_asset(path)
	if world_asset:
		build_texture_mipmaps(state)
	var generated: Node = document.generate_scene(state, GltfAnimationFidelity.bake_fps(state))
	if generated == null:
		return null
	if generated is not Node3D:
		generated.free()
		return null
	if world_asset:
		_filter_anisotropic(generated)
	_claim(generated, generated)
	var packed: PackedScene = PackedScene.new()
	var packed_error: Error = packed.pack(generated)
	generated.free()
	if packed_error != OK:
		push_warning("glb cache: pack failed for %s (%s)" % [
			path, error_string(packed_error)])
		return null
	return packed

static func is_world_asset(path: String) -> bool:
	return _canonical_path(path).begins_with(ProjectSettings.globalize_path(WORLD_ASSET_ROOT))

## Gives every image the state carries a mip chain. The images are the objects
## the generated materials will reference, so this must run before
## generate_scene(). Returns how many images were rebuilt.
static func build_texture_mipmaps(state: GLTFState) -> int:
	var rebuilt := 0
	for texture_value: Variant in state.get_images():
		var texture: ImageTexture = texture_value as ImageTexture
		if texture == null:
			continue
		var image: Image = texture.get_image()
		if image == null or image.is_empty() or image.has_mipmaps():
			continue
		if image.is_compressed() and image.decompress() != OK:
			continue
		image.generate_mipmaps()
		texture.set_image(image)
		rebuilt += 1
	return rebuilt

static func _filter_anisotropic(root: Node) -> void:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = (node as MeshInstance3D).mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var material := mesh.surface_get_material(surface) as BaseMaterial3D
			if material != null:
				material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC

# PackedScene.pack() only stores nodes owned by the packed root.
static func _claim(node: Node, scene_owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = scene_owner
		_claim(child, scene_owner)
