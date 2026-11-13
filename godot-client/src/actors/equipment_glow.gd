extends RefCounted
## Secondary meshes leave shared authored materials and the occlusion overlay
## untouched. Their additive pass is visible even without HDR bloom.
const Palette := preload("res://src/ui/item_glow.gd")
const SHADER := preload("res://src/actors/equipment_glow.gdshader")
const RetainedSkin := preload("res://src/mounts/retained_mount_skin.gd")
const META := "item_glow_clone"
var _parts: Dictionary = {}

func sync(nodes: Dictionary, descriptors: Dictionary, skeleton: Skeleton3D) -> void:
	for part: Variant in _parts.keys():
		var sources: Array = nodes.get(part, [])
		var style := Palette.profile(descriptors.get(str(part), descriptors.get(part, {})))
		var record: Dictionary = _parts[part]
		if style.get("key", "") != record.key or sources != record.sources:
			_clear(part)
		else:
			for pair: Dictionary in record.pairs:
				if not is_instance_valid(pair.source) or not is_instance_valid(pair.clone): continue
				var source: MeshInstance3D = pair.source
				var clone: MeshInstance3D = pair.clone
				for shape: int in source.get_blend_shape_count():
					clone.set_blend_shape_value(shape, source.get_blend_shape_value(shape))
	for part: Variant in nodes:
		if _parts.has(part): continue
		var style := Palette.profile(descriptors.get(str(part), descriptors.get(part, {})))
		if style.is_empty(): continue
		var material := ShaderMaterial.new()
		material.shader = SHADER
		var colors := PackedColorArray(style.colors)
		var families := PackedInt32Array(style.families)
		material.set_shader_parameter("color_count", colors.size())
		while colors.size() < 4: colors.append(colors[0])
		while families.size() < 4: families.append(families[0])
		material.set_shader_parameter("colors", colors)
		material.set_shader_parameter("families", families)
		material.set_shader_parameter("strength", style.strength)
		var clones: Array[MeshInstance3D] = []
		var pairs: Array[Dictionary] = []
		for node: Node in nodes[part]:
			var meshes: Array[Node] = [node]
			meshes.append_array(node.find_children("*", "MeshInstance3D", true, false))
			for candidate: Node in meshes:
				if not candidate is MeshInstance3D or candidate.has_meta(META): continue
				var source := candidate as MeshInstance3D
				if source.mesh == null or source.is_queued_for_deletion(): continue
				var reference := RetainedSkin.for_secondary(source.mesh, source.skin, skeleton)
				if not reference.errors.is_empty():
					push_error(str(reference.errors))
					continue
				var clone := MeshInstance3D.new()
				clone.name = "ItemGlow"
				clone.set_meta(META, true)
				clone.mesh = reference.mesh
				clone.material_override = material
				clone.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				clone.layers = 2 # gameplay only; omitted from map cameras/silhouettes
				# Inherit visibility, transforms and bone attachments from the source.
				source.add_child(clone)
				if source.skin != null and skeleton != null:
					clone.skin = source.skin
					clone.skeleton = clone.get_path_to(skeleton)
				for shape: int in source.get_blend_shape_count():
					clone.set_blend_shape_value(shape, source.get_blend_shape_value(shape))
				clones.append(clone)
				pairs.append({"source": source, "clone": clone})
		_parts[part] = {"key": style.key, "sources": nodes[part].duplicate(), "clones": clones, "pairs": pairs}

func _clear(part: Variant) -> void:
	for clone: Variant in _parts[part].clones:
		if is_instance_valid(clone):
			clone.hide()
			clone.queue_free()
	_parts.erase(part)
