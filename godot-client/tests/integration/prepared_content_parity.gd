extends RefCounted
## Direct, real-asset representation parity. Deliberately not a frame benchmark.
## Same process/package/renderer: raw GLTF reference then exact native variant.
const Prepared := preload("res://src/world/prepared_content.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const Graphics := preload("res://src/world/graphics_options.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const MapExtension := preload("res://src/world/map_mesh_extension.gd")
const MeshPool := preload("res://src/world/external_mesh_pool.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const FULL_KIT_A := {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
const EPSILON := 0.00001
const SAMPLE_EPSILON := 0.0001
var _tree: SceneTree
var _errors: Array[String] = []
var _assertions := 0
var _mesh_cache: Dictionary = {}
var _material_cache: Dictionary = {}
var _texture_cache: Dictionary = {}
var _animation_cache: Dictionary = {}
var _report: Dictionary = {}
var _prior_no_map_cache := ""


func _node_name(node: Node) -> String:
	var name := str(node.name)
	var automatic := "@" + node.get_class() + "@"
	if name.begins_with(automatic) and name.trim_prefix(automatic).is_valid_int():
		# Godot's unnamed-node suffix is a process allocation counter. Preserve
		# the class and exact sibling position, rather than comparing that ID.
		return "@%s#%d" % [node.get_class(), node.get_index(true)]
	return name


func _relative_path(root: Node, node: Node) -> String:
	var parts := PackedStringArray()
	var current := node
	while current != root and current != null:
		parts.insert(0, _node_name(current))
		current = current.get_parent()
	return "/".join(parts) if not parts.is_empty() else "."


func _expect(value: bool, message: String) -> void:
	_assertions += 1
	if not value and _errors.size() < 64:
		_errors.append(message)


func _json(path: String) -> Dictionary:
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		return {}
	return parser.data as Dictionary


func _vector(value: Variant) -> Array:
	if value is Vector2 or value is Vector2i:
		return [value.x, value.y]
	if value is Vector3 or value is Vector3i:
		return [value.x, value.y, value.z]
	if value is Vector4 or value is Vector4i or value is Quaternion:
		return [value.x, value.y, value.z, value.w]
	if value is Color:
		return [value.r, value.g, value.b, value.a]
	if value is Transform3D:
		return [value.basis.x.x, value.basis.x.y, value.basis.x.z,
			value.basis.y.x, value.basis.y.y, value.basis.y.z,
			value.basis.z.x, value.basis.z.y, value.basis.z.z,
			value.origin.x, value.origin.y, value.origin.z]
	if value is AABB:
		return [_vector(value.position), _vector(value.size)]
	if value is Basis:
		return [_vector(value.x), _vector(value.y), _vector(value.z)]
	if value is Transform2D:
		return [_vector(value.x), _vector(value.y), _vector(value.origin)]
	if value is Rect2 or value is Rect2i:
		return [_vector(value.position), _vector(value.size)]
	if value is Plane:
		return [_vector(value.normal), value.d]
	return []


func _plain(value: Variant, depth := 0) -> Variant:
	if depth > 16:
		return "<depth-limit>"
	if value == null or value is bool or value is int or value is float or value is String:
		return value
	if value is StringName or value is NodePath:
		return str(value)
	if value is Texture2D:
		return _texture(value as Texture2D)
	if value is Material:
		return _material(value as Material, depth + 1)
	if value is Shader:
		return {"shaderCode": (value as Shader).code}
	if value is Array:
		var array: Array = []
		for item: Variant in value:
			array.append(_plain(item, depth + 1))
		return array
	if value is Dictionary:
		var result: Dictionary = {}
		for key: Variant in value:
			result[str(key)] = _plain(value[key], depth + 1)
		return result
	if value is Resource:
		return {"resourceClass": value.get_class()}
	var vector := _vector(value)
	if not vector.is_empty():
		return vector
	# Packed numeric/string arrays contain no object identity. Hash exact data;
	# do not serialize a RID or native Object pointer into parity evidence.
	if typeof(value) in [TYPE_PACKED_BYTE_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY,
		TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_STRING_ARRAY,
		TYPE_PACKED_VECTOR2_ARRAY, TYPE_PACKED_VECTOR3_ARRAY, TYPE_PACKED_VECTOR4_ARRAY, TYPE_PACKED_COLOR_ARRAY]:
		return {"packedType": typeof(value), "count": value.size(), "sha256": _hash(value)}
	return {"unsupportedType": typeof(value)}


func _hash(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(value))
	return context.finish().hex_encode()


func _texture(texture: Texture2D) -> Dictionary:
	var identity := texture.get_instance_id()
	if _texture_cache.has(identity):
		return _texture_cache[identity]
	# Readback is intentional qualification work on main, outside performance
	# samples. Native ImageTexture may replace CompressedTexture2D; compare the
	# actual image policy/data, not that representation class name.
	var image := texture.get_image()
	var result := {"width": texture.get_width(), "height": texture.get_height(), "readable": image != null}
	if image != null:
		result.merge({"format": image.get_format(), "mipmaps": image.get_mipmap_count(),
			"bytes": image.get_data_size(), "dataSha256": _hash(image.get_data())})
	_texture_cache[identity] = result
	return result


func _material(material: Material, depth := 0) -> Dictionary:
	var identity := material.get_instance_id()
	if _material_cache.has(identity):
		return _material_cache[identity]
	var result := {"class": material.get_class(), "name": material.resource_name, "properties": {}}
	_material_cache[identity] = result
	for property: Dictionary in material.get_property_list():
		var name := str(property.name)
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0 or name in [
			"resource_path", "resource_name", "resource_local_to_scene", "script"] or name.begins_with("metadata/"):
			continue
		result.properties[name] = _plain(material.get(name), depth + 1)
	return result


func _mesh(mesh: Mesh) -> Dictionary:
	var identity := mesh.get_instance_id()
	if _mesh_cache.has(identity):
		return _mesh_cache[identity]
	var result := {"name": mesh.resource_name, "aabb": _vector(mesh.get_aabb()), "surfaces": [],
		"blendShapes": [], "blendShapeMode": (mesh as ArrayMesh).blend_shape_mode if mesh is ArrayMesh else -1}
	if mesh is ArrayMesh:
		for shape: int in (mesh as ArrayMesh).get_blend_shape_count():
			result.blendShapes.append(str((mesh as ArrayMesh).get_blend_shape_name(shape)))
	for surface: int in mesh.get_surface_count():
		var row := {"primitive": (mesh as ArrayMesh).surface_get_primitive_type(surface) if mesh is ArrayMesh else Mesh.PRIMITIVE_TRIANGLES,
			"arrays": _hash(mesh.surface_get_arrays(surface)), "blendShapeArrays": _hash(mesh.surface_get_blend_shape_arrays(surface))}
		if mesh is ArrayMesh:
			row["name"] = (mesh as ArrayMesh).surface_get_name(surface)
		result.surfaces.append(row)
	_mesh_cache[identity] = result
	return result


func _animation(animation: Animation) -> Dictionary:
	var identity := animation.get_instance_id()
	if _animation_cache.has(identity):
		return _animation_cache[identity]
	var tracks: Array = []
	for index: int in animation.get_track_count():
		var keys: Array = []
		for key: int in animation.track_get_key_count(index):
			keys.append([animation.track_get_key_time(index, key), animation.track_get_key_transition(index, key),
				_plain(animation.track_get_key_value(index, key))])
		tracks.append({"type": animation.track_get_type(index), "path": str(animation.track_get_path(index)),
			"interpolation": animation.track_get_interpolation_type(index),
			"loopWrap": animation.track_get_interpolation_loop_wrap(index),
			"enabled": animation.track_is_enabled(index), "keys": keys.size(), "keySha256": _hash(keys)})
	var result := {"length": animation.length, "loopMode": animation.loop_mode, "step": animation.step,
		"tracks": tracks}
	_animation_cache[identity] = result
	return result


func _skeleton(skeleton: Skeleton3D) -> Array:
	var result: Array = []
	for bone: int in skeleton.get_bone_count():
		result.append({"name": str(skeleton.get_bone_name(bone)), "parent": skeleton.get_bone_parent(bone),
			"rest": _vector(skeleton.get_bone_rest(bone)), "position": _vector(skeleton.get_bone_pose_position(bone)),
			"rotation": _vector(skeleton.get_bone_pose_rotation(bone)), "scale": _vector(skeleton.get_bone_pose_scale(bone))})
	return result


func _snapshot(root: Node3D, poses_only := false) -> Dictionary:
	var result: Dictionary = {}
	var nodes: Array[Node] = [root]
	while not nodes.is_empty():
		var node: Node = nodes.pop_back()
		var path := _relative_path(root, node)
		var row := {"class": node.get_class(), "children": []}
		var children := node.get_children()
		for child: Node in children:
			row.children.append(_node_name(child))
			if child is Node3D:
				nodes.append(child)
		if node is Node3D:
			row["transform"] = _vector((node as Node3D).transform)
			row["visible"] = (node as Node3D).visible
		if node is Skeleton3D:
			row["bones"] = _skeleton(node as Skeleton3D)
		if not poses_only:
			if node is MeshInstance3D:
				var instance := node as MeshInstance3D
				row["mesh"] = _mesh(instance.mesh) if instance.mesh != null else null
				row["shadow"] = instance.cast_shadow
				row["skeleton"] = str(instance.skeleton)
				row["skin"] = []
				if instance.skin != null:
					for bind: int in instance.skin.get_bind_count():
						row.skin.append({"bone": instance.skin.get_bind_bone(bind), "name": str(instance.skin.get_bind_name(bind)),
							"pose": _vector(instance.skin.get_bind_pose(bind))})
				row["materials"] = []
				if instance.mesh != null:
					for surface: int in instance.mesh.get_surface_count():
						var material := instance.get_active_material(surface)
						row.materials.append(_material(material) if material != null else null)
				row["blendShapes"] = []
				if instance.mesh != null:
					for shape: int in instance.get_blend_shape_count():
						row.blendShapes.append(instance.get_blend_shape_value(shape))
			if node is MultiMeshInstance3D:
				var batch := node as MultiMeshInstance3D
				var multi := batch.multimesh
				row["multiMesh"] = null
				if multi != null:
					var active_material := batch.material_override
					if active_material == null and multi.mesh != null and multi.mesh.get_surface_count() == 1:
						active_material = multi.mesh.surface_get_material(0)
					row.multiMesh = {"count": multi.instance_count, "visible": multi.visible_instance_count,
						"format": multi.transform_format, "colors": multi.use_colors, "custom": multi.use_custom_data,
						"buffer": _hash(multi.buffer), "mesh": _mesh(multi.mesh) if multi.mesh != null else null,
						"material": _material(active_material) if active_material != null else null, "shadow": batch.cast_shadow}
			if node is CollisionObject3D:
				var body := node as CollisionObject3D
				row["collision"] = {"layer": body.collision_layer, "mask": body.collision_mask, "rayPickable": body.input_ray_pickable}
			if node is CollisionShape3D:
				var collision := node as CollisionShape3D
				var shape: Dictionary = {"disabled": collision.disabled, "class": collision.shape.get_class() if collision.shape != null else "null"}
				if collision.shape is ConcavePolygonShape3D:
					shape["faces"] = _hash((collision.shape as ConcavePolygonShape3D).get_faces())
				elif collision.shape is ConvexPolygonShape3D:
					shape["points"] = _hash((collision.shape as ConvexPolygonShape3D).points)
				elif collision.shape is BoxShape3D:
					shape["size"] = _vector((collision.shape as BoxShape3D).size)
				elif collision.shape is CapsuleShape3D:
					shape.merge({"radius": (collision.shape as CapsuleShape3D).radius,
						"height": (collision.shape as CapsuleShape3D).height})
				row["shape"] = shape
		result[path] = row
	return result


func _difference(expected: Variant, actual: Variant, path: String, tolerance := EPSILON) -> String:
	if (expected is float or expected is int) and (actual is float or actual is int):
		return "" if is_finite(float(expected)) and is_finite(float(actual)) and absf(float(expected) - float(actual)) <= tolerance \
			else "%s: %s != %s" % [path, str(expected), str(actual)]
	if expected is Dictionary and actual is Dictionary:
		if expected.size() != actual.size():
			return path + ": dictionary member count differs"
		for key: Variant in expected:
			if not actual.has(key):
				return path + ": missing " + str(key)
			var found := _difference(expected[key], actual[key], path + "/" + str(key), tolerance)
			if not found.is_empty():
				return found
		return ""
	if expected is Array and actual is Array:
		if expected.size() != actual.size():
			return path + ": array size differs"
		for index: int in expected.size():
			var found := _difference(expected[index], actual[index], path + "/%d" % index, tolerance)
			if not found.is_empty():
				return found
		return ""
	return "" if expected == actual else "%s: %s != %s" % [path, str(expected).left(160), str(actual).left(160)]


func _animations(root: Node3D) -> Dictionary:
	var result: Dictionary = {}
	for node: Node in root.find_children("*", "AnimationPlayer", true, false):
		var player := node as AnimationPlayer
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var animations: Dictionary = {}
		for clip: StringName in player.get_animation_list():
			animations[str(clip)] = _animation(player.get_animation(clip))
		result[_relative_path(root, player)] = animations
	return result


func _sample_poses(root: Node3D, visual_root: Node3D = null) -> Dictionary:
	var result: Dictionary = {}
	if visual_root == null:
		visual_root = root
	for node: Node in root.find_children("*", "AnimationPlayer", true, false):
		var player := node as AnimationPlayer
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		var clips := player.get_animation_list()
		var sampled := 0
		for clip: StringName in clips:
			if clip == &"RESET":
				continue
			# All tracks/keys are checked above. Three deterministic clip samples
			# additionally prove the saved animation paths bind to the live rig.
			if sampled >= 3:
				break
			var animation := player.get_animation(clip)
			player.play(clip)
			for fraction: float in [0.0, 0.37, 0.81]:
				player.seek(animation.length * fraction, true)
				for skeleton: Node in root.find_children("*", "Skeleton3D", true, false):
					(skeleton as Skeleton3D).force_update_all_bone_transforms()
				result["%s|%s|%.2f" % [_relative_path(root, player), str(clip), fraction]] = _snapshot(visual_root, true)
			sampled += 1
		player.stop()
	return result


func _clear_snapshot_caches() -> void:
	_mesh_cache.clear()
	_material_cache.clear()
	_texture_cache.clear()
	_animation_cache.clear()


func _drain() -> void:
	await _tree.physics_frame
	await _tree.process_frame
	await _tree.process_frame


func _physics_probes(root: Node3D) -> Array:
	var candidates: Array[Dictionary] = []
	for node: Node in root.find_children("*", "CollisionShape3D", true, false):
		var collision := node as CollisionShape3D
		var body := collision.get_parent() as CollisionObject3D
		if body == null or body.collision_layer == 0 or collision.disabled or collision.shape == null:
			continue
		var point := Vector3.ZERO
		if collision.shape is ConcavePolygonShape3D:
			var faces := (collision.shape as ConcavePolygonShape3D).get_faces()
			if faces.size() < 3: continue
			point = (faces[0] + faces[1] + faces[2]) / 3.0
		elif collision.shape is BoxShape3D:
			point.y = (collision.shape as BoxShape3D).size.y / 2.0
		else:
			continue
		candidates.append({"path": _relative_path(root, collision), "point": collision.to_global(point),
			"mask": body.collision_layer})
		if candidates.size() >= 4: break
	# Two actual physics barriers ensure the new body's registration reaches
	# the server. Exact helper/callback invocation counts cannot prove a hit.
	await _tree.physics_frame
	await _tree.process_frame
	await _tree.physics_frame
	await _tree.process_frame
	var result: Array = []
	var space := root.get_world_3d().direct_space_state
	for candidate: Dictionary in candidates:
		var point: Vector3 = candidate.point
		var query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 100,
			point - Vector3.UP * 100, int(candidate.mask))
		var hit := space.intersect_ray(query)
		var collider := hit.get("collider") as Node
		result.append({"source": candidate.path, "mask": int(candidate.mask), "hit": not hit.is_empty(),
			"position": _vector(root.to_local(hit.position)) if hit.get("position") is Vector3 else [],
			"collider": _relative_path(root, collider) if collider != null and root.is_ancestor_of(collider) else ""})
	return result


func _retire(root: Node3D, loader: Node) -> void:
	if is_instance_valid(loader):
		loader.call("unload_world")
		loader.queue_free()
	elif is_instance_valid(root):
		root.queue_free()
	await _drain()
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	_clear_snapshot_caches()
	await _drain()


func _load_target(kind: String, path: String, mode: String) -> Dictionary:
	OS.set_environment(Prepared.ENVIRONMENT, mode)
	_expect(Prepared.selected_mode() == mode, "fixture controls the exact prepared selector; remove conflicting --prepared-content argument")
	if Prepared.selected_mode() != mode:
		return {"root": null, "loader": null}
	if kind == "world":
		var loader := WorldLoader.new()
		_tree.root.add_child(loader)
		loader.load_world(path)
		loader.set_process(false) # Never let a raw cache write change this comparison.
		return {"root": loader.world_root, "loader": loader, "cacheStatus": str(loader.cache_status)}
	if kind == "scene":
		var root: Node3D
		if mode == "raw":
			var packed := GlbSceneCache._build_raw(path)
			root = packed.instantiate() as Node3D if packed != null else null
		else:
			root = GlbSceneCache.instantiate(path)
		if root != null:
			_tree.root.add_child(root)
		return {"root": root, "loader": null}
	if kind == "mesh":
		var instance := MeshInstance3D.new()
		instance.name = "PrototypeReference"
		instance.mesh = MeshPool.acquire(path.get_file().get_basename(), path)
		_expect(instance.mesh != null, "actual prototype mesh loads in " + mode + ": " + path)
		_tree.root.add_child(instance)
		return {"root": instance, "loader": null}
	return {"root": null, "loader": null}


func _hit_map() -> Dictionary:
	var result: Dictionary = {}
	for entry: Dictionary in Prepared.snapshot().consumed_entries:
		result[str(entry.entry_id)] = int(entry.hits)
	return result


func _isolate(first: Node3D, second: Node3D) -> Dictionary:
	var material_checks := 0
	var batch_checks := 0
	var counterparts: Dictionary = {".": second}
	for node: Node in second.find_children("*", "", true, false):
		counterparts[_relative_path(second, node)] = node
	for node: Node in first.find_children("*", "", true, false):
		var other := counterparts.get(_relative_path(first, node)) as Node
		if node is MeshInstance3D and other is MeshInstance3D:
			var a := node as MeshInstance3D
			var b := other as MeshInstance3D
			if a.mesh != null and a.mesh.get_surface_count() > 0:
				var ma := a.get_active_material(0)
				var mb := b.get_active_material(0)
				if ma != null and mb != null:
					var original := mb.render_priority
					var prior := ma.render_priority
					ma.render_priority = 1 if prior == 0 else 0
					_expect(mb.render_priority == original, "native instance material mutation remains private: " + str(first.get_path_to(node)))
					ma.render_priority = prior
					material_checks += 1
		if node is MultiMeshInstance3D and other is MultiMeshInstance3D:
			var a := (node as MultiMeshInstance3D).multimesh
			var b := (other as MultiMeshInstance3D).multimesh
			if a != null and b != null and a.instance_count > 0 and b.instance_count > 0:
				var original := b.get_instance_transform(0)
				var prior := a.get_instance_transform(0)
				var changed := prior
				changed.origin += Vector3(0.25, 0, 0)
				a.set_instance_transform(0, changed)
				_expect(b.get_instance_transform(0) == original, "native instance MultiMesh buffer mutation remains private")
				a.set_instance_transform(0, prior)
				batch_checks += 1
	return {"materials": material_checks, "multiMeshes": batch_checks}


func _required_actor_sources() -> Array[String]:
	var models := _json("res://data/actors/models.json")
	var equipment := _json("res://data/actors/equipment.json")
	var model: Dictionary = models.get("models", {}).get("luminous_male", {})
	var result: Array[String] = []
	for source: String in [str(model.get("scene", "")), str(model.get("animationLibrary", ""))]:
		if not source.is_empty(): result.append(Prepared.logical_source(source))
	var hair: Array = model.get("hairStyles", [])
	if hair.size() > 4: result.append(Prepared.logical_source(str(hair[4])))
	var groups: Array = equipment.get("fitGroups", {}).get("luminous_male", [])
	var aliases: Dictionary = equipment.get("aliases", {})
	for slot: int in FULL_KIT_A:
		var key := "%d:%d" % [slot, int(FULL_KIT_A[slot])]
		var seen: Dictionary = {}
		while aliases.has(key) and not seen.has(key):
			seen[key] = true
			key = str(aliases[key])
		var config: Dictionary = equipment.get("models", {}).get(key, {}).duplicate(true)
		var variants: Dictionary = config.get("variants", {})
		for group: String in groups:
			if variants.has(group):
				config.merge(variants[group], true)
				break
		var source := str(config.get("scene", ""))
		_expect(not source.is_empty(), "FULL_KIT_A source resolves for " + key)
		if not source.is_empty(): result.append(Prepared.logical_source(source))
	_expect(result.size() == 10, "actual body/hair/universal and seven FULL_KIT_A component paths resolve")
	return result


func _clear_actor_caches() -> void:
	# Fixture mode switches must not reuse raw-derived wardrobe Resources in
	# the native arm. Normal clients select representation for the process.
	# Only call after all fixture actors have been freed and drained.
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	ReplicatedActor3D._equipment_pieces_cache.clear()
	ReplicatedActor3D._rebound_skins.clear()
	ReplicatedActor3D._drape_envelopes.clear()
	ReplicatedActor3D._draped_capes.clear()
	ReplicatedActor3D._torso_reaches.clear()
	ReplicatedActor3D._fabric_lines.clear()
	ReplicatedActor3D._shin_reaches.clear()
	ReplicatedActor3D._health_gradient = null
	ReplicatedActor3D._stand_in_mesh = null
	ReplicatedActor3D._stand_in_material = null
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()


func _equipped_actor(mode: String, kit: Dictionary = FULL_KIT_A, appearance: Dictionary = {}) -> ReplicatedActor3D:
	OS.set_environment(Prepared.ENVIRONMENT, mode)
	_expect(Prepared.selected_mode() == mode, "actor arm uses requested representation")
	if mode == "raw":
		# Match shipping loose GLTF, even if this source project happens to have
		# actor importer products with different generated LODs/compression.
		var scenes: Dictionary = {}
		for source: String in _required_actor_sources():
			var path := Prepared.source_path(source)
			var packed := GlbSceneCache._build_raw(path)
			_expect(packed != null, "raw actor component preseed " + source)
			if packed != null:
				scenes[ProjectSettings.globalize_path(path)] = packed
		GlbSceneCache.install_prepared(scenes)
	var models := _json("res://data/actors/models.json")
	var model: Dictionary = models.get("models", {}).get("luminous_male", {})
	var mapping := _json(str(model.get("animationMap", "")))
	var equipment := _json("res://data/actors/equipment.json")
	var actor := ReplicatedActor3D.new()
	actor.name = "PreparedParityActor"
	actor.process_mode = Node.PROCESS_MODE_DISABLED
	_tree.root.add_child(actor)
	var errors := actor.configure({"actor_id": 4242, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "actor_type": 1, "name": "PreparedParity", "health": 5000, "max_health": 5000,
		"alive": true, "appearance": appearance.duplicate(true), "equipment_visuals": kit.duplicate()},
		CoordinateAdapter.new(), model, mapping, equipment)
	_expect(errors.is_empty(), "actual FULL_KIT_A actor configures in " + mode + ": " + str(errors))
	_expect(actor.get_skeleton() != null and actor.animation_player != null,
		"actual FULL_KIT_A actor has retargeted rig/animation player in " + mode)
	return actor


func _actor_hair_state(actor: ReplicatedActor3D) -> Dictionary:
	var holders := 0
	var visible_meshes := 0
	var skeleton := actor.get_skeleton()
	if skeleton != null:
		for child: Node in skeleton.get_children():
			if not str(child.name).begins_with("AppearanceHair_"): continue
			holders += 1
			for node: Node in child.find_children("*", "MeshInstance3D", true, false):
				visible_meshes += 1 if (node as MeshInstance3D).is_visible_in_tree() else 0
	for node: Node in actor.find_children("hair", "MeshInstance3D", true, false):
		visible_meshes += 1 if (node as MeshInstance3D).is_visible_in_tree() else 0
	return {"style": AppearanceVariants.hair_style(int(actor._appearance.get("hair", 0))),
		"headVisual": int(actor._equipment_visuals.get(3, 0)),
		"wardrobeHidesHair": actor._hidden_body_surfaces.has("hair"),
		"holders": holders, "visibleHairMeshes": visible_meshes}


func _check_actor_hair_state(state: Dictionary, kit: Dictionary, expect_hair: bool, label: String) -> void:
	_expect(int(state.headVisual) == int(kit.get(3, 0)), "actual head equipment matches kit " + label)
	if expect_hair:
		_expect(int(state.style) == 4 and int(state.holders) > 0 and int(state.visibleHairMeshes) > 0
			and not bool(state.wardrobeHidesHair), "hatless actual fitted hairstyle is present and visible " + label)
	else:
		# The unchanged FULL_KIT_A anchor has appearance{}: style zero is
		# deliberately bald. Record actual wardrobe hiding separately rather
		# than falsely attributing this absence to weapon114 or a helmet.
		_expect(int(state.style) == 0 and int(state.holders) == 0 and int(state.visibleHairMeshes) == 0,
			"full kit preserves intentional bald/default hair policy " + label)


func _head_component_source() -> String:
	var models := _json("res://data/actors/models.json")
	var equipment := _json("res://data/actors/equipment.json")
	var config: Dictionary = equipment.get("models", {}).get("3:117", {}).duplicate(true)
	for group: String in equipment.get("fitGroups", {}).get("luminous_male", []):
		if config.get("variants", {}).has(group):
			config.merge(config.variants[group], true)
			break
	return Prepared.logical_source(str(config.get("scene", "")))


func _equipped_actor_parity() -> void:
	var sources := _required_actor_sources()
	var hair := sources[2]
	var full_sources: Array[String] = sources.duplicate()
	full_sources.erase(hair)
	await _equipped_kit_parity(FULL_KIT_A, {}, "FULL_KIT_A", "equippedActor", full_sources, false)
	if not _errors.is_empty(): return
	var hatless := FULL_KIT_A.duplicate()
	hatless[3] = 0
	var hatless_sources: Array[String] = sources.duplicate()
	hatless_sources.erase(_head_component_source())
	await _equipped_kit_parity(hatless, {"hair": AppearanceVariants.pack_hair(4, 0)},
		"FULL_KIT_A_HATLESS_STYLE4", "hatlessEquippedActor", hatless_sources, true)


func _equipped_kit_parity(kit: Dictionary, appearance: Dictionary, label: String, report_key: String, actor_sources: Array[String], expect_hair: bool) -> void:
	_clear_actor_caches()
	var raw := _equipped_actor("raw", kit, appearance)
	var raw_model := raw.get_node_or_null("NativeModel") as Node3D
	if raw_model == null:
		_expect(false, "raw actor native model exists")
		raw.queue_free()
		await _drain()
		_clear_actor_caches()
		return
	var raw_hair := _actor_hair_state(raw)
	_check_actor_hair_state(raw_hair, kit, expect_hair, label + "/raw")
	var expected := _snapshot(raw_model)
	var animations := _animations(raw)
	var samples := _sample_poses(raw, raw_model)
	raw.queue_free()
	await _drain()
	_clear_actor_caches()
	_clear_snapshot_caches()
	await _drain()
	var before := _hit_map()
	var native := _equipped_actor("require-pilot", kit, appearance)
	var native_model := native.get_node_or_null("NativeModel") as Node3D
	if native_model == null:
		_expect(false, "prepared actor native model exists")
		native.queue_free()
		await _drain()
		_clear_actor_caches()
		return
	var native_hair := _actor_hair_state(native)
	_check_actor_hair_state(native_hair, kit, expect_hair, label + "/native")
	_expect(_difference(raw_hair, native_hair, label + "/hair-policy").is_empty(), "actual hair visibility policy parity " + label)
	var difference := _difference(expected, _snapshot(native_model), label)
	_expect(difference.is_empty(), "actual equipped actor hierarchy/wardrobe/skin/material parity " + difference)
	var animation_difference := _difference(animations, _animations(native), label + "/retargeted")
	_expect(animation_difference.is_empty(), "actual equipped actor retargeted clips parity " + animation_difference)
	var pose_difference := _difference(samples, _sample_poses(native, native_model), label + "/poses", SAMPLE_EPSILON)
	_expect(pose_difference.is_empty(), "actual equipped actor sampled live poses parity " + pose_difference)
	var consumed: Array = []
	for entry: Dictionary in Prepared.snapshot().consumed_entries:
		if int(entry.hits) > int(before.get(str(entry.entry_id), 0)):
			consumed.append(entry.duplicate())
	for source: String in actor_sources:
		var observed := false
		for entry: Dictionary in consumed:
			if str(entry.source) == source and str(entry.kind) == "scene":
				observed = true
		_expect(observed, "actual equipped actor consumes native component " + source)
	_report[report_key] = {"kit": kit, "appearance": appearance, "componentSources": actor_sources,
		"rawHairPolicy": raw_hair, "nativeHairPolicy": native_hair,
		"consumed": consumed, "nodeCount": expected.size(), "animationPlayers": animations.size(),
		"sampledClipFrames": samples.size(), "parity": difference.is_empty() and animation_difference.is_empty() and pose_difference.is_empty(),
		"scope": "configure/wardrobe/retarget/manual clip sampling; process/cloth/mount/effects disabled"}
	native.queue_free()
	await _drain()
	_clear_actor_caches()
	_clear_snapshot_caches()
	await _drain()


func run(tree: SceneTree, plan_path: String) -> Dictionary:
	_tree = tree
	var prior_mode := OS.get_environment(Prepared.ENVIRONMENT)
	_prior_no_map_cache = OS.get_environment("ELORIA_NO_MAP_CACHE")
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	MapCache.forget_setting()
	var plan := _json(plan_path)
	_expect(int(plan.get("schema_version", 0)) == 1 and plan.get("required_targets") is Array,
		"exact describe-pilot qualification plan is required")
	_report = {"schemaVersion": 1, "fixture": "prepared_content_pilot", "targets": [],
		"runtimeBuild": {"template": OS.has_feature("template"), "editor": OS.has_feature("editor"),
			"globalizedResourceRoot": ProjectSettings.globalize_path("res://"),
			"resolvedProjectRoot": Prepared._project_root(),
			"userDataDir": OS.get_user_data_dir()}, "engine": Engine.get_version_info(),
		"textureSkip": Graphics.active_texture_skip(), "usableFormats": Vram.usable_formats(),
		"scope": "direct selected component and independent package parity; no gameplay/camera/route/performance claim"}
	if not _errors.is_empty():
		return _finish(prior_mode)
	var texture := str(plan.get("expected_texture_quality", ""))
	_expect(texture in Graphics.TEXTURE_QUALITIES and Graphics.active_texture_skip() == Graphics.TEXTURE_QUALITIES.find(texture),
		"actual isolated texture profile matches explicit qualification plan")
	_expect(Quantization.ensure_registered() and Vram.ensure_registered() and MapExtension.ensure_registered(),
		"main initializes every runtime extension before actual asset work")
	var targets: Array = plan.required_targets
	var selected: Dictionary = {}
	var worlds := 0
	var prototypes := 0
	for target: Dictionary in targets:
		selected[str(target.get("source", ""))] = true
		worlds += 1 if str(target.get("kind", "")) == "world" else 0
		prototypes += 1 if str(target.get("kind", "")) == "mesh" else 0
	_expect(worlds >= 2 and prototypes >= 1 and selected.has(str(plan.get("chunk_source", ""))),
		"plan includes exact selected child, independent interior and shared prototype")
	_expect(selected.has("godot-client/assets/world/interactives/storage.glb"), "plan includes approved storage")
	for source: String in _required_actor_sources():
		_expect(selected.has(source), "plan covers actual FULL_KIT_A/body/hair/universal component " + source)
	for target: Dictionary in targets:
		if not _errors.is_empty(): break
		var kind := str(target.kind)
		var logical := str(target.source)
		var path := Prepared.source_path(logical)
		_expect(not path.is_empty() and FileAccess.file_exists(path), "selected raw runtime input exists: " + logical)
		if not _errors.is_empty(): break
		GlbSceneCache.clear()
		var raw_began := Time.get_ticks_usec()
		var raw := _load_target(kind, path, "raw")
		var raw_root := raw.get("root") as Node3D
		_expect(raw_root != null, "raw source is usable: " + logical)
		if raw_root == null:
			await _retire(raw_root, raw.get("loader") as Node)
			break
		var expected := _snapshot(raw_root)
		var expected_animations := _animations(raw_root)
		var expected_poses := _sample_poses(raw_root)
		var expected_physics: Array = []
		if kind == "world":
			expected_physics = await _physics_probes(raw_root)
			_expect(not expected_physics.is_empty(), "real world source exposes collision probes: " + logical)
			for probe: Dictionary in expected_physics:
				_expect(bool(probe.hit), "raw registered physics ray hits: " + logical + "/" + str(probe.source))
		var raw_us := Time.get_ticks_usec() - raw_began
		await _retire(raw_root, raw.get("loader") as Node)
		raw.clear()
		var before := _hit_map()
		var native_began := Time.get_ticks_usec()
		var native := _load_target(kind, path, "require-pilot")
		var native_root := native.get("root") as Node3D
		_expect(native_root != null, "required native variant is usable: " + logical)
		if native_root == null:
			await _retire(native_root, native.get("loader") as Node)
			break
		var after := _hit_map()
		var consumed: Array = []
		for entry: Dictionary in Prepared.snapshot().consumed_entries:
			if str(entry.source) == logical and str(entry.kind) == kind and int(entry.hits) > int(before.get(str(entry.entry_id), 0)):
				consumed.append(entry.duplicate())
		_expect(not consumed.is_empty(), "actual positive exact prepared consumed entry: " + logical)
		var actual := _snapshot(native_root)
		var difference := _difference(expected, actual, logical)
		_expect(difference.is_empty(), "node/TRS/mesh/skin/material/image/collision parity " + difference)
		var animation_difference := _difference(expected_animations, _animations(native_root), logical + "/animations")
		_expect(animation_difference.is_empty(), "all animation tracks/keys parity " + animation_difference)
		var pose_difference := _difference(expected_poses, _sample_poses(native_root), logical + "/samples", SAMPLE_EPSILON)
		_expect(pose_difference.is_empty(), "live sampled animation/rig parity " + pose_difference)
		var physics_difference := ""
		if kind == "world":
			var actual_physics: Array = await _physics_probes(native_root)
			physics_difference = _difference(expected_physics, actual_physics, logical + "/physics", SAMPLE_EPSILON)
			_expect(physics_difference.is_empty(), "actual registered ray-hit parity " + physics_difference)
		var isolation := {"materials": 0, "multiMeshes": 0}
		if kind != "mesh":
			var second := _load_target(kind, path, "require-pilot")
			var second_root := second.get("root") as Node3D
			_expect(second_root != null, "second native instance is usable for isolation: " + logical)
			if second_root != null:
				isolation = _isolate(native_root, second_root)
			await _retire(second_root, second.get("loader") as Node)
		var native_us := Time.get_ticks_usec() - native_began
		_report.targets.append({"kind": kind, "source": logical, "nodeCount": expected.size(),
			"animationPlayers": expected_animations.size(), "sampledClipFrames": expected_poses.size(),
			"physicsProbes": expected_physics,
			"consumed": consumed, "isolation": isolation,
			"rawDiagnosticWallUsec": raw_us, "nativeDiagnosticWallUsec": native_us,
			"diagnosticIncludesReadbackAndValidation": true,
			"parity": difference.is_empty() and animation_difference.is_empty() and pose_difference.is_empty() and physics_difference.is_empty()})
		await _retire(native_root, native.get("loader") as Node)
		native.clear()
		before.clear()
		after.clear()
	if _errors.is_empty():
		await _equipped_actor_parity()
	return _finish(prior_mode)


func _finish(prior_mode: String) -> Dictionary:
	if prior_mode.is_empty(): OS.unset_environment(Prepared.ENVIRONMENT)
	else: OS.set_environment(Prepared.ENVIRONMENT, prior_mode)
	if _prior_no_map_cache.is_empty(): OS.unset_environment("ELORIA_NO_MAP_CACHE")
	else: OS.set_environment("ELORIA_NO_MAP_CACHE", _prior_no_map_cache)
	MapCache.forget_setting()
	_report["ready"] = _errors.is_empty()
	_report["assertions"] = _assertions
	_report["errors"] = _errors.duplicate()
	var output := OS.get_environment("RABBITLANDS_PREPARED_PARITY_REPORT").strip_edges()
	if output.is_empty(): output = "user://prepared-content-pilot-report.json"
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(_report, "\t", true, true))
		file.close()
	else:
		_report.ready = false
		_report.errors.append("cannot write parity report")
	print("PREPARED_CONTENT_PILOT ", "PASS" if bool(_report.ready) else "FAIL", " targets=", _report.targets.size(), " assertions=", _assertions)
	for error: String in _report.errors:
		print("PREPARED_CONTENT_PILOT_FAILURE ", error)
	return _report
