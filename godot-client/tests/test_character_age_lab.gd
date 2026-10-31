extends SceneTree
## The offline head/fit preview edits age without a negotiated server.
const LAB := preload("res://prototypes/rl_heads/rl_head_lab.gd")
var failures := 0
var checks := 0

func _init() -> void:
	_run.call_deferred()

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	var lab := LAB.new()
	root.add_child(lab)
	for frame: int in 5: await process_frame
	var sliders: Dictionary = lab._amount_sliders
	check(sliders.has("skin_age") and sliders.has("hair_grey"), "offline preview has both age sliders")
	check((sliders.skin_age as HSlider).editable and (sliders.hair_grey as HSlider).editable, "offline age does not need server negotiation")
	(sliders.skin_age as HSlider).value = .71
	(sliders.hair_grey as HSlider).value = .38
	check(is_equal_approx(lab.face.skin_age, .71) and is_equal_approx(lab.face.hair_grey, .38), "offline slider handlers update source face")
	check(is_equal_approx(lab.actor.rl_head().appearance.skin_age, .71) and is_equal_approx(lab.actor.rl_head().appearance.hair_grey, .38), "offline slider handlers update actual actor")
	var saved: Dictionary = lab._actor_appearance()
	check(is_equal_approx(saved.rl_head.skin_age, .71) and is_equal_approx(saved.rl_head.hair_grey, .38), "fit preview JSON retains age")
	check(not (sliders.hair_tie_height as HSlider).get_parent().visible, "unqualified preset does not show a tie height control")
	lab.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("Character age offline lab: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
