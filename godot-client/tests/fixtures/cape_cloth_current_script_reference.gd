extends "res://src/actors/cape_cloth.gd"
## The current production solver with only optional native execution disabled.
## Inheriting the live implementation keeps damping, measured fabric and
## post-solve leg clearance identical to the native wrapper under test.

func _initialize_native_constraint_kernel() -> void:
	_native_constraint_kernel_initialized = true
	_native_constraint_kernel = null
	_native_constraint_status = "current_script_reference"
