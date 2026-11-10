extends SkeletonModifier3D
## A seated sewing loop on the imported skeleton. The existing two-bone
## seat solver preserves bone lengths and leaves network position untouched.
const SeatPose := preload("res://src/mounts/rider_seat_pose.gd")
var actor: Node3D
var settings: Dictionary
var solver: RefCounted
var elapsed := 0.0

func setup(body: Node3D, profile: Dictionary) -> Array[String]:
	actor = body
	settings = profile
	solver = SeatPose.new()
	return solver.configure(actor, get_skeleton(), settings, Animation.new(), actor.get_node("NativeModel"))

func _process_modification_with_delta(delta: float) -> void:
	if solver == null or not is_instance_valid(actor):
		return
	elapsed += delta
	var seat := Transform3D(actor.global_basis * Basis(Vector3.UP, PI),
		actor.global_transform * Vector3(0.0, float(settings.get("seatHeight", 0.58)),
			-float(settings.get("seatForward", 0.0))))
	solver.fit(seat, "idle", elapsed, 2.4)
