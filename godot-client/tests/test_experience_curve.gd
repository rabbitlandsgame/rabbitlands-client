extends SceneTree
## All server thresholds, including the 64-bit-safe integer tail, must agree.

const XPTable = preload("res://src/state/experience_curve.gd")
const SERVER_SHA256 := "41e6f880e8e41eb032d9815f5d97384e6f0aa3d4b03aa71d3904faf8a977b36b"
var failures := 0

func _init() -> void:
	var thresholds := PackedStringArray()
	var previous_cost: int = 0
	for level: int in range(501):
		var threshold: int = XPTable.for_level(level)
		thresholds.append(str(threshold))
		if level == 0:
			continue
		var cost: int = threshold - XPTable.for_level(level - 1)
		_expect(cost > previous_cost if level <= 148 else cost == 10000000,
			"cost increases to the plateau and stays flat: level %d" % level)
		previous_cost = cost
	_expect(",".join(thresholds).sha256_text() == SERVER_SHA256,
		"all 501 thresholds match the approved server table")
	_expect(XPTable.for_level(-1) == 0, "negative level clamps to zero")
	_expect(XPTable.for_level(501) == XPTable.for_level(500), "overall ceiling clamps")
	_expect(XPTable.max_level_for("attack") == 200, "individual skills cap at 200")
	_expect(XPTable.max_level_for("overall") == 500, "overall caps at 500")
	print("experience curve: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)
