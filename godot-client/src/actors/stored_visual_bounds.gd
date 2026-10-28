extends RefCounted
## Keep actor placement/picking stable when unused morph envelopes are removed.
## Renderer culling continues to use the mesh's actual (potentially smaller)
## bounds. This optional record affects only the actor's logical presentation.
const KEY := "rabbitlands_actor_bounds_v1"

static func read(mesh: MeshInstance3D) -> AABB:
	var fallback := mesh.get_aabb()
	if mesh.mesh == null: return fallback
	var extras: Variant = mesh.mesh.get_meta("extras",{})
	if not extras is Dictionary: return fallback
	var record: Variant = extras.get(KEY)
	if not record is Dictionary: return fallback
	var position: Variant = record.get("position")
	var size: Variant = record.get("size")
	if not position is Array or not size is Array or position.size() != 3 or size.size() != 3: return fallback
	for axis in 3:
		if not (position[axis] is float or position[axis] is int) or not (size[axis] is float or size[axis] is int): return fallback
		if not is_finite(float(position[axis])) or not is_finite(float(size[axis])) or float(size[axis]) < 0: return fallback
	var span := Vector3(float(size[0]),float(size[1]),float(size[2]))
	var origin := Vector3(float(position[0]),float(position[1]),float(position[2]))
	if span == Vector3.ZERO or not span.is_finite() or not origin.is_finite(): return fallback
	return AABB(origin,span)
