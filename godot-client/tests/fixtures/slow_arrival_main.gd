extends "res://src/app/main.gd"
## Simulate one expensive atomic build without loading model resources.
var built_ids: Array = []
var deferred_ids: Array = []
var model_ready := true
var delay_usec := 5000
var resource_checks := 0

func _spawn_actor(id: Variant, build := true, _previous: ReplicatedActor3D = null) -> bool:
	if build:
		built_ids.append(id)
		OS.delay_usec(delay_usec)
	else:
		deferred_ids.append(id)
	return true

func _record_distance(_dto: Dictionary, _reference: Vector3) -> float:
	return 1.0

func _remote_model_ready(_id: int) -> bool:
	resource_checks += 1
	return model_ready

func _crowd_reference_point() -> Vector3:
	return Vector3.ZERO
