extends SceneTree
## Run with --headless --script res://tests/integration/torso_body_cover.gd.

var failures := 0

## The high-collar torsos that floated every bridged race's head on
## 2026-10-06: two starter kits (Studded Jack, Acolyte Tunic) plus the Bark
## Jerkin and the Furtrim Coat.
const HIGH_COLLAR_TORSOS := [209, 222, 184, 189]
## Measured ceiling on the "Shared neck bridge" faces a high collar may remove
## from a rig. Since the race rebase (rebase_race_body.py) the bridge takes the
## same face test as the rest of the body. Every vertex of a male bridge and of
## a female bridge behind the neck axis keeps over .5 Head/neck_01 weight; the
## 16 female throat faces with a corner at .32 to .5 sit in front of the axis
## and keep more than TorsoBodyCover.FRONT_BRIDGE_MIN_WEIGHT. So no rig loses a
## bridge face (measured 2026-10-07 for all 16 rigs under the four high collars
## and the four class kits). Dropping the whole bridge (83e3703d3) removed 809
## to 1,754 faces and floated the head; the 2026-10-06 rear trim, written for
## the old flared bridges, cut 34 (male) to 156 (female) faces out of the
## rebuilt necks. After any race body rebuild re-measure from this test's
## "removed %d faces" output.
const BRIDGE_REMOVAL_CEILING := 0
## Faces in loose lower-neck shells the wardrobe-only neckline strips. The
## 2026-10-05 Human female carries one, a 30-face fold at the left trapezius
## (x -.08 m, y 1.465 to 1.475 m), and every rebased female inherits it with
## the Human body; the Human male has none. Shells are found welded across
## every surface, so the fragments of a race's neck bridge never count.
## Measured 2026-10-07.
const DETACHED_COLLAR_FACES := {"female": 30, "male": 0}
## The neck between the jaw and every generated collar's rear rim.
const ATTACHED_NECK_BAND := Vector2(1.52, 1.57)
## Below its bridge a rebased race is the Human body of its sex, so its shared
## body is cut face for face like the Human's: faces whose rest centroids match,
## above this height, must be kept or removed alike, and at least
## HUMAN_MATCHED_FACES of them must match. Measured 2026-10-07: under the high
## collars 2,027 (male) and 3,455 (female) shared-body faces; on the wardrobe
## neckline, which counts the bridge too, 2,036 to 2,037 and 3,621.
const HUMAN_MATCH_MIN_Y := 1.30
const HUMAN_MATCHED_FACES := 1800
const BRIDGE_MATERIAL := "Shared neck bridge"
const RACE_HEAD_MATERIAL := "Race head"

## The Human's wardrobe-neckline and high-collar cuts, by sex, for the races.
var human_wardrobe := {}
var human_collar := {}

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	# The Human bodies first: every rebased race is compared with them.
	var paths: Array[String] = []
	var others: Array[String] = []
	for path: String in DirAccess.get_files_at("res://assets/actors/native/races"):
		if path.ends_with(".glb"):
			(paths if path.begins_with("luminous_") else others).append(path)
	paths.append_array(others)
	var races := 0
	var race_names := PackedStringArray()
	for path: String in paths:
		var race := path.get_basename()
		var sex := "female" if race.ends_with("_female") else "male"
		var scene := load("res://assets/actors/native/races/" + path) as PackedScene
		var body := scene.instantiate()
		root.add_child(body)
		var skeleton := body.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
		var fit := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin.y / 1.5684900288581848
		# The throat rule splits the bridge at the canonical neck_01 -> Head axis;
		# every rig must still stand on it (measured 2026-10-07: within .6 mm).
		var neck_rest := skeleton.get_bone_global_rest(skeleton.find_bone("neck_01")).origin / fit
		var head_rest := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin / fit
		expect(neck_rest.distance_to(TorsoBodyCover.NECK_AXIS_BASE) < .002
			and head_rest.distance_to(TorsoBodyCover.NECK_AXIS_TOP) < .002,
			path + " keeps the canonical neck axis the throat rule splits on: neck %s, head %s"
			% [neck_rest, head_rest])
		var removed := 0
		var retained := 0
		var bridge_surfaces := 0
		for node: Node in body.find_children("*", "MeshInstance3D", true, false):
			var mesh := node as MeshInstance3D
			if mesh.skin == null:
				continue
			var original := mesh.mesh
			var transform := skeleton.global_transform.affine_inverse() * mesh.global_transform
			var body_mesh := mesh.name.to_lower() in ["body", "char1", "mesh_node"]
			TorsoBodyCover.apply(mesh, true, transform, fit)
			var covered_mesh := mesh.mesh
			expect(mesh.mesh != original, path + " has a private covered mesh")
			expect(mesh.mesh.get_surface_count() == original.get_surface_count(), "surface numbering survives")
			for surface: int in range(original.get_surface_count()):
				var before := original.surface_get_arrays(surface)
				var after := mesh.mesh.surface_get_arrays(surface)
				var material := original.surface_get_material(surface)
				var bridge_surface := material != null and material.resource_name == BRIDGE_MATERIAL
				if body_mesh and bridge_surface:
					bridge_surfaces += 1
				# A race's neck bridge is cut like the rest of the body: nothing moves.
				expect(before[Mesh.ARRAY_VERTEX] == after[Mesh.ARRAY_VERTEX],
					path + " " + str(mesh.name) + " surface " + str(surface) + " keeps vertex positions")
				expect(before[Mesh.ARRAY_BONES] == after[Mesh.ARRAY_BONES], "bones stay intact")
				expect(before[Mesh.ARRAY_WEIGHTS] == after[Mesh.ARRAY_WEIGHTS], "weights stay intact")
				expect(original.surface_get_material(surface) == mesh.mesh.surface_get_material(surface),
					"surface material stays intact")
				var vertices: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
				var source: PackedInt32Array = before[Mesh.ARRAY_INDEX]
				if source.is_empty():
					for index: int in range(vertices.size()):
						source.append(index)
				var expected := PackedInt32Array()
				for i: int in range(0, source.size(), 3):
					var center := (transform * ((vertices[source[i]] + vertices[source[i + 1]]
						+ vertices[source[i + 2]]) / 3.0)) / fit
					var covered := independently_covered(mesh.name.to_lower(), center)
					if independently_retained(mesh, before, source, i, center,
							transform, fit, covered, false, {}, bridge_surface):
						expected.append_array(source.slice(i, i + 3))
				if expected.is_empty():
					expected = PackedInt32Array([0, 0, 0])
				var indices: PackedInt32Array = after[Mesh.ARRAY_INDEX]
				expect(indices == expected,
					path + " " + str(mesh.name) + " surface " + str(surface)
					+ " retains exactly the independently reconstructed face set")
				removed += source.size() - indices.size()
				for i: int in range(0, indices.size(), 3):
					if indices[i] == indices[i + 1]:
						continue
					retained += 1
			TorsoBodyCover.apply(mesh, true, transform, fit)
			expect(mesh.mesh == covered_mesh, "identical coverage reuses its cached mesh")
			if body_mesh:
				verify_wardrobe_neckline(mesh, original, transform, fit, race, sex)
			TorsoBodyCover.apply(mesh, false, transform, fit)
			expect(mesh.mesh == original, "unequip restores the exact body resource")
		var expected_bridge_surfaces := 0 if path.begins_with("luminous_") else 2
		expect(bridge_surfaces == expected_bridge_surfaces,
			path + " imports the authored Shared neck bridge surface contract")
		expect(removed > 100, path + " removes covered clothing")
		expect(retained > 100, path + " preserves uncovered body")
		races += 1
		race_names.append(race)
		body.free()
	print("TORSO BODY COVER: %d races, %d failures" % [races, failures])
	expect(races == 16, "all races tested")
	# Exercise the actual attachment path, including replacement detection and
	# three equip/unequip cycles. Checking cut() alone would miss a node-name or
	# wardrobe-refresh integration failure.
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for race: String in race_names:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var config: Dictionary = models[race]
		var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config["animationMap"]))
		var errors := actor.configure({"actor_id": 991, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": race, "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), config, animations, equipment)
		expect(errors.is_empty(), race + " actor configures: " + str(errors))
		for visual: int in [192, 228, 187]:
			actor.apply_equipment_visuals({5: visual})
			var covered := 0
			for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
				var mesh := node as MeshInstance3D
				if mesh.name.to_lower() in ["hair", "eyes"]:
					expect(not mesh.has_meta("uncovered_body_mesh"), "coverage leaves hair and eyes alone")
				if mesh.has_meta("uncovered_body_mesh") and mesh.mesh != mesh.get_meta("uncovered_body_mesh"):
					covered += 1
			expect(covered > 0, race + " generated armour activates body replacement")
			actor.apply_equipment_visuals({})
			for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
				var mesh := node as MeshInstance3D
				if mesh.has_meta("uncovered_body_mesh"):
					expect(mesh.mesh == mesh.get_meta("uncovered_body_mesh"), "actor unequip restores body")
		for visual: int in HIGH_COLLAR_TORSOS:
			actor.apply_equipment_visuals({5: visual})
			verify_attached_neck(actor, race, visual)
		actor.apply_equipment_visuals({})
		actor.free()
	print("TORSO EQUIP/UNEQUIP: %d failures" % failures)
	quit(1 if failures else 0)

func independently_covered(instance_name: String, point: Vector3,
		mask_to_wardrobe_neckline: bool = false) -> bool:
	if (mask_to_wardrobe_neckline
			and instance_name in ["body", "char1", "mesh_node"]):
		var collar := (point.y > TorsoBodyCover.NECK_ENVELOPE_MIN_Y
			and point.y < TorsoBodyCover.HIGH
			and absf(point.x) < TorsoBodyCover.NECK_ENVELOPE_HALF_WIDTH)
		var front_apron := (point.y > TorsoBodyCover.FRONT_APRON_MIN_Y
			and point.y < TorsoBodyCover.FRONT_APRON_MAX_Y
			and absf(point.x) < TorsoBodyCover.FRONT_APRON_HALF_WIDTH
			and point.z > TorsoBodyCover.FRONT_APRON_MIN_Z)
		return collar and not front_apron
	var covered := (point.y > .95 and point.y < 1.535 and absf(point.x) < .665)
	if instance_name == "wardrobe_shirt":
		covered = covered or (point.y > 1.40 and point.y < 1.65 and absf(point.x) < .20)
	return covered

func independently_retained(instance: MeshInstance3D, arrays: Array,
		ids: PackedInt32Array, start: int, center: Vector3,
		to_rig: Transform3D, fit: float, covered: bool,
		mask_to_wardrobe_neckline: bool = false,
		detached_neck_vertices: Dictionary = {}, bridge_surface: bool = false) -> bool:
	if instance.name.to_lower() not in ["body", "char1", "mesh_node"] or instance.skin == null:
		return not covered
	if (mask_to_wardrobe_neckline
			and (detached_neck_vertices.has(ids[start])
				or detached_neck_vertices.has(ids[start + 1])
				or detached_neck_vertices.has(ids[start + 2]))):
		return false
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var stride: int = bones.size()/vertices.size()
	var all_corners_protected := true
	var lowest_corner_weight := 1.0
	for corner: int in range(3):
		var corner_weight := 0.0
		for slot: int in range(stride):
			var offset := ids[start+corner]*stride+slot
			var bone_name := instance.skin.get_bind_name(bones[offset])
			if bone_name.is_empty():
				var skeleton := instance.get_node(instance.skeleton) as Skeleton3D
				bone_name = skeleton.get_bone_name(instance.skin.get_bind_bone(bones[offset]))
			if bone_name in [&"Head", &"neck_01"]:
				corner_weight += weights[offset]
		all_corners_protected = all_corners_protected and corner_weight > .5
		lowest_corner_weight = minf(lowest_corner_weight, corner_weight)
	# Inside the collar every face, a race's neck bridge included, stays only
	# while every corner keeps over half its Head/neck_01 weight, except the
	# bridge's throat: in front of the canonical neck_01 (0, 1.452, -.051) ->
	# Head (0, 1.568, .011) axis, under armour, a quarter is enough there.
	var neck_envelope := (covered
		and center.y > TorsoBodyCover.NECK_ENVELOPE_MIN_Y
		and absf(center.x) < TorsoBodyCover.NECK_ENVELOPE_HALF_WIDTH)
	if (neck_envelope and bridge_surface and not mask_to_wardrobe_neckline
			and center.z >= lerpf(-.051, .011, (center.y - 1.452) / (1.568 - 1.452))):
		return lowest_corner_weight > .25
	if neck_envelope:
		return all_corners_protected
	return all_corners_protected or not covered

## Regression for heads floating above a high collar. The rig's own rest
## skeleton supplies the neck axis. Four contracts: the bridge loses no more
## than its measured ceiling; every 30 degree sector keeps at least half of
## the neck surface just below the jaw; the shared body below the bridge is cut
## face for face like the Human's under the same collar (the 2026-10-06 rear
## trim cut holes into the rebuilt necks); and no bridge spike (a face hanging
## by one edge) or loose bridge shard is left.
func verify_attached_neck(actor: ReplicatedActor3D, race: String, visual: int) -> void:
	var label := "%s with torso 5:%d" % [race, visual]
	var sex := "female" if race.ends_with("_female") else "male"
	var skeleton := actor.get_skeleton()
	var fit := actor.rig_fit_scale()
	var neck := skeleton.get_bone_global_rest(skeleton.find_bone("neck_01")).origin / fit
	var head := skeleton.get_bone_global_rest(skeleton.find_bone("Head")).origin / fit
	var band_before: Array[int] = []
	var band_after: Array[int] = []
	for sector: int in range(12):
		band_before.append(0)
		band_after.append(0)
	var removed := 0
	var bodies := 0
	var cut := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.name.to_lower() not in ["body", "char1", "mesh_node"] \
				or not mesh.has_meta("uncovered_body_mesh"):
			continue
		bodies += 1
		var original := mesh.get_meta("uncovered_body_mesh") as Mesh
		var transform := skeleton.global_transform.affine_inverse() * mesh.global_transform
		cut.merge(neck_cut(original, mesh.mesh, transform, fit, false))
		for surface: int in range(original.get_surface_count()):
			var material := original.surface_get_material(surface)
			var bridge_surface := material != null and material.resource_name == BRIDGE_MATERIAL
			for pass_index: int in range(2):
				var arrays := (original if pass_index == 0 else mesh.mesh).surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var ids: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
				if ids.is_empty():
					for index: int in range(vertices.size()):
						ids.append(index)
				for start: int in range(0, ids.size(), 3):
					if ids[start] == ids[start + 1] and ids[start] == ids[start + 2]:
						continue
					if bridge_surface:
						removed += 1 if pass_index == 0 else -1
					var center := (transform * ((vertices[ids[start]] + vertices[ids[start + 1]]
						+ vertices[ids[start + 2]]) / 3.0)) / fit
					var axis := neck.lerp(head, (center.y - neck.y) / (head.y - neck.y))
					var radial := Vector2(center.x - axis.x, center.z - axis.z)
					if center.y <= ATTACHED_NECK_BAND.x or center.y >= ATTACHED_NECK_BAND.y \
							or radial.length() <= .035 or radial.length() >= .11:
						continue
					var sector := int(floor(fposmod(atan2(radial.x, radial.y), TAU) / TAU * 12.0)) % 12
					if pass_index == 0:
						band_before[sector] += 1
					else:
						band_after[sector] += 1
	expect(bodies > 0, label + " cuts a body mesh under the collar")
	expect(removed <= BRIDGE_REMOVAL_CEILING,
		label + " keeps the shared neck bridge: removed %d faces, ceiling %d"
		% [removed, BRIDGE_REMOVAL_CEILING])
	for sector: int in range(12):
		expect(band_after[sector] * 2 >= band_before[sector],
			label + " keeps its neck attached in sector %d: %d of %d faces"
			% [sector, band_after[sector], band_before[sector]])
	if race.begins_with("luminous_"):
		human_collar["%s:%d" % [sex, visual]] = cut
	else:
		expect_human_cut(cut, human_collar.get("%s:%d" % [sex, visual], {}) as Dictionary,
			label + " cuts its body below the bridge exactly like the Human's")
	var debris := independent_bridge_debris(actor)
	expect(debris.x == 0, label + " leaves no neck-bridge spike: %d" % debris.x)
	expect(debris.y == 0, label + " leaves no loose neck-bridge shard: %d faces" % debris.y)

## Kept (true) or removed (false) for every face of `original` outside the race
## head (and, without `with_bridge`, the neck bridge) whose rest centroid lies
## above HUMAN_MATCH_MIN_Y, keyed by that centroid to a tenth of a millimetre.
func neck_cut(original: Mesh, covered: Mesh, transform: Transform3D, fit: float,
		with_bridge: bool = true) -> Dictionary:
	var result := {}
	for surface: int in range(original.get_surface_count()):
		var material := original.surface_get_material(surface)
		var material_name := material.resource_name if material != null else ""
		if material_name == RACE_HEAD_MATERIAL or (material_name == BRIDGE_MATERIAL
				and not with_bridge):
			continue
		var before := original.surface_get_arrays(surface)
		var vertices: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
		var source: PackedInt32Array = before[Mesh.ARRAY_INDEX]
		var kept_ids: PackedInt32Array = covered.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
		var kept := {}
		for start: int in range(0, kept_ids.size(), 3):
			kept[Vector3i(kept_ids[start], kept_ids[start + 1], kept_ids[start + 2])] = true
		for start: int in range(0, source.size(), 3):
			var center := (transform * ((vertices[source[start]] + vertices[source[start + 1]]
				+ vertices[source[start + 2]]) / 3.0)) / fit
			if center.y <= HUMAN_MATCH_MIN_Y:
				continue
			result[Vector3i((center * 10000.0).round())] = kept.has(
				Vector3i(source[start], source[start + 1], source[start + 2]))
	return result

func expect_human_cut(cut: Dictionary, human: Dictionary, label: String) -> void:
	var matched := 0
	var differing := 0
	for key: Variant in cut:
		var human_key: Variant = near_key(human, key as Vector3i)
		if human_key == null:
			continue
		matched += 1
		if bool(cut[key]) != bool(human[human_key]):
			differing += 1
	expect(matched >= HUMAN_MATCHED_FACES and differing == 0,
		label + ": %d of %d matched faces differ" % [differing, matched])

## The same moved points with the same targets, to a tenth of a millimetre:
## a race keeps its own rest skeleton, whose scale differs from the Human's by
## a few micrometres, so keys may round one step apart.
func same_entries(first: Dictionary, second: Dictionary) -> bool:
	if first.size() != second.size():
		return false
	for key: Variant in first:
		var other: Variant = near_key(second, key as Vector3i)
		if other == null:
			return false
		var offset := (second[other] as Vector3i) - (first[key] as Vector3i)
		if maxi(absi(offset.x), maxi(absi(offset.y), absi(offset.z))) > 1:
			return false
	return true

## `key`, or the key one rounding step from it, if `values` holds one.
func near_key(values: Dictionary, key: Vector3i) -> Variant:
	if values.has(key):
		return key
	for x: int in range(-1, 2):
		for y: int in range(-1, 2):
			for z: int in range(-1, 2):
				var other := key + Vector3i(x, y, z)
				if values.has(other):
					return other
	return null

## Bridge faces of the covered body with two open edges (x) and faces in
## components made only of bridge faces (y), welded by rest position across
## every surface: the spikes and loose shards a cut through the bridge leaves.
func independent_bridge_debris(actor: ReplicatedActor3D) -> Vector2i:
	var skeleton := actor.get_skeleton()
	var fit := actor.rig_fit_scale()
	var result := Vector2i.ZERO
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.name.to_lower() not in ["body", "char1", "mesh_node"] \
				or not mesh.has_meta("uncovered_body_mesh"):
			continue
		var transform := skeleton.global_transform.affine_inverse() * mesh.global_transform
		var point_ids := {}
		var faces: Array[PackedInt32Array] = []
		var bridge_faces: Array[bool] = []
		for surface: int in range(mesh.mesh.get_surface_count()):
			var material := mesh.mesh.surface_get_material(surface)
			var bridge := material != null and material.resource_name == BRIDGE_MATERIAL
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var ids: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for start: int in range(0, ids.size(), 3):
				if ids[start] == ids[start + 1] and ids[start] == ids[start + 2]:
					continue
				var corners := PackedInt32Array()
				for corner: int in range(3):
					var point := (transform * vertices[ids[start + corner]]) / fit
					var key := Vector3i(roundi(point.x * 100000.0), roundi(point.y * 100000.0),
						roundi(point.z * 100000.0))
					if not point_ids.has(key):
						point_ids[key] = point_ids.size()
					corners.append(int(point_ids[key]))
				faces.append(corners)
				bridge_faces.append(bridge)
		var edge_counts := {}
		var edge_faces := {}
		for face: int in range(faces.size()):
			for corner: int in range(3):
				var a := faces[face][corner]
				var b := faces[face][(corner + 1) % 3]
				var edge := Vector2i(mini(a, b), maxi(a, b))
				edge_counts[edge] = int(edge_counts.get(edge, 0)) + 1
				if not edge_faces.has(edge):
					edge_faces[edge] = []
				(edge_faces[edge] as Array).append(face)
		var component := PackedInt32Array()
		component.resize(faces.size())
		component.fill(-1)
		for first: int in range(faces.size()):
			if component[first] >= 0:
				continue
			var members: Array[int] = [first]
			component[first] = first
			var only_bridge := true
			var cursor := 0
			while cursor < members.size():
				var face := members[cursor]
				cursor += 1
				only_bridge = only_bridge and bridge_faces[face]
				for corner: int in range(3):
					var a := faces[face][corner]
					var b := faces[face][(corner + 1) % 3]
					for other: Variant in edge_faces[Vector2i(mini(a, b), maxi(a, b))]:
						if component[int(other)] < 0:
							component[int(other)] = first
							members.append(int(other))
			if only_bridge:
				result.y += members.size()
		for face: int in range(faces.size()):
			if not bridge_faces[face]:
				continue
			var open_edges := 0
			for corner: int in range(3):
				var a := faces[face][corner]
				var b := faces[face][(corner + 1) % 3]
				if int(edge_counts[Vector2i(mini(a, b), maxi(a, b))]) == 1:
					open_edges += 1
			if open_edges >= 2:
				result.x += 1
	return result

## The wardrobe-only neckline (develop's 5:189/5:209/5:216/5:225 once). On the
## Human it is reconstructed face for face and point for point. A rebased race
## must strip the same detached shells, keep and remove the same faces below
## its bridge and tuck the same rim points as the Human of its sex; its bridge
## and race head, the visible neck and head, never move above 1.50 m (some race
## heads have open edges under the chin), and the bridge stays.
func verify_wardrobe_neckline(mesh: MeshInstance3D, original: Mesh,
		transform: Transform3D, fit: float, race: String, sex: String) -> void:
	var path := race + ".glb"
	TorsoBodyCover.apply(mesh, true, transform, fit, [], false, true)
	var detached := independently_detached_neck_vertices(original, transform, fit)
	var detached_faces := 0
	for surface: int in range(original.get_surface_count()):
		var source: PackedInt32Array = original.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
		var surface_detached := detached[surface] as Dictionary
		for start: int in range(0, source.size(), 3):
			if (surface_detached.has(source[start]) or surface_detached.has(source[start + 1])
					or surface_detached.has(source[start + 2])):
				detached_faces += 1
	expect(detached_faces == int(DETACHED_COLLAR_FACES[sex]),
		path + " identifies exactly %d detached collar faces, got %d"
		% [int(DETACHED_COLLAR_FACES[sex]), detached_faces])
	var moved := {}
	var neck_moved := 0
	var largest := 0.0
	var bridge_kept := 0
	for surface: int in range(original.get_surface_count()):
		var material := original.surface_get_material(surface)
		var material_name := material.resource_name if material != null else ""
		var before := original.surface_get_arrays(surface)
		var after := mesh.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = before[Mesh.ARRAY_VERTEX]
		var after_vertices: PackedVector3Array = after[Mesh.ARRAY_VERTEX]
		expect(before[Mesh.ARRAY_TEX_UV] == after[Mesh.ARRAY_TEX_UV],
			path + " wardrobe neckline preserves UVs")
		expect(before[Mesh.ARRAY_BONES] == after[Mesh.ARRAY_BONES],
			path + " wardrobe neckline preserves bone indices")
		expect(before[Mesh.ARRAY_WEIGHTS] == after[Mesh.ARRAY_WEIGHTS],
			path + " wardrobe neckline preserves skin weights")
		for vertex: int in range(vertices.size()):
			if vertices[vertex] != after_vertices[vertex]:
				var point := (transform * vertices[vertex]) / fit
				moved[Vector3i((point * 10000.0).round())] = Vector3i(
					((transform * after_vertices[vertex]) / fit * 10000.0).round())
		var kept_ids: PackedInt32Array = after[Mesh.ARRAY_INDEX]
		var visible_neck := material_name in [BRIDGE_MATERIAL, RACE_HEAD_MATERIAL]
		var counted := {}
		for start: int in range(0, kept_ids.size(), 3):
			if kept_ids[start] == kept_ids[start + 1] and kept_ids[start] == kept_ids[start + 2]:
				continue
			if material_name == BRIDGE_MATERIAL:
				bridge_kept += 1
			if not visible_neck:
				continue
			for corner: int in range(3):
				var vertex := kept_ids[start + corner]
				if counted.has(vertex):
					continue
				counted[vertex] = true
				var point := (transform * vertices[vertex]) / fit
				if point.y <= 1.50:
					continue
				var distance := ((transform * after_vertices[vertex]) / fit).distance_to(point)
				largest = maxf(largest, distance)
				if distance > .01:
					neck_moved += 1
		if not race.begins_with("luminous_"):
			continue
		# The Human: the exact reconstruction, face for face and point for point.
		var source: PackedInt32Array = before[Mesh.ARRAY_INDEX]
		if source.is_empty():
			for source_index: int in range(vertices.size()):
				source.append(source_index)
		var expected := PackedInt32Array()
		for source_index: int in range(0, source.size(), 3):
			var center := (transform * ((vertices[source[source_index]]
				+ vertices[source[source_index + 1]]
				+ vertices[source[source_index + 2]]) / 3.0)) / fit
			var covered := independently_covered(mesh.name.to_lower(), center, true)
			if independently_retained(mesh, before, source, source_index,
					center, transform, fit, covered, true, detached[surface]):
				expected.append_array(source.slice(source_index, source_index + 3))
		var expected_vertices := independently_inset_neckline_rim(
			vertices, expected, transform, fit)
		expect(after_vertices == expected_vertices,
			path + " insets only the independently reconstructed welded rim")
		var inset := 0
		for vertex: int in range(vertices.size()):
			if vertices[vertex] == expected_vertices[vertex]:
				continue
			inset += 1
			var before_point := (transform * vertices[vertex]) / fit
			var after_point := (transform * expected_vertices[vertex]) / fit
			expect(is_equal_approx(after_point.y,
				independently_wardrobe_neckline_y(before_point))
				and is_equal_approx(after_point.x,
					before_point.x * TorsoBodyCover.NECK_RIM_INSET)
				and is_equal_approx(after_point.z,
					before_point.z * TorsoBodyCover.NECK_RIM_INSET),
				path + " inset rim follows the shaped neckline")
		expect(inset > 0, path + " insets a non-empty welded rim")
		if expected.is_empty():
			expected = PackedInt32Array([0, 0, 0])
		expect(kept_ids == expected,
			path + " wardrobe neckline retains the independently reconstructed faces")
	var cut := neck_cut(original, mesh.mesh, transform, fit)
	if race.begins_with("luminous_"):
		expect(original.get_surface_count() == 1, path + " is one Human surface")
		human_wardrobe[sex] = {"cut": cut, "moved": moved}
		return
	var human: Dictionary = human_wardrobe.get(sex, {})
	expect_human_cut(cut, human.get("cut", {}) as Dictionary,
		path + " wardrobe neckline cuts below the bridge exactly like the Human's")
	expect(same_entries(moved, human.get("moved", {}) as Dictionary),
		path + " wardrobe neckline tucks exactly the Human's rim: %d points moved, the Human %d"
		% [moved.size(), (human.get("moved", {}) as Dictionary).size()])
	expect(neck_moved == 0, path + " wardrobe neckline keeps the visible bridge and race head in"
		+ " place: %d kept vertices above 1.50 m moved over 1 cm (largest %.1f cm)"
		% [neck_moved, largest * 100.0])
	expect(bridge_kept > 0, path + " wardrobe neckline keeps the shared neck bridge")

func independently_wardrobe_neckline_y(point: Vector3) -> float:
	var front := smoothstep(-0.040, 0.010, point.z)
	var centre := 1.0 - smoothstep(0.015, 0.100, absf(point.x))
	return lerpf(1.462, 1.450, front * centre)

func independently_inset_neckline_rim(source_vertices: PackedVector3Array,
		kept: PackedInt32Array, to_rig: Transform3D,
		fit: float) -> PackedVector3Array:
	var vertices := source_vertices.duplicate()
	if kept.is_empty():
		return vertices
	var point_ids := {}
	var welded := PackedInt32Array()
	welded.resize(vertices.size())
	for vertex: int in range(vertices.size()):
		var point := (to_rig * vertices[vertex]) / fit
		var key := Vector3i(roundi(point.x * 100000.0), roundi(point.y * 100000.0),
			roundi(point.z * 100000.0))
		if not point_ids.has(key):
			point_ids[key] = point_ids.size()
		welded[vertex] = int(point_ids[key])
	var edge_counts := {}
	for index: int in range(0, kept.size(), 3):
		for corners: Vector2i in [
				Vector2i(kept[index], kept[index + 1]),
				Vector2i(kept[index + 1], kept[index + 2]),
				Vector2i(kept[index + 2], kept[index])]:
			var first := welded[corners.x]
			var second := welded[corners.y]
			var edge := Vector2i(mini(first, second), maxi(first, second))
			edge_counts[edge] = int(edge_counts.get(edge, 0)) + 1
	var boundary_points := {}
	for edge_value: Variant in edge_counts:
		if int(edge_counts[edge_value]) != 1:
			continue
		var edge := edge_value as Vector2i
		boundary_points[edge.x] = true
		boundary_points[edge.y] = true
	var from_rig := to_rig.affine_inverse()
	for vertex: int in range(vertices.size()):
		if not boundary_points.has(welded[vertex]):
			continue
		var point := (to_rig * vertices[vertex]) / fit
		if (point.y <= TorsoBodyCover.NECK_RIM_MIN_Y
				or point.y >= TorsoBodyCover.NECK_RIM_MAX_Y
				or absf(point.x) >= TorsoBodyCover.NECK_RIM_HALF_WIDTH
				or point.z <= TorsoBodyCover.NECK_RIM_MIN_Z
				or point.z >= TorsoBodyCover.NECK_RIM_MAX_Z):
			continue
		point.y = independently_wardrobe_neckline_y(point)
		point.x *= TorsoBodyCover.NECK_RIM_INSET
		point.z *= TorsoBodyCover.NECK_RIM_INSET
		vertices[vertex] = from_rig * (point * fit)
	return vertices

## Vertex ids, per surface, of the small components wholly inside the collar
## band, welded by rest position across every surface of the mesh.
func independently_detached_neck_vertices(mesh: Mesh, to_rig: Transform3D,
		fit: float) -> Array[Dictionary]:
	var point_ids := {}
	var rest_points := PackedVector3Array()
	var welded: Array[PackedInt32Array] = []
	var sources: Array[PackedInt32Array] = []
	for surface: int in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var source: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if source.is_empty():
			for vertex: int in range(vertices.size()):
				source.append(vertex)
		var ids := PackedInt32Array()
		ids.resize(vertices.size())
		for vertex: int in range(vertices.size()):
			var point := (to_rig * vertices[vertex]) / fit
			var key := Vector3i(roundi(point.x * 100000.0), roundi(point.y * 100000.0),
				roundi(point.z * 100000.0))
			if not point_ids.has(key):
				point_ids[key] = rest_points.size()
				rest_points.append(point)
			ids[vertex] = int(point_ids[key])
		welded.append(ids)
		sources.append(source)
	var parents := PackedInt32Array()
	parents.resize(rest_points.size())
	for point_id: int in range(parents.size()):
		parents[point_id] = point_id
	for surface: int in range(sources.size()):
		for start: int in range(0, sources[surface].size(), 3):
			var first_root := independent_component_root(parents, welded[surface][sources[surface][start]])
			for corner: int in range(1, 3):
				var other_root := independent_component_root(parents,
					welded[surface][sources[surface][start + corner]])
				if first_root != other_root:
					parents[other_root] = first_root
	var face_counts := {}
	for surface: int in range(sources.size()):
		for start: int in range(0, sources[surface].size(), 3):
			var root := independent_component_root(parents, welded[surface][sources[surface][start]])
			face_counts[root] = int(face_counts.get(root, 0)) + 1
	var minima := {}
	var maxima := {}
	for point_id: int in range(rest_points.size()):
		var root := independent_component_root(parents, point_id)
		var point := rest_points[point_id]
		minima[root] = point if not minima.has(root) else (minima[root] as Vector3).min(point)
		maxima[root] = point if not maxima.has(root) else (maxima[root] as Vector3).max(point)
	var detached_roots := {}
	for root_value: Variant in face_counts:
		var root := int(root_value)
		var minimum := minima[root] as Vector3
		var maximum := maxima[root] as Vector3
		if (int(face_counts[root]) <= 128
				and minimum.y >= 1.460 and maximum.y <= 1.520
				and maxf(absf(minimum.x), absf(maximum.x)) <= 0.100
				and minimum.z >= -0.110 and maximum.z <= 0.040):
			detached_roots[root] = true
	var result: Array[Dictionary] = []
	for surface: int in range(welded.size()):
		var detached := {}
		for vertex: int in range(welded[surface].size()):
			if detached_roots.has(independent_component_root(parents, welded[surface][vertex])):
				detached[vertex] = true
		result.append(detached)
	return result

func independent_component_root(parents: PackedInt32Array, point_id: int) -> int:
	var root := point_id
	while parents[root] != root:
		root = parents[root]
	return root
