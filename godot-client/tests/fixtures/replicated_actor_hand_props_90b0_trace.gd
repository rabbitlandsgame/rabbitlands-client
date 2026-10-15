extends "res://tests/fixtures/replicated_actor_hand_props_90b0_baseline.gd"
## Untimed lookup counter for the frozen accessor. Performance trials instantiate
## the plain baseline fixture instead, so this override cannot bias timings.

var trace_enabled := false
var equipment_model_lookups := 0


func reset_hand_prop_trace() -> void:
	equipment_model_lookups = 0


func hand_prop_trace() -> Dictionary:
	return {"equipmentModelLookups": equipment_model_lookups}


func _equipment_model_config(part: int, visual_id: int) -> Dictionary:
	if trace_enabled:
		equipment_model_lookups += 1
	return super._equipment_model_config(part, visual_id)
