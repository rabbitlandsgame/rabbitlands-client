extends SceneTree
## Render regression evidence through work-output/gpu_lock.sh (one window).
## ELORIA_ARTIFACT_DIR is required. Optional ELORIA_GRIP_MODELS/KITS/ACTIONS
## are comma-separated filters; ELORIA_GRIP_BODIES points to raw candidates.
## Use isolated APPDATA/LOCALAPPDATA. Default: 16 bodies, four kits, three
## actions, full-body and both hand views at clip time 0.5.

const KITS := {
    "vanguard": {0:114,1:106,2:105,3:134,4:220,5:209,6:249},
    "ranger": {0:164,3:159,4:230,5:225,6:226},
    "arcanist": {0:142,3:115,4:185,5:222,6:198},
    "warden": {0:163,2:100,3:122,4:176,5:189,6:205},
}

func _init() -> void:
    call_deferred("run")

func run() -> void:
    root.size = Vector2i(900,700)
    var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
    if output.is_empty():
        push_error("Set ELORIA_ARTIFACT_DIR to a scratch output directory")
        quit(1)
        return
    DirAccess.make_dir_recursive_absolute(output)
    var bodies := OS.get_environment("ELORIA_GRIP_BODIES")
    var selection := OS.get_environment("ELORIA_GRIP_MODELS")
    var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
    var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
    var env := WorldEnvironment.new()
    env.environment = Environment.new()
    env.environment.background_mode = Environment.BG_COLOR
    env.environment.background_color = Color(0.15,0.17,0.20)
    env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.environment.ambient_light_color = Color.WHITE
    env.environment.ambient_light_energy = 0.8
    root.add_child(env)
    var light := DirectionalLight3D.new()
    light.rotation_degrees = Vector3(-35,-45,0)
    root.add_child(light)
    var fill := DirectionalLight3D.new()
    fill.rotation_degrees = Vector3(-20,130,0)
    fill.light_energy = 0.7
    root.add_child(fill)
    var camera := Camera3D.new()
    root.add_child(camera)
    camera.current = true
    camera.fov = 30
    for option: Dictionary in models.creationOptions:
        var slug := str(option.model)
        if not selection.is_empty() and not slug in selection.split(","):
            continue
        var model: Dictionary = models.models[slug].duplicate(true)
        if not bodies.is_empty():
            var candidate := bodies.path_join(slug + ".glb")
            if FileAccess.file_exists(candidate):
                model.scene = candidate
        var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(model.animationMap))
        for kit: String in KITS:
            var kit_selection := OS.get_environment("ELORIA_GRIP_KITS")
            if not kit_selection.is_empty() and not kit in kit_selection.split(","):
                continue
            var actor := ReplicatedActor3D.new()
            root.add_child(actor)
            var errors := actor.configure({"actor_id":901,"x":0,"y":0,"rotation":0,"appearance":{},"equipment_visuals":KITS[kit]},CoordinateAdapter.new({"walkingHeight":0.0}),model,animation,equipment)
            if not errors.is_empty():
                push_error(str(errors))
                quit(1)
                return
            actor.position = Vector3.ZERO
            actor.rotation = Vector3.ZERO
            actor.set_physics_process(false)
            actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
            var actions := OS.get_environment("ELORIA_GRIP_ACTIONS")
            if actions.is_empty():
                actions = "idle,combat_idle,walk"
            for action_name: String in actions.split(","):
                var action := StringName(action_name)
                actor.play_action(action,true)
                actor.animation_player.advance(0.5)
                actor._advance_facing_offset(1.0)
                for frame: int in 8:
                    await process_frame
                var skeleton := actor.get_skeleton()
                var hand: Vector3 = actor._equipment_nodes[0][0].global_position
                if kit == "ranger":
                    hand = actor.combat_presentation.bow.global_position
                for view: String in ["full","front","side"]:
                    var centre := Vector3(0,0.95,0) if view=="full" else hand + Vector3(0,-0.025,0)
                    var offset := Vector3(-2,1.1,-3.8) if view=="full" else (Vector3(0,0.03,-0.48) if view=="front" else Vector3(-0.42 if kit=="ranger" else 0.42,-0.04,-0.24))
                    camera.position = centre+offset
                    camera.look_at(centre)
                    for frame: int in 2:
                        await process_frame
                    await RenderingServer.frame_post_draw
                    var name := "%s-%s-%s-%s.png" % [slug,kit,action,view]
                    root.get_texture().get_image().save_png(output.path_join(name))
                print("GRIP_RENDER ",slug," ",kit," ",action)
            actor.queue_free()
            await process_frame
    NativeAnimationImporter.clear()
    quit()