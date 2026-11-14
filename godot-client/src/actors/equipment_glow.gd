extends RefCounted
## One sparse particle draw per equipped item; authored surfaces stay untouched.
const Palette := preload("res://src/ui/item_glow.gd")
const Motes := preload("res://src/actors/equipment_motes_3d.gd")
var _parts: Dictionary = {}

func sync(nodes: Dictionary, descriptors: Dictionary, skeleton: Skeleton3D) -> void:
	for part: Variant in _parts.keys():
		var sources: Array = nodes.get(part, [])
		var style := Palette.profile(descriptors.get(str(part), descriptors.get(part, {})))
		var record: Dictionary = _parts[part]
		if not is_instance_valid(record.emitter) or style.get("key", "") != record.key or sources != record.sources:
			_clear(part)
	for part: Variant in nodes:
		if _parts.has(part): continue
		var style := Palette.profile(descriptors.get(str(part), descriptors.get(part, {})))
		if style.is_empty(): continue
		var sources: Array[MeshInstance3D] = []
		for node: Node in nodes[part]:
			var meshes: Array[Node] = [node]
			meshes.append_array(node.find_children("*", "MeshInstance3D", true, false))
			for candidate: Node in meshes:
				if not candidate is MeshInstance3D or candidate.is_queued_for_deletion(): continue
				var source := candidate as MeshInstance3D
				if source.mesh != null: sources.append(source)
		if sources.is_empty(): continue
		var emitter := Motes.new()
		emitter.name = "ItemMotes"
		sources[0].add_child(emitter)
		emitter.configure(sources, style, skeleton)
		_parts[part] = {"key": style.key, "sources": nodes[part].duplicate(), "emitter": emitter}

func _clear(part: Variant) -> void:
	var emitter: Variant = _parts[part].emitter
	if is_instance_valid(emitter):
		emitter.hide()
		emitter.set_process(false)
		emitter.queue_free()
	_parts.erase(part)
