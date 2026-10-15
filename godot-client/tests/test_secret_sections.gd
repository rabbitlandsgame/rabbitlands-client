extends SceneTree
## SecretSections shows a player only the secret they stand in: the other
## sections of a `<region>_secrets` map go dark, and nodes no section claims
## (sky, fog volumes) stay as they are.

const SectionsScript := preload("res://src/world/secret_sections.gd")
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var world := Node3D.new()
	world.name = "World"
	root.add_child(world)
	# alpha: a floor named for its section and a lamp claimed by position
	var a_walk := MeshInstance3D.new()
	a_walk.name = "Walk_alpha_stone"
	a_walk.position = Vector3(10, 0, 10)
	world.add_child(a_walk)
	var a_lamp := OmniLight3D.new()
	a_lamp.name = "Lamp"
	a_lamp.position = Vector3(12, 2, 12)
	world.add_child(a_lamp)
	# beta: a wall named for its section and a prop claimed by position
	var b_build := MeshInstance3D.new()
	b_build.name = "Build_beta_brick"
	b_build.position = Vector3(100, 0, 10)
	world.add_child(b_build)
	var b_prop := MeshInstance3D.new()
	b_prop.name = "Prop"
	b_prop.position = Vector3(105, 0, 15)
	world.add_child(b_prop)
	# nothing claims this one
	var loose := MeshInstance3D.new()
	loose.name = "Sky"
	loose.position = Vector3(500, 0, 500)
	world.add_child(loose)

	var manifest := WorldManifest.new()
	manifest.data = {
		"secret": true,
		"sections": [
			{"id": "alpha", "bounds": {"min": [0, 0], "max": [40, 40]}},
			{"id": "beta", "bounds": {"min": [92, 0], "max": [132, 40]}},
		],
	}
	var sections = SectionsScript.new()
	var claimed: int = sections.configure(manifest, world)
	_expect(claimed == 4, "four nodes are claimed by a section (got %d)" % claimed)
	_expect(sections.is_active(), "a secret manifest activates the controller")

	sections.update(Vector3(20, 0, 20), true)
	_expect(sections.current_section() == "alpha", "the player in alpha sees alpha")
	_expect(a_walk.visible and a_lamp.visible, "alpha's floor and lamp are shown")
	_expect(not b_build.visible and not b_prop.visible, "beta is blacked out from alpha")
	_expect(loose.visible, "nodes no section claims stay visible")

	sections.update(Vector3(60, 0, 20))
	_expect(sections.current_section() == "alpha", "the gutter between sections keeps the last one")
	_expect(a_walk.visible and not b_build.visible, "nothing changes in the gutter")

	sections.update(Vector3(110, 0, 20))
	_expect(sections.current_section() == "beta", "arriving in beta switches the section")
	_expect(b_build.visible and b_prop.visible, "beta's wall and prop are shown")
	_expect(not a_walk.visible and not a_lamp.visible, "alpha is blacked out from beta")
	_expect(loose.visible, "the loose node is still visible")

	# actors and map objects are judged by where they stand, each frame
	var me := Node3D.new()
	me.position = Vector3(110, 0, 20)
	world.add_child(me)
	var other := Node3D.new()
	other.position = Vector3(20, 0, 20)
	world.add_child(other)
	var neighbour := Node3D.new()
	neighbour.position = Vector3(120, 0, 30)
	world.add_child(neighbour)
	sections.cull_dynamic([me, other, neighbour], me)
	_expect(me.visible, "the local player is never culled")
	_expect(not other.visible, "an actor in another secret is hidden")
	_expect(neighbour.visible, "an actor in the same secret is shown")
	other.position = Vector3(115, 0, 25)
	sections.cull_dynamic([me, other, neighbour], me)
	_expect(other.visible, "an actor who walks into the section appears")
	other.position = Vector3(20, 0, 20)
	sections.cull_dynamic([me, other, neighbour], me)
	_expect(not other.visible, "and is hidden again when they leave")

	sections.reset()
	_expect(a_walk.visible and a_lamp.visible and b_build.visible and b_prop.visible,
		"reset shows every section again")
	_expect(other.visible, "reset shows the actors it had hidden")
	_expect(not sections.is_active(), "reset deactivates the controller")

	# an ordinary map with sections is not a secret and is left alone
	var plain := WorldManifest.new()
	plain.data = {"sections": [{"id": "x", "bounds": {"min": [0, 0], "max": [1, 1]}}]}
	_expect(sections.configure(plain, world) == 0 and not sections.is_active(),
		"a manifest without secret: true claims nothing")
	sections.update(Vector3(0.5, 0, 0.5), true)
	_expect(a_walk.visible and b_build.visible and loose.visible,
		"an inactive controller hides nothing")

	await _test_retired_scene_nodes(manifest, plain)

	if failures == 0:
		print("test_secret_sections: all checks passed")
	quit(failures)


func _test_retired_scene_nodes(manifest: WorldManifest, plain: WorldManifest) -> void:
	var world := Node3D.new()
	root.add_child(world)
	# Map changes leave an old import/light subtree queued while the new map
	# is configured. Its children are not themselves marked for deletion.
	var retiring := Node3D.new()
	world.add_child(retiring)
	var retired_light := OmniLight3D.new()
	retired_light.position = Vector3(10, 2, 10)
	retiring.add_child(retired_light)
	retiring.queue_free()
	var alpha := MeshInstance3D.new()
	alpha.name = "Walk_alpha_live"
	world.add_child(alpha)
	var beta := MeshInstance3D.new()
	beta.name = "Build_beta_live"
	world.add_child(beta)
	var removed := MeshInstance3D.new()
	removed.name = "Build_alpha_removed"
	world.add_child(removed)
	var sections = SectionsScript.new()
	_expect(sections.configure(manifest, world) == 3,
		"indexing excludes an entire subtree queued for deletion")
	# A mesh can also disappear after indexing. A dead first member must not
	# prevent later live members and the next section from changing visibility.
	removed.free()
	await process_frame
	beta.visible = false
	sections.update(Vector3(110, 0, 20), true)
	_expect(not alpha.visible and beta.visible,
		"section changes continue past freed scene members")
	var removed_actor := Node3D.new()
	removed_actor.position = Vector3(20, 0, 20)
	world.add_child(removed_actor)
	var actor := Node3D.new()
	actor.position = Vector3(20, 0, 20)
	world.add_child(actor)
	sections.cull_dynamic([removed_actor, actor])
	_expect(not removed_actor.visible and not actor.visible,
		"both actors are tracked when hidden outside the current section")
	var stale: Variant = removed_actor
	removed_actor.free()
	actor.visible = true
	sections.cull_dynamic([stale, actor])
	_expect(not actor.visible, "a freed dynamic input does not stop later actor culling")
	sections.reset()
	_expect(not sections.is_active() and sections.current_section().is_empty(),
		"reset clears state after static and culled dynamic members were freed")
	_expect(alpha.visible and beta.visible and actor.visible,
		"reset restores surviving members and actors after stale references")
	# Leaving a secret can free the entire world before the next configure.
	sections.configure(manifest, world)
	sections.update(Vector3(20, 0, 20), true)
	world.free()
	var next_world := Node3D.new()
	root.add_child(next_world)
	_expect(sections.configure(plain, next_world) == 0 and not sections.is_active(),
		"entering an ordinary map safely resets a freed secret scene")
	var next_beta := MeshInstance3D.new()
	next_beta.name = "Build_beta_new_visit"
	next_world.add_child(next_beta)
	_expect(sections.configure(manifest, next_world) == 1,
		"reentering a secret indexes only the new scene")
	sections.update(Vector3(20, 0, 20), true)
	_expect(not next_beta.visible, "section culling works again after reentry")
	sections.reset()
	next_world.free()


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures += 1
	push_error("FAIL: " + message)
