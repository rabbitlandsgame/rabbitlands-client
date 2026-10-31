extends RefCounted
## Data-only marks for Main's existing actor loop. Main owns all visibility,
## living, local-player and duplicate-service filtering and passes drawn node
## positions, including deferred bodies. Call retain(actor_nodes) once before
## collecting; it establishes a bounded current-population capacity.
## Returned dictionaries are read-only to consumers and never pooled across IDs.

const ACTOR_GRACE := 32
const MAX_STYLES := 64
var _marks: Dictionary = {}
var _style_keys: Dictionary = {}
var _styles: Dictionary = {}
var _capacity := ACTOR_GRACE

func mark(actor_id: int, position: Vector3, dto: Dictionary) -> Dictionary:
	var key := Vector2i(int(dto.get("kind", 0)), int(dto.get("name_colour", 0)))
	var existing: Variant = _marks.get(actor_id)
	var result: Dictionary
	if existing != null:
		result = existing
		if _style_keys[actor_id] != key:
			var style := _style(key, dto)
			result["type"] = style.type
			result["colour"] = style.colour
			_style_keys[actor_id] = key
	else:
		if _marks.size() >= _capacity:
			# Only misses under actor-ID churn reach this path. Discard a cache
			# reference, never repurpose the dictionary an overlay may still hold.
			var oldest: Variant = _marks.keys()[0]
			_marks.erase(oldest)
			_style_keys.erase(oldest)
		var style := _style(key, dto)
		result = {"position": position, "type": style.type, "colour": style.colour}
		_marks[actor_id] = result
		_style_keys[actor_id] = key
	result["position"] = position
	return result

func _style(key: Vector2i, dto: Dictionary) -> Dictionary:
	var existing: Variant = _styles.get(key)
	if existing != null:
		return existing
	if _styles.size() >= MAX_STYLES:
		_styles.clear()
	var result := {"type": actor_type(dto), "colour": ReplicatedActor3D.map_dot_colour(dto)}
	_styles[key] = result
	return result

func retain(actor_nodes: Dictionary) -> void:
	_capacity = actor_nodes.size() + ACTOR_GRACE
	if _marks.size() <= _capacity:
		return
	for actor_id: Variant in _marks.keys():
		if not actor_nodes.has(actor_id):
			_marks.erase(actor_id)
			_style_keys.erase(actor_id)
			if _marks.size() <= _capacity:
				break

func clear() -> void:
	_marks.clear()
	_style_keys.clear()
	_styles.clear()
	_capacity = ACTOR_GRACE

static func actor_type(dto: Dictionary) -> StringName:
	var kind: int = int(dto.get("kind", 0))
	if kind == ReplicatedActor3D.CREATURE_ACTOR_KIND:
		return (&"invasion" if int(dto.get("name_colour", 0))
			== ReplicatedActor3D.INVASION_NAME_COLOUR else &"creature")
	return &"player" if kind in [1, 3, 4] else &"npc"
