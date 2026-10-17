extends RefCounted
## GLTFDocument bakes tracks at 30 Hz by default, even when the file is denser.
## Opted-in authored assets declare the cadence needed by their contact solve.
static func bake_fps(state: GLTFState) -> float:
	var asset: Variant = state.json.get("asset", {})
	if not asset is Dictionary: return 30.0
	var extras: Variant = asset.get("extras", {})
	if not extras is Dictionary: return 30.0
	var declared: Variant = extras.get("rabbitlands_animation_bake_fps", 30.0)
	if typeof(declared) not in [TYPE_INT, TYPE_FLOAT]: return 30.0
	var value := float(declared)
	return clampf(value, 30.0, 3072.0) if is_finite(value) else 30.0
