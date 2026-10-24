extends RefCounted
## No game/autoload dependency: the release runner copies this file and its
## entrypoint into a tiny disposable project before materializing game assets.
const POLICY := "actual-renderer-supported-format-subset-v1"

static func software_adapter_matches(platform: String, adapter_name: String, adapter_type: int) -> bool:
	var normalized := adapter_name.to_lower()
	return (platform == "windows" and adapter_type == RenderingDevice.DEVICE_TYPE_CPU \
		and ("warp" in normalized or "microsoft basic render driver" in normalized)) \
		or (platform == "linux" and "llvmpipe" in normalized)

static func detected_formats() -> int:
	var mask := 0
	var device := RenderingServer.get_rendering_device()
	if device != null:
		var usage := RenderingDevice.TEXTURE_USAGE_SAMPLING_BIT | RenderingDevice.TEXTURE_USAGE_CAN_UPDATE_BIT
		if device.texture_is_format_supported_for_usage(RenderingDevice.DATA_FORMAT_BC1_RGB_UNORM_BLOCK, usage) \
			and device.texture_is_format_supported_for_usage(RenderingDevice.DATA_FORMAT_BC1_RGB_SRGB_BLOCK, usage):
			mask |= 1
		if device.texture_is_format_supported_for_usage(RenderingDevice.DATA_FORMAT_BC5_UNORM_BLOCK, usage):
			mask |= 2
		if device.texture_is_format_supported_for_usage(RenderingDevice.DATA_FORMAT_BC7_UNORM_BLOCK, usage) \
			and device.texture_is_format_supported_for_usage(RenderingDevice.DATA_FORMAT_BC7_SRGB_BLOCK, usage):
			mask |= 4
		return mask
	if RenderingServer.has_os_feature("s3tc"):
		mask |= 1
	if RenderingServer.has_os_feature("rgtc"):
		mask |= 2
	if RenderingServer.has_os_feature("bptc"):
		mask |= 4
	return mask

static func buffer_roundtrip(filename: String = "release-cook-buffer-probe.res") -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return {"ok": false, "error": "main_thread_required"}
	if filename.is_empty() or filename != filename.get_file() or not filename.ends_with(".res"):
		return {"ok": false, "error": "scoped_probe_filename_required"}
	var path := "user://" + filename
	if FileAccess.file_exists(path):
		return {"ok": false, "error": "fresh_probe_path_required"}
	var batch := MultiMesh.new()
	batch.transform_format = MultiMesh.TRANSFORM_3D
	batch.mesh = BoxMesh.new()
	batch.instance_count = 1
	var expected := Transform3D(Basis.IDENTITY, Vector3(1.25, 2.5, 3.75))
	batch.set_instance_transform(0, expected)
	var count := batch.buffer.size()
	if count != 12 or not batch.get_instance_transform(0).is_equal_approx(expected):
		return {"ok": false, "error": "renderer_buffer_unreadable", "buffer_elements": count}
	var saved: int = ResourceSaver.save(batch, path)
	if saved != OK:
		return {"ok": false, "error": "native_save_failed", "code": saved}
	batch = null
	var restored := ResourceLoader.load(path, "MultiMesh", ResourceLoader.CACHE_MODE_IGNORE) as MultiMesh
	var valid := restored != null and restored.buffer.size() == 12 \
		and restored.get_instance_transform(0).is_equal_approx(expected)
	restored = null
	var removed := DirAccess.remove_absolute(ProjectSettings.globalize_path(path)) == OK
	return {"ok": valid and removed, "error": "" if valid and removed else ("native_reload_failed" if not valid else "probe_cleanup_failed"),
		"buffer_elements": count, "save_reload": valid, "removed": removed}

static func observe(platform: String, filename: String = "release-cook-buffer-probe.res") -> Dictionary:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return {"policy": POLICY, "requested_platform": platform, "resource_buffer_probe": false,
			"resource_buffer_detail": {"ok": false, "error": "main_thread_required"}}
	var name := RenderingServer.get_video_adapter_name()
	var type := int(RenderingServer.get_video_adapter_type())
	var device := RenderingServer.get_rendering_device()
	var buffer := buffer_roundtrip(filename)
	var actual_platform: String = {"Windows": "windows", "Linux": "linux"}.get(OS.get_name(), "unsupported")
	# Godot 4.7.2 exposes the selected RD name but not its C++ get_device_type
	# method to scripts. Keep that absence explicit; never invent a second
	# independent type observation by copying RenderingServer's value.
	var device_type_available := device != null and device.has_method("get_device_type")
	var device_type := int(device.call("get_device_type")) if device_type_available else -1
	return {"policy": POLICY, "platform": actual_platform,
		"requested_platform": platform, "rendering_method": RenderingServer.get_current_rendering_method(),
		"rendering_driver": RenderingServer.get_current_rendering_driver_name(), "display_driver": DisplayServer.get_name(),
		"adapter_name": name, "adapter_vendor": RenderingServer.get_video_adapter_vendor(),
		"adapter_type": type, "expected_cpu_type": int(RenderingDevice.DEVICE_TYPE_CPU),
		"rendering_device_present": device != null,
		"rendering_device_name": device.get_device_name() if device != null else "",
		"rendering_device_type_available": device_type_available, "rendering_device_type": device_type,
		"software_adapter": software_adapter_matches(actual_platform, name, type),
		"detected_format_mask": detected_formats(), "resource_buffer_probe": bool(buffer.ok),
		"resource_buffer_detail": buffer}

static func policy_errors(observation: Dictionary, platform: String, method: String, driver: String) -> Array[String]:
	var failures: Array[String] = []
	if observation.get("policy") != POLICY or observation.get("platform") != platform \
		or observation.get("requested_platform") != platform or platform not in ["windows", "linux"]:
		failures.append("actual native platform or observation policy differs")
	if observation.get("rendering_method") != method or observation.get("rendering_driver") != driver:
		failures.append("actual rendering method/driver differs")
	if (platform == "windows" and (method != "forward_plus" or driver != "d3d12")) \
		or (platform == "linux" and (method != "gl_compatibility" or driver != "opengl3")):
		failures.append("unsupported native software rendering method/driver")
	if str(observation.get("display_driver", "")).to_lower() in ["", "headless"]:
		failures.append("a real display driver is required")
	if typeof(observation.get("detected_format_mask")) != TYPE_INT or observation.get("detected_format_mask") != 7:
		failures.append("actual BC1/BC5/BC7 sampling/update support is required")
	if typeof(observation.get("resource_buffer_probe")) != TYPE_BOOL or observation.get("resource_buffer_probe") != true:
		failures.append("actual resource-buffer save/reload is required")
	var name: Variant = observation.get("adapter_name")
	var type: Variant = observation.get("adapter_type")
	if not name is String or str(name).strip_edges().is_empty() or typeof(type) != TYPE_INT:
		failures.append("actual adapter name/type is required")
	elif not software_adapter_matches(platform, str(name), int(type)):
		failures.append("actual adapter is not the qualified CPU software renderer")
	if typeof(observation.get("software_adapter")) != TYPE_BOOL or observation.get("software_adapter") != true:
		failures.append("actual software-adapter classification is required")
	if platform == "windows":
		if typeof(observation.get("expected_cpu_type")) != TYPE_INT or observation.get("expected_cpu_type") != 4:
			failures.append("pinned CPU enum value differs")
		if observation.get("rendering_device_present") != true \
			or observation.get("rendering_device_name") != name:
			failures.append("selected RenderingDevice name does not match the CPU adapter")
		if observation.get("rendering_device_type_available") == true \
			and (typeof(observation.get("rendering_device_type")) != TYPE_INT \
				or observation.get("rendering_device_type") != RenderingDevice.DEVICE_TYPE_CPU):
			failures.append("exposed RenderingDevice type does not confirm the CPU adapter")
	return failures
