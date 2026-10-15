class_name CombatPresentation3D
extends Node3D
## Visual cues use the AnimationPlayer clock, including speed changes and LOD.
## Skeletal attachments update after the skeleton evaluates, avoiding hand lag.
var actor: ReplicatedActor3D
var bow: RangerBow3D
var effects_enabled := true
var _mesh := ImmediateMesh.new()
var _material := CombatEffectMesh.material()
var _trail: Array[Vector3] = []
var _last_action: StringName
var _last_time := -1.0
var _hand_l := -1
var _hand_r := -1
var _equipped_bow := false
var _spell_color := Color.TRANSPARENT
var _spell_action: StringName
var spell_power := 1
var _power_action: StringName

func set_spell_palette(color: Color, power := 1) -> void:
	_spell_color = color
	_spell_action = actor.current_action
	set_spell_power(power)

func set_spell_power(power: int) -> void:
	spell_power = clampi(power, 1, 10)
	_power_action = actor.current_action
	update_pose()

func configure(owner_actor: ReplicatedActor3D) -> void:
	actor = owner_actor
	name = "CombatPresentation"
	var skeleton := actor.get_skeleton()
	_hand_l = skeleton.find_bone("hand_l")
	_hand_r = skeleton.find_bone("hand_r")
	var mesh_node := MeshInstance3D.new()
	mesh_node.name = "ActionEffects"
	mesh_node.mesh = _mesh
	mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mesh_node)
	skeleton.skeleton_updated.connect(update_pose)

func set_equipped_bow(path: String) -> void:
	_equipped_bow = not path.is_empty()
	if not _equipped_bow:
		# Unequipping while already idle used to leave the previous class bow
		# visible: update_pose's idle fast path only hid it when the action also
		# changed. Hide it as part of the equipment transition itself so class
		# previews and live equipment swaps cannot retain a stale ranged prop.
		if bow != null:
			bow.hide()
		if actor != null:
			actor.set_hand_props_visible(true)
		return
	_ensure_bow()
	bow.set_asset(path)
	update_pose()

func _ensure_bow() -> void:
	if bow == null:
		bow = RangerBow3D.new()
		add_child(bow)

func hand_position(index: int) -> Vector3:
	var skeleton := actor.get_skeleton()
	return (skeleton.global_transform * skeleton.get_bone_global_pose(index)) * Vector3(0, 0.035, 0)

## The fist bore uses the same mirrored fit as a sword in the left hand.
## Its frame follows the wrist while relaxed; aiming still uses both hands.
func carried_bow_grip() -> Transform3D:
	var skeleton := actor.get_skeleton()
	var rest := skeleton.get_bone_global_rest(_hand_l)
	var fit := actor.rig_fit_scale("legacy")
	var socket := Transform3D(Basis.from_euler(Vector3(deg_to_rad(80.0), 0, 0)),
		rest.origin + Vector3(0.0757, -0.05, 0) * fit)
	return skeleton.global_transform * skeleton.get_bone_global_pose(_hand_l) * rest.affine_inverse() * socket

func update_pose() -> void:
	if not is_instance_valid(actor) or _hand_l < 0 or _hand_r < 0:
		return
	var action := actor.current_action
	if action != _power_action:
		if not (action == &"cast_channel" and _power_action == &"cast_channel_enter"):
			spell_power = 1
		_power_action = action
	if action not in [&"cast", &"cast_channel_enter", &"cast_channel", &"cast_aggressive", &"cast_defensive", &"heal"]:
		spell_power = 1
	var brightness := SpellPresentation.power_intensity(spell_power)
	_material.albedo_color = Color(1.0, 1.0, 1.0, brightness)
	var has_cue := action in [&"cast", &"cast_channel_enter", &"cast_channel", &"cast_aggressive",
		&"cast_defensive", &"heal", &"attack_primary", &"attack_secondary", &"ranged_draw", &"ranged_hold", &"ranged_attack"]
	if not has_cue and not _equipped_bow:
		_spell_color = Color.TRANSPARENT
		if action != _last_action:
			_mesh.clear_surfaces()
			_trail.clear()
			if bow != null:
				bow.hide()
			actor.set_hand_props_visible(true)
		_last_action = action
		return
	var time := actor.animation_player.current_animation_position
	var advanced := not is_equal_approx(time, _last_time)
	if action != _last_action or time < _last_time:
		_trail.clear()
	_last_action = action
	_last_time = time
	var left := hand_position(_hand_l)
	var right := hand_position(_hand_r)
	var drawing := action in [&"ranged_draw", &"ranged_hold"]
	var ranging := drawing or action == &"ranged_attack"
	if ranging:
		_ensure_bow()
	if bow != null:
		bow.visible = ranging or _equipped_bow
	if bow != null and bow.visible:
		# Relaxed carrying follows the closed fist; active draw/release keeps
		# the authored aiming frame and nock positions from both hands.
		bow.set_idle_fit(false)
		var skeleton_size := actor.get_skeleton().global_basis.get_scale().y
		var size := actor.rig_fit_scale() * skeleton_size
		var grip := carried_bow_grip()
		bow.pose(left if ranging else grip.origin, right,
			actor.global_basis.y.normalized(), -actor.global_basis.z.normalized(),
			drawing, time if action == &"ranged_attack" else -1.0, size, skeleton_size)
		if not ranging:
			bow.global_basis = grip.basis.orthonormalized().scaled(Vector3.ONE * size)
	actor.set_hand_props_visible(not ranging)
	_mesh.clear_surfaces()
	if not effects_enabled or not actor.is_visible_in_tree():
		return
	var casting := action in [&"cast", &"cast_channel_enter", &"cast_channel", &"cast_aggressive", &"cast_defensive", &"heal"]
	var melee := action in [&"attack_primary", &"attack_secondary"]
	if not casting and not melee and action != &"ranged_attack":
		return
	if melee:
		var tip_world: Variant = actor.weapon_trail_tip()
		if not tip_world is Vector3:
			return
		if advanced:
			if time >= 0.20 and time <= 0.48:
				_trail.append(to_local(tip_world as Vector3))
				if _trail.size() > 7:
					_trail.pop_front()
			elif not _trail.is_empty():
				_trail.pop_front()
		if _trail.size() < 2:
			return
	if action == &"ranged_attack" and time >= 0.15:
		return
	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _material)
	var l := to_local(left)
	var r := to_local(right)
	var duration := maxf(0.01, actor.animation_player.current_animation_length)
	var progress := time / duration
	var fade := 1.0 if action == &"cast_channel" else smoothstep(0.0, 0.12, time) * (1.0 - smoothstep(0.72, 1.0, progress))
	var color := Color(0.40, 0.72, 1.0, fade)
	if action == &"heal":
		color = Color(0.34, 0.92, 0.62, fade)
	elif action in [&"cast", &"cast_aggressive"]:
		color = Color(1.0, 0.43, 0.16, fade)
	if casting and action == _spell_action and _spell_color.a > 0.0:
		color = Color(_spell_color, fade)
	if casting:
		var size := SpellPresentation.power_scale(spell_power)
		var radius := SpellPresentation.power_radius(spell_power)
		for hand: Vector3 in [l, r]:
			CombatEffectMesh.arc(_mesh, hand, (0.105 + sin(time*7.0)*0.012) * radius, 0.012 * size, color,
				time*2.0, TAU*0.8)
			CombatEffectMesh.spark(_mesh, hand, 0.07 * size, Color(0.86, 0.95, 1.0, fade*0.8))
			var count := SpellPresentation.power_count(6, spell_power)
			for i: int in count:
				var angle := float(i)*TAU/count + time*3.0
				var point := hand + Vector3(cos(angle), sin(angle*1.5)*0.65, sin(angle))*0.19*radius
				CombatEffectMesh.spark(_mesh, point, 0.025 * size, color)
		if action == &"cast_defensive":
			var centre := (l+r)*0.5 + Vector3(0, 0, -0.16)
			var shield_basis := Basis(Vector3.RIGHT, PI*0.5)
			for ring_radius: float in [0.34, 0.43, 0.46]:
				CombatEffectMesh.arc(_mesh, centre, ring_radius * radius * smoothstep(0.0, 0.22, time),
					0.014 * size, color, time*0.3, TAU, shield_basis)
			for i: int in 6:
				var a := i*TAU/6.0 + PI/6.0
				var b := (i+1)*TAU/6.0 + PI/6.0
				CombatEffectMesh.line(_mesh, centre+Vector3(cos(a),sin(a),0)*0.30*radius,
					centre+Vector3(cos(b),sin(b),0)*0.30*radius, 0.018*size, color, Vector3.FORWARD)
		elif action == &"heal" or action == &"cast_channel":
			CombatEffectMesh.arc(_mesh, Vector3(0, 0.045, 0), 0.43*radius, 0.013*size, color, -time, TAU*0.88)
			var count := SpellPresentation.power_count(18, spell_power)
			for i: int in count:
				var phase := fposmod(time*0.55 + float(i)/count, 1.0)
				var angle := float(i)*2.4 + time*1.7
				var c := color
				c.a *= sin(phase*PI)*0.75
				CombatEffectMesh.spark(_mesh, Vector3(cos(angle)*0.42*radius, phase*1.65,
					sin(angle)*0.42*radius), 0.035*size, c)
	if melee:
		for i: int in range(1, _trail.size()):
			var weight := float(i)/_trail.size()
			CombatEffectMesh.line(_mesh, _trail[i-1], _trail[i], 0.075*weight,
				Color(0.77, 0.88, 1.0, weight*0.45), Vector3.FORWARD)
	if action == &"ranged_attack" and time < 0.15:
		CombatEffectMesh.spark(_mesh, l, 0.08*(1.0-time/0.15), Color(0.94,0.78,0.43,0.7))
	_mesh.surface_end()
