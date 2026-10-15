class_name ReboundSkinPool
extends RefCounted
## Candidate pool for finalized rebound Skin resources.
##
## The returned Skin is borrowed immutable state: callers must finish building a
## candidate before interning it and must never mutate a returned resource.
## Keeping the resource itself, rather than rebuilding it per mesh, preserves
## Godot's identity-based Skeleton3D SkinReference registration.

static var _interned: Dictionary = {}


static func intern_finalized(candidate: Skin) -> Skin:
	if candidate == null:
		return null
	var key := _content_key(candidate)
	var existing := _interned.get(key) as Skin
	if existing != null:
		return existing
	_interned[key] = candidate
	return candidate


static func _content_key(skin: Skin) -> String:
	# Variant serialization preserves the exact float bytes in each Transform3D
	# and the ordered bind count, names, bone indexes, and poses. Hex encoding
	# makes the complete byte sequence an exact Dictionary key; this is not a
	# hash-only alias and never uses approximate transform comparison.
	var binds: Array = [skin.get_bind_count()]
	for index: int in range(skin.get_bind_count()):
		binds.append([
			skin.get_bind_name(index),
			skin.get_bind_bone(index),
			skin.get_bind_pose(index),
		])
	return var_to_bytes(binds).hex_encode()
