# Standalone contract for the identity and exact-content dimensions used by
# crowd_skin_census.gd. Run only when a Godot test slot is available.
extends RefCounted

const CENSUS = preload("res://tests/fixtures/crowd_skin_census.gd")

static func contract() -> Dictionary:
	var poses: Array[Transform3D] = [Transform3D.IDENTITY,
		Transform3D(Basis.IDENTITY, Vector3(0.0, 1.0, 0.0))]
	var names: Array[String] = ["root", "spine_01"]
	var shared := _skin(names, poses)
	var equal_content_a := _skin(names, poses)
	var different_name := _skin(["root_alt", "spine_01"], poses)
	var different_order := _skin(["spine_01", "root"], poses)
	var different_pose := _skin(names, [poses[0], Transform3D(Basis.IDENTITY,
		Vector3(0.0, 1.001, 0.0))])
	var equal_content_b := _skin(names, poses)
	var actor_a := ReplicatedActor3D.new()
	actor_a.name = "CensusA"
	_equipment_mesh(actor_a, shared)
	_equipment_mesh(actor_a, shared)
	_equipment_mesh(actor_a, equal_content_a)
	_equipment_mesh(actor_a, different_name)
	_equipment_mesh(actor_a, different_order)
	_equipment_mesh(actor_a, different_pose)
	_equipment_mesh(actor_a, null)
	_equipment_mesh(actor_a, shared, false)
	var actor_b := ReplicatedActor3D.new()
	actor_b.name = "CensusB"
	_equipment_mesh(actor_b, shared)
	_equipment_mesh(actor_b, equal_content_b)
	var ignored := Node.new()
	var census := CENSUS.census({"a": actor_a, "b": actor_b, "ignored": ignored})
	var total: Dictionary = census.get("total", {}) as Dictionary
	var row_a := _actor_row(census.get("perActor", []) as Array, "CensusA")
	var row_b := _actor_row(census.get("perActor", []) as Array, "CensusB")
	var checks := {
		"actorAResources": row_a.get("meshInstances") == 6 and row_a.get("distinctSkins") == 5 and row_a.get("deduplicatedBindCount") == 10,
		"actorAContents": row_a.get("distinctSkinContents") == 4 and row_a.get("deduplicatedContentBindCount") == 8,
		"actorBResources": row_b.get("meshInstances") == 2 and row_b.get("distinctSkins") == 2 and row_b.get("deduplicatedBindCount") == 4,
		"actorBContents": row_b.get("distinctSkinContents") == 1 and row_b.get("deduplicatedContentBindCount") == 2,
		"aggregateResources": total.get("actors") == 2 and total.get("meshInstances") == 8 and total.get("distinctSkins") == 6 and total.get("sumActorDistinctSkins") == 7 and total.get("sumActorDeduplicatedBindCount") == 14,
		"aggregateContents": total.get("distinctSkinContents") == 4 and total.get("sumActorDistinctSkinContents") == 5 and total.get("sumActorDeduplicatedContentBindCount") == 10,
		"referencesRemainInternal": not bool((census.get("skinReferences", {}) as Dictionary).get("available", true)),
	}
	actor_a.free()
	actor_b.free()
	ignored.free()
	var passed := true
	for result: Variant in checks.values():
		passed = passed and bool(result)
	checks["passed"] = passed
	return checks

static func _equipment_mesh(actor: ReplicatedActor3D, skin: Skin,
		native_equipment: bool = true) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	if native_equipment:
		mesh.set_meta("native_equipment", true)
	mesh.skin = skin
	actor.add_child(mesh)
	return mesh

static func _actor_row(rows: Array, name: String) -> Dictionary:
	for row_value: Variant in rows:
		var row: Dictionary = row_value as Dictionary
		if str(row.get("actor", "")) == name:
			return row
	return {}

static func _skin(names: Array[String], poses: Array[Transform3D]) -> Skin:
	var skin := Skin.new()
	for index: int in range(names.size()):
		skin.add_named_bind(names[index], poses[index])
	return skin
