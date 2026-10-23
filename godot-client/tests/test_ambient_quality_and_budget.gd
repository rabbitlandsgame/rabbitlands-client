extends SceneTree
## Synthetic box/skeleton fixture only; this does not restore an authored herd.
const Quality := preload("res://src/actors/actor_render_quality.gd")
var failures := 0

class FixturePopulation extends AmbientPopulation:
	func _load_catalog() -> Dictionary:
		return {"fixture": {"scene": "user://synthetic-ambient-quality-fixture.tscn"}}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var source := Node3D.new()
	var rig := Skeleton3D.new()
	rig.name = "Rig"
	rig.add_bone("root")
	source.add_child(rig)
	rig.owner = source
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	source.add_child(mesh)
	mesh.owner = source
	var player := AnimationPlayer.new()
	source.add_child(player)
	player.owner = source
	var animation := Animation.new()
	animation.length = 1.0
	animation.loop_mode = Animation.LOOP_LINEAR
	var track := animation.add_track(Animation.TYPE_POSITION_3D)
	animation.track_set_path(track, NodePath("Rig:root"))
	animation.position_track_insert_key(track, 0.0, Vector3.ZERO)
	animation.position_track_insert_key(track, 1.0, Vector3.UP * 0.1)
	var library := AnimationLibrary.new()
	library.add_animation("Idle_A", animation)
	player.add_animation_library("", library)
	var packed := PackedScene.new()
	_check(packed.pack(source) == OK, "synthetic ambient fixture packs")
	source.free()
	var population := FixturePopulation.new()
	root.add_child(population)
	population.set_process(false)
	population._scenes["fixture"] = packed
	var manifest := WorldManifest.new()
	manifest.data = {"ambientPopulation": {"groups": [{"model": "fixture", "count": 20,
		"center": [0, 0, 0], "radius": 0, "animation": "Idle_A", "seed": 117}]}}
	var initial := population.populate(manifest, null)
	_check(initial <= 4 and initial < 20 and population.pending_creation_count() > 0,
		"a large declaration does not instantiate its whole herd on one frame")
	population.apply_render_quality(Quality.Quality.LOW)
	var previous := population._spawned.size()
	for frame: int in 80:
		if population.pending_creation_count() == 0:
			break
		await physics_frame
		await process_frame
		var count := population._spawned.size()
		_check(count - previous <= 2, "LOW continuation creates at most two animals per pass")
		previous = count
	_check(population.pending_creation_count() == 0 and population._spawned.size() == 20,
		"bounded passes eventually create the complete declared population")
	var animal := population._spawned[0]
	var body := animal.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	_check(is_equal_approx(body.lod_bias, 0.35) and body.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"existing and newborn animals share LOW mesh/shadow quality")
	population.apply_render_quality(Quality.Quality.HIGH)
	_check(is_equal_approx(body.lod_bias, 1.0) and body.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"quality round trip restores authored ambient mesh values")
	var pair := population._animated[0]
	population._apply_animal_tier(pair, AnimationGate.Tier.PAUSED)
	_check(animal.process_mode == Node.PROCESS_MODE_DISABLED and not (pair[1] as AnimationPlayer).active,
		"offscreen ambient player and skeleton subtree sleep together")
	population._apply_animal_tier(pair, AnimationGate.Tier.HALF)
	_check(animal.process_mode == Node.PROCESS_MODE_INHERIT
		and (pair[1] as AnimationPlayer).callback_mode_process == AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		and (pair[2] as Skeleton3D).modifier_callback_mode_process == Skeleton3D.MODIFIER_CALLBACK_MODE_PROCESS_MANUAL,
		"half-rate ambient animation carries its cached skeleton modifiers")
	population.process_mode = Node.PROCESS_MODE_DISABLED
	await _drain()
	population.clear()
	_check(population.pending_creation_count() == 0 and population._animated.is_empty(),
		"clear cancels queued creation and gate membership")
	await _drain()
	population.queue_free()
	await _drain()
	print("AMBIENT_QUALITY_BUDGET failures=", failures)
	quit(1 if failures else 0)

func _drain() -> void:
	await physics_frame
	await process_frame
	await process_frame

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
