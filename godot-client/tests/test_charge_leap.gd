extends SceneTree
const Leap = preload("res://src/actors/charge_leap_motion.gd")
var failures := 0

func _init() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var route := PackedVector3Array([Vector3.ZERO, Vector3(1, 0.2, 0), Vector3(2, 0.4, 0)])
	var motion = Leap.new(route, 0.36)
	check(motion.position_at(0).is_equal_approx(route[0]), "takeoff starts at the route origin")
	check(motion.position_at(0.36).is_equal_approx(route[-1]), "landing reaches the route endpoint")
	check(motion.position_at(0.18).y > motion.ground_at(0.18).y + 0.6, "flight has a visible vertical arc")
	var previous: Vector3 = motion.position_at(0)
	for frame in range(1, 145):
		var point: Vector3 = motion.position_at(frame * 0.36 / 144.0)
		check(point.is_finite() and point.y >= motion.ground_at(frame * 0.36 / 144.0).y - 0.0001, "arc remains finite and above terrain")
		check(point.distance_to(previous) < 0.1, "flight stays continuous between samples")
		previous = point
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.server_target = route[-1]
	actor.begin_charge_leap(route, 0.36)
	actor._physics_process(0.18)
	check(actor.global_position.y > 0.6, "live actor becomes airborne")
	actor.play_action(&"run")
	check(actor._charge_leap != null and actor.current_action != &"run", "movement commands cannot replace the leap pose")
	var airborne: float = actor.global_position.y
	actor.set_surface_height(0.4)
	check(is_equal_approx(actor.global_position.y, airborne), "surface sampling cannot pull an airborne actor down")
	actor._physics_process(0.18)
	check(actor._charge_leap == null and actor.global_position.is_equal_approx(actor.server_target), "landing restores the confirmed ground position")
	actor.position = Vector3.ZERO
	actor.server_target = route[1]
	actor.begin_charge_leap(route, 0.36)
	actor._physics_process(0.38)
	check(actor._charge_leap != null and actor.global_position.is_equal_approx(route[-1]), "a delayed final packet cannot pull the landing backward")
	actor.server_target = route[-1]
	actor._physics_process(0.01)
	check(actor._charge_leap == null, "the confirmed endpoint releases the landing hold")
	actor.position = Vector3.ZERO
	actor.begin_charge_leap(route, 0.36)
	actor._physics_process(0.1)
	var frame := Transform3D(Basis(Vector3.UP, PI / 2), Vector3(20, 1, 5))
	var before: Vector3 = actor._charge_leap.position_at(0.1)
	actor.rebase_world(frame)
	check(actor._charge_leap.position_at(0.1).is_equal_approx(frame * before), "map-frame rebasing preserves flight")
	actor.play_action(&"death", true)
	check(actor._charge_leap == null and actor.global_position.is_equal_approx(actor.server_target), "death interrupts the leap at the confirmed tile")
	actor.free()
	print("charge leap: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
