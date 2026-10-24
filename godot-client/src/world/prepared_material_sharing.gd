extends RefCounted
## Resource-only canonicalization. No dependency on ExternalMeshPool: that pool
## calls this adapter while publishing its own prepared prototype.
const TexturePool := preload("res://src/world/external_texture_pool.gd")
static var _mutex := Mutex.new()
static var _meshes: Dictionary = {}

static func material(source: Material, images: Dictionary) -> Material:
	var result := source.duplicate(false) as Material
	for property: Dictionary in result.get_property_list():
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var value: Variant = result.get(str(property.name))
		if value is ImageTexture and images.has(value.resource_path):
			result.set(str(property.name), TexturePool._publish_or_adopt(
				str(images[value.resource_path]), value as ImageTexture))
	return result

static func mesh_resource(record: Dictionary) -> Mesh:
	var source := record.get("resource") as Mesh
	if str(record.get("status", "")) != "hit" or source == null:
		return null
	var entry: Dictionary = record.get("entry", {})
	var images: Dictionary = entry.get("shared_images", {})
	var key := str(source.get_instance_id()) + "|" + JSON.stringify(images, "", true)
	_mutex.lock()
	var prior: WeakRef = _meshes.get(key)
	var shared := prior.get_ref() as Mesh if prior != null else null
	_mutex.unlock()
	if shared != null:
		return shared
	# A shared native template is immutable. Change only the duplicate's surface
	# material references, then let the ordinary weak mesh pool publish/adopt it.
	var changed: Dictionary = {}
	for surface: int in source.get_surface_count():
		var template := source.surface_get_material(surface)
		if template != null:
			var replacement: Material = null
			for property: Dictionary in template.get_property_list():
				if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
					continue
				var value: Variant = template.get(str(property.name))
				if value is ImageTexture and images.has(value.resource_path):
					var canonical := TexturePool._publish_or_adopt(str(images[value.resource_path]), value)
					if canonical != value:
						if replacement == null:
							replacement = template.duplicate(false) as Material
						replacement.set(str(property.name), canonical)
			if replacement != null:
				changed[surface] = replacement
	var candidate := source
	if not changed.is_empty():
		candidate = source.duplicate(false) as Mesh
		for surface: int in changed:
			candidate.surface_set_material(surface, changed[surface] as Material)
	_mutex.lock()
	prior = _meshes.get(key)
	shared = prior.get_ref() as Mesh if prior != null else null
	if shared == null:
		shared = candidate
		_meshes[key] = weakref(shared)
	_mutex.unlock()
	return shared
