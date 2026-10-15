extends "res://tests/integration/rendered_cape_over_armour.gd"
## Runs the rendered armour-clearance fixture with the reviewed pre-cache cloth
## solver. The actor, equipment, settling, measurement, and captures remain the
## same as the production fixture; only the modifier is replaced, synchronously,
## before the first frame can process it.

const BASELINE := "res://tests/fixtures/cape_cloth_baseline.gd"
const BASELINE_BODY_SHA256 := "b253940492529c94ee1d116607dc054994479f33538748f788d3b4005e1ba84c"

var _baseline_checked := false


func _spawn(visuals: Dictionary) -> ReplicatedActor3D:
	if not _baseline_checked:
		_check_baseline_provenance()
		_baseline_checked = true
	var actor := super._spawn(visuals)
	var skeleton := super._skeleton_of(actor)
	if skeleton == null:
		_failures += 1
		return actor
	var original: SkeletonModifier3D = skeleton.get_node_or_null("CapeCloth")
	if original == null:
		_failures += 1
		return actor
	var untouched := not bool(original.get("_cached")) \
		and not bool(original.get("_settled")) \
		and (original.get("_bones") as Array).is_empty() \
		and (original.get("_points") as Array).is_empty() \
		and (original.get("_previous") as Array).is_empty() \
		and (original.get("_lengths") as Array).is_empty()
	if not untouched:
		_failures += 1
		push_error("Production cloth advanced before baseline injection; aborting reproduction.")
		quit(2)
		return actor
	var was_active := original.active
	var old_influence := original.influence
	var old_process_mode := original.process_mode
	var old_index := original.get_index()
	var torso: PackedFloat32Array = original.get("_torso_reach")
	var lumbar: PackedFloat32Array = original.get("_lumbar_reach")

	original.active = false
	skeleton.remove_child(original)
	original.free()
	var replacement: SkeletonModifier3D = (load(BASELINE) as Script).new()
	replacement.name = "CapeCloth"
	replacement.influence = old_influence
	replacement.process_mode = old_process_mode
	skeleton.add_child(replacement)
	skeleton.move_child(replacement, old_index)
	replacement.call("set_torso_reach", torso, lumbar)
	replacement.active = was_active
	actor.set("_cape_cloth", replacement)
	return actor


func _check_baseline_provenance() -> void:
	var source := FileAccess.get_file_as_string(BASELINE)
	var body_at := source.find("extends SkeletonModifier3D")
	if body_at < 0:
		_failures += 1
		push_error("Frozen baseline does not contain the original script body.")
		return
	var normalized := source.substr(body_at).replace("\r\n", "\n")
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(normalized.to_utf8_buffer())
	var digest := context.finish().hex_encode()
	if digest != BASELINE_BODY_SHA256:
		_failures += 1
		push_error("Frozen baseline source does not match reviewed SHA-256.")
