class_name LightMarkerBinder
extends RefCounted
## Turns a manifest's `lighting.markers` into real lights in the scene.
##
## Packages declare their warm landmark lights and brazier lights as named
## markers with a colour, an energy hint and a range hint rather than as glTF
## light extensions, so the package needs no loader change and no extension the
## client does not implement. This binder is the client side of that contract.
##
## Maps that declare no markers get nothing, so this is a no-op for every
## package authored before the convention existed.

const DEFAULT_ENERGY := 2.4
const DEFAULT_RANGE := 14.0

static func apply(manifest: WorldManifest, parent: Node3D,
		shadows: bool = false) -> int:
	if manifest == null or parent == null:
		return 0
	var lighting: Variant = manifest.data.get("lighting", {})
	if lighting is not Dictionary:
		return 0
	var markers: Variant = (lighting as Dictionary).get("markers", [])
	if markers is not Array:
		return 0
	var bound := 0
	for raw: Variant in markers as Array:
		if raw is not Dictionary:
			continue
		var marker: Dictionary = raw
		var position: Variant = marker.get("position")
		if position is not Array or (position as Array).size() < 3:
			continue
		var light := OmniLight3D.new()
		light.name = str(marker.get("id", "Light_%d" % bound))
		light.position = Vector3(float((position as Array)[0]),
			float((position as Array)[1]), float((position as Array)[2]))
		light.light_color = _colour(marker.get("color"))
		light.light_energy = float(marker.get("energyHint", DEFAULT_ENERGY))
		light.omni_range = float(marker.get("rangeHint", DEFAULT_RANGE))
		# Point lights that cast shadows are expensive and a marker light is a
		# fill, not a key light, so shadows stay off unless a caller asks.
		light.shadow_enabled = shadows
		parent.add_child(light)
		bound += 1
	return bound

static func _colour(value: Variant) -> Color:
	if value is Array and (value as Array).size() >= 3:
		var values: Array = value
		return Color(float(values[0]), float(values[1]), float(values[2]))
	if value is String:
		return Color(str(value))
	return Color(1.0, 0.85, 0.65)
