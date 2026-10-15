extends SceneTree
## Exercise event timing, real world anchors and frame-rate-independent flight.
var failures := 0

func _init() -> void:
	call_deferred("run")

func check(value: bool, description: String) -> void:
	if not value:
		failures += 1
		push_error(description)

func make_effect(id: int, from: Vector3, to: Variant) -> WorldEffect3D:
	var effect := WorldEffect3D.new()
	root.add_child(effect)
	effect.configure(id, from, to)
	effect.set_process(false)
	return effect

func run() -> void:
	check_power_scaling()
	check_server_impact_timing()
	for id: int in [0, 1, 2, 10, 73, 83, 84, 85, 86, 999]:
		for destination: Vector3 in [Vector3(5, 0, 0), Vector3(0, 5, 0), Vector3(0.1, 0, 0), Vector3(70, -5, 20)]:
			var effect := make_effect(id, Vector3.ZERO, destination)
			check(effect.flight != null, "targeted spell has a flight")
			check(effect.get_node_or_null("EffectBeam") == null, "targeted spell has no solid connecting cylinder")
			check(not effect.impact_started and not (effect.get_node("EffectRing") as Node3D).visible,
				"target reaction is absent before arrival")
			check(not (effect.get_node("EffectBurst") as GPUParticles3D).emitting, "particles wait for contact")
			var flight := effect.flight
			check(flight.duration >= 0.22 and flight.duration <= 0.62, "near and distant flights have bounded durations")
			var start: Vector3 = destination + Vector3.UP if id in [10, 86] else Vector3.UP
			var end: Vector3 = Vector3.UP if id in [10, 86] else destination + Vector3.UP
			check(flight.point_at(0.0).is_equal_approx(start) and flight.point_at(1.0).is_equal_approx(end),
				"every strand starts and lands exactly at the correct actor, including reverse drain")
			for step: int in 11:
				for strand: int in 3:
					check((flight.point_at(step / 10.0, strand) as Vector3).is_finite(), "vertical and short paths remain finite")
			effect._process(float(flight.duration) * 0.5)
			check(not effect.impact_started, "midflight cannot trigger an early impact")
			effect._process(float(flight.duration) * 0.5 + 0.001)
			check(effect.impact_started, "crossing arrival triggers contact")
			effect._process(0.25)
			check((flight.get_node("SpellEnergy") as MeshInstance3D).mesh.get_surface_count() == 0,
				"trail fully dissolves after contact")
			effect._process(WorldEffect3D.LIFETIME_SECONDS)
			check(effect.is_queued_for_deletion(), "effect frees itself after the impact finishes")
			effect.free()
	for destination: Variant in [null, Vector3.ZERO, Vector3(0.01, 0, 0)]:
		var effect := make_effect(1, Vector3.ZERO, destination)
		check(effect.flight == null and effect.impact_started, "self casts use a local effect without a degenerate flight")
		effect.free()
	var source := Node3D.new()
	var target := Node3D.new()
	root.add_child(source)
	root.add_child(target)
	source.position = Vector3(12, 2, -7)
	target.position = Vector3(16, 4, -7)
	var bound := make_effect(2, source.position, target.position)
	bound.bind_actors(source, target)
	bound.release_delay = 0.2
	bound._process(0.1)
	check(not bound.impact_started, "gathering time does not consume flight or impact lifetime")
	source.position.z += 0.2
	bound._process(0.1)
	check(bound.to_global(bound.flight.start).is_equal_approx(source.position + Vector3.UP), "release uses updated caster position")
	var launch: Vector3 = bound.flight.start
	source.position.x -= 2.0
	target.position.x += 0.2
	bound._process(0.02)
	check((bound.flight.start as Vector3).is_equal_approx(launch), "released trail does not drag behind a moving caster")
	check(bound.to_global(bound.flight.destination).is_equal_approx(target.position + Vector3.UP), "flight tracks a moving target")
	target.free()
	source.free()
	bound._process(0.01)
	check((bound.flight.destination as Vector3).is_finite(), "removed actors retain the last valid endpoint")
	bound.free()
	var fast := make_effect(2, Vector3.ZERO, Vector3(5, 0, 0))
	var slow := make_effect(2, Vector3.ZERO, Vector3(5, 0, 0))
	for frame: int in 12:
		fast._process(1.0 / 60.0)
	for frame: int in 6:
		slow._process(1.0 / 30.0)
	check(fast.flight.point_at(fast.elapsed / fast.flight.duration).is_equal_approx(
		slow.flight.point_at(slow.elapsed / slow.flight.duration)), "30 and 60 fps place the projectile at the same point")
	fast.free()
	slow.free()
	print("spell flights: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func check_server_impact_timing() -> void:
	for destination: Vector3 in [Vector3.ZERO, Vector3(0.01, 0, 0), Vector3(6, 0, 0)]:
		for area: bool in [false, true]:
			var effect := make_effect(83, Vector3.ZERO, destination)
			if area: effect.configure_area(4.0, "burst")
			var travel := 0.0 if destination.length() < 0.05 else 0.62
			effect.configure_timing(0.45, travel)
			check(not effect.impact_started, "server-timed damage has no early ring, including same-tile hits")
			effect._process(0.45 + travel - 0.001)
			check(not effect.impact_started, "target and burst particles wait through release and travel")
			effect._process(0.002)
			check(effect.impact_started, "target and burst contact follows the server's clock")
			check(is_equal_approx(effect.elapsed, 0.45 + travel + 0.001), "no extra local release delay is added")
			effect.free()
	var moving := make_effect(83, Vector3.ZERO, Vector3.RIGHT * 3)
	moving.configure_timing(0.45, 0.3)
	moving.flight.set_endpoints(Vector3.UP, Vector3(20, 2, 0))
	check(is_equal_approx(moving.flight.duration, 0.3), "following a moving actor preserves the agreed arrival time")
	moving.free()

func check_power_scaling() -> void:
	check(is_equal_approx(SpellPresentation.power_scale(5), 1.9), "P5 reaches the former P10 core size")
	check(SpellPresentation.power_scale(10) >= 1.9 * 2.0
		and SpellPresentation.power_count(32, 10) >= 67 * 2
		and SpellPresentation.power_intensity(10) >= 1.27 * 2.0,
		"P10 at least doubles the former maximum's core size, particle count and brightness")
	var previous_particles := 0
	var previous_radius := 0.0
	var baseline: Vector3
	var duration := 0.0
	for power: int in range(1, 11):
		var effect := WorldEffect3D.new()
		root.add_child(effect)
		effect.configure(2, Vector3(2, 0, 3), Vector3(7, 0, 3), power)
		var particles := (effect.get_node("EffectBurst") as GPUParticles3D).amount
		var radius := ((effect.get_node("EffectRing") as MeshInstance3D).mesh as TorusMesh).outer_radius
		check(particles > previous_particles and radius > previous_radius,
			"every power tier increases effect density and radius")
		check(particles <= 144 and radius < 1.7, "maximum power stays within the visual budget")
		previous_particles = particles
		previous_radius = radius
		if power == 1:
			baseline = effect.flight.point_at(0.5)
			duration = effect.flight.duration
		else:
			check((effect.flight.point_at(0.5) as Vector3).is_equal_approx(baseline)
				and is_equal_approx(effect.flight.duration, duration),
				"power changes neither trajectory nor arrival timing")
		effect.free()
	var state := root.get_node("AppState")
	var requests: Array[Dictionary] = []
	var received: Array[Dictionary] = []
	state.actor_animation_requested.connect(func(event: Dictionary) -> void: requests.append(event))
	state.special_effect_requested.connect(func(event: Dictionary) -> void: received.append(event))
	state.call("_on_packet", 70, PackedByteArray([4, 1, 6, 1]))
	check(requests.back().action == &"cast_channel_enter" and requests.back().power == 6,
		"accepted cast power reaches channeling")
	state.call("_on_packet", 70, PackedByteArray([1, 0, 8, 2]))
	check(requests.back().action == &"cast_aggressive" and requests.back().power == 8,
		"standard harm keeps its offensive animation and actual power")
	state.call("_on_packet", 79, PackedByteArray([2, 91, 0, 77, 0, 7]))
	check(received.back().power == 7 and received.back().target_id == 77,
		"remote cast carries its own power, independent of local preferences")
	state.call("_on_packet", 79, PackedByteArray([12, 91, 0, 10]))
	check(received.back().power == 10 and received.back().target_id == -1,
		"powered self cast does not invent a target")
	state.call("_on_packet", 79, PackedByteArray([2, 91, 0, 77, 0]))
	check(received.back().power == 1, "legacy event uses the existing base intensity")
	for bytes: PackedByteArray in [PackedByteArray([2, 91, 0, 0]), PackedByteArray([2, 91, 0, 77, 0, 11])]:
		check(EloriaProtocol.decode_server(79, bytes).type == "invalid", "invalid network power is rejected")
	for power: int in [-10, 1000]:
		var effect := WorldEffect3D.new()
		root.add_child(effect)
		effect.configure(2, Vector3.ZERO, Vector3.RIGHT * 5, power)
		check(effect.power_level in [1, 10] and effect.flight.power_level == effect.power_level,
			"direct visual calls also clamp out-of-range power")
		effect.free()
