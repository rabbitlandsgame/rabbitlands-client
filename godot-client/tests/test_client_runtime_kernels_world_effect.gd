extends "res://tests/test_world_effect_native_presentation.gd"
## RB-C1n: test_world_effect_native_presentation.gd, unchanged, against NativeWorldEffectGeometry compiled into
## the verified client_runtime payload instead of the benchmark extension.
## Flags as in test_client_runtime_crowd_kernels.gd: `--runtime-dir=<payload>`,
## `--expect-native=present` (otherwise a missing payload is a SKIP).

const RuntimeKernels := preload("res://tests/test_client_runtime_crowd_kernels.gd")
var _runtime_payload := {}

## Before the autoloads' _ready, so AppState sees the classes as it would after
## an early load.
func _initialize() -> void:
	_runtime_payload = RuntimeKernels.load_payload()

func _run() -> void:
	if not RuntimeKernels.skip_suite(self, _runtime_payload, "test_world_effect_native_presentation.gd"):
		await super._run()
