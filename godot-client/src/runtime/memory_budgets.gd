extends RefCounted
## Memory budgets per machine class (perf work 2026-11, owner decision 10).
##
## An 8 GB or integrated-GPU machine gets smaller caches than a desktop: the
## budget table below is the one place their sizes live, and callers ask
## `value(key)` for this machine's figure instead of keeping a constant.
##
## The class is computed on every launch, unlike the first-run graphics tier
## (hardware_tier.gd), which is seeded once into a fresh profile: budgets must
## also hold for profiles from before the tier existed and for players who
## raised their quality by hand. It reads the same probe and the same limits:
##
##   small   an integrated, software or virtual GPU (HardwareTier.adapter_class:
##           Apple silicon counts by memory only, a D3D12 Intel iGPU by its
##           name), or physical memory of LOW_MEMORY_BYTES (8.5 GiB) or less;
##   medium  otherwise, MEDIUM_MEMORY_BYTES (16.5 GiB) or less, or physical
##           memory unknown;
##   large   everything else.
##
## CPU threads do not decide memory, so a 4-thread desktop with 16 GB and a
## discrete GPU is tier low but memory medium; every small machine is tier low
## (tests/test_memory_budgets.gd checks that over a grid of machines).
## Dedicated video memory is not readable from GDScript: a 2 GB card is small
## only through its machine's memory. The browser build keeps its own caps
## (main.gd: WorldPark at most 512 MiB) on top of these.
##
## RABBITLANDS_MEMORY_CLASS=small|medium|large or the user argument
## `--memory-class=` forces a class for tests and measurement (the argument
## wins; parsed by HardwareTier.memory_class_override, which also keeps such a
## launch from seeding a first-run tier). `current()` records where the class
## came from: probe, environment, argument, or test.
##
## The script declares no `class_name` (callers preload it), like
## hardware_tier.gd: an autoload or a worker may need it before the global
## class cache is current. Ask `current()` (or anything that calls it) first
## on the main thread, at startup: the probe asks the RenderingServer for the
## adapter's name, which a worker can only get through the main thread (a
## worker asking while the main thread waits for it never returns; measured).
## The main thread's answer is cached for the session and only read, from any
## thread. A worker that asks before the main thread has gets a provisional
## answer (see `_provisional`), which is not cached.

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

const MIB := 1 << 20

const SMALL := "small"
const MEDIUM := "medium"
const LARGE := "large"
## In HardwareTier.MEMORY_CLASSES order (the override accepts these names).
const CLASSES: Array[String] = [SMALL, MEDIUM, LARGE]
## Adapter classes that make a machine small whatever its memory.
const SMALL_ADAPTERS: Array[String] = ["integrated", "software", "virtual"]

## Budget keys. `value()` also accepts them as StringName (&"rl_head_bytes").
## Parked and preloaded worlds together (WorldPark).
const WORLD_PARK_BYTES := "world_park_bytes"
## Whether WorldPark preloads interiors on approach and before anticipated
## (scripted) travel.
const WORLD_PARK_PRELOAD := "world_park_preload"
## Creature entries of GlbSceneCache, the evictable domain.
const CREATURE_SCENE_BYTES := "creature_scene_bytes"
## How long a creature entry must have been idle before it may be evicted.
const CREATURE_SCENE_IDLE_MSEC := "creature_scene_idle_msec"
## RL head file cache: files in use and idle, sidecars included.
const RL_HEAD_BYTES := "rl_head_bytes"
## RL identity bake: baked mesh data in all, and the idle part of it.
const RL_BAKE_BYTES := "rl_bake_bytes"
const RL_BAKE_IDLE_BYTES := "rl_bake_idle_bytes"
## Bodies the crowd keeps parked for reuse after they leave view.
const CROWD_PARK_LIMIT := "crowd_park_limit"

## The approved table (memory-classes design, section 1). Medium and large
## keep today's WorldPark (world_park_policy.gd BUDGET_BYTES), bake
## (rl_head_identity_bake.gd BUDGET_BYTES, IDLE_BYTES) and park pool
## (crowd_presentation.gd PARK_LIMIT) values: the approval reduces them on
## small machines only. The RL head file cache has no budget yet (held until
## logout; all-or-nothing). The territory stream budget
## (256 MiB) is not a class budget. WorldPark (M2), the creature scene cache
## (M5) and the crowd park pool (M7a) read this table; the RL head file and
## identity bake rows have no reader until M4.
const BUDGETS := {
	SMALL: {
		WORLD_PARK_BYTES: 384 * MIB,
		WORLD_PARK_PRELOAD: false,
		CREATURE_SCENE_BYTES: 256 * MIB,
		CREATURE_SCENE_IDLE_MSEC: 20000,
		RL_HEAD_BYTES: 64 * MIB,
		RL_BAKE_BYTES: 64 * MIB,
		RL_BAKE_IDLE_BYTES: 16 * MIB,
		CROWD_PARK_LIMIT: 16,
	},
	MEDIUM: {
		WORLD_PARK_BYTES: 1792 * MIB,
		WORLD_PARK_PRELOAD: true,
		CREATURE_SCENE_BYTES: 512 * MIB,
		CREATURE_SCENE_IDLE_MSEC: 60000,
		RL_HEAD_BYTES: 192 * MIB,
		RL_BAKE_BYTES: 192 * MIB,
		RL_BAKE_IDLE_BYTES: 48 * MIB,
		CROWD_PARK_LIMIT: 48,
	},
	LARGE: {
		WORLD_PARK_BYTES: 1792 * MIB,
		WORLD_PARK_PRELOAD: true,
		CREATURE_SCENE_BYTES: 1024 * MIB,
		CREATURE_SCENE_IDLE_MSEC: 120000,
		RL_HEAD_BYTES: 384 * MIB,
		RL_BAKE_BYTES: 192 * MIB,
		RL_BAKE_IDLE_BYTES: 48 * MIB,
		CROWD_PARK_LIMIT: 48,
	},
}

## This session's answer (`current`), empty until first asked. Replaced whole,
## never changed in place, under `_lock`, so a reader holding the old one is
## safe.
static var _current: Dictionary = {}
static var _lock := Mutex.new()
## One warning per session for a worker that asked first (a benign race if
## two workers do at once: at worst two warnings).
static var _warned_provisional := false

## The memory class `inputs` (HardwareTier.probe) fall in, with what put them
## there: {"class", "basis", "adapter_class", "memory_gib"}. `basis` names the
## reasons ("integrated_gpu", "memory", "memory_unknown"); it is empty for
## large. Pure: no probe, no override.
static func classify(inputs: Dictionary) -> Dictionary:
	var adapter := HardwareTier.adapter_class(inputs)
	var memory := int(inputs.get("physical_memory", -1))
	var basis := PackedStringArray()
	if adapter in SMALL_ADAPTERS:
		basis.append(adapter + "_gpu")
	if memory > 0 and memory <= HardwareTier.LOW_MEMORY_BYTES:
		basis.append("memory")
	var found := SMALL
	if basis.is_empty():
		found = MEDIUM
		if memory <= 0:
			basis.append("memory_unknown")
		elif memory <= HardwareTier.MEDIUM_MEMORY_BYTES:
			basis.append("memory")
		else:
			found = LARGE
	return {"class": found, "basis": Array(basis), "adapter_class": adapter,
		"memory_gib": snappedf(memory / float(HardwareTier.GIB), 0.1) if memory > 0 else -1.0}

## `classify(inputs)` with a forced class applied: `override` is
## HardwareTier.memory_class_override()'s answer. Adds "source" (probe,
## environment or argument), "probed_class" (what the probe alone said) and,
## when the launch named a class that does not exist, "rejected". Pure.
static func resolve(inputs: Dictionary, override: Dictionary) -> Dictionary:
	var result := classify(inputs)
	result["probed_class"] = result["class"]
	result["source"] = "probe"
	var forced := str(override.get("memory_class", ""))
	if forced in CLASSES:
		result["class"] = forced
		result["source"] = str(override.get("source", "environment"))
	var rejected: Variant = override.get("rejected", PackedStringArray())
	if (rejected is PackedStringArray or rejected is Array) and not rejected.is_empty():
		result["rejected"] = Array(rejected)
	return result

## This session's class and why, computed once (probe plus any override) and
## then cached: {"class", "source", "probed_class", "basis", "adapter_class",
## "memory_gib"}, "rejected" when a forced class was not a class, and
## "provisional": true on a worker that asked before the main thread did. A
## copy: changing it changes nothing.
static func current() -> Dictionary:
	return _resolved().duplicate(true)

## This session's class: "small", "medium" or "large".
static func memory_class() -> String:
	return str(_resolved()["class"])

static func is_small() -> bool:
	return memory_class() == SMALL

## This session's figure for `key` (one of the key constants above), or null
## for a key the table does not have.
static func value(key: Variant) -> Variant:
	return value_for(memory_class(), key)

## `memory_class`'s figure for `key`; an unknown class reads medium's, an
## unknown key null (and an error, so a misspelt key is not silently zero).
static func value_for(memory_class_name: String, key: Variant) -> Variant:
	var row: Dictionary = BUDGETS.get(memory_class_name, BUDGETS[MEDIUM])
	var name := str(key)
	if not row.has(name):
		push_error("memory budgets: no budget named %s" % name)
		return null
	return row[name]

## The whole row for `memory_class` ("" for this session's), as a copy, for
## a diagnostics record.
static func budgets(memory_class_name := "") -> Dictionary:
	var name := memory_class_name if not memory_class_name.is_empty() else memory_class()
	return (BUDGETS.get(name, BUDGETS[MEDIUM]) as Dictionary).duplicate()

## Makes this session's class `memory_class_name` until `reset()`, for tests.
## False (and nothing changes) for a name that is not a class.
static func override_for_tests(memory_class_name: String) -> bool:
	if not memory_class_name in CLASSES:
		push_error("memory budgets: %s is not a memory class" % memory_class_name)
		return false
	var forced := {"class": memory_class_name, "source": "test", "probed_class": "",
		"basis": [], "adapter_class": "", "memory_gib": -1.0}
	_lock.lock()
	_current = forced
	_lock.unlock()
	return true

## Forgets the cached class: the next question probes again.
static func reset() -> void:
	_lock.lock()
	_current = {}
	_lock.unlock()

static func _resolved() -> Dictionary:
	_lock.lock()
	var answer := _current
	_lock.unlock()
	if not answer.is_empty():
		return answer
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return _provisional()
	# Main thread: probing here never waits for another thread, so holding
	# the lock cannot deadlock; a worker that arrives meanwhile waits for it.
	_lock.lock()
	if _current.is_empty():
		_current = resolve(HardwareTier.probe(), HardwareTier.memory_class_override())
	answer = _current
	_lock.unlock()
	return answer

## A worker's answer before the main thread has asked: HardwareTier.probe()
## without the adapter's name and vendor, the two inputs a worker cannot read
## without waiting for the main thread (measured in 4.7.2; the adapter type,
## driver, memory and threads return at once). A forced class still decides,
## and Vulkan's device type still classifies the GPU; only the name rules
## (an Intel iGPU under D3D12, Compatibility, Apple silicon) are missing. Not
## cached, so the main thread's first question still probes in full.
static func _provisional() -> Dictionary:
	if not _warned_provisional:
		_warned_provisional = true
		push_warning("memory budgets: asked first on a worker thread; ask on the main thread at startup")
	var memory := OS.get_memory_info()
	var inputs := {
		"adapter_type": int(RenderingServer.get_video_adapter_type()),
		"adapter_name": "",
		"adapter_vendor": "",
		"rendering_driver": RenderingServer.get_current_rendering_driver_name(),
		"physical_memory": int(memory.get("physical", -1)),
		"cpu_threads": OS.get_processor_count(),
	}
	var answer := resolve(inputs, HardwareTier.memory_class_override())
	answer["provisional"] = true
	return answer
