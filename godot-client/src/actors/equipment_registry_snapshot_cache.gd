class_name EquipmentRegistrySnapshotCache
extends RefCounted
## Bounded registry of explicitly prepared, immutable equipment catalogues.
## Main prepares its JSON catalogue once; actors acquire that exact frozen
## snapshot by identity. Arbitrary mutable dictionaries retain the former
## Dictionary.duplicate(true) behavior and are never remembered by identity.

const CAPACITY := 4

static var _prepared: Array[Dictionary] = []
static var _prepares := 0
static var _hits := 0
static var _fallback_copies := 0
static var _uncached_prepares := 0


static func prepare(candidate: Dictionary) -> Dictionary:
	# The production catalogue is JSON-shaped. Unexpected Objects or recursive
	# containers preserve defensive-copy behavior but are not registered.
	if not _cacheable(candidate, []):
		_uncached_prepares += 1
		return candidate.duplicate(true)
	var snapshot := _frozen_copy(candidate) as Dictionary
	_prepared.append(snapshot)
	_prepares += 1
	while _prepared.size() > CAPACITY:
		_prepared.pop_front()
	return snapshot


static func acquire(candidate: Dictionary) -> Dictionary:
	for snapshot: Dictionary in _prepared:
		if is_same(candidate, snapshot):
			_hits += 1
			return snapshot
	_fallback_copies += 1
	return candidate.duplicate(true)


static func clear() -> void:
	_prepared.clear()
	_prepares = 0
	_hits = 0
	_fallback_copies = 0
	_uncached_prepares = 0


static func stats() -> Dictionary:
	return {
		"capacity": CAPACITY,
		"entries": _prepared.size(),
		"prepares": _prepares,
		"hits": _hits,
		"fallbackCopies": _fallback_copies,
		"uncachedPrepares": _uncached_prepares,
	}


static func _frozen_copy(value: Variant) -> Variant:
	if value is Dictionary:
		var out: Dictionary = value.duplicate(false)
		for key: Variant in out.keys():
			out[key] = _frozen_copy(value[key])
		out.make_read_only()
		return out
	if value is Array:
		var out: Array = value.duplicate(false)
		for index: int in range(value.size()):
			out[index] = _frozen_copy(value[index])
		out.make_read_only()
		return out
	return value


static func _cacheable(value: Variant, ancestors: Array, dictionary_key := false) -> bool:
	if value is Object:
		return false
	# The production JSON contains scalar keys and ordinary containers only.
	# Container keys can retain mutable identity, while packed arrays cannot be
	# made read-only. Both stay on the old defensive-copy path.
	if dictionary_key and (value is Dictionary or value is Array):
		return false
	if value is PackedByteArray or value is PackedInt32Array \
			or value is PackedInt64Array or value is PackedFloat32Array \
			or value is PackedFloat64Array or value is PackedStringArray \
			or value is PackedVector2Array or value is PackedVector3Array \
			or value is PackedColorArray or value is PackedVector4Array:
		return false
	if value is Dictionary or value is Array:
		for ancestor: Variant in ancestors:
			if is_same(ancestor, value):
				return false
		ancestors.append(value)
		if value is Dictionary:
			for key: Variant in value:
				if not _cacheable(key, ancestors, true) \
						or not _cacheable(value[key], ancestors):
					ancestors.pop_back()
					return false
		else:
			for child: Variant in value:
				if not _cacheable(child, ancestors):
					ancestors.pop_back()
					return false
		ancestors.pop_back()
	return true
