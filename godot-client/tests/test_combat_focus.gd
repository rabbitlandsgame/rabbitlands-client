extends SceneTree
## Focused protocol/art coverage without loading a world or creature models.
const StatusIcons := preload("res://src/ui/status_effect_icons.gd")
const TechniqueIcons := preload("res://src/ui/technique_icons.gd")
const Presentation := preload("res://src/world/technique_presentation.gd")
const Effect := preload("res://src/world/technique_effect_3d.gd")
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	var state := root.get_node("AppState")
	state.actors[910] = {"actor_id": 910, "kind": 5, "health": 100, "max_health": 100}
	state.call("_on_packet", 212, JSON.stringify({"kind": "actor_status", "actor_id": 910,
		"effects": ["focus_lock"]}).to_utf8_buffer())
	expect(state.actors[910].status_effects == ["focus_lock"], "focus lock reaches the creature")
	expect(state.actors[910].negative_statuses == ["focus_lock"], "focus lock uses the overhead status row")
	expect(StatusIcons.known(["focus_lock"]) == ["focus_lock"], "overhead renderer recognizes focus lock")
	expect(StatusIcons.TEXTURES.focus_lock.get_size() == Vector2(24, 24), "focus icon matches existing status size")
	state.call("_on_packet", 212, JSON.stringify({"kind": "actor_status", "actor_id": 910,
		"effects": []}).to_utf8_buffer())
	expect(state.actors[910].status_effects.is_empty(), "authoritative expiry removes the focus icon")
	state.actors.erase(910)
	expect(TechniqueIcons.icon_for("provoke") != null, "Provoke has established technique artwork")
	expect(Presentation.PROFILES.has("provoke") and "provoke" in Presentation.SUPPORT,
		"Provoke has a support animation and effect")
	var stage := Node3D.new()
	root.add_child(stage)
	var source := Node3D.new()
	var target := Node3D.new()
	stage.add_child(source)
	stage.add_child(target)
	var effect := Effect.new()
	stage.add_child(effect)
	effect.configure("provoke", "impact", source, target, true)
	effect.sample(0.2)
	expect(effect.geometry != null, "Provoke's impact cue renders without actor dependencies")
	var preview := Image.new()
	expect(preview.load_svg_from_string(FileAccess.get_file_as_string(
		"res://assets/ui/status/focus_lock.svg"), 4.0) == OK, "focus SVG rasterizes")
	var output := ProjectSettings.globalize_path("res://test-artifacts/combat-focus")
	DirAccess.make_dir_recursive_absolute(output)
	expect(preview.save_png(output.path_join("focus-lock.png")) == OK, "focus icon preview saved")
	stage.queue_free()
	await process_frame
	print("combat focus client: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
