extends SceneTree
## LiveEffectBudget per graphics quality (Low actor tier, LAT-L2).
##
## High and Medium keep the limits they had before the tier; Low draws a
## quarter of each kind (12 spells, 12 missiles, 8 techniques, 6 numbers, 38
## ordinary visuals in all) where it drew half. What involves the player, their
## target or their selection is still drawn over any limit.

const BUDGET := preload("res://src/world/live_effect_budget.gd")
const POLICY := preload("res://src/actors/actor_render_quality.gd")

const LOW := 0
const MEDIUM := 1
const HIGH := 2
## The limits each quality gave before the Low actor tier (scale 0.5 / 0.75 /
## 1.0 of LIMITS), and the Low row the tier approves.
const BEFORE_TIER := {
	LOW: {&"spell": 24, &"missile": 24, &"technique": 16, &"number": 12},
	MEDIUM: {&"spell": 36, &"missile": 36, &"technique": 24, &"number": 18},
	HIGH: {&"spell": 48, &"missile": 48, &"technique": 32, &"number": 24},
}
const LOW_TIER := {&"spell": 12, &"missile": 12, &"technique": 8, &"number": 6}

var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error(message)


func run() -> void:
	_check_limits()
	_check_low_admission()
	_check_tracking()
	print("live effect budget: %d checks, %s" % [checks,
		"PASS" if failures == 0 else "%d FAILURES" % failures])
	quit(failures)


func _limits(quality: int) -> Dictionary:
	var budget: RefCounted = BUDGET.new()
	budget.set("quality", quality)
	var limits := {}
	for kind: StringName in BUDGET.LIMITS:
		limits[kind] = int(budget.call("limit", kind))
	return limits


func _check_limits() -> void:
	var fresh: RefCounted = BUDGET.new()
	check(int(fresh.get("quality")) == HIGH and _limits(HIGH) == BEFORE_TIER[HIGH]
		and int(fresh.call("limit", &"spell")) == 48,
		"a new budget starts at High with the full limits")
	check(_limits(HIGH) == BEFORE_TIER[HIGH], "High keeps 48/48/32/24: %s" % _limits(HIGH))
	check(_limits(MEDIUM) == BEFORE_TIER[MEDIUM], "Medium keeps 36/36/24/18: %s" % _limits(MEDIUM))
	check(_limits(LOW) == LOW_TIER, "Low draws 12/12/8/6: %s" % _limits(LOW))
	var ordinary := 0
	for kind: StringName in LOW_TIER:
		ordinary += int(_limits(LOW)[kind])
	check(ordinary == 38, "Low admits at most 38 ordinary visuals at once (%d)" % ordinary)
	for level: int in [LOW, MEDIUM, HIGH]:
		var expected := {}
		for kind: StringName in BUDGET.LIMITS:
			expected[kind] = maxi(1, int(int(BUDGET.LIMITS[kind]) * POLICY.effect_scale(level)))
		check(_limits(level) == expected,
			"quality %d reads ActorRenderQuality.effect_scale" % level)
	# The quality was clamped before the tier; it still is, so an unexpected
	# value cannot pick another row than it did.
	check(_limits(-1) == _limits(LOW) and _limits(7) == _limits(HIGH),
		"a quality outside the range clamps to Low or High as before")
	var low: RefCounted = BUDGET.new()
	low.set("quality", LOW)
	check(int(low.call("limit", &"unknown")) == int(float(1 << 30) * 0.25),
		"an unknown kind stays effectively unbounded")
	var described: Dictionary = low.call("describe")
	check(described.get("limits", {}) == LOW_TIER and bool(described.get("enabled", false)),
		"describe() reports the Low limits the crowd census reads")


func _check_low_admission() -> void:
	var budget: RefCounted = BUDGET.new()
	budget.set("quality", LOW)
	var parent := Node.new()
	root.add_child(parent)
	for kind: StringName in LOW_TIER:
		var admitted := 0
		for index: int in int(LOW_TIER[kind]) + 5:
			if bool(budget.call("admit", kind, false)):
				admitted += 1
				var node := Node.new()
				parent.add_child(node)
				budget.call("track", node, kind)
		check(admitted == int(LOW_TIER[kind]),
			"Low admits %d ordinary %s visuals and skips the rest (%d)" % [LOW_TIER[kind], kind, admitted])
		check(bool(budget.call("admit", kind, true)),
			"a %s involving the player, target or selection is drawn over the Low limit" % kind)
	var described: Dictionary = budget.call("describe")
	check(int((described.skipped as Dictionary).get(&"spell", 0)) == 5
		and int((described.admitted as Dictionary).get(&"spell", 0)) == 13
		and int((described.live as Dictionary).get(&"spell", 0)) == 12,
		"the census counts skipped, admitted and live spells: %s" % described)
	# Raising the quality makes room at once for what is already live.
	budget.set("quality", HIGH)
	check(bool(budget.call("admit", &"spell", false)),
		"switching Low to High admits ordinary spells again")
	budget.set("quality", LOW)
	budget.set("enabled", false)
	check(bool(budget.call("admit", &"number", false)), "a disabled budget admits everything")
	parent.free()


func _check_tracking() -> void:
	var budget: RefCounted = BUDGET.new()
	budget.set("quality", LOW)
	var parent := Node.new()
	root.add_child(parent)
	var nodes: Array[Node] = []
	for index: int in 6:
		check(bool(budget.call("admit", &"number", false)), "number %d fits the Low budget" % index)
		var node := Node.new()
		parent.add_child(node)
		budget.call("track", node, &"number")
		nodes.append(node)
	check(not bool(budget.call("admit", &"number", false)), "the seventh ordinary number is skipped")
	nodes[0].free()
	check(int(budget.call("live", &"number")) == 5, "a number leaving the tree frees its place")
	check(bool(budget.call("admit", &"number", false)), "and the next one fits again")
	budget.call("track", null, &"number")
	check(int(budget.call("live", &"number")) == 5, "tracking nothing counts nothing")
	parent.free()
	check(int(budget.call("live", &"number")) == 0, "every tracked node released on exit")
