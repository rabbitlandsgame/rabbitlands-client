extends SceneTree
## Headless contract for the RL head (src/actors/rl_head/): the assets against
## their own extras and each other (every hair and beard fitted to the head
## shipped beside it), the appearance byte form, identity and expression kept
## apart through animation, the body cut through torso and cape changes, the
## importer's shape filter, LOD choice per quality, the hooks on the real
## ReplicatedActor3D - activated by tier for every Human at High, with the
## lab's `rl_head` override and the RL_HEADS=classic switch - the hair-motion
## budget and the open-headwear refit (RLHeadwearFit) against the shipped
## placement, which the shipped heads keep unless RL_HEADWEAR_FIT=shipped.
##
##   Godot --headless --path godot-client --script res://tests/test_rl_head.gd

const Stage := preload("res://prototypes/rl_heads/rl_head_stage.gd")

var _failures := 0
var _stage: Node3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	_check_assets()
	_check_encoding()
	_check_importer_filter()
	await _check_actor("female", "mira")
	await _check_actor("male", "rowan")
	await _check_body_cut_composition("female")
	await _check_removal("male")
	await _check_dev_switch()
	_check_lod_selection()
	await _check_hair_motion()
	await _check_headwear_fit()
	print("rl head: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(1 if _failures > 0 else 0)


func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS ", message)
	else:
		_failures += 1
		push_error("rl head: " + message)


# ---------------------------------------------------------------- assets

func _check_assets() -> void:
	for sex: String in ["female", "male"]:
		var info := RLHeadLibrary.head(sex)
		_expect(not info.is_empty(), "%s head module loads" % sex)
		if info.is_empty():
			continue
		var names: PackedStringArray = info["control_names"]
		_expect(names.size() >= 2, "%s head declares controls (%d)" % [sex, names.size()])
		var mesh := ((info["lods"] as Array)[0] as Array)[0]["mesh"] as Mesh
		var shapes := PackedStringArray()
		for index: int in mesh.get_blend_shape_count():
			shapes.append(str(mesh.get_blend_shape_name(index)))
		var missing := PackedStringArray()
		for control: String in names:
			for side: String in ["_p", "_n"]:
				if not shapes.has("id_" + control + side):
					missing.append("id_" + control + side)
		for expression: String in info["expressions"] as PackedStringArray:
			if not shapes.has(expression):
				missing.append(expression)
		_expect(missing.is_empty(), "%s blend shapes match rlHead extras %s" % [sex, missing])
		var stray := PackedStringArray()
		for shape: String in shapes:
			if not shape.begins_with("id_") and not shape.begins_with("ex_"):
				stray.append(shape)
		_expect(stray.is_empty(), "%s head carries only id_/ex_ shapes %s" % [sex, stray])
		var groups := {}
		for control: Dictionary in info["controls"] as Array:
			groups[str(control.get("group", ""))] = true
		_expect(not groups.has(""), "%s every control names a group" % sex)
		var cut: Dictionary = info["body_cut"]
		_expect(str(cut.get("body", "")) == "luminous_" + sex
			and cut.get("hiddenBodyTriangles") is Array, "%s body cut names its body and triangles" % sex)
		var eye: Dictionary = info["eye"]
		_expect(eye.has("right") and eye.has("left")
			and float((eye["right"] as Dictionary)["iris_radius"]) > 0.01,
			"%s iris centres measured off the eye surface" % sex)
	_check_asset_consistency()


## Hair and facial hair are fitted to one build of a head: each records the
## SHA-256 of the head GLB it was fitted to, which must be the head shipped for
## its sex. KNOWN_STALE lists an asset known to be fitted to an older head
## (reported, not failed, while its recorded hash is exactly that one; it must
## be rebuilt by the hair author - see docs/rl-head-prototype.md).
const KNOWN_STALE := {"hair/mira_bun.glb": "7dc7d99a549dbab2d06559ad1211a6a70db54d544da634bb0c91ea1ba0ebb966"}

func _check_asset_consistency() -> void:
	var heads := {}
	for sex: String in ["female", "male"]:
		heads[sex] = FileAccess.get_sha256(RLHeadLibrary.head_path(sex))
	for folder: Array in [["hair/", "rlHair"], ["beards/", "rlBeard"]]:
		for file: String in DirAccess.get_files_at(RLHeadLibrary.ROOT + folder[0]):
			if file.get_extension() != "glb":
				continue
			var relative: String = folder[0] + file
			var extras := RLHeadLibrary.asset_extras(RLHeadLibrary.ROOT + relative, folder[1])
			var sex := str(extras.get("sex", ""))
			var recorded := str(extras.get("headSHA256", ""))
			_expect(heads.has(sex), "%s names the head sex it was fitted to (%s)" % [relative, sex])
			if not heads.has(sex):
				continue
			if recorded != heads[sex] and KNOWN_STALE.get(relative, "") == recorded:
				print("KNOWN ISSUE %s was fitted to head %s, not the shipped %s head %s" % [relative,
					recorded.left(12), sex, str(heads[sex]).left(12)])
				continue
			_expect(recorded == heads[sex], "%s was fitted to the shipped %s head (%s against %s)" % [relative,
				sex, recorded.left(12), str(heads[sex]).left(12)])


# ---------------------------------------------------------------- encoding

func _check_encoding() -> void:
	var names := RLHeadLibrary.head("female").get("control_names", PackedStringArray()) as PackedStringArray
	for preset: String in RLHeadAppearance.preset_names():
		var face := RLHeadAppearance.from_preset(preset)
		_round_trip(face, names, "preset " + preset)
	var random := RandomNumberGenerator.new()
	random.seed = 4242
	for trial: int in 25:
		var face := RLHeadAppearance.new()
		face.sex = "male" if trial % 2 else "female"
		for control: String in names:
			if random.randf() < 0.7:
				face.set_control(control, random.randf_range(-1.0, 1.0))
		face.skin = Color(random.randf(), random.randf(), random.randf())
		face.eyes = Color(random.randf(), random.randf(), random.randf())
		face.hair_color = Color(random.randf(), random.randf(), random.randf())
		face.brow_color = Color(random.randf(), random.randf(), random.randf())
		face.lip_tint = Color(random.randf(), random.randf(), random.randf())
		face.freckles = random.randf()
		face.liner = random.randf()
		face.stubble = random.randf()
		face.hair = ["none", "mira_bun", "a_style_no_registry_lists"][trial % 3]
		face.beard = ["none", "stubble", "full_beard"][trial % 3]
		face.brow_style = float(random.randi_range(0, 12)) / 4.0
		face.brow_thickness = random.randf_range(-1.0, 1.0)
		face.liner_wing = random.randf()
		_round_trip(face, names, "random face %d" % trial)
	var face := RLHeadAppearance.from_preset("mira")
	var bytes := face.encode(names)
	var reordered := names.duplicate()
	reordered.reverse()
	_expect(RLHeadAppearance.decode(bytes, reordered) == null,
		"a different control set is refused, not misread")
	_expect(RLHeadAppearance.decode(bytes.slice(0, 9), names) == null, "cut-short bytes are refused")
	_expect(bytes.size() <= 32, "a face fits in %d bytes" % bytes.size())
	# Version 1 had no brow bytes: it still decodes, with the default brow.
	var control_bytes := (int(bytes[4]) + 1) / 2
	var version_one := bytes.slice(0, 5 + control_bytes + 12)
	version_one.append_array(bytes.slice(5 + control_bytes + 14))
	version_one[0] = 1
	var old := RLHeadAppearance.decode(version_one, names)
	_expect(old != null and old.hair == face.hair and old.beard == face.beard
		and old.brow_style == RLHeadAppearance.DEFAULT_BROW_STYLE and old.brow_thickness == 0.0
		and old.liner_wing == 0.0 and absf(old.freckles - face.freckles) <= 0.034,
		"version 1 bytes decode with the default brow and no wing")
	var mira := RLHeadAppearance.from_preset("mira")
	_expect(mira.brow_style == 0.0 and is_equal_approx(mira.brow_thickness, 0.2)
		and is_equal_approx(mira.liner_wing, 0.8) and str(mira.to_dict()["brow_style"]) == "arched",
		"presets name their brow style; the dictionary form writes the name")
	var blended := RLHeadAppearance.from_dict({"brow_style": 1.5})
	_expect(blended.brow_style == 1.5 and float(blended.to_dict()["brow_style"]) == 1.5,
		"a fractional brow style blends and round-trips as a number")
	var dictionary := face.to_dict()
	var back := RLHeadAppearance.from_dict(dictionary)
	_expect(back.to_dict() == dictionary, "the dictionary form round-trips exactly")
	var edited := RLHeadAppearance.from_dict({"preset": "mira", "controls": {"nose_width": 0.5}})
	_expect(edited.control("nose_width") == 0.5 and edited.hair == face.hair,
		"a dictionary overlays the preset it names")


func _round_trip(face: RLHeadAppearance, names: PackedStringArray, label: String) -> void:
	var bytes := face.encode(names)
	var decoded := RLHeadAppearance.decode(bytes, names)
	var ok := decoded != null and decoded.encode(names) == bytes and decoded.sex == face.sex \
		and decoded.hair == face.hair and decoded.beard == face.beard
	if ok:
		for control: String in names:
			ok = ok and absf(decoded.control(control) - face.control(control)) <= 0.5 / 7.0 + 0.0001
		for pair: Array in [[decoded.skin, face.skin], [decoded.eyes, face.eyes],
				[decoded.lip_tint, face.lip_tint]]:
			var a: Color = pair[0]
			var b: Color = pair[1]
			ok = ok and absf(a.r - b.r) <= 0.017 and absf(a.g - b.g) <= 0.009 and absf(a.b - b.b) <= 0.017
		ok = ok and absf(decoded.freckles - face.freckles) <= 0.034
		ok = ok and absf(decoded.brow_style - face.brow_style) <= 0.125 \
			and absf(decoded.brow_thickness - face.brow_thickness) <= 0.5 / 7.0 + 0.0001 \
			and absf(decoded.liner_wing - face.liner_wing) <= 0.034
	_expect(ok, "byte form round-trips: " + label)


# ---------------------------------------------------------------- importer

func _check_importer_filter() -> void:
	var owner := Node3D.new()
	var mesh_node := MeshInstance3D.new()
	mesh_node.name = "Probe"
	var mesh := ArrayMesh.new()
	for shape: String in ["id_nose_width_p", "ex_blink_l", "Cape_Clearance"]:
		mesh.add_blend_shape(shape)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var blend := []
	for shape: int in 3:
		var shape_arrays := []
		shape_arrays.resize(Mesh.ARRAY_MAX)
		shape_arrays[Mesh.ARRAY_VERTEX] = arrays[Mesh.ARRAY_VERTEX]
		blend.append(shape_arrays)
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, blend)
	mesh_node.mesh = mesh
	owner.add_child(mesh_node)
	var defaults := NativeAnimationImporter._blend_shape_defaults(owner)
	_expect(defaults.keys() == ["Probe:Cape_Clearance"],
		"the importer keeps RESET defaults for correctives and skips id_/ex_ shapes %s" % [defaults.keys()])
	owner.free()


# ---------------------------------------------------------------- actor

func _rl_actor(sex: String, value: Variant, visuals: Dictionary = {}) -> ReplicatedActor3D:
	return Stage.spawn(_stage, sex, {"rl_head": value}, visuals)


func _shape_values(nodes: Array[MeshInstance3D], prefix: String) -> Dictionary:
	var values := {}
	for mesh_node: MeshInstance3D in nodes:
		for index: int in mesh_node.mesh.get_blend_shape_count():
			var shape := str(mesh_node.mesh.get_blend_shape_name(index))
			if shape.begins_with(prefix):
				values["%s:%s" % [mesh_node.name, shape]] = mesh_node.get_blend_shape_value(index)
	return values


func _check_actor(sex: String, preset: String) -> void:
	var actor := _rl_actor(sex, preset)
	await process_frame
	var rig := actor.rl_head()
	_expect(rig != null, "%s: appearance.rl_head builds an RL head" % preset)
	if rig == null:
		actor.queue_free()
		return
	_expect(actor.animation_player != null and actor.animation_player.has_animation("Walk"),
		"%s: the animation import ran" % preset)
	var library := actor.animation_player.get_animation_library("")
	var reset := library.get_animation(&"RESET")
	var leaked := 0
	for clip: StringName in library.get_animation_list():
		var animation := library.get_animation(clip)
		for track: int in animation.get_track_count():
			var path := str(animation.track_get_path(track))
			if path.contains(":id_") or path.contains(":ex_"):
				leaked += 1
	_expect(reset != null and leaked == 0, "%s: no clip carries an id_/ex_ track" % preset)
	var native := actor.get_node("NativeModel") as Node3D
	for hidden: String in ["eyes", "eyebrows", "scalp"]:
		var node := native.find_child(hidden, true, false) as MeshInstance3D
		_expect(node != null and not node.visible, "%s: body %s hidden" % [preset, hidden])
	var legacy_hair := 0
	for child: Node in actor.get_skeleton().get_children():
		if child.name.begins_with("AppearanceHair_") and child.name != RLHeadRig.HAIR_NODE_NAME \
				and (child as Node3D).visible:
			legacy_hair += 1
	_expect(legacy_hair == 0, "%s: no legacy hairstyle shows under the RL head" % preset)
	var body := native.find_child("body", true, false) as MeshInstance3D
	var cut := RLHeadBodyCut.describe(body.get_meta(&"uncovered_body_mesh") as Mesh,
		str(rig.head_info()["path"]))
	_expect(str(cut.get("method", "")) == "list",
		"%s: the authored triangle list was verified and used %s" % [preset, cut])
	var patch_ok := false
	var head_node: MeshInstance3D = rig.identity_targets()[0]
	for surface: int in head_node.mesh.get_surface_count():
		var imported := head_node.mesh.surface_get_material(surface)
		if imported != null and imported.resource_name == RLHeadLibrary.BODY_PATCH_MATERIAL:
			patch_ok = head_node.get_surface_override_material(surface) == body.get_active_material(0)
	_expect(patch_ok, "%s: the body patch draws with the body's own material" % preset)
	# Identity and expression stay apart, also through animation.
	var names: PackedStringArray = rig.head_info()["control_names"]
	rig.set_control(names[0], 0.8)
	rig.set_control(names[1], -0.6)
	var identity := _shape_values(rig.identity_targets(), "id_")
	_expect(is_equal_approx(float(identity.get("%s:id_%s_p" % [head_node.name, names[0]], 0.0)), 0.8)
		and is_equal_approx(float(identity.get("%s:id_%s_n" % [head_node.name, names[1]], 0.0)), 0.6),
		"%s: controls drive their _p/_n shapes" % preset)
	var expression := rig.expression()
	expression.always_update = true
	expression.set_expression("smile", 1.0, 0.0)
	expression.blink()
	expression.advance(0.1)
	_expect(_shape_values(rig.identity_targets(), "id_") == identity,
		"%s: expressions and blinks leave every id_ weight alone" % preset)
	var smile := _shape_values(rig.expression_targets(), "ex_")
	_expect(float(smile.get("%s:ex_smile" % head_node.name, 0.0)) > 0.99
		and float(smile.get("%s:ex_blink_l" % head_node.name, 0.0)) > 0.3,
		"%s: smile and blink weights written" % preset)
	rig.set_control(names[2], 0.4)
	_expect(_shape_values(rig.expression_targets(), "ex_") == smile,
		"%s: identity changes leave every ex_ weight alone" % preset)
	identity = _shape_values(rig.identity_targets(), "id_")
	expression.set_process(false)
	actor.animation_player.play("Walk")
	for step: int in 6:
		actor.animation_player.advance(0.1)
		await process_frame
	_expect(_shape_values(rig.identity_targets(), "id_") == identity
		and _shape_values(rig.expression_targets(), "ex_") == smile,
		"%s: animation playback leaves id_ and ex_ weights unchanged" % preset)
	_expect(PackedStringArray(expression.available_shapes()).has("ex_blink_r"),
		"%s: expression shapes found on the head" % preset)
	# A brow style, thickness or wing is one instance uniform: nothing else on
	# the head changes, no mesh is rebuilt and no blend shape moves.
	for change: Array in [["brow_style", 1.0], ["brow_thickness", -0.7], ["liner_wing", 0.9]]:
		var before := _instance_values(head_node)
		var shapes_before := _shape_values(rig.identity_targets(), "")
		var nodes_before := rig.identity_targets()
		var face := rig.appearance.duplicate_appearance()
		var field: String = change[0]
		face.set(field, fposmod(float(face.get(field)) + float(change[1]), 3.0) if field == "brow_style"
			else float(change[1]))
		actor.apply_appearance_variants({"rl_head": face.to_dict()})
		var after := _instance_values(head_node)
		var changed: Array = []
		for uniform_name: String in after:
			if after[uniform_name] != before[uniform_name]:
				changed.append(uniform_name)
		_expect(changed == [field] and is_equal_approx(float(after[field]), float(face.get(field)))
			and _shape_values(rig.identity_targets(), "") == shapes_before
			and rig.identity_targets() == nodes_before,
			"%s: changing %s touches only that uniform %s" % [preset, field, changed])
	var hair_style := rig.appearance.hair
	if FileAccess.file_exists(RLHeadLibrary.hair_path(hair_style)):
		var hair_nodes: Array = rig.mesh_nodes()["hair"]
		_expect(not hair_nodes.is_empty() and rig.hair_motion() != null and rig.hair_motion().has_springs(),
			"%s: hairstyle %s drawn with its springs" % [preset, hair_style])
		var attachment := actor.get_skeleton().get_node_or_null(RLHeadRig.HAIR_NODE_NAME)
		actor.apply_equipment_visuals({3: 134})
		await process_frame
		_expect(attachment != null and not (attachment as Node3D).visible,
			"%s: a hair-covering helm hides the RL hairstyle" % preset)
		actor.apply_equipment_visuals({})
		await process_frame
		_expect((attachment as Node3D).visible, "%s: taking the helm off shows it again" % preset)
	actor.queue_free()
	await process_frame


func _instance_values(mesh_node: MeshInstance3D) -> Dictionary:
	var values := {}
	for uniform_name: String in RLHeadRig.INSTANCE_UNIFORMS:
		values[uniform_name] = mesh_node.get_instance_shader_parameter(uniform_name)
	return values


func _hidden_triplets(original: Mesh, head_path: String) -> Dictionary:
	var plan: Dictionary = RLHeadBodyCut._plans.get("%d|%s" % [original.get_instance_id(), head_path], {})
	return plan.get("hidden", {}) as Dictionary


func _cut_is_clean(mesh: Mesh, hidden: Dictionary) -> bool:
	var arrays := mesh.surface_get_arrays(0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	for index: int in range(0, indices.size(), 3):
		if hidden.has(RLHeadBodyCut._triplet(indices[index], indices[index + 1], indices[index + 2])):
			return false
	return true


## A body mesh before Human body refinement (which compacts its arrays).
func _unrefined(body: MeshInstance3D) -> Mesh:
	if body.has_meta(CharacterProportions.BODY_RESULT_META) \
			and body.mesh == body.get_meta(CharacterProportions.BODY_RESULT_META):
		return body.get_meta(CharacterProportions.BODY_SOURCE_META) as Mesh
	return body.mesh


func _check_body_cut_composition(sex: String) -> void:
	var actor := _rl_actor(sex, "mira" if sex == "female" else "rowan")
	# The plain actor below High: develop's head, the same shared body.
	var plain := Stage.spawn(_stage, sex, {}, {}, ActorRenderQuality.Quality.MEDIUM, 9301)
	await process_frame
	var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var plain_body := plain.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
	var original := body.get_meta(&"uncovered_body_mesh") as Mesh
	_expect(original == _unrefined(plain_body), "%s: the cut starts from the shared imported body" % sex)
	_expect(_unrefined(body) == body.get_meta(RLHeadBodyCut.CUT_META),
		"%s: body refinement fits the cut mesh, not the other way round" % sex)
	var hidden := _hidden_triplets(original, str(actor.rl_head().head_info()["path"]))
	var bare_cut := _unrefined(body)
	var bare_count := RLHeadRig.mesh_triangles(bare_cut)
	_expect(bare_count == RLHeadRig.mesh_triangles(original) - hidden.size() and _cut_is_clean(bare_cut, hidden),
		"%s: bare body loses exactly the listed triangles (%d)" % [sex, hidden.size()])
	var orders: Array = [
		[{5: Stage.TORSO}, {5: Stage.TORSO, 2: Stage.CAPE}, {2: Stage.CAPE}, {}],
		[{2: Stage.CAPE}, {2: Stage.CAPE, 5: Stage.TORSO}, {5: Stage.TORSO}, {}],
		[{5: Stage.TORSO, 2: Stage.CAPE, 3: 134}, {3: 134}, {}],
	]
	for order: Array in orders:
		for visuals: Dictionary in order:
			actor.apply_equipment_visuals(visuals)
			plain.apply_equipment_visuals(visuals)
			await process_frame
			var torso_worn := visuals.has(5)
			var plain_mesh := _unrefined(plain_body)
			var source := body.get_meta(RLHeadBodyCut.SOURCE_META) as Mesh
			_expect(_cut_is_clean(_unrefined(body), hidden) and source == plain_mesh,
				"%s %s: head cut taken from the same torso cover a plain actor wears" % [sex, visuals])
			if not torso_worn:
				_expect(_unrefined(body) == bare_cut, "%s %s: the bare head cut comes back" % [sex, visuals])
			var scalp := actor.get_node("NativeModel").find_child("scalp", true, false) as MeshInstance3D
			_expect(not scalp.visible, "%s %s: the scalp stays hidden" % [sex, visuals])
	var plain_cover := plain_body.get_meta(&"uncovered_body_mesh", _unrefined(plain_body)) as Mesh
	_expect(plain_cover == original, "%s: TorsoBodyCover still restores the untouched body" % sex)
	actor.queue_free()
	plain.queue_free()
	await process_frame


func _check_removal(sex: String) -> void:
	var actor := _rl_actor(sex, "rowan", {5: Stage.TORSO})
	await process_frame
	var native := actor.get_node("NativeModel") as Node3D
	var body := native.find_child("body", true, false) as MeshInstance3D
	var with_head := RLHeadRig.mesh_triangles(body.mesh)
	# Without the lab's override a High Human draws its own derived RL head...
	actor.apply_appearance_variants({"skin": 2, "hair": 1})
	await process_frame
	_expect(actor.rl_head() != null and actor.rl_head().appearance.preset.is_empty(),
		"%s: dropping rl_head at High draws the face the appearance asks for" % sex)
	# ...and below High none: develop's own head.
	actor.apply_render_quality(ActorRenderQuality.Quality.MEDIUM, false)
	await process_frame
	_expect(actor.rl_head() == null and RLHeadRig.find_on(actor.get_skeleton()) == null,
		"%s: switching to Medium removes the rig" % sex)
	_expect(not body.has_meta(RLHeadBodyCut.CUT_META)
		and RLHeadRig.mesh_triangles(body.mesh) > with_head,
		"%s: the body gets its head back under the torso cover" % sex)
	var eyes := native.find_child("eyes", true, false) as MeshInstance3D
	_expect(eyes.visible and not eyes.has_meta(ReplicatedActor3D.RL_HEAD_SHOWN_META),
		"%s: the body's own eyes return" % sex)
	var legacy := 0
	for child: Node in actor.get_skeleton().get_children():
		if child.name.begins_with("AppearanceHair_"):
			legacy += 1
	_expect(legacy == 1, "%s: the legacy hairstyle returns" % sex)
	actor.apply_render_quality(ActorRenderQuality.Quality.HIGH, false)
	await process_frame
	_expect(actor.rl_head() != null and body.has_meta(RLHeadBodyCut.CUT_META),
		"%s: back at High the RL head is put back on the live actor" % sex)
	actor.queue_free()
	await process_frame


func _check_dev_switch() -> void:
	# The default: every Human at High draws the RL head; Medium and Low do not.
	var female := Stage.spawn(_stage, "female", {"skin": 1})
	var male := Stage.spawn(_stage, "male", {"skin": 1})
	var medium := Stage.spawn(_stage, "female", {"skin": 1}, {}, ActorRenderQuality.Quality.MEDIUM, 9302)
	await process_frame
	_expect(female.rl_head() != null and female.rl_head().appearance.sex == "female",
		"a luminous female at High draws the RL head")
	_expect(male.rl_head() != null and male.rl_head().appearance.sex == "male",
		"a luminous male at High draws the male RL head")
	_expect(medium.rl_head() == null, "a luminous female at Medium keeps develop's head")
	# Headless reports the Forward+ method; the Compatibility renderer keeps
	# develop's High head unless RL_HEADS=all.
	_expect(ReplicatedActor3D.rl_heads_renderer_supported()
		== (RenderingServer.get_current_rendering_method() != "gl_compatibility"),
		"the RL head is drawn in every renderer but Compatibility")
	female.queue_free()
	male.queue_free()
	medium.queue_free()
	# RL_HEADS=classic keeps develop's classic High head, the lab override too.
	OS.set_environment("RL_HEADS", "classic")
	ReplicatedActor3D.reload_rl_heads_switch()
	var plain := Stage.spawn(_stage, "female", {"skin": 1})
	var lab := _rl_actor("female", "mira")
	await process_frame
	_expect(plain.rl_head() == null and lab.rl_head() == null, "RL_HEADS=classic builds no RL head")
	plain.queue_free()
	lab.queue_free()
	OS.set_environment("RL_HEADS", "")
	ReplicatedActor3D.reload_rl_heads_switch()
	# The lab's empty override means no RL head, at any quality.
	var bare := Stage.spawn(_stage, "female", {"skin": 1, "rl_head": ""})
	await process_frame
	_expect(bare.rl_head() == null, "an empty rl_head override builds no RL head")
	bare.queue_free()
	await process_frame


# ---------------------------------------------------------------- LOD

func _check_lod_selection() -> void:
	var skeleton := Skeleton3D.new()
	for bone: String in ["spine_03", "neck_01", "Head"]:
		skeleton.add_bone(bone)
	_stage.add_child(skeleton)
	var info := RLHeadLibrary.head("female")
	var piece: Dictionary = ((info["lods"] as Array)[0] as Array)[0]
	var three_levels: Array = [[piece], [piece], [piece]]
	var expected := {ActorRenderQuality.Quality.HIGH: 3, ActorRenderQuality.Quality.MEDIUM: 2,
		ActorRenderQuality.Quality.LOW: 1}
	for quality: int in expected:
		var rig := RLHeadRig.new()
		rig.quality = quality
		rig.appearance = RLHeadAppearance.from_preset("mira")
		rig._skeleton = skeleton
		skeleton.add_child(rig)
		var levels: Array = rig._instance_levels(three_levels, "Probe", "")
		_expect(levels.size() == expected[quality],
			"%s instances %d of 3 LOD levels" % [ActorRenderQuality.quality_name(quality), levels.size()])
		rig._head_lods = levels
		var name := ActorRenderQuality.quality_name(quality)
		var visible_at := func(distance: float) -> int:
			rig.update_lod(distance)
			for index: int in levels.size():
				if ((levels[index] as Array)[0] as MeshInstance3D).visible:
					return index
			return -1
		var bands: Array = RLHeadRig.LOD_DISTANCES[quality]
		if bands.is_empty():
			_expect(visible_at.call(2.0) == 0 and visible_at.call(60.0) == 0,
				"%s draws its one level at every distance" % name)
		else:
			var first_edge := float(bands[0])
			_expect(visible_at.call(2.0) == 0, "%s shows its first level up close" % name)
			_expect(visible_at.call(first_edge + 0.5) == 0,
				"%s holds the near level inside the hysteresis" % name)
			_expect(visible_at.call(first_edge + 3.0) == 1, "%s hands over past %.0f m" % [name, first_edge])
			_expect(visible_at.call(first_edge - 0.5) == 1 and visible_at.call(2.0) == 0,
				"%s comes back only past the margin" % name)
			_expect(visible_at.call(80.0) == levels.size() - 1, "%s shows its last level far away" % name)
			var shown := 0
			for level: Array in levels:
				shown += 1 if (level[0] as MeshInstance3D).visible else 0
			_expect(shown == 1, "%s keeps exactly one level visible" % name)
		var one_level: Array = rig._instance_levels([[piece]], "Single", "")
		_expect(one_level.size() == 1 and ((one_level[0] as Array)[0] as MeshInstance3D).visible,
			"%s draws a single-mesh asset" % ActorRenderQuality.quality_name(quality))
		rig.free()
	skeleton.free()


# ---------------------------------------------------------------- hair motion

func _check_hair_motion() -> void:
	_expect(ClassDB.class_exists("SpringBoneSimulator3D")
		and ClassDB.class_exists("SpringBoneCollisionSphere3D")
		and ClassDB.class_exists("SpringBoneCollisionCapsule3D"),
		"Godot provides the spring-bone simulator and its collisions")
	var camera := Camera3D.new()
	_stage.add_child(camera)
	camera.current = true
	var members: Array[RLHairMotion] = []
	for index: int in 11:
		var holder := Node3D.new()
		holder.position = Vector3(float(index) * 1.5, 0.0, 0.0)
		_stage.add_child(holder)
		var skeleton := Skeleton3D.new()
		var root_bone := skeleton.add_bone("hair_root")
		var previous := root_bone
		for joint: int in 3:
			var bone := skeleton.add_bone("lock_0_%d" % joint)
			skeleton.set_bone_parent(bone, previous)
			skeleton.set_bone_rest(bone, Transform3D(Basis.IDENTITY, Vector3(0.0, -0.05, 0.0)))
			skeleton.reset_bone_pose(bone)
			previous = bone
		holder.add_child(skeleton)
		var motion := RLHairMotion.new()
		holder.add_child(motion)
		var built := motion.configure(skeleton, {"springs": [{"bones": ["lock_0_0", "lock_0_1", "lock_0_2"],
			"stiffness": 1.0, "damping": 0.4, "gravity": 0.5, "radius": 0.01}],
			"collisions": [{"shape": "sphere", "offset": [0, 0.05, 0], "radius": 0.09},
				{"shape": "capsule", "offset": [0, 0, 0], "radius": 0.05, "height": 0.2}]})
		if index == 0:
			_expect(built and motion.has_springs(), "springs built from rlHair extras")
		members.append(motion)
	camera.global_position = Vector3(0.0, 0.0, 2.0)
	await process_frame
	await process_frame
	var running := 0
	var far_running := false
	for motion: RLHairMotion in members:
		if motion.is_running():
			running += 1
			far_running = far_running or (motion.get_parent() as Node3D).global_position.x > 11.9
	_expect(running == RLHairMotion.MAX_ACTIVE, "at most %d actors swing their hair (%d)"
		% [RLHairMotion.MAX_ACTIVE, running])
	_expect(not far_running, "hair beyond %.0f m rests" % RLHairMotion.RANGE_METRES)
	# The springs really move bones: swing the nearest head sideways and the
	# lock's tip leaves its rest pose. A modifier's pose holds only while the
	# skeleton is being updated, so it is read when the simulator reports.
	var swung := members[0]
	var swung_skeleton := swung.get_parent().get_child(0) as Skeleton3D
	var tip := swung_skeleton.find_bone("lock_0_2")
	var holder := swung.get_parent() as Node3D
	var furthest := [0.0]
	swung._simulator.modification_processed.connect(func() -> void:
		furthest[0] = maxf(float(furthest[0]), swung_skeleton.get_bone_global_pose(tip).origin.distance_to(
			swung_skeleton.get_bone_global_rest(tip).origin)))
	for step: int in 6:
		holder.position.x += 0.25
		await process_frame
	_expect(swung.is_running() and float(furthest[0]) > 0.001,
		"SpringBoneSimulator3D swings a running lock (%.1f mm off rest)" % (float(furthest[0]) * 1000.0))
	for motion: RLHairMotion in members:
		motion.enabled = false
	await process_frame
	var still := true
	for motion: RLHairMotion in members:
		still = still and not motion.is_running()
	_expect(still, "switching motion off (below HIGH, or the lab) stops every chain")
	for motion: RLHairMotion in members:
		motion.get_parent().queue_free()
	camera.queue_free()
	await process_frame


# ---------------------------------------------------------------- headwear

## A plain actor of another race, built as the stage builds a luminous one.
func _race_actor(slug: String, visuals: Dictionary) -> ReplicatedActor3D:
	var config: Dictionary = ((Stage.data("models").get("models", {}) as Dictionary).get(slug, {})
		as Dictionary).duplicate(true)
	var actor := ReplicatedActor3D.new()
	_stage.add_child(actor)
	actor.configure({"actor_id": 9400, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": {"skin": 1, "hair": 0}, "equipment_visuals": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), config, Stage.data("animation"),
		Stage.data("equipment"))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.apply_equipment_visuals(visuals)
	return actor


## The head piece's nodes on an actor: the BoneAttachment3D and any refitted
## skinned meshes.
func _head_piece(actor: ReplicatedActor3D) -> Dictionary:
	var attachment: BoneAttachment3D = null
	var refits: Array[MeshInstance3D] = []
	for child: Node in actor.get_skeleton().get_children():
		if child.is_queued_for_deletion():
			continue
		# By role, not name: a part rebuilt while the old one awaits its free
		# gets an engine-made name.
		if child is BoneAttachment3D and child.has_meta("native_equipment") \
				and (child as BoneAttachment3D).bone_name == "Head":
			attachment = child as BoneAttachment3D
		elif child is MeshInstance3D and child.has_meta(&"rl_headwear_fit"):
			refits.append(child as MeshInstance3D)
	return {"attachment": attachment, "refits": refits}


## Largest model-space extent of the piece as drawn at rest.
func _piece_extent(actor: ReplicatedActor3D) -> float:
	var nodes := _head_piece(actor)
	var box := AABB()
	var first := true
	var meshes: Array[MeshInstance3D] = []
	var transforms: Array[Transform3D] = []
	var skeleton := actor.get_skeleton()
	var head_rest := skeleton.get_bone_global_rest(skeleton.find_bone("Head"))
	if not (nodes["refits"] as Array).is_empty():
		for mesh_node: MeshInstance3D in nodes["refits"]:
			meshes.append(mesh_node)
			transforms.append(Transform3D.IDENTITY)
	elif nodes["attachment"] != null:
		for found: Node in (nodes["attachment"] as Node).find_children("*", "MeshInstance3D", true, false):
			var mesh_node := found as MeshInstance3D
			meshes.append(mesh_node)
			var holder := mesh_node.get_parent() as Node3D
			transforms.append(head_rest * holder.transform * mesh_node.transform)
	for index: int in meshes.size():
		for surface: int in meshes[index].mesh.get_surface_count():
			for p: Vector3 in meshes[index].mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]:
				var q := transforms[index] * p
				if first:
					box = AABB(q, Vector3.ZERO)
					first = false
				else:
					box = box.expand(q)
	return maxf(box.size.x, box.size.z)


func _check_headwear_fit() -> void:
	var data := RLHeadwearFit.data()
	_expect(not data.is_empty(), "headwear fit data loads")
	for visual: int in [111, 112, 114, 119]:
		_expect(RLHeadwearFit.has_piece(visual), "open piece 3:%d has a fit" % visual)
	for visual: int in [134, 159, 150, 170]:
		_expect(not RLHeadwearFit.has_piece(visual), "closed piece 3:%d keeps its shipped fit" % visual)
	var circlet := RLHeadwearFit.piece(111)
	_expect(RLHeadwearFit.fit_name(circlet, "female", "") == "female", "bald fit chosen with no hair")
	_expect(RLHeadwearFit.fit_name(circlet, "female", "mira_bun") == "female/mira_bun",
		"a hairstyle's own fit is chosen")
	_expect(RLHeadwearFit.fit_name(circlet, "female", "no_such_style") == "female/*",
		"an unfitted hairstyle takes the fallback fit")
	_expect(RLHeadwearFit.fit_name(circlet, "luminous_female", "") == "luminous_female",
		"the shipped luminous head has a bald fit of its own")
	_expect(not RLHeadwearFit.fits_shipped_body("luminous_male")
		and not RLHeadwearFit.fits_shipped_body("luminous_female"),
		"shipped heads keep the shipped placement by default (D8)")
	# another race's head wears its own variant exactly as before
	var race := _race_actor("greyhaven_female", {3: 111, 5: Stage.TORSO})
	await process_frame
	var plain := _head_piece(race)
	_expect(plain["attachment"] != null and (plain["refits"] as Array).is_empty()
		and (plain["attachment"] as Node).get_child_count() == 1,
		"a greyhaven head wears the circlet exactly as before")
	race.queue_free()
	# a Human below High (no RL head) wears it as shipped
	var medium := Stage.spawn(_stage, "female", {"skin": 1, "hair": 0}, {3: 111, 5: Stage.TORSO},
		ActorRenderQuality.Quality.MEDIUM, 9303)
	await process_frame
	var shipped_piece := _head_piece(medium)
	_expect(shipped_piece["attachment"] != null and (shipped_piece["refits"] as Array).is_empty()
		and (shipped_piece["attachment"] as Node).get_child_count() == 1,
		"a luminous head below High wears the circlet as shipped")
	medium.queue_free()
	# RL_HEADWEAR_FIT=shipped turns the shipped-head fits on (owner decision pending)
	OS.set_environment("RL_HEADWEAR_FIT", "shipped")
	RLHeadwearFit.reload()
	_expect(RLHeadwearFit.fits_shipped_body("luminous_male")
		and not RLHeadwearFit.fits_shipped_body("greyhaven_female"),
		"RL_HEADWEAR_FIT=shipped: luminous refitted, other races left as shipped")
	var legacy := Stage.spawn(_stage, "female", {"skin": 1, "hair": 0}, {3: 111, 5: Stage.TORSO},
		ActorRenderQuality.Quality.MEDIUM, 9304)
	await process_frame
	var shipped := _head_piece(legacy)
	var shipped_key := str((shipped["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if shipped["attachment"] != null else ""
	_expect(not (shipped["refits"] as Array).is_empty() and shipped_key.begins_with("111|luminous_female||"),
		"the shipped luminous head takes its own circlet fit when switched on (%s)" % shipped_key)
	legacy.apply_appearance_variants({"skin": 1, "hair": 2})
	await process_frame
	var haired := _head_piece(legacy)
	var haired_key := str((haired["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if haired["attachment"] != null else ""
	_expect(haired_key.begins_with("111|luminous_female|luminous_female_"),
		"a shipped hairstyle refits the circlet over it (%s)" % haired_key)
	legacy.queue_free()
	OS.set_environment("RL_HEADWEAR_FIT", "")
	RLHeadwearFit.reload()
	var shipped_extent := 0.327  # the human_female variant as shipped, model space
	# an RL head refits it
	var actor := _rl_actor("female", "mira", {3: 111, 5: Stage.TORSO})
	await process_frame
	var fitted := _head_piece(actor)
	var refits: Array = fitted["refits"]
	_expect(refits.size() >= 1, "mira: the circlet is rebuilt for the RL head")
	_expect(fitted["attachment"] != null and (fitted["attachment"] as Node).get_child_count() == 0,
		"mira: the shipped placement is not drawn as well")
	var fitted_extent := _piece_extent(actor)
	_expect(fitted_extent < shipped_extent * 0.85,
		"mira: the circlet is smaller (%.3f m against %.3f m shipped)" % [fitted_extent, shipped_extent])
	var trail_vertices := 0
	for mesh_node: MeshInstance3D in refits:
		_expect(mesh_node.skin != null and mesh_node.skin.get_bind_count() == RLHeadwearFit.BONES.size(),
			"mira: %s is skinned to the head and shoulders" % mesh_node.name)
		var arrays := mesh_node.mesh.surface_get_arrays(0)
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		for index: int in range(0, weights.size(), 4):
			if weights[index] < 0.99:
				trail_vertices += 1
	_expect(trail_vertices > 50, "mira: the ribbons ride the neck and shoulders (%d vertices)" % trail_vertices)
	var key := str((fitted["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, ""))
	_expect(key.contains("mira_bun"), "mira: fitted over her hair (%s)" % key)
	# a closed helm on the RL head is the shipped one
	actor.apply_equipment_visuals({3: 134, 5: Stage.TORSO})
	await process_frame
	var helm := _head_piece(actor)
	_expect((helm["refits"] as Array).is_empty() and helm["attachment"] != null
		and (helm["attachment"] as Node).get_child_count() == 1,
		"mira: a closed helm keeps its shipped placement")
	# back to the circlet, then bald: the fit follows the hair
	actor.apply_equipment_visuals({3: 111, 5: Stage.TORSO})
	await process_frame
	var face := actor.rl_head().appearance.duplicate_appearance()
	face.hair = RLHeadAppearance.NONE
	actor.apply_appearance_variants({"rl_head": face.to_dict()})
	await process_frame
	var bald := _head_piece(actor)
	var bald_key := str((bald["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if bald["attachment"] != null else ""
	_expect(not (bald["refits"] as Array).is_empty() and bald_key.begins_with("111|female||"),
		"mira bald: the circlet is refitted to the bare head (%s)" % bald_key)
	# a game hairstyle under the RL head: the fit follows it
	actor.apply_appearance_variants({"skin": 1, "hair": AppearanceVariants.pack_hair(2, 4)})
	await process_frame
	var long_hair := _head_piece(actor)
	var long_key := str((long_hair["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if long_hair["attachment"] != null else ""
	_expect(not (long_hair["refits"] as Array).is_empty() and long_key.begins_with("111|female|legacy:long|"),
		"a game hairstyle under the RL head refits the circlet over it (%s)" % long_key)
	# below High the shipped head wears the shipped circlet again
	actor.apply_render_quality(ActorRenderQuality.Quality.MEDIUM, false)
	await process_frame
	var restored := _head_piece(actor)
	var restored_key := str((restored["attachment"] as Node).get_meta(ReplicatedActor3D.RL_HEADWEAR_META, "")) \
		if restored["attachment"] != null else ""
	_expect((restored["refits"] as Array).is_empty() and restored_key.is_empty()
		and restored["attachment"] != null and (restored["attachment"] as Node).get_child_count() == 1,
		"without the RL head the circlet is the shipped one (%s)" % restored_key)
	actor.queue_free()
	await process_frame
