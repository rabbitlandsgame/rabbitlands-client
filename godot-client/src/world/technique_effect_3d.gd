extends Node3D
## Bounded transient combat cues. Uses the same draw path in game and preview;
## no hit tests, actor movement, status duration, or gameplay state live here.
const Presentation = preload("res://src/world/technique_presentation.gd")
const MAX_LIFETIME := 2.1
var key := ""
var phase := "strike"
var hit := false
var elapsed := 0.0
var contact := 0.0
var lifetime := 1.3
var _source: WeakRef
var _target: WeakRef
var _target_point := Vector3.ZERO
var _target_floor := Vector3.ZERO
var _origin := Vector3.ZERO
var _forward := Vector3.FORWARD
var _right := Vector3.RIGHT
var _mesh := ImmediateMesh.new()
var _material := CombatEffectMesh.material()
var geometry: MeshInstance3D

func configure(technique: String, event_phase: String, source: Node3D, target: Node3D, landed: bool) -> void:
	key = technique
	phase = event_phase
	hit = landed
	_source = weakref(source)
	_target = weakref(target) if is_instance_valid(target) else null
	_target_floor = target.global_position if is_instance_valid(target) else source.global_position
	_target_point = _target_floor + Vector3.UP
	global_position = source.global_position
	contact = Presentation.contact_delay(key, phase, source.global_position.distance_to(_target_floor))
	lifetime = minf(MAX_LIFETIME, contact + (1.5 if key in Presentation.SUPPORT else 0.85))
	geometry = MeshInstance3D.new()
	geometry.name = "TechniqueCue"
	geometry.mesh = _mesh
	geometry.layers = 1
	geometry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(geometry)
	add_to_group("technique_visual_effects")
	sample(0.0)

func _process(delta: float) -> void:
	sample(elapsed + delta)
	if elapsed >= lifetime: queue_free()

func sample(time: float) -> void:
	elapsed = time
	_mesh.clear_surfaces()
	var source := _source.get_ref() as Node3D if _source != null else null
	if not is_instance_valid(source) or not Presentation.PROFILES.has(key): return
	_origin = to_local(source.global_position)
	var target := _target.get_ref() as Node3D if _target != null else null
	if is_instance_valid(target):
		_target_floor = target.global_position
		_target_point = target.spell_target_position() if target.has_method("spell_target_position") else _target_floor + Vector3.UP
	elif _target == null:
		_target_floor = source.global_position
		_target_point = source.global_position + Vector3.UP
	var offset := _target_floor - source.global_position
	offset.y = 0
	_forward = offset.normalized() if offset.length_squared() > 0.01 else -source.global_basis.z.normalized()
	_right = _forward.cross(Vector3.UP).normalized()
	var p := clampf((elapsed - contact) / maxf(0.01, lifetime - contact), 0.0, 1.0)
	var color := Presentation.color_for(key)
	color.a = 0.75 * (1.0 - p) * smoothstep(0.0, 0.06, elapsed + 0.01)
	if elapsed >= lifetime: return
	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _material)
	if phase not in ["impact", "pulse"]: _source_cue(p, color)
	if elapsed >= contact and (hit or phase == "pulse"):
		_impact_cue(to_local(_target_point), to_local(_target_floor), p, color)
	# Keeps a harmless vertex surface for a miss after its swing has faded.
	CombatEffectMesh.spark(_mesh, _origin, 0.001, Color.TRANSPARENT)
	_mesh.surface_end()

func _line(a: Vector3, b: Vector3, width: float, color: Color) -> void:
	CombatEffectMesh.line(_mesh, a, b, width, color, Vector3.UP)

func _arc(center: Vector3, radius: float, width: float, color: Color, start := 0.0, sweep := TAU, basis := Basis.IDENTITY) -> void:
	CombatEffectMesh.arc(_mesh, center, radius, width, color, start, sweep, basis)

func _motes(center: Vector3, p: float, color: Color, count := 12, radius := 0.8, rising := false) -> void:
	for i: int in count:
		var angle := i * 2.39996
		var speed := 0.4 + float(i % 4) * 0.18
		var height := (0.1 + p * 1.3) if rising else (sin(p * PI) * 0.55 - p * p * 0.35)
		var at := center + Vector3(cos(angle) * p * radius * speed, height, sin(angle) * p * radius * speed)
		CombatEffectMesh.spark(_mesh, at, (0.025 + float(i % 3) * 0.009) * (1.0 - p), color)

func _source_cue(p: float, color: Color) -> void:
	var chest := _origin + Vector3.UP * 1.0
	var axis := Basis(_right, Vector3.UP, -_forward).orthonormalized()
	match key:
		"heavy_blow", "executioners_stroke", "sunder":
			_arc(chest + _forward * 0.55, 0.62, 0.07 if key != "sunder" else 0.10, color, -1.3 + p * 1.7, PI * 0.65, Basis(_right, PI * 0.5))
		"measured_strike", "lunge", "backstab", "keep_at_bay":
			_line(chest + _right * 0.15, chest + _forward * (0.6 + sin(p * PI) * 0.65), 0.045, color)
		"cleave", "flurry", "hamstring":
			var height := 0.35 if key == "hamstring" else 0.95
			for i: int in (3 if key == "flurry" else 1):
				var tone := Color(color, color.a * (1.0 - i * 0.20))
				_arc(_origin + Vector3.UP * (height + i * 0.12), 0.75 + p * 0.35, 0.055, tone, atan2(_forward.z, _forward.x) - 1.2 + p * 0.8 + i * 0.22, PI * 0.85)
		"shield_bash", "brace", "riposte":
			var center := chest + _forward * (0.35 + sin(p * PI) * 0.2)
			if key == "riposte" and phase == "counter":
				_line(center - _right * 0.3, center + _forward * 0.6, 0.05, color)
				_line(center + _right * 0.3, center + _forward * 0.6, 0.05, color)
				return
			_arc(center, 0.34 + p * 0.07, 0.028, color, 0, TAU, axis * Basis(Vector3.RIGHT, PI * 0.5))
			_line(center - _right * 0.25, center + Vector3.DOWN * 0.30, 0.04, color)
			_line(center + Vector3.DOWN * 0.30, center + _right * 0.25, 0.04, color)
		"intercept":
			var end := to_local(_target_point)
			for i: int in 6:
				var a := float(i) / 6.0
				var b := float(i + 1) / 6.0
				_line(chest.lerp(end, a) + Vector3.UP * sin(a * PI) * 0.35, chest.lerp(end, b) + Vector3.UP * sin(b * PI) * 0.35, 0.025, color)
			_arc(_origin + Vector3.UP * 0.06, 0.48, 0.025, color, 0, TAU * 0.75)
		"charge", "fighting_retreat", "step_back":
			if key == "charge" and phase == "land":
				_arc(_origin + Vector3.UP * 0.04, 0.25 + p * 0.7, 0.035, color)
				_motes(_origin, p, color, 10, 0.9)
				return
			if key == "charge" and phase == "strike":
				_line(chest, chest + _forward * (0.45 + sin(p * PI) * 0.65), 0.055, color)
				return
			var direction := _forward if key == "charge" else -_forward
			for side: int in [-1, 1]:
				var at := _origin + _right * side * 0.30 + Vector3.UP * 0.12
				_line(at - direction * (0.25 + p * 0.7), at + direction * 0.25, 0.045, color)
			_motes(_origin, p, Color(color, color.a * 0.5), 10, 0.65)
		"challenge", "provoke", "war_cry":
			for i: int in 3:
				_arc(_origin + Vector3.UP * (0.12 + i * 0.23), 0.30 + p * (2.8 if key == "war_cry" else 1.4) + i * 0.08, 0.025, color, 0, TAU)
		"second_wind":
			_motes(_origin + Vector3.UP * 0.2, p, color, 16, 0.6, true)
			_arc(chest, 0.32 + p * 0.12, 0.02, color, elapsed * 2.0, PI * 1.4, Basis(Vector3.RIGHT, PI * 0.5))
		_:
			# Bow technique cues decorate release, never invent extra projectiles.
			if key in Presentation.RANGED:
				_motes(chest + _forward * 0.25, p, color, 6, 0.35)

func _impact_cue(center: Vector3, floor: Vector3, p: float, color: Color) -> void:
	match key:
		"shield_bash":
			_arc(center, 0.16 + p * 0.48, 0.04 * (1.0 - p), color, 0, TAU, Basis(Vector3.RIGHT, PI * 0.5))
			for i: int in 3:
				var angle := elapsed * 4 + i * TAU / 3
				CombatEffectMesh.spark(_mesh, center + Vector3(cos(angle) * 0.21, 0.65, sin(angle) * 0.21), 0.045, color)
		"sunder":
			for side: int in [-1, 1]:
				_line(center + Vector3.UP * 0.3, center + _right * side * (0.16 + p * 0.22), 0.045, color)
				_line(center + _right * side * (0.16 + p * 0.22), center + Vector3.DOWN * 0.35 + _right * side * 0.10, 0.035, color)
			_motes(center, p, color, 14, 0.85)
		"hamstring", "pinning_shot":
			_arc(floor + Vector3.UP * 0.09, 0.20 + p * 0.3, 0.04, color, -elapsed, TAU * 0.85)
			for side: int in [-1, 1]:
				_line(floor + _right * side * 0.4 + Vector3.UP * 0.04, floor + _right * side * 0.14 + Vector3.UP * 0.25, 0.035, color)
		"mark_target", "challenge", "provoke", "aimed_shot":
			var width := 0.23 + p * 0.08
			for side: int in [-1, 1]:
				var edge := center + _right * side * width
				_line(edge + Vector3.UP * 0.28, edge + Vector3.DOWN * 0.28, 0.025, color)
				for top: int in [-1, 1]:
					_line(edge + Vector3.UP * top * 0.28, edge - _right * side * 0.10 + Vector3.UP * top * 0.28, 0.025, color)
		"backstab", "executioners_stroke":
			for side: int in [-1, 1]:
				_line(center + _right * side * 0.32 + Vector3.UP * 0.3, center - _right * side * 0.32 + Vector3.DOWN * 0.3, 0.065 * (1.0 - p), color)
			_motes(center, p, color, 10, 0.5)
		"keep_at_bay":
			for i: int in 3:
				_arc(floor + _forward * (p * 0.6 + i * 0.15) + Vector3.UP * 0.15, 0.35 + i * 0.14, 0.035, color, atan2(_forward.z, _forward.x) - 0.7, 1.4)
		"intercept", "brace", "war_cry", "second_wind":
			_arc(floor + Vector3.UP * 0.06, 0.25 + p * 0.65, 0.025, color)
			_motes(floor + Vector3.UP * 0.10, p, color, 14, 0.7, true)
		_:
			_motes(center, p, color, 18 if key in ["heavy_blow", "volley", "charge"] else 9, 0.9)
			_arc(floor + Vector3.UP * 0.05, 0.12 + p * 0.6, 0.018, Color(color, color.a * 0.4), 0, TAU * 0.8)
