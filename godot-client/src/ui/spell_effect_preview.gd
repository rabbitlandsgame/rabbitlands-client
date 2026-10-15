extends VBoxContainer
## A local demonstration of the catalog's production effect, in its own world.
## No actors, packets or gameplay state are created or changed by this view.
const LOOP_SECONDS := 2.1

var viewport: SubViewport
var stage: Node3D
var effects: Node3D
var power_level := 1
var definition: Dictionary = {}
var clock := 0.0
var _camera: Camera3D
var _figures: Node3D
var _caption: Label
var _empty: Label
var _view: SubViewportContainer

func _ready() -> void:
	name = "SpellEffectPreview"
	custom_minimum_size = Vector2(208, 180)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_view = SubViewportContainer.new()
	_view.name = "EffectView"
	_view.stretch = true
	_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_view.hide()
	add_child(_view)
	_empty = Label.new()
	_empty.text = "Select a spell\nto preview its effect"
	_empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_empty.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_empty.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_empty)
	_caption = Label.new()
	_caption.name = "PreviewCaption"
	_caption.text = "Effect preview"
	_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_caption.add_theme_font_size_override("font_size", 12)
	add_child(_caption)
	visibility_changed.connect(_update_visibility)
	set_process(false)

func set_spell(spell: Dictionary, power: int) -> void:
	var tier := clampi(power, 1, 10)
	if definition == spell and power_level == tier:
		return
	definition = spell.duplicate(true)
	power_level = tier
	_empty.visible = definition.is_empty()
	_view.visible = not definition.is_empty()
	_caption.text = "Effect preview" if definition.is_empty() else "%s · Power %d" % [
		str(definition.get("scope", "self")).capitalize(), power_level]
	_update_visibility()

func _update_visibility() -> void:
	var active := is_visible_in_tree() and not definition.is_empty()
	set_process(active)
	if active and viewport == null:
		_build_stage()
	if viewport == null:
		return
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if active else SubViewport.UPDATE_DISABLED
	stage.process_mode = Node.PROCESS_MODE_INHERIT if active else Node.PROCESS_MODE_DISABLED
	_clear_effects()
	if active:
		_arrange_stage()
		replay()

func _build_stage() -> void:
	viewport = SubViewport.new()
	viewport.name = "PreviewWorld"
	viewport.own_world_3d = true
	viewport.handle_input_locally = false
	viewport.gui_disable_input = true
	viewport.msaa_3d = Viewport.MSAA_2X
	_view.add_child(viewport)
	stage = Node3D.new()
	viewport.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("111c29")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b2c8df")
	environment.environment.ambient_light_energy = 0.8
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -25, 0)
	stage.add_child(light)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	stage.add_child(_camera)
	_camera.position = Vector3(0, 5.8, 9)
	_camera.look_at(Vector3(0, 0.6, 0))
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(24, 18)
	_add_mesh(stage, floor_mesh, Vector3(0, -0.035, 0), Color("1d2c3b"))
	_figures = Node3D.new()
	_figures.name = "PreviewFigures"
	stage.add_child(_figures)
	effects = Node3D.new()
	effects.name = "PreviewEffects"
	stage.add_child(effects)

func _arrange_stage() -> void:
	for child in _figures.get_children():
		child.free()
	var scope := str(definition.get("scope", "self"))
	_camera.size = maxf(6.8, 4.8 + SpellPresentation.power_radius(power_level) * 2.0)
	if scope == "target":
		_add_figure(Vector3(-1.7, 0, 0), Color("93bbd1"))
		_add_figure(Vector3(1.7, 0, 0), Color("ccab82"))
	elif scope == "burst":
		_camera.size = maxf(_camera.size, 10.8)
		_add_figure(Vector3(-3.8, 0, 0), Color("93bbd1"))
		for point: Vector3 in [Vector3(0.3, 0, 0.4), Vector3(2.0, 0, -0.6), Vector3(2.8, 0, 0.7)]:
			_add_figure(point, Color("ccab82"))
	elif scope == "allies":
		for point: Vector3 in [Vector3.ZERO, Vector3(-1.5, 0, -0.6), Vector3(1.5, 0, -0.6)]:
			_add_figure(point, Color("93bbd1"))
	else:
		_add_figure(Vector3.ZERO, Color("93bbd1"))

func _add_mesh(parent: Node3D, mesh: Mesh, at: Vector3, color: Color) -> void:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = at
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.85
	instance.material_override = material
	parent.add_child(instance)

func _add_figure(at: Vector3, color: Color) -> void:
	var figure := Node3D.new()
	figure.position = at
	_figures.add_child(figure)
	var body := CapsuleMesh.new()
	body.radius = 0.19
	body.height = 0.85
	_add_mesh(figure, body, Vector3.UP * 0.65, color)
	var head := SphereMesh.new()
	head.radius = 0.16
	head.height = 0.32
	_add_mesh(figure, head, Vector3.UP * 1.28, color.lightened(0.15))
	var base := CylinderMesh.new()
	base.top_radius = 0.4
	base.bottom_radius = 0.44
	base.height = 0.06
	_add_mesh(figure, base, Vector3.UP * 0.015, color.darkened(0.6))

func _clear_effects() -> void:
	if effects != null:
		for child in effects.get_children():
			child.free()

func replay() -> void:
	clock = 0.0
	if viewport == null or not is_visible_in_tree() or definition.is_empty():
		return
	_clear_effects()
	var scope := str(definition.get("scope", "self"))
	var visual := int(definition.get("visual", -1))
	if visual < 0:
		return
	if scope == "target":
		_add_effect(visual, Vector3(-1.7, 0, 0), Vector3(1.7, 0, 0))
	elif scope == "burst":
		var effect := _add_effect(visual, Vector3(1.5, 0, 0))
		effect.configure_area(2.5, scope)
	elif scope == "allies":
		for figure: Node3D in _figures.get_children():
			_add_effect(visual, figure.position)
	else:
		_add_effect(visual, Vector3.ZERO)

func _add_effect(visual: int, origin: Vector3, target: Variant = null) -> WorldEffect3D:
	var effect := WorldEffect3D.new()
	effects.add_child(effect)
	effect.configure(visual, origin, target, power_level)
	return effect

func _process(delta: float) -> void:
	clock += delta
	if clock >= LOOP_SECONDS:
		replay()
