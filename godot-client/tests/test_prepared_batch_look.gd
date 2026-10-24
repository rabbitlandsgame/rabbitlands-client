extends SceneTree
## Real renderer: prepared private raw batch overrides must not block the
## existing first-member look/chroma binding or change authored overrides.
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const REGION := "amethyst_barrens"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("prepared batch look: " + message)

func _claim(node: Node, owner: Node) -> void:
	for child: Node in node.get_children():
		child.owner = owner
		_claim(child, owner)

func _batch(world: Node3D, identity: String, material_name: String, authored: bool) -> void:
	var material := StandardMaterial3D.new()
	material.resource_name = material_name
	material.albedo_color = Color(0.2, 0.55, 0.17)
	var mesh := BoxMesh.new()
	mesh.size = Vector3(2, 4, 2)
	mesh.material = material
	var batch := MultiMeshInstance3D.new()
	batch.name = identity
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = mesh
	batch.multimesh.instance_count = 2
	if authored:
		var override := StandardMaterial3D.new()
		override.resource_name = "authored_override"
		override.albedo_color = Color.BLUE
		batch.material_override = override
	world.add_child(batch)
	for index: int in 2:
		var member := MeshInstance3D.new()
		member.name = ("%s-oak-tree-%d" if identity != "Crystal" else "%s-crystal-%d") % ["kit", index]
		member.mesh = mesh
		member.position = Vector3(index * 4, 0, world.get_child_count() * 5)
		member.visible = false
		member.set_meta(WorldLoader.BATCH_PATH_META, NodePath(identity))
		member.set_meta(WorldLoader.BATCH_INDEX_META, index)
		world.add_child(member)
		batch.multimesh.set_instance_transform(index, member.transform)

func _source() -> PackedScene:
	var world := Node3D.new()
	world.name = "Fixture"
	_batch(world, "Crown", "leaf_atlas", false)
	_batch(world, "Crystal", "amethyst_crystal", false)
	_batch(world, "Authored", "leaf_atlas", true)
	_claim(world, world)
	var packed := PackedScene.new()
	_expect(packed.pack(world) == OK, "synthetic raw world packs")
	world.free()
	return packed

func _link(world: Node3D) -> void:
	var linker := WorldLoader.new()
	linker.world_root = world
	linker._resolve_batch_links()
	linker.world_root = null
	linker.free()

func _paint(world: Node3D) -> void:
	LookFoliage.paint(world, REGION)
	LookFoliage.keep_chroma(world, REGION)

func _run() -> void:
	var old_look := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "full_painted")
	var packed := _source()
	var raw := packed.instantiate() as Node3D
	var record := {"status": "hit", "resource": packed, "entry": {}}
	var first := Lifecycle.instantiate(record)
	var second := Lifecycle.instantiate(record)
	_expect(raw != null and first != null and second != null, "raw and two prepared instances exist")
	if raw == null or first == null or second == null:
		if raw != null: raw.free()
		if first != null: first.free()
		if second != null: second.free()
		quit(1)
		return
	# Batch jitter intentionally hashes the imported root name. Independent
	# owners preserve the same authored root name instead of auto-renaming
	# three sibling Fixtures and accidentally testing three different seeds.
	var containers: Array[Node3D] = []
	for world: Node3D in [raw, first, second]:
		var container := Node3D.new()
		root.add_child(container)
		containers.append(container)
		world.name = "Fixture"
		container.add_child(world)
		_link(world)
	var a := first.get_node("Crown") as MultiMeshInstance3D
	var b := second.get_node("Crown") as MultiMeshInstance3D
	var authored := first.get_node("Authored") as MultiMeshInstance3D
	var authored_override: Material = authored.material_override
	var original_weak := a.get_meta(Lifecycle.RAW_BATCH_OVERRIDE) as WeakRef
	_expect(a.material_override != null and b.material_override != null
		and a.material_override != b.material_override and original_weak.get_ref() == a.material_override,
		"generated raw batch material is private and identified weakly")
	_expect(not authored.has_meta(Lifecycle.RAW_BATCH_OVERRIDE)
		and (authored_override as BaseMaterial3D).albedo_color == Color.BLUE,
		"authored non-null override is private but never marked as replaceable")
	_paint(raw)
	_paint(first)
	_paint(second)
	var reference := (raw.get_node("Crown") as MultiMeshInstance3D).material_override as ShaderMaterial
	var painted_a := a.material_override as ShaderMaterial
	var painted_b := b.material_override as ShaderMaterial
	_expect(reference != null and painted_a != null and painted_b != null
		and painted_a.shader == reference.shader
		and painted_a.get_shader_parameter(&"look_seed") == reference.get_shader_parameter(&"look_seed"),
		"prepared crown batch receives the same first-member paint/seed as raw")
	var raw_crystal := (raw.get_node("Crystal") as MultiMeshInstance3D).material_override as ShaderMaterial
	var crystal := (first.get_node("Crystal") as MultiMeshInstance3D).material_override as ShaderMaterial
	_expect(raw_crystal != null and crystal != null and crystal.shader == raw_crystal.shader
		and crystal.get_shader_parameter(&"look_chroma") == raw_crystal.get_shader_parameter(&"look_chroma"),
		"signature chroma also replaces only the generated raw batch override")
	_expect(original_weak.get_ref() != null
		and (a.get_meta(Lifecycle.MaterialOwnership.META) as Array).has(original_weak.get_ref()),
		"separate destruction-order ownership retains the replaced raw material through render-instance lifetime")
	_expect(authored.material_override == authored_override
		and (authored_override as BaseMaterial3D).albedo_color == Color.BLUE,
		"paint and chroma preserve the exact authored override object and values")
	if painted_a != null and painted_b != null and reference != null:
		var unchanged: Variant = painted_b.get_shader_parameter(&"look_seed")
		painted_a.set_shader_parameter(&"look_seed", 0.987)
		_expect(painted_b.get_shader_parameter(&"look_seed") == unchanged
			and reference.get_shader_parameter(&"look_seed") != 0.987,
			"painted prepared batch mutations cannot alter another instance or raw reference")
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": REGION + "__chunk_fixture"}, "continentGeography": {}}
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "original")
	LookSwitch.sync(first, manifest)
	_expect(a.material_override == null and authored.material_override == authored_override,
		"live original switch removes generated paint and preserves authored override")
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "full_painted")
	LookSwitch.sync(first, manifest)
	_expect(a.material_override is ShaderMaterial and authored.material_override == authored_override,
		"live full-painted switch restores batch paint without replacing authored override")
	var pristine := packed.instantiate() as Node3D
	_expect((pristine.get_node("Crown") as MultiMeshInstance3D).material_override == null,
		"native adaptation and look never mutate the cached raw template")
	pristine.free()
	for container: Node3D in containers:
		container.free()
	_expect(original_weak.get_ref() == null,
		"weak identity marker and material ownership are finite after actual instance destruction")
	if old_look.is_empty(): OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else: OS.set_environment(LookProfile.ENABLE_VARIABLE, old_look)
	await process_frame
	await process_frame
	print("prepared batch look tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)
