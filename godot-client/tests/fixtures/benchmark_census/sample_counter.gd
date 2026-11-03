extends RefCounted
## Test fixture for the crowd benchmark's census contributors
## (tests/test_crowd_benchmark_census_hook.gd). A real contributor lives in
## res://tests/integration/census/ and has the same three methods. This one
## counts the actors and facts it is given and declines the "skip" boundary.

var _boundary := ""
var _counts := {"actors": 0, "built": 0, "inFrustum": 0, "local": 0}


func begin(boundary: String, context: Dictionary) -> bool:
	_boundary = boundary
	_counts["contextLocalId"] = int(context.get("localId", -1))
	return boundary != "skip"


func actor(_node: Object, facts: Dictionary) -> void:
	_counts.actors += 1
	_counts.built += int(bool(facts.get("built", false)))
	_counts.inFrustum += int(bool(facts.get("inFrustum", false)))
	_counts.local += int(bool(facts.get("local", false)))


func finish() -> Dictionary:
	var out := _counts.duplicate()
	out["boundary"] = _boundary
	return out
