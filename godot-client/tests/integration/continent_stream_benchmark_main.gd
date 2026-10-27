extends "res://tests/integration/crowd_benchmark_main.gd"
## Keep Main's real preview construction, with identical hidden resources in
## each isolated comparison process instead of a random race/equipment roll.
const PREVIEW_SEED := 424242

func _randomize_creation_appearance(_rng: RandomNumberGenerator = null) -> void:
	var fixed := RandomNumberGenerator.new()
	fixed.seed = PREVIEW_SEED
	super._randomize_creation_appearance(fixed)
