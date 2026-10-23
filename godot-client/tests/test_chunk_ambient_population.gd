extends SceneTree

var failures := 0

class FixturePopulation extends AmbientPopulation:
	func _load_catalog() -> Dictionary:
		return {"fixture": {"scene": "user://chunk-ambient-test/animal.tscn"}}
const SCRATCH := "user://chunk-ambient-test"

func _init() -> void:
	call_deferred("_run")

func _expect(value: bool, message: String) -> void:
	if value:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _cell(stream: ContinentChunkStream, identity: String, x: float, layer := 8) -> Node3D:
	var cell := Node3D.new()
	cell.name = identity
	cell.set_meta("continent_chunk_id", identity)
	var body := StaticBody3D.new()
	body.collision_layer = layer
	body.collision_mask = 0
	body.position = Vector3(x, 1.5, 0)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40, 1, 40)
	shape.shape = box
	body.add_child(shape)
	cell.add_child(body)
	stream.add_child(cell)
	stream.cells[identity] = {"root":cell, "entry":{"id":identity,"estimatedResidentBytes":20,
		"bounds":{"min":[x-20,1,-20],"max":[x+20,2,20]}}}
	stream._update_resident_bytes()
	stream.cell_ready.emit(identity,cell)
	return cell

func _settle(population: AmbientPopulation, label: String) -> bool:
	# Collision registration needs a physics boundary; creation is bounded per
	# rendered process frame. Physics catch-up alone cannot renew that budget,
	# and a cold model load can consume a whole pass after the first animal.
	for index: int in 120:
		await physics_frame
		await process_frame
		if population.pending_creation_count() == 0:
			return true
	_expect(false, "%s completes its bounded creation queue: %s" % [
		label, str(population.creation_status())])
	return false

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(SCRATCH)
	var animal := Node3D.new()
	animal.name = "FixtureAnimal"
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	animal.add_child(mesh)
	mesh.owner = animal
	var packed := PackedScene.new()
	_expect(packed.pack(animal) == OK, "ambient model fixture packs")
	_expect(ResourceSaver.save(packed,SCRATCH.path_join("animal.tscn")) == OK, "ambient model fixture writes")
	animal.free()
	var stage := Node3D.new()
	root.add_child(stage)
	var stream := ContinentChunkStream.new()
	stream.position = Vector3(80,4,-50)
	stage.add_child(stream)
	var population := FixturePopulation.new()
	stream.add_child(population)
	var manifest := WorldManifest.new()
	manifest.data = {"ambientPopulation":{"groups":[
		{"id":"west", "model":"fixture", "count":2, "center":[0,99,0], "radius":0, "seed":13},
		{"id":"east", "model":"fixture", "count":2, "center":[600,99,0], "radius":0, "seed":17}]}}
	var space := stage.get_world_3d().direct_space_state
	population.populate(manifest,space,stream)
	population._streamed_catalog = {"fixture":{"scene":SCRATCH.path_join("animal.tscn")}}
	if not (await _settle(population, "cold territory")):
		stage.free()
		quit(1)
		return
	_expect(population._spawned.is_empty() and population._scenes.is_empty(),
		"cold territory creates neither floating animals nor resident model resources")
	var west := _cell(stream,"west",0)
	if not (await _settle(population, "west terrain")):
		stage.free()
		quit(1)
		return
	_expect(population._spawned.size() == 2, "only the newly loaded terrain's wildlife instantiates")
	for node: Node3D in population._spawned:
		_expect(node.get_parent() == west and is_equal_approx(node.global_position.y,6.0),
			"wildlife belongs to its actual chunk and grounds through the translated territory frame")
	var old: Variant = population._spawned[0]
	population.populate(manifest,space,stream)
	_expect(population._spawned[0] == old, "adoption retains the same wildlife instances")
	stream._retire_cell("west")
	_expect(population._spawned.is_empty() and population._scenes.is_empty(),
		"retirement releases wildlife tracking and unused packed model cache")
	for index: int in 4:
		stream._drain_retired()
	_expect(not is_instance_valid(old), "bounded chunk retirement frees its actual wildlife descendants")
	var east := _cell(stream,"east",600,16)
	if not (await _settle(population, "east preview terrain")):
		stage.free()
		quit(1)
		return
	_expect(population._spawned.size() == 2 and population._spawned[0].get_parent() == east,
		"later preview-layer terrain grounds and owns only its nearby wildlife")
	_expect(is_equal_approx(population._spawned[0].global_position.x,680.0),
		"neighbor scenery remains in the same shared world frame")
	var legacy := FixturePopulation.new()
	stage.add_child(legacy)
	legacy._scenes["fixture"] = packed
	var initial := legacy.populate(manifest,space)
	_expect(initial <= 4, "legacy unchunked creation obeys its first-pass count allowance")
	if not (await _settle(legacy, "legacy unchunked population")):
		stage.free()
		quit(1)
		return
	_expect(legacy.pending_creation_count() == 0 and legacy._spawned.size() == 4
		and legacy._spawned[0].get_parent() == legacy,
		"legacy unchunked maps complete their declared population through bounded passes")
	stage.free()
	await process_frame
	print("chunk ambient population tests: ", "PASS" if failures == 0 else "FAIL")
	quit(0 if failures == 0 else 1)
