extends SceneTree
## Synthetic contract for exact-content rebound Skin interning.

const POOL = preload("res://src/actors/rebound_skin_pool.gd")
var _failures := 0


func _init() -> void:
	var poses := [
		Transform3D.IDENTITY,
		Transform3D(Basis.IDENTITY, Vector3(0.0, 1.0, 0.0)),
	]
	var names := ["pool_contract_root", "pool_contract_spine"]
	var bones := [7, 11]
	var first := _skin(bones, names, poses)
	var equal_content := _skin(bones, names, poses)
	var different_name := _skin(bones, [names[0] + "_alt", names[1]], poses)
	var different_bone := _skin([8, 11], names, poses)
	var different_order := _skin([bones[1], bones[0]],
		[names[1], names[0]], [poses[1], poses[0]])
	var different_pose := _skin(bones, names, [poses[0],
		Transform3D(Basis.IDENTITY,
			Vector3(0.0, 1.00000011920928955078125, 0.0))])
	var different_bind_count := _skin([bones[0], bones[1], 13],
		[names[0], names[1], "pool_contract_extra"],
		[poses[0], poses[1], Transform3D.IDENTITY])

	var canonical: Skin = POOL.intern_finalized(first)
	_expect(canonical == first, "the first finalized Skin is retained")
	_expect(POOL.intern_finalized(equal_content) == canonical,
		"exact equal bind content shares Skin identity")
	_expect(POOL.intern_finalized(different_name) != canonical,
		"different bind name does not alias")
	_expect(POOL.intern_finalized(different_bone) != canonical,
		"different rig bone index does not alias")
	_expect(POOL.intern_finalized(different_order) != canonical,
		"different bind order does not alias")
	_expect(different_pose.get_bind_pose(1).origin.y != poses[1].origin.y,
		"adjacent float32 pose is retained as a different exact value")
	_expect(POOL.intern_finalized(different_pose) != canonical,
		"adjacent exact pose float does not alias")
	_expect(POOL.intern_finalized(different_bind_count) != canonical,
		"different bind count does not alias")
	_expect(POOL.intern_finalized(null) == null,
		"null candidates are rejected without entering the pool")

	_expect(first.get_bind_count() == 2
		and first.get_bind_name(0) == names[0]
		and first.get_bind_bone(0) == bones[0]
		and first.get_bind_pose(1) == poses[1],
		"interning does not mutate the input Skin")
	print("rebound skin pool contract: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _skin(bones: Array, names: Array, poses: Array) -> Skin:
	var skin := Skin.new()
	for index: int in range(names.size()):
		skin.add_bind(int(bones[index]), poses[index] as Transform3D)
		skin.set_bind_name(index, str(names[index]))
	return skin


func _expect(value: bool, label: String) -> void:
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
