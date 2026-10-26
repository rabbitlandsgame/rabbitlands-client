extends SceneTree
## Fixed physical fingertip/palm landmarks on the imported Human meshes.
## Compare the actual four-weight surface, including vertices partly owned by
## the hand, rather than claiming closure from animated bone-tip positions.
const HAND := preload("res://src/actors/human_hand_pose.gd")
const POLISH := preload("res://src/actors/human_locomotion_polish.gd")
var checks := 0
var failures := 0
var metrics: Array = []

func _init() -> void: run.call_deferred()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func snapshot(animation: Animation) -> Array:
	var values: Array = [animation.length, animation.loop_mode, animation.step]
	for marker: StringName in animation.get_marker_names():
		values.append([marker, animation.get_marker_time(marker), animation.get_marker_color(marker)])
	for track: int in animation.get_track_count():
		var row: Array = [animation.track_get_path(track), animation.track_get_type(track),
			animation.track_get_interpolation_type(track), animation.track_get_interpolation_loop_wrap(track), animation.track_is_enabled(track)]
		for key: int in animation.track_get_key_count(track):
			row.append([animation.track_get_key_time(track,key), animation.track_get_key_value(track,key), animation.track_get_key_transition(track,key)])
		values.append(row)
	return values

func copy_clip(source: Animation) -> Animation:
	var result := Animation.new()
	result.length = source.length; result.loop_mode = source.loop_mode; result.step = source.step
	for track: int in source.get_track_count(): source.copy_track(track,result)
	for marker: StringName in source.get_marker_names():
		result.add_marker(marker,source.get_marker_time(marker)); result.set_marker_color(marker,source.get_marker_color(marker))
	return result

func asset_snapshot(mesh: MeshInstance3D, rig: Skeleton3D) -> Array:
	var values: Array = []
	for surface: int in mesh.mesh.get_surface_count():
		values.append(var_to_bytes(mesh.mesh.surface_get_arrays(surface)))
	for bind: int in mesh.skin.get_bind_count():
		values.append([mesh.skin.get_bind_name(bind),mesh.skin.get_bind_bone(bind),mesh.skin.get_bind_pose(bind)])
	for bone: int in rig.get_bone_count():
		values.append([rig.get_bone_name(bone),rig.get_bone_parent(bone),rig.get_bone_rest(bone)])
	return values

func entries(mesh: MeshInstance3D, rig: Skeleton3D, vertices: Array) -> Array:
	var arrays := mesh.mesh.surface_get_arrays(0)
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var influences: int = joints.size()/points.size()
	var result: Array = []
	for vertex: int in vertices:
		expect(vertex >= 0 and vertex < points.size(), "fixed physical hand vertex remains available")
		var row: Array = []
		for slot: int in influences:
			var index := vertex*influences+slot
			if weights[index] <= 0: continue
			var bind := joints[index]
			var bone := rig.find_bone(mesh.skin.get_bind_name(bind)) if mesh.skin.get_bind_name(bind) != &"" else mesh.skin.get_bind_bone(bind)
			row.append([bone,mesh.skin.get_bind_pose(bind)*points[vertex],weights[index]])
		result.append(row)
	return result

func centroid(samples: Array, rig: Skeleton3D, hand: int, rest := false) -> Vector3:
	var result := Vector3.ZERO
	for vertex: Array in samples:
		for entry: Array in vertex:
			var transform := rig.get_bone_global_rest(entry[0]) if rest else rig.get_bone_global_pose(entry[0])
			result += (transform*(entry[1] as Vector3))*float(entry[2])
	result /= float(samples.size())
	var transform := rig.get_bone_global_rest(hand) if rest else rig.get_bone_global_pose(hand)
	return transform.affine_inverse()*result

func protected_keys(seed: Animation, result: Animation, sex: String) -> void:
	var pose := HAND.pose_for(sex)
	expect(result.length == seed.length and result.loop_mode == seed.loop_mode and result.step == seed.step, "duration, loop and playback cadence remain exact")
	expect(result.get_track_count() == seed.get_track_count(), "running hand pose adds no tracks")
	expect(result.get_marker_names() == seed.get_marker_names(), "action marker names remain exact")
	for marker: StringName in seed.get_marker_names():
		expect(result.get_marker_time(marker) == seed.get_marker_time(marker), "action event time remains exact")
	for track: int in seed.get_track_count():
		var name := str(seed.track_get_path(track).get_concatenated_subnames()).get_slice(":",0)
		var permitted := seed.track_get_type(track) == Animation.TYPE_ROTATION_3D and pose.has(name)
		expect(result.track_get_path(track) == seed.track_get_path(track) and result.track_get_type(track) == seed.track_get_type(track), "track identity remains exact")
		expect(result.track_get_key_count(track) == seed.track_get_key_count(track), "original key count remains exact")
		expect(result.track_get_interpolation_type(track) == seed.track_get_interpolation_type(track) and result.track_get_interpolation_loop_wrap(track) == seed.track_get_interpolation_loop_wrap(track), "interpolation remains exact")
		for key: int in seed.track_get_key_count(track):
			expect(result.track_get_key_time(track,key) == seed.track_get_key_time(track,key) and result.track_get_key_transition(track,key) == seed.track_get_key_transition(track,key), "original key and transition times remain exact")
			if not permitted:
				expect(result.track_get_key_value(track,key) == seed.track_get_key_value(track,key), "all wrist, accepted arm, root, lower-body, position and scale keys remain exact")
			else:
				var q: Quaternion = result.track_get_key_value(track,key)
				expect(is_finite(q.x) and is_finite(q.y) and is_finite(q.z) and is_finite(q.w) and absf(q.length()-1.0)<0.00001, "finite normalized finger quaternion")
				if sex == "female" or name.begins_with("thumb_"):
					expect(absf(q.dot((pose[name] as Quaternion).normalized()))>0.999999, "female profile and thumb opposition remain complete")
				elif key == 0:
					var original: Quaternion = seed.track_get_key_value(track,key)
					var target: Quaternion = (pose[name] as Quaternion).normalized()
					var original_gap := original.angle_to(target)
					if original_gap > 0.01:
						expect(q.angle_to(target)>original_gap*0.12 and q.angle_to(target)<original_gap*0.18, "male nonthumb fold retains15percent of the accepted seed")
		if permitted:
			var first := result.rotation_track_interpolate(track,0.0)
			var last := result.rotation_track_interpolate(track,result.length)
			var relative := (first.inverse()*last).normalized()
			expect(Vector3(relative.x,relative.y,relative.z).length()<0.0001, "finger pose remains continuous at the run loop")

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	expect(HAND.pose_for("orun").is_empty(), "unknown anatomy receives no Human pose")
	var isolated := HAND.pose_for("male"); isolated.clear()
	expect(HAND.pose_for("male").size() == 30, "callers cannot mutate the shared authored profile")
	HAND.apply_to_clip(null,"male")
	for sex: String in ["male","female"]:
		var actor := ReplicatedActor3D.new(); actor.apply_render_quality(1,true); root.add_child(actor)
		var errors := actor.configure({"actor_id":9902,"actor_type":1 if sex=="male" else 0,"x":0,"y":0,"rotation":0,"kind":1,"name":"","appearance":{},"equipment_visuals":{}},
			CoordinateAdapter.new({"walkingHeight":0.0}),models["luminous_"+sex],animations,equipment)
		expect(errors.is_empty(), sex+" actual native actor loads")
		actor.set_process(false); actor.set_physics_process(false)
		var rig := actor.get_skeleton(); var player := actor.animation_player
		var source: AnimationLibrary = player.get_meta(POLISH.SOURCE_META)
		var untouched := {}
		for name: StringName in [&"Run_Female",&"Walk",&"Combat_Slash_A",&"Combat_Cast_Aggressive"]:
			if source.has_animation(name): untouched[name]=snapshot(source.get_animation(name))
		# Rebuild the accepted seed explicitly so this test remains independent
		# of whether the actor's integration hook has already baked new hands.
		var seed := POLISH._travel(source.get_animation(&"Run_Female"),true,POLISH._walking_hands(source.get_animation(&"Walk")))
		if sex == "male":
			POLISH._male_placement(seed,rig,true)
			POLISH._male_running_hands(seed,source.get_animation(&"Fighting_Idle"),rig)
		var candidate := copy_clip(seed)
		var unknown := copy_clip(seed); var unknown_before := snapshot(unknown)
		HAND.apply_to_clip(unknown,"orun")
		expect(snapshot(unknown) == unknown_before, "unknown profile preserves every channel")
		var mesh := actor.get_node("NativeModel").find_child("body",true,false) as MeshInstance3D
		var before_asset := asset_snapshot(mesh,rig)
		HAND.apply_to_clip(candidate,sex)
		protected_keys(seed,candidate,sex)
		var samples := {}; var targets := {}
		for side: String in ["l","r"]:
			var hand := rig.find_bone("hand_"+side); var sign := 1.0 if side=="l" else -1.0
			var landmarks: Dictionary = LANDMARKS[sex][side]
			samples[side]=[]; targets[side]=[]
			for group: Array in landmarks.caps: samples[side].append(entries(mesh,rig,group))
			for finger: int in range(4):
				var pad := centroid(entries(mesh,rig,landmarks.palms[finger]),rig,hand,true)
				var tip := centroid(samples[side][finger],rig,hand,true)
				targets[side].append(Vector3(pad.x+sign*0.012,0.087,tip.z))
			var target: Array = landmarks.thumb_target
			targets[side].append(Vector3(target[0],target[1],target[2]))
		player.remove_animation_library(&"")
		var library := AnimationLibrary.new(); library.add_animation(&"Seed",seed); library.add_animation(&"Hands",candidate); player.add_animation_library(&"",library)
		for phase: float in [0.0,0.25,0.5,0.75,1.0]:
			var distances := {}; var protected := {}
			for variant: StringName in [&"Seed",&"Hands"]:
				player.play(variant); player.pause(); player.seek(seed.length*phase,true); rig.force_update_all_bone_transforms()
				distances[variant]={}; protected[variant]=[]
				for name: String in ["upperarm_l","upperarm_r","lowerarm_l","lowerarm_r","hand_l","hand_r","pelvis","foot_l","foot_r"]:
					protected[variant].append(rig.get_bone_global_pose(rig.find_bone(name)))
				for side: String in ["l","r"]:
					var hand := rig.find_bone("hand_"+side); var values: Array = []
					for finger: int in range(5): values.append(centroid(samples[side][finger],rig,hand).distance_to(targets[side][finger]))
					distances[variant][side]=values
			expect(protected[&"Seed"] == protected[&"Hands"], "sampled accepted upperarms, elbows, wrists and lowerbody stay exactly unchanged")
			for side: String in ["l","r"]:
				var before: Array = distances[&"Seed"][side]; var after: Array = distances[&"Hands"][side]
				var old_mean := (float(before[0])+float(before[1])+float(before[2])+float(before[3]))/4.0
				var new_mean := (float(after[0])+float(after[1])+float(after[2])+float(after[3]))/4.0
				expect(new_mean < old_mean*0.93, "fixed physical fingertip caps fold closer to the loose palm pocket "+sex+side)
				expect(float(after[4]) < float(before[4])+0.001, "actual thumb opposition improves without a new tip-to-tip pinch target")
				metrics.append({"sex":sex,"side":side,"phase":phase,"baseline_tip_gap_m":old_mean,"new_tip_gap_m":new_mean,"thumb_before_m":before[4],"thumb_after_m":after[4]})
		expect(asset_snapshot(mesh,rig) == before_asset, "all mesh arrays, skin weights/binds and skeleton rest hierarchy remain exact")
		for name: StringName in untouched: expect(snapshot(source.get_animation(name)) == untouched[name], "shared source run, walk, attack and cast clips remain immutable")
		actor.free(); await process_frame
	var destination := OS.get_environment("RL_HUMAN_HAND_METRICS")
	if not destination.is_empty(): FileAccess.open(destination,FileAccess.WRITE).store_string(JSON.stringify({"checks":checks,"failures":failures,"metrics":metrics},"  "))
	print("Human hand pose: %d checks, %d failures" % [checks,failures])
	quit(1 if failures else 0)
# Fixed reviewed cap/palm vertex IDs on the current native Human body surfaces.
const LANDMARKS := {
	"female": {
		"l": {
			"caps": [
				[3272, 3285, 3303, 3305, 3310, 3317, 3304, 3306, 3316, 3323, 3328, 3337, 3335, 3315, 3322, 3338, 3339, 3344, 3334, 3309, 3345, 3336],
				[3259, 3300, 3347, 3340, 3346, 3349, 3350, 3353, 3351, 3341, 3355, 3356, 3357, 3348, 3359, 3352, 3358, 3354],
				[3289, 3297, 3298, 3308, 3307, 3318, 3311, 3290, 3314, 3326, 3327, 3312, 3333, 3342, 3343],
				[3107, 3125, 3146, 3162, 3166, 3187, 3186, 3197, 3124, 3207, 3218, 3212, 3161, 3211, 3216, 3165, 3210, 3145, 3235, 3217],
				[2834, 2848, 2867, 2872, 2868, 2875, 2874, 2890, 2905, 2835, 2912, 2913, 2961, 2930, 2931, 2934, 2927, 2958, 2951, 2949, 2968, 2925, 2950, 2926, 2932, 2981, 2933, 2980, 2969],
			],
			"palms": [
				[2637, 2643, 2648, 2647, 2661, 2670, 2674, 2675, 2677, 2644, 2691, 2693, 2704, 2752, 2710, 2731, 2748, 2711, 2732, 2638, 2751, 2769, 2770, 2747, 2660, 2730, 2775, 2768, 2776, 2801, 2802, 2800, 2806, 2852, 2866],
				[2626, 2627, 2641, 2640, 2785, 2784, 2812, 2813, 2855, 2856],
				[2636, 2614, 2633, 2697, 2703, 2831, 2698, 2791, 2790, 2807, 2832, 2825, 2833, 2808, 2826],
				[2614, 2633, 2622, 2689, 2697, 2760, 2623, 2690, 2779, 2698, 2791, 2778, 2790, 2827],
			],
			"thumb_target": [0.033401328273748906, 0.096, 0.046]
		},
		"r": {
			"caps": [
				[34, 36, 37, 35, 33, 38, 49, 53, 47, 54, 62, 61, 39, 64, 66, 68, 76, 63, 48, 65, 67],
				[0, 1, 2, 3, 5, 6, 7, 9, 11, 10, 13, 16, 14, 18, 4, 8, 12, 15, 17],
				[42, 46, 45, 52, 56, 57, 60, 55, 58, 71, 59],
				[198, 197, 201, 205, 209, 214, 208, 200, 196, 211, 203, 212, 199, 217, 204, 222, 221, 213, 207, 223, 202],
				[533, 3396, 3397, 532, 531, 3398, 534, 540, 557, 3399, 541, 3400, 542, 3401, 551, 3402, 546, 558],
			],
			"palms": [
				[577, 600, 601, 667, 639, 642, 624, 644, 656, 675, 680, 622, 684, 714, 623, 743, 749, 767, 766, 785, 791, 713, 790, 712],
				[606, 592, 584, 605, 583, 607, 663, 714, 725, 726, 713, 712],
				[576, 606, 591, 594, 603, 605, 607, 650, 649, 575, 663, 692, 703, 702, 747, 737],
				[564, 585, 651, 594, 597, 657, 703, 707, 717, 742, 702, 716, 750, 706, 741, 715],
			],
			"thumb_target": [-0.03259065353872251, 0.096, 0.049]
		},
	},
	"male": {
		"l": {
			"caps": [
				[539, 604, 607, 609, 611, 606, 612, 615, 616, 618, 602, 617, 629, 603, 631, 610, 635, 538, 639, 619, 608, 628, 636, 638, 637, 630, 634],
				[595, 596, 651, 666, 671, 670, 675, 674, 676, 594, 678, 680, 684, 686, 685, 682, 597, 652, 679, 677, 681, 687, 665, 683, 688, 691, 690, 689],
				[588, 613, 622, 623, 624, 633, 632, 641, 614, 642, 654, 640, 656, 657, 660, 653, 662, 587, 621, 667, 668, 669, 659, 663, 672, 673, 658, 655, 661, 664],
				[473, 489, 497, 498, 507, 510, 491, 525, 526, 524, 527, 528, 530, 522, 490, 544, 545, 551, 554, 543, 547, 523, 529, 546, 566, 565, 552, 563, 540, 542, 564, 553, 541],
				[295, 303, 309, 301, 308, 312, 296, 314, 316, 313, 302, 315, 297],
			],
			"palms": [
				[142, 150, 149, 176, 181, 185, 184, 215, 230, 231, 288, 289, 182, 287],
				[148, 147, 172, 200, 209, 199, 236, 239, 253, 254, 240, 271, 242, 255, 399, 243, 237, 324, 272, 326, 238, 241, 325],
				[139, 141, 166, 165, 216, 374, 167, 217, 382, 385, 376, 273, 390, 398, 375, 397, 274],
				[144, 146, 367, 369, 143, 366, 374, 376, 398, 370, 375, 397, 145],
			],
			"thumb_target": [0.022769274211070552, 0.096, 0.027999999999999997]
		},
		"r": {
			"caps": [
				[3277, 3280, 3278, 3286, 3287, 3276, 3289, 3291, 3294, 3295, 3298, 3301, 3305, 3307, 3306, 3279, 3292, 3310, 3288, 3290, 3293, 3321, 3296, 3309, 3297, 3300, 3299, 3302, 3308, 3303, 3304],
				[3181, 3186, 3184, 3187, 3188, 3190, 3185, 3192, 3183, 3193, 3195, 3191, 3182, 3196, 3194, 3189, 3200, 3204, 3205, 3207, 3206, 3202, 3201, 3208, 3203],
				[3227, 3228, 3226, 3241, 3246, 3247, 3250, 3252, 3255, 3258, 3254, 3256, 3249, 3225, 3240, 3248, 3245, 3253, 3257, 3251],
				[3363, 3366, 3364, 3367, 3371, 3365, 3373, 3377, 3378, 3399, 3401, 3402, 3372, 3400, 3397, 3370, 3398],
				[2985, 2990, 2986, 2992, 2987, 2996, 2997, 2998, 2988, 2989, 2991],
			],
			"palms": [
				[2915, 2914, 2963, 2912, 3058, 2964, 3103, 2913, 3116, 3102, 2962, 3117],
				[3427, 3428, 2970, 2966, 3031, 2973, 2965, 2971, 2969, 2972, 2967, 3033, 3032, 2974, 2968, 3035, 3034, 3072, 2975, 3073, 3082, 3071, 3096, 3097],
				[3463, 3467, 3466, 3487, 3486, 3465, 3464, 3503, 3094, 3488, 3095, 3138, 3489, 3504, 3139],
				[3481, 3487, 3486, 3482, 3150, 3149, 3488, 3489, 3140, 3141, 3151],
			],
			"thumb_target": [-0.023422397299610938, 0.096, 0.066]
		},
	},
}
