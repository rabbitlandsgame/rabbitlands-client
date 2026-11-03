extends SceneTree
## Memory budgets per machine class (src/runtime/memory_budgets.gd): the class
## matrix, that every small machine is also hardware tier low, the override
## precedence (argument over environment over probe; tests), the session
## cache, and the approved budget table, whose medium and large rows keep
## today's constants. Restores RABBITLANDS_MEMORY_CLASS at the end.

const MemoryBudgets := preload("res://src/runtime/memory_budgets.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const GIB := 1 << 30
const MIB := 1 << 20

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	var saved_class := OS.get_environment(HardwareTier.MEMORY_CLASS_VARIABLE)
	OS.unset_environment(HardwareTier.MEMORY_CLASS_VARIABLE)
	MemoryBudgets.reset()
	_check_matrix()
	_check_small_implies_low()
	_check_overrides()
	await _check_session()
	_check_table()
	_check_today()
	MemoryBudgets.reset()
	if saved_class.is_empty():
		OS.unset_environment(HardwareTier.MEMORY_CLASS_VARIABLE)
	else:
		OS.set_environment(HardwareTier.MEMORY_CLASS_VARIABLE, saved_class)
	print("memory budgets tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _machine(type: int, adapter: String, driver: String, memory_gib: float, threads: int,
		vendor := "") -> Dictionary:
	return {"adapter_type": type, "adapter_name": adapter, "adapter_vendor": vendor,
		"rendering_driver": driver, "physical_memory": int(memory_gib * GIB) if memory_gib > 0 else -1,
		"cpu_threads": threads}

func _class(inputs: Dictionary) -> String:
	return str(MemoryBudgets.classify(inputs)["class"])

func _check_matrix() -> void:
	var integrated := RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU
	var discrete := RenderingDevice.DEVICE_TYPE_DISCRETE_GPU
	var other := RenderingDevice.DEVICE_TYPE_OTHER
	var uhd := MemoryBudgets.classify(_machine(integrated, "Intel(R) UHD Graphics 620", "vulkan", 7.8, 8, "Intel"))
	expect(uhd["class"] == "small" and uhd.basis == ["integrated_gpu", "memory"]
		and uhd.adapter_class == "integrated" and is_equal_approx(float(uhd.memory_gib), 7.8),
		"8 GB iGPU is small, for its iGPU and its memory: %s" % uhd)
	expect(JSON.stringify(uhd) == "{\"adapter_class\":\"integrated\",\"basis\":[\"integrated_gpu\",\"memory\"],\"class\":\"small\",\"memory_gib\":7.8}",
		"classify returns exactly class, basis, adapter_class and memory_gib: %s" % JSON.stringify(uhd))
	var gtx := MemoryBudgets.classify(_machine(discrete, "NVIDIA GeForce GTX 1050 Ti", "vulkan", 7.9, 8))
	expect(gtx["class"] == "small" and gtx.basis == ["memory"], "8 GB dGPU is small, for its memory: %s" % gtx)
	expect(_class(_machine(discrete, "Quadro K620", "vulkan", 7.9, 4)) == "small",
		"the K620 machine (2 GB card, 8 GB RAM) is small through its memory")
	var rtx := MemoryBudgets.classify(_machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 15.8, 12))
	expect(rtx["class"] == "medium" and rtx.basis == ["memory"], "16 GB dGPU is medium: %s" % rtx)
	var four := _machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 31.7, 4)
	var four_class := MemoryBudgets.classify(four)
	expect(four_class["class"] == "large" and four_class.basis.is_empty()
		and HardwareTier.classify(four).tier == "low",
		"32 GB with 4 threads is memory large (and still tier low): %s" % four_class)
	expect(_class(_machine(integrated, "Apple M1", "metal", 8.0, 8)) == "small"
		and _class(_machine(integrated, "Apple M2 Pro", "metal", 16.0, 10)) == "medium"
		and _class(_machine(integrated, "Apple M3 Max", "metal", 36.0, 14)) == "large",
		"Apple silicon 8/16/36 GB is small/medium/large: judged by memory only")
	var unknown := MemoryBudgets.classify(_machine(discrete, "NVIDIA GeForce RTX 3060", "vulkan", 0, 12))
	expect(unknown["class"] == "medium" and unknown.basis == ["memory_unknown"]
		and float(unknown.memory_gib) == -1.0, "unknown memory is medium: %s" % unknown)
	expect(_class(_machine(integrated, "Intel(R) Iris(R) Xe Graphics", "vulkan", 0, 8)) == "small",
		"unknown memory with an iGPU is still small")
	expect(_class(_machine(discrete, "Intel(R) Graphics", "d3d12", 31.7, 24, "Intel")) == "small",
		"an Intel iGPU that D3D12 reports as discrete is small by its name")
	expect(_class(_machine(other, "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
		"opengl3_angle", 15.9, 12, "Google Inc. (Intel)")) == "small",
		"Compatibility's untyped Intel adapter is small by its name")
	expect(_class(_machine(integrated, "Intel(R) Iris(R) Xe Graphics", "vulkan", 31.7, 16)) == "small",
		"an iGPU is small however much memory the machine has")
	expect(_class(_machine(RenderingDevice.DEVICE_TYPE_CPU, "llvmpipe (LLVM 15.0.7, 256 bits)", "vulkan", 64.0, 32)) == "small"
		and _class(_machine(RenderingDevice.DEVICE_TYPE_VIRTUAL_GPU, "Virtio-GPU Venus", "vulkan", 31.7, 16)) == "small",
		"software and virtual GPUs are small")
	expect(_class(_machine(discrete, "Intel(R) Arc(TM) A770 Graphics", "d3d12", 31.7, 16)) == "large",
		"a discrete Arc card with 32 GB is large")
	var low_edge := {"adapter_type": discrete, "adapter_name": "NVIDIA GeForce RTX 3060",
		"rendering_driver": "vulkan", "cpu_threads": 12}
	low_edge["physical_memory"] = HardwareTier.LOW_MEMORY_BYTES
	expect(_class(low_edge) == "small", "exactly LOW_MEMORY_BYTES (8.5 GiB) is small")
	low_edge["physical_memory"] = HardwareTier.LOW_MEMORY_BYTES + 1
	expect(_class(low_edge) == "medium", "one byte over 8.5 GiB is medium")
	low_edge["physical_memory"] = HardwareTier.MEDIUM_MEMORY_BYTES
	expect(_class(low_edge) == "medium", "exactly MEDIUM_MEMORY_BYTES (16.5 GiB) is medium")
	low_edge["physical_memory"] = HardwareTier.MEDIUM_MEMORY_BYTES + 1
	expect(_class(low_edge) == "large", "one byte over 16.5 GiB is large")

## Every small machine is tier low; threads never change the memory class.
func _check_small_implies_low() -> void:
	var adapters := [
		[RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Intel(R) UHD Graphics 620", "vulkan"],
		[RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "AMD Radeon(TM) Graphics", "vulkan"],
		[RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Apple M1", "metal"],
		[RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "Intel(R) Graphics", "d3d12"],
		[RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "NVIDIA GeForce GTX 1050 Ti", "vulkan"],
		[RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "Quadro K620", "d3d12"],
		[RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "Intel(R) Arc(TM) A770 Graphics", "d3d12"],
		[RenderingDevice.DEVICE_TYPE_OTHER, "AMD Radeon RX 6600", "opengl3"],
		[RenderingDevice.DEVICE_TYPE_OTHER, "Intel(R) UHD Graphics 630", "opengl3"],
		[RenderingDevice.DEVICE_TYPE_OTHER, "", ""],
		[RenderingDevice.DEVICE_TYPE_CPU, "llvmpipe (LLVM 15.0.7, 256 bits)", "vulkan"],
		[RenderingDevice.DEVICE_TYPE_VIRTUAL_GPU, "Virtio-GPU Venus", "vulkan"],
	]
	var memories := [-1, 2 * GIB, 7.8 * GIB, HardwareTier.LOW_MEMORY_BYTES, HardwareTier.LOW_MEMORY_BYTES + 1,
		12 * GIB, 15.8 * GIB, HardwareTier.MEDIUM_MEMORY_BYTES, HardwareTier.MEDIUM_MEMORY_BYTES + 1,
		31.7 * GIB, 128 * GIB]
	var threads := [0, 2, 4, 6, 8, 12, 24, 64]
	var checked := 0
	var small := 0
	var violations := PackedStringArray()
	var thread_dependent := PackedStringArray()
	for adapter: Array in adapters:
		for memory: Variant in memories:
			var first := ""
			for count: int in threads:
				var inputs := {"adapter_type": adapter[0], "adapter_name": adapter[1],
					"rendering_driver": adapter[2], "physical_memory": int(memory), "cpu_threads": count}
				var memory_class := _class(inputs)
				checked += 1
				if memory_class == "small":
					small += 1
					if HardwareTier.classify(inputs).tier != "low":
						violations.append("%s" % inputs)
				if first.is_empty():
					first = memory_class
				elif memory_class != first:
					thread_dependent.append("%s" % inputs)
	expect(violations.is_empty(), "small implies tier low over %d machines (%d small): %s" % [
		checked, small, violations])
	expect(small > 0 and small < checked, "the grid has small and non-small machines")
	expect(thread_dependent.is_empty(), "CPU threads never change the memory class: %s" % thread_dependent)

func _check_overrides() -> void:
	var desktop := _machine(RenderingDevice.DEVICE_TYPE_DISCRETE_GPU, "NVIDIA GeForce RTX 5080 Laptop GPU",
		"vulkan", 31.6, 24)
	var none := MemoryBudgets.resolve(desktop, HardwareTier.resolve_memory_class("", PackedStringArray()))
	expect(none["class"] == "large" and none.source == "probe" and none.probed_class == "large"
		and not none.has("rejected"), "no override: the probe decides: %s" % none)
	var cases := [
		["small", [], "small", "environment", []],
		[" SMALL ", [], "small", "environment", []],
		["small", ["--memory-class=medium"], "medium", "argument", []],
		["", ["--memory-class=small", "--memory-class=medium"], "medium", "argument", []],
		["tiny", [], "large", "probe", ["tiny"]],
		["small", ["--memory-class=huge"], "small", "environment", ["huge"]],
		["tiny", ["--memory-class=huge"], "large", "probe", ["tiny", "huge"]],
		["", ["--memory-classes=small", "--other"], "large", "probe", []],
	]
	for case: Array in cases:
		var override := HardwareTier.resolve_memory_class(case[0], PackedStringArray(case[1]))
		var resolved := MemoryBudgets.resolve(desktop, override)
		var rejected: Array = resolved.get("rejected", [])
		expect(resolved["class"] == case[2] and resolved.source == case[3]
			and resolved.probed_class == "large" and rejected == case[4],
			"override env=%s args=%s -> %s from %s: %s" % [case[0], case[1], case[2], case[3], resolved])
	var small_machine := _machine(RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU, "Intel(R) UHD Graphics 620",
		"vulkan", 7.8, 8)
	var raised := MemoryBudgets.resolve(small_machine, HardwareTier.resolve_memory_class("large", PackedStringArray()))
	expect(raised["class"] == "large" and raised.probed_class == "small" and raised.basis == ["integrated_gpu", "memory"],
		"a forced class keeps the probe's reasons beside it: %s" % raised)

func _check_session() -> void:
	MemoryBudgets.reset()
	var probed := MemoryBudgets.current()
	expect(probed.source == "probe" and probed["class"] in MemoryBudgets.CLASSES
		and probed["class"] == probed.probed_class and not probed.has("provisional"),
		"with no override this machine's class comes from the probe: %s" % probed)
	var expected := str(MemoryBudgets.resolve(HardwareTier.probe(), HardwareTier.memory_class_override())["class"])
	expect(MemoryBudgets.memory_class() == expected, "current() is resolve(probe, override)")
	var copy := MemoryBudgets.current()
	copy["class"] = "changed"
	(copy.basis as Array).append("changed")
	expect(MemoryBudgets.memory_class() == probed["class"] and MemoryBudgets.current().basis == probed.basis,
		"current() hands out a copy")
	OS.set_environment(HardwareTier.MEMORY_CLASS_VARIABLE, "small")
	expect(MemoryBudgets.memory_class() == probed["class"], "the answer is cached for the session")
	MemoryBudgets.reset()
	var forced := MemoryBudgets.current()
	expect(forced["class"] == "small" and forced.source == "environment" and MemoryBudgets.is_small(),
		"after reset() RABBITLANDS_MEMORY_CLASS=small is read: %s" % forced)
	expect(int(MemoryBudgets.value(MemoryBudgets.WORLD_PARK_BYTES)) == 384 * MIB
		and MemoryBudgets.value(&"world_park_preload") == false
		and int(MemoryBudgets.value(&"crowd_park_limit")) == 16,
		"value() reads the small row, by String or StringName key")
	OS.unset_environment(HardwareTier.MEMORY_CLASS_VARIABLE)
	expect(MemoryBudgets.override_for_tests("medium"), "override_for_tests takes a class")
	var test_class := MemoryBudgets.current()
	expect(test_class["class"] == "medium" and test_class.source == "test"
		and int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_BYTES)) == 512 * MIB,
		"override_for_tests sets the session's class: %s" % test_class)
	expect(MemoryBudgets.override_for_tests("large") and MemoryBudgets.memory_class() == "large"
		and int(MemoryBudgets.value(MemoryBudgets.RL_HEAD_BYTES)) == 384 * MIB,
		"a later override_for_tests replaces the earlier one")
	MemoryBudgets.reset()
	expect(MemoryBudgets.current().source == "probe" and MemoryBudgets.memory_class() == probed["class"],
		"reset() returns to the probed class")
	expect(MemoryBudgets.budgets("small") == MemoryBudgets.BUDGETS["small"]
		and MemoryBudgets.budgets() == MemoryBudgets.BUDGETS[MemoryBudgets.memory_class()],
		"budgets() returns a class's row, this session's by default")
	var row := MemoryBudgets.budgets("small")
	row[MemoryBudgets.CROWD_PARK_LIMIT] = 1
	expect(int(MemoryBudgets.value_for("small", MemoryBudgets.CROWD_PARK_LIMIT)) == 16, "budgets() hands out a copy")
	expect(MemoryBudgets.value_for("unknown", MemoryBudgets.WORLD_PARK_BYTES) == MemoryBudgets.value_for(
		"medium", MemoryBudgets.WORLD_PARK_BYTES), "an unknown class reads medium's row")
	# Once asked on the main thread, workers read the cached answer.
	MemoryBudgets.override_for_tests("small")
	var answers := []
	var guard := Mutex.new()
	var task := WorkerThreadPool.add_group_task(func(_index: int) -> void:
		var budget := int(MemoryBudgets.value(MemoryBudgets.CREATURE_SCENE_BYTES))
		var name := MemoryBudgets.memory_class()
		if budget != 256 * MIB or name != "small":
			guard.lock()
			answers.append("%s %d" % [name, budget])
			guard.unlock(), 64)
	WorkerThreadPool.wait_for_group_task_completion(task)
	expect(answers.is_empty(), "64 worker reads get the session's answer: %s" % [answers])
	# A worker that asks first must not wait for the RenderingServer (the
	# adapter name is answered through the main thread), or a main thread
	# blocked on that worker would hang. The main thread stays busy (no frame,
	# no flush) while the worker runs.
	MemoryBudgets.reset()
	var first := []
	var probe_task := WorkerThreadPool.add_task(func() -> void:
		first.append(MemoryBudgets.current()))
	var deadline := Time.get_ticks_msec() + 3000
	while not WorkerThreadPool.is_task_completed(probe_task) and Time.get_ticks_msec() < deadline:
		OS.delay_msec(2)
	var returned := WorkerThreadPool.is_task_completed(probe_task)
	while not WorkerThreadPool.is_task_completed(probe_task):
		await process_frame
	WorkerThreadPool.wait_for_task_completion(probe_task)
	var provisional: Dictionary = first[0] if not first.is_empty() else {}
	# Headless reports no adapter name, so here the provisional class is the
	# full probe's.
	expect(returned and provisional.get("class") == probed["class"] and provisional.get("provisional") == true,
		"a worker that asks first gets a provisional class without waiting for the main thread: %s" % [provisional])
	var settled := MemoryBudgets.current()
	expect(settled.source == "probe" and not settled.has("provisional"),
		"the provisional answer is not cached: the main thread's first question probes in full: %s" % settled)
	MemoryBudgets.reset()

func _check_table() -> void:
	expect(MemoryBudgets.CLASSES == HardwareTier.MEMORY_CLASSES,
		"the classes are the names the override accepts, in the same order")
	var golden := {
		"small": {"world_park_bytes": 384 * MIB, "world_park_preload": false,
			"creature_scene_bytes": 256 * MIB, "creature_scene_idle_msec": 20000,
			"rl_head_bytes": 64 * MIB, "rl_bake_bytes": 64 * MIB, "rl_bake_idle_bytes": 16 * MIB,
			"crowd_park_limit": 16},
		"medium": {"world_park_bytes": 1792 * MIB, "world_park_preload": true,
			"creature_scene_bytes": 512 * MIB, "creature_scene_idle_msec": 60000,
			"rl_head_bytes": 192 * MIB, "rl_bake_bytes": 192 * MIB, "rl_bake_idle_bytes": 48 * MIB,
			"crowd_park_limit": 48},
		"large": {"world_park_bytes": 1792 * MIB, "world_park_preload": true,
			"creature_scene_bytes": 1024 * MIB, "creature_scene_idle_msec": 120000,
			"rl_head_bytes": 384 * MIB, "rl_bake_bytes": 192 * MIB, "rl_bake_idle_bytes": 48 * MIB,
			"crowd_park_limit": 48},
	}
	expect(var_to_str(MemoryBudgets.BUDGETS) == var_to_str(golden),
		"the budget table is the approved one (values, types and key order):\n%s" % var_to_str(MemoryBudgets.BUDGETS))
	var keys := [MemoryBudgets.WORLD_PARK_BYTES, MemoryBudgets.WORLD_PARK_PRELOAD,
		MemoryBudgets.CREATURE_SCENE_BYTES, MemoryBudgets.CREATURE_SCENE_IDLE_MSEC,
		MemoryBudgets.RL_HEAD_BYTES, MemoryBudgets.RL_BAKE_BYTES, MemoryBudgets.RL_BAKE_IDLE_BYTES,
		MemoryBudgets.CROWD_PARK_LIMIT]
	for memory_class: String in MemoryBudgets.CLASSES:
		expect((MemoryBudgets.BUDGETS[memory_class] as Dictionary).keys() == keys,
			"every key constant names a budget in the %s row" % memory_class)
	for key: String in keys:
		if key == MemoryBudgets.WORLD_PARK_PRELOAD:
			continue
		var small := int(MemoryBudgets.value_for("small", key))
		var medium := int(MemoryBudgets.value_for("medium", key))
		var large := int(MemoryBudgets.value_for("large", key))
		expect(small > 0 and small <= medium and medium <= large, "%s grows with the class" % key)
	expect(int(MemoryBudgets.value_for("small", MemoryBudgets.RL_BAKE_IDLE_BYTES))
		<= int(MemoryBudgets.value_for("small", MemoryBudgets.RL_BAKE_BYTES)),
		"the idle bake budget is part of the bake budget")

## Medium and large keep today's values (the approval reduces small only).
## Read from the consumers' source text, so this test neither loads those
## scripts nor breaks once a later chunk replaces a constant with value():
## a constant that is gone is skipped.
func _check_today() -> void:
	var today := [
		["res://src/world/world_park_policy.gd", "BUDGET_BYTES", MemoryBudgets.WORLD_PARK_BYTES],
		["res://src/actors/rl_head/rl_head_identity_bake.gd", "BUDGET_BYTES", MemoryBudgets.RL_BAKE_BYTES],
		["res://src/actors/rl_head/rl_head_identity_bake.gd", "IDLE_BYTES", MemoryBudgets.RL_BAKE_IDLE_BYTES],
		["res://src/world/crowd_presentation.gd", "PARK_LIMIT", MemoryBudgets.CROWD_PARK_LIMIT],
	]
	for entry: Array in today:
		var constant: Variant = _source_constant(entry[0], entry[1])
		if constant == null:
			print("SKIP: %s %s is no longer a constant" % [entry[0].get_file(), entry[1]])
			continue
		expect(int(MemoryBudgets.value_for("medium", entry[2])) == int(constant)
			and int(MemoryBudgets.value_for("large", entry[2])) == int(constant)
			and int(MemoryBudgets.value_for("small", entry[2])) <= int(constant),
			"%s: medium and large keep today's %s.%s = %d" % [entry[2], entry[0].get_file(), entry[1], int(constant)])

func _source_constant(path: String, name: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	var pattern := RegEx.new()
	pattern.compile("(?m)^const %s\\s*:?=\\s*([0-9*\\s]+)$" % name)
	var found := pattern.search(FileAccess.get_file_as_string(path))
	if found == null:
		return null
	var expression := Expression.new()
	if expression.parse(found.get_string(1).strip_edges()) != OK:
		return null
	return expression.execute()
