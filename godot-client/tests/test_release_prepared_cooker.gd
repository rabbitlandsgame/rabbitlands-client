extends SceneTree
## Run with the qualified windowed software renderer; never accepts dummy data.
const Cooker := preload("res://tools/cook_prepared_assets.gd")
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func _run() -> void:
	_check(Cooker._isolated_user_matches("windows", "C:/Owned/Godot/app_userdata/Eloria", "c:\\owned\\Godot\\app_userdata\\Eloria/"), "Windows native namespace compares case-insensitively")
	_check(Cooker._isolated_user_matches("linux", "/owned/godot/app_userdata/Eloria", "/owned/godot/app_userdata/Eloria/"), "Linux native lowercase godot namespace matches exactly")
	_check(not Cooker._isolated_user_matches("linux", "/owned/godot/app_userdata/Eloria", "/owned/Godot/app_userdata/Eloria"), "Linux never folds namespace case")
	_check(not Cooker._isolated_user_matches("linux", "/owned/godot/app_userdata/Eloria", "/player/godot/app_userdata/Eloria"), "player directory cannot satisfy the isolated namespace")
	_check(not Cooker._isolated_user_matches("windows", "", ""), "empty namespace is refused")
	_check(not Cooker._isolated_user_matches("macos", "/owned", "/owned"), "unqualified host is refused")
	_check(Cooker._software_adapter_matches("windows", "Microsoft Basic Render Driver", RenderingDevice.DEVICE_TYPE_CPU), "actual Windows WARP CPU identity is accepted")
	_check(not Cooker._software_adapter_matches("windows", "Microsoft Basic Render Driver", RenderingDevice.DEVICE_TYPE_DISCRETE_GPU), "WARP name without actual CPU type is refused")
	_check(not Cooker._software_adapter_matches("windows", "Hardware GPU", RenderingDevice.DEVICE_TYPE_CPU), "CPU enum without qualified adapter identity is refused")
	_check(Cooker._software_adapter_matches("linux", "llvmpipe (LLVM 20)", RenderingDevice.DEVICE_TYPE_OTHER), "Linux GL's actual OTHER adapter type remains honest")
	_check(not Cooker._software_adapter_matches("linux", "Hardware GPU", RenderingDevice.DEVICE_TYPE_CPU), "Linux hardware is not software by enum alone")
	_check(Cooker._resource_buffer_roundtrip(), "actual renderer preserves readable MultiMesh instance buffers and transforms")
	print("RELEASE_PREPARED_COOKER_CHECKS checks=", checks, " failures=", failures)
	quit(1 if failures else 0)
