@tool
extends Node
## Library thumbnails for Map Assets.
##
## Godot's EditorResourcePreview returns nothing for imported .glb scenes, so the
## palette renders its own. Every visible mesh of an entry is merged into one
## ArrayMesh, keeping each surface's material. The mesh is drawn in a private
## SubViewport, one thumbnail per frame, and read back on the next frame.
##
## Nothing blocks or pumps the editor loop, unlike make_mesh_previews, which
## re-enters callers and crashes if the dock is freed mid-render. Results are
## cached as PNGs in the editor cache folder, keyed by source path, node and
## modification time.

signal thumbnail_ready(entry_id: String, texture: Texture2D)

const Placement := preload("res://addons/map_asset_palette/placement.gd")
const Prefabs := preload("res://addons/map_asset_palette/prefab_library.gd")
const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const SIZE := 128
const MAX_SURFACES := 96
const CACHE_FOLDER := "map_asset_thumbnails"

var cache_directory := ""
var _queue: Array[Dictionary] = []
var _queued := {}
var _viewport: SubViewport
var _camera: Camera3D
var _model: MeshInstance3D
var _pending: Dictionary = {}
var _pending_frame := -1


func _ready() -> void:
	# The dock queues its first thumbnails before it enters the tree.
	set_process(not is_idle())


func request(entry: Dictionary, urgent: bool = false) -> void:
	var entry_id := String(entry.get("id", ""))
	if entry_id.is_empty():
		return
	if _queued.has(entry_id):
		if not urgent:
			return
		for index in _queue.size():
			if String(_queue[index].id) == entry_id:
				_queue.remove_at(index)
				break
	_queued[entry_id] = true
	if urgent:
		_queue.push_front(entry.duplicate(true))
	else:
		_queue.append(entry.duplicate(true))
	set_process(true)


func clear() -> void:
	_queue.clear()
	_queued.clear()
	_pending = {}


func is_idle() -> bool:
	return _queue.is_empty() and _pending.is_empty()


func _process(_delta: float) -> void:
	if not _pending.is_empty():
		if Engine.get_process_frames() <= _pending_frame + 1:
			return
		_finish_pending()
	# Cache hits are cheap: drain them all, then start at most one render.
	while not _queue.is_empty():
		var entry: Dictionary = _queue.pop_front()
		var entry_id := String(entry.id)
		var cached_texture := cached(cache_directory, entry)
		if cached_texture != null:
			_queued.erase(entry_id)
			thumbnail_ready.emit(entry_id, cached_texture)
			continue
		if not _start_render(entry):
			_queued.erase(entry_id)
			thumbnail_ready.emit(entry_id, null)
			continue
		return
	if _pending.is_empty():
		set_process(false)


func _start_render(entry: Dictionary) -> bool:
	# The headless editor has no renderer to draw with.
	if DisplayServer.get_name() == "headless":
		return false
	var mesh := merged_mesh(entry)
	if mesh == null:
		return false
	_ensure_viewport()
	_model.mesh = mesh
	var bounds := mesh.get_aabb()
	var radius := maxf(bounds.size.length() * 0.5, 0.05)
	var centre := bounds.get_center()
	var distance := radius / sin(deg_to_rad(_camera.fov * 0.5)) * 1.05
	_camera.near = maxf(distance - radius * 2.0, 0.01)
	_camera.far = distance + radius * 2.0
	_camera.position = centre + Vector3(1.0, 0.75, 1.0).normalized() * distance
	_camera.look_at(centre, Vector3.UP)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	_pending = entry
	_pending_frame = Engine.get_process_frames()
	return true


func _finish_pending() -> void:
	var entry := _pending
	_pending = {}
	var entry_id := String(entry.id)
	_queued.erase(entry_id)
	var image := _viewport.get_texture().get_image() if _viewport != null else null
	if image == null or image.is_empty() or image.is_invisible():
		thumbnail_ready.emit(entry_id, null)
		return
	var path := _cache_path(cache_directory, entry)
	if not path.is_empty():
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		image.save_png(path)
	thumbnail_ready.emit(entry_id, ImageTexture.create_from_image(image))


func _ensure_viewport() -> void:
	if is_instance_valid(_viewport):
		return
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(SIZE, SIZE)
	_viewport.transparent_bg = true
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.75, 0.78, 0.85)
	environment.environment.ambient_light_energy = 0.9
	_viewport.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 35.0, 0.0)
	sun.light_energy = 1.1
	_viewport.add_child(sun)
	_camera = Camera3D.new()
	_camera.fov = 30.0
	_viewport.add_child(_camera)
	_model = MeshInstance3D.new()
	_viewport.add_child(_model)
	add_child(_viewport, false, Node.INTERNAL_MODE_BACK)


static func cached(directory: String, entry: Dictionary) -> Texture2D:
	var path := _cache_path(directory, entry)
	if path.is_empty() or not FileAccess.file_exists(path):
		return null
	var image := Image.load_from_file(path)
	return ImageTexture.create_from_image(image) if image != null and not image.is_empty() else null


## One mesh holding every visible surface of the entry in the entry's own frame.
static func merged_mesh(entry: Dictionary) -> ArrayMesh:
	var created := {}
	if Markers.is_marker_entry(entry):
		created = {"node": Markers.pin_node(String(entry.get("marker_kind", "")))}
	elif Prefabs.is_prefab_entry(entry):
		created = Prefabs.instantiate(entry)
	else:
		created = Placement.instantiate_entry(entry)
	var root := created.get("node") as Node3D
	if root == null:
		return null
	var merged := ArrayMesh.new()
	_append(root, Transform3D.IDENTITY, true, merged)
	root.free()
	return merged if merged.get_surface_count() > 0 else null


static func _append(node: Node, relative: Transform3D, visible: bool, merged: ArrayMesh) -> void:
	var here_visible := visible
	if node is Node3D:
		here_visible = here_visible and (node as Node3D).visible
	if node is MeshInstance3D and here_visible and (node as MeshInstance3D).mesh != null:
		var mesh_node := node as MeshInstance3D
		var mesh := mesh_node.mesh
		var normal_basis := relative.basis.inverse().transposed()
		for index in mesh.get_surface_count():
			if merged.get_surface_count() >= MAX_SURFACES:
				return
			# Primitive meshes (Box, Sphere, ...) are always triangles; only an
			# ArrayMesh can carry lines or points.
			if mesh is ArrayMesh and (mesh as ArrayMesh).surface_get_primitive_type(index) != \
					Mesh.PRIMITIVE_TRIANGLES:
				continue
			var arrays := mesh.surface_get_arrays(index)
			var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			if vertices.is_empty():
				continue
			for vertex_index in vertices.size():
				vertices[vertex_index] = relative * vertices[vertex_index]
			arrays[Mesh.ARRAY_VERTEX] = vertices
			if arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array:
				var normals := arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array
				for normal_index in normals.size():
					normals[normal_index] = (normal_basis * normals[normal_index]).normalized()
				arrays[Mesh.ARRAY_NORMAL] = normals
			# Skinning and tangents do not matter for a still thumbnail.
			arrays[Mesh.ARRAY_BONES] = null
			arrays[Mesh.ARRAY_WEIGHTS] = null
			arrays[Mesh.ARRAY_TANGENT] = null
			merged.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			merged.surface_set_material(merged.get_surface_count() - 1,
				mesh_node.get_active_material(index))
	for child in node.get_children():
		var child_relative := relative
		if child is Node3D:
			child_relative = relative * (child as Node3D).transform
		_append(child, child_relative, here_visible, merged)


static func _cache_path(directory: String, entry: Dictionary) -> String:
	if directory.is_empty():
		return ""
	var scene_path := String(entry.get("scene_path", ""))
	if scene_path.is_empty() or not FileAccess.file_exists(scene_path):
		return ""
	var key := "%s|%s|%d|%d" % [scene_path, String(entry.get("source_node", "")),
		FileAccess.get_modified_time(scene_path), SIZE]
	return directory.path_join(CACHE_FOLDER).path_join(key.sha256_text().substr(0, 24) + ".png")
