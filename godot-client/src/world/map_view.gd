extends RefCounted
## Shared framing for the live Tab map. Backdrop meshes are not map extents.

const RESOLUTION := 1024
const MARGIN := 1.04
## Metres of the neighbours shown around a continent exterior on the Tab map,
## where their pictures stand and a click walks across the seam.
const NEIGHBOUR_BUFFER_METRES := 96.0

static func bounds_for(manifest: WorldManifest, section_id: String = "") -> AABB:
	var asset: Dictionary = manifest.data.get("asset", {})
	if bool(manifest.data.get("secret", false)) and not section_id.is_empty():
		for section: Dictionary in manifest.data.get("sections", []):
			if str(section.get("id", "")) != section_id:
				continue
			var section_bounds: Dictionary = section.get("bounds", {})
			var low: Array = section_bounds.get("min", [])
			var high: Array = section_bounds.get("max", [])
			if low.size() == 2 and high.size() == 2:
				var world_bounds := _bounds(asset.get("bounds", {}))
				return AABB(Vector3(float(low[0]), world_bounds.position.y, float(low[1])),
					Vector3(float(high[0]) - float(low[0]), world_bounds.size.y,
						float(high[1]) - float(low[1])))
	for key: String in ["mapBounds", "playableBounds"]:
		var bounds := _bounds(asset.get(key, {}))
		if bounds.size.x > 0.0 and bounds.size.z > 0.0:
			return bounds
	var bounds := _bounds(asset.get("bounds", {}))
	# Some older packages declare the server's addressable X/Z rectangle
	# instead of playableBounds (notably Sunmane).
	var transform: Dictionary = manifest.data.get("coordinateTransform", {})
	var addressable: Dictionary = transform.get("addressableWorldBounds", {})
	var low: Array = addressable.get("min", [])
	var high: Array = addressable.get("max", [])
	if low.size() == 2 and high.size() == 2:
		return AABB(Vector3(float(low[0]), bounds.position.y, float(low[1])),
			Vector3(float(high[0]) - float(low[0]), bounds.size.y,
				float(high[1]) - float(low[1])))
	return bounds

static func configure(camera: Camera3D, viewport: SubViewport, bounds: AABB, buffer := 0.0) -> void:
	if bounds.size.x <= 0.0 or bounds.size.z <= 0.0:
		return
	if buffer > 0.0:
		bounds = AABB(bounds.position - Vector3(buffer, 0.0, buffer), bounds.size + Vector3(2.0 * buffer, 0.0, 2.0 * buffer))
	# A rectangular interior should fill a rectangular image, without stretching
	# its terrain or wasting half of a square texture on inaccessible space.
	var aspect := bounds.size.x / bounds.size.z
	viewport.size = (Vector2i(RESOLUTION, maxi(1, roundi(RESOLUTION / aspect)))
		if aspect >= 1.0 else Vector2i(maxi(1, roundi(RESOLUTION * aspect)), RESOLUTION))
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.global_position = Vector3(bounds.get_center().x,
		maxf(bounds.end.y + 100.0, 300.0), bounds.get_center().z)
	camera.rotation_degrees = Vector3(-90.0, 0.0, 0.0)
	# Account for texture rounding so neither edge gets clipped.
	camera.size = maxf(bounds.size.z,
		bounds.size.x * float(viewport.size.y) / float(viewport.size.x)) * MARGIN
	camera.far = maxf(2500.0, camera.global_position.y - bounds.position.y + 100.0)

static func _bounds(value: Variant) -> AABB:
	if not value is Dictionary:
		return AABB()
	var low: Array = value.get("min", [])
	var high: Array = value.get("max", [])
	if low.size() != 3 or high.size() != 3:
		return AABB()
	var minimum := Vector3(float(low[0]), float(low[1]), float(low[2]))
	var maximum := Vector3(float(high[0]), float(high[1]), float(high[2]))
	return AABB(minimum, maximum - minimum)
