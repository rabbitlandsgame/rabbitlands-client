extends SceneTree
## Focused runtime checks for the first equipment-review corrections.
const Strap := preload("res://src/actors/quiver_strap_fit.gd")
var failures: Array[String] = []
var checks := 0
func _init() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)
		push_error(label)
func read_json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary
func run() -> void:
	var models: Dictionary = read_json("res://data/actors/models.json").models
	var equipment := read_json("res://data/actors/equipment.json")
	for race: String in ["luminous", "votary", "glasswarden", "orun", "greyhaven", "ssarathi", "stoneborn", "mycelari"]:
		for sex: String in ["male", "female"]:
			var name := race + "_" + sex
			var config: Dictionary = models[name].duplicate(true)
			config["hairStyles"] = []
			var actor := ReplicatedActor3D.new()
			root.add_child(actor)
			var errors := actor.configure({"actor_id":9040,"x":0,"y":0,"rotation":0,"kind":1,
				"name":"","appearance":{"skin":0},"equipment_visuals":{}},
				CoordinateAdapter.new({"walkingHeight":0.0}),config,
				read_json(str(config.get("animationMap","res://data/animations/luminous.json"))),equipment)
			check(errors.is_empty(), name + " configures")
			actor.set_process(false)
			actor.set_physics_process(false)
			actor.apply_equipment_visuals({0:164,3:115,4:230,5:225,6:226,8:1})
			actor.play_action(&"idle",true)
			actor.animation_player.advance(0.3)
			actor.animation_player.pause()
			await process_frame
			# Headless rendering does not advance skeleton modifiers. Exercise
			# the actual carry modifier after the animation pose, as the renderer
			# does, before reading the wrist-owned bow grip.
			actor._weapon_carry._process_modification_with_delta(1.0/60.0)
			actor.combat_presentation.update_pose()
			var bow := actor.combat_presentation.bow
			check(bow != null and bow.global_basis.y.normalized().dot(actor.global_basis.y.normalized())>.50
				and bow.global_basis.y.normalized().dot(-actor.global_basis.z.normalized())>.50,
				name + " carries the idle bow diagonally forward and up")
			for action: StringName in [&"ranged_draw", &"ranged_hold", &"ranged_attack", &"idle"]:
				actor.play_action(action,true)
				actor.animation_player.advance(0.3)
				actor.animation_player.pause()
				actor.combat_presentation.update_pose()
				check(bow.global_position.is_finite(), name + " finite bow after " + str(action))
			for torso: int in [210,211,232,234,238,242]:
				actor.apply_equipment_visuals({5:torso})
				var skins := []
				for piece: Node in actor._equipment_nodes.get(5,[]):
					if piece.has_meta("equipment_forearm_skin"): skins.append(piece)
				check(skins.size()==1,name+" torso %d has one exposed forearm surface"%torso)
				if not skins.is_empty():
					actor.apply_appearance_variants({"skin":4})
					var body := actor._native_model.find_child("body", true, false) as MeshInstance3D
					check(skins[0].material_override == body.get_active_material(0),
						name+" forearm shares the native hands' calibrated skin material")
			if race=="luminous":
				actor.apply_equipment_visuals({2:100,3:122,4:172,5:188,6:193})
				actor.set_cape_cloth_allowed(true)
				actor.play_action(&"idle",true)
				actor.animation_player.advance(.3)
				actor.animation_player.pause()
				await process_frame
				var cloth := actor.get_skeleton().get_node_or_null("CapeCloth")
				check(cloth != null,name+" has cloth")
				if cloth != null:
					cloth.active = false
					cloth.reset()
					for i in range(180): cloth._process_modification_with_delta(1.0/60.0)
					var fixed: Array = cloth._points.duplicate(true)
					cloth.reset()
					for i in range(90):
						cloth._process_modification_with_delta(1.0/120.0)
						cloth._process_modification_with_delta(3.0/120.0)
					var drift := 0.0
					for chain: int in range(fixed.size()):
						for i: int in range(fixed[chain].size()):
							drift=maxf(drift,(fixed[chain][i] as Vector3).distance_to(cloth._points[chain][i]))
					check(drift<.00001,name+" idle cape is independent of display cadence: %.6f m"%drift)
					var settled: Array = cloth._points.duplicate(true)
					for i in range(120): cloth._process_modification_with_delta(1.0/60.0)
					var movement := 0.0
					for chain: int in range(settled.size()):
						for i: int in range(settled[chain].size()):
							movement=maxf(movement,(settled[chain][i] as Vector3).distance_to(cloth._points[chain][i]))
					check(movement<.004,name+" idle cape settles: %.6f m"%movement)
					print("CAPE_MEASURE ", name, " cadence_difference_m=", drift, " settled_movement_m=", movement)
					# Skeleton modifiers receive the animation's input pose again
					# each display frame, including frames without a physics step.
					var held := {}
					var skeleton := actor.get_skeleton()
					for chain: PackedInt32Array in cloth._bones:
						for bone: int in chain:
							held[bone]=skeleton.get_bone_pose(bone)
							skeleton.reset_bone_pose(bone)
					cloth._process_modification_with_delta(1.0/120.0)
					var retained := true
					for bone: int in held:
						retained=retained and (held[bone] as Transform3D).is_equal_approx(skeleton.get_bone_pose(bone))
					check(retained,name+" retains settled cape between simulation steps")
					actor.position=Vector3.ZERO
					cloth.reset()
					for i in range(180):
						actor.position.z+=1.7/60.0
						cloth._process_modification_with_delta(1.0/60.0)
					var moving: Array=cloth._points.duplicate(true)
					actor.position=Vector3.ZERO
					cloth.reset()
					for i in range(90):
						actor.position.z+=1.7/120.0
						cloth._process_modification_with_delta(1.0/120.0)
						actor.position.z+=1.7*3.0/120.0
						cloth._process_modification_with_delta(3.0/120.0)
					var moving_drift:=0.0
					for chain: int in range(moving.size()):
						for i: int in range(moving[chain].size()):
							moving_drift=maxf(moving_drift,(moving[chain][i] as Vector3).distance_to(cloth._points[chain][i]))
					check(moving_drift<.035,name+" moving cape tolerates mixed display cadence: %.6f m"%moving_drift)
					print("CAPE_MOVING_MEASURE ",name," cadence_difference_m=",moving_drift)
			actor.queue_free()
			await process_frame
			print("FIT_BODY_OK ", name)
	print("EQUIPMENT_REVIEW_FIT ", checks," checks; failures=",failures)
	quit(0 if failures.is_empty() else 1)
