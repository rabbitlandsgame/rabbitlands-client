extends Node3D

const Quest = preload("res://quest_state.gd")
const MapCanvas = preload("res://route_map.gd")
const Art = preload("res://art_runtime.gd")
var q = Quest.new()
var nav := AStarGrid2D.new()
var camera: Camera3D
var player: Node3D
var marker: Node3D
var beacon_light: OmniLight3D
var beacon_flame: MeshInstance3D
var beam: MeshInstance3D
var boat: Node3D
var sky: Environment
var gates: Dictionary = {}
var labels: Dictionary = {}
var objective: Label
var hint: Label
var voice: Label
var status: Label
var chapter: Label
var toast: Label
var window: PanelContainer
var window_body: VBoxContainer
var map_canvas: Control
var window_kind := ""
var path: Array[Vector2i] = []
var pending_target := ""
var orbit := 0.5
var zoom := 28.0
var overview := false
var harvest_item := ""
var harvest_clock := 0.0
var fighting := false
var combat_clock := 0.0
var save_clock := 0.0
var time := 0.0
var help_button: Button
var nav_flags := ""
var art: Dictionary
var boar_visual: Node3D

func _ready() -> void:
	_build_world()
	_build_ui()
	q.changed.connect(_refresh)
	if OS.get_environment("LANTERN_FRESH") != "1":
		q.restore()
	_refresh()
	player.position = tile_position(Vector2i(q.state.tile[0], q.state.tile[1]))
	_update_camera(1.0)

func tile_position(t: Vector2i) -> Vector3:
	var idx: int = clampi(t.y, 0, 119)*120+clampi(t.x, 0, 119)
	return Vector3(t.x, float(q.layout.walkGrid[idx])*.2-2.2, -t.y)

func _build_world() -> void:
	var document := GLTFDocument.new()
	var gltf := GLTFState.new()
	var error := document.append_from_file(ProjectSettings.globalize_path("res://package/world.glb"), gltf)
	assert(error == OK, "The generated island package must load")
	Art.mipmaps(gltf)
	var island := document.generate_scene(gltf)
	art = JSON.parse_string(FileAccess.get_file_as_string("res://package/art.json"))
	add_child(island)
	for node: Node in island.get_children():
		if node is MeshInstance3D:
			for surface in range((node as MeshInstance3D).mesh.get_surface_count()):
				var mat := (node as MeshInstance3D).get_active_material(surface) as BaseMaterial3D
				if mat:
					# COLOR_0 supplies the grass/path blend and stone weathering.
					mat.vertex_color_use_as_albedo = true
					mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		if node is MeshInstance3D and str(node.name).begins_with("Walk_"):
			(node as MeshInstance3D).create_trimesh_collision()
		if node is MeshInstance3D and str(node.name).begins_with("Scenery_Water"):
			(node as MeshInstance3D).material_override = Art.water_material(q.layout)
	sky = Environment.new()
	sky.background_mode = Environment.BG_COLOR
	sky.background_color = Color("243e4b")
	sky.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	sky.ambient_light_color = Color("a7b5c0")
	sky.ambient_light_energy = .35
	sky.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	sky.tonemap_white = 6.0
	var env := WorldEnvironment.new()
	env.environment = sky
	add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_color = Color("c4d8e0")
	sun.light_energy = .8
	sun.shadow_enabled = true
	add_child(sun)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.far = 500
	add_child(camera)
	camera.current = true
	player = _person(Color("e8c17e"))
	player.name = "Player"
	add_child(player)
	var torch := OmniLight3D.new()
	torch.name = "Torch"
	torch.position = Vector3(.4, 1.5, -.3)
	torch.light_color = Color("ffc16b")
	torch.omni_range = 9
	torch.light_energy = 1.8
	player.add_child(torch)
	for id: String in ["nesh", "caldus", "dock"]:
		var person := _person(Color("678f92") if id == "nesh" else Color("a07965"))
		person.name = "Person_"+id
		person.position = tile_position(_tile(q.target(id).tile))
		add_child(person)
		if id == "nesh":
			var lamp := OmniLight3D.new()
			lamp.position.y = 2.0
			lamp.light_color = Color("ffc67e")
			lamp.light_energy = 2.0
			lamp.omni_range = 8
			person.add_child(lamp)
	boar_visual = Art.instantiate("boar")
	boar_visual.name = "Boar"
	boar_visual.position = tile_position(_tile(q.target("boar").tile))
	boar_visual.rotation.y = -.8
	add_child(boar_visual)
	Art.animate(boar_visual,"Idle_A")
	for spec: Array in [["reed", "reed", 1.0], ["quartz", "quartz", 1.5]]:
		var resource := Art.instantiate(spec[0])
		resource.name = "Resource_"+spec[0]
		resource.position = tile_position(_tile(q.target(spec[1]).tile))
		resource.scale = Vector3.ONE*float(spec[2])
		add_child(resource)
	for at: Array in art.lanterns:
		var lamp := OmniLight3D.new()
		lamp.position = Vector3(at[0],at[1],at[2])
		lamp.light_color = Color("ffbe73")
		lamp.light_energy = 1.25
		lamp.omni_range = 5
		add_child(lamp)
	for entry: Dictionary in q.layout.targets:
		var label := Label3D.new()
		label.text = entry.label
		label.font_size = 32
		label.pixel_size = .018
		label.outline_size = 7
		label.no_depth_test = true
		label.modulate = Color("dce6e6")
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = tile_position(_tile(entry.tile)) + Vector3(0, 2.7, 0)
		add_child(label)
		labels[entry.id] = label
	marker = Node3D.new()
	marker.name = "ActiveObjective"
	var ring := MeshInstance3D.new()
	var torus := TorusMesh.new()
	torus.inner_radius = .65
	torus.outer_radius = .95
	torus.rings = 24
	ring.mesh = torus
	ring.material_override = _material(Color("ffd484"), true)
	ring.position.y = .15
	marker.add_child(ring)
	var arrow := MeshInstance3D.new()
	var cone := CylinderMesh.new()
	cone.top_radius = .45
	cone.bottom_radius = 0
	cone.height = .7
	arrow.mesh = cone
	arrow.position.y = 3.5
	arrow.material_override = ring.material_override
	marker.add_child(arrow)
	add_child(marker)
	for gate: Dictionary in q.layout.gates:
		var root := Art.instantiate("gate")
		var placement: Dictionary = art.gatePlacements[str(gate.id)]
		root.position = Vector3(placement.position[0], placement.position[1], placement.position[2])
		root.scale = Vector3(placement.scale[0], placement.scale[1], placement.scale[2])
		var leaf := Node3D.new()
		root.add_child(leaf)
		for part: Node in root.get_children():
			if str(part.name).begins_with("GateLeaf"):
				part.owner = null
				root.remove_child(part)
				leaf.add_child(part)
		add_child(root)
		gates[gate.id] = leaf
	beacon_flame = _box(Vector3(1,2,1), Vector3(99,13,-101),Color("ffc475"))
	beacon_flame.material_override = _material(Color("ffc475"),true)
	add_child(beacon_flame)
	beacon_light = OmniLight3D.new()
	beacon_light.position = Vector3(99,12,-101)
	beacon_light.light_color = Color("ffd69b")
	beacon_light.light_energy = 5
	beacon_light.omni_range = 30
	add_child(beacon_light)
	beam = Art.light_beam()
	beam.position = Vector3(99,12.7,-101)
	add_child(beam)
	boat = Art.instantiate("boat")
	boat.position = Vector3(117,-.5,-70)
	add_child(boat)
	nav.region = Rect2i(0,0,120,120)
	nav.cell_size = Vector2.ONE
	nav.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	nav.update()

func _person(color: Color) -> Node3D:
	return Art.person(color)

func _material(color: Color, glow := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = .9
	if glow:
		m.emission_enabled = true
		m.emission = color
	return m

func _box(size: Vector3, at: Vector3, color: Color) -> MeshInstance3D:
	var box := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	box.mesh = mesh
	box.position = at
	box.material_override = _material(color)
	return box

func _style(background: Color, border := Color("41565d")) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(9)
	style.content_margin_left = 18
	style.content_margin_right = 18
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	return style

func _text(text: String, size := 18) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color",Color("e5e9e4"))
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return label

func _button(text: String, callback: Callable, parent: Node) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size.y = 39
	b.add_theme_font_size_override("font_size",16)
	b.add_theme_stylebox_override("normal",_style(Color("243a42")))
	b.add_theme_stylebox_override("hover",_style(Color("36545b"),Color("e7ba75")))
	b.pressed.connect(callback)
	parent.add_child(b)
	return b

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var screen := Control.new()
	screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(screen)
	var panel := PanelContainer.new()
	panel.position = Vector2(24,24)
	panel.size = Vector2(410,380)
	panel.add_theme_stylebox_override("panel",_style(Color(.055,.095,.12,.96)))
	screen.add_child(panel)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation",12)
	panel.add_child(col)
	col.add_child(_text("ELORIA  /  THE LAST LANTERN",17))
	chapter = _text("",13)
	chapter.add_theme_color_override("font_color",Color("dbb879"))
	col.add_child(chapter)
	objective = _text("",26)
	col.add_child(objective)
	hint = _text("",17)
	col.add_child(hint)
	voice = _text("",17)
	voice.add_theme_color_override("font_color",Color("9ec4c7"))
	col.add_child(voice)
	help_button = _button("Walk to the marker", _guide, col)
	var note := _text("PLAYABLE DRAFT · Local progress only\nSimplified combat, UI and progression",12)
	note.add_theme_color_override("font_color",Color("9baeb4"))
	col.add_child(note)
	var bottom := VBoxContainer.new()
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_left = 24
	bottom.offset_right = -24
	bottom.offset_top = -158
	bottom.offset_bottom = -22
	bottom.add_theme_constant_override("separation",8)
	screen.add_child(bottom)
	var toast_panel := PanelContainer.new()
	toast_panel.add_theme_stylebox_override("panel",_style(Color(.055,.095,.12,.96)))
	bottom.add_child(toast_panel)
	toast = _text("",16)
	toast_panel.add_child(toast)
	status = _text("",16)
	bottom.add_child(status)
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation",8)
	bottom.add_child(bar)
	for entry: Array in [["Map · Tab","map"],["Inventory · I","inventory"],["Manufacturing · C","craft"],
		["Statistics · P","stats"],["Quest · J","journal"]]:
		var kind: String = entry[1]
		_button(entry[0],func(): _open(kind),bar)
	_button("Overview · O",func(): overview = not overview,bar)
	_button("Restart draft",func(): _open("restart"),bar)
	window = PanelContainer.new()
	window.position = Vector2(510,60)
	window.size = Vector2(630, 300)
	window.add_theme_stylebox_override("panel",_style(Color(.065,.115,.14,.98),Color("779393")))
	screen.add_child(window)
	window_body = VBoxContainer.new()
	window_body.add_theme_constant_override("separation",9)
	window.add_child(window_body)
	window.hide()

func _tile(value: Array) -> Vector2i:
	return Vector2i(int(value[0]),int(value[1]))

func _refresh_nav() -> void:
	var signature := "%s/%s/%s" % [q.has_flag("crafted"), q.has_flag("prepared"), q.has_flag("lit")]
	if signature == nav_flags:
		return
	nav_flags = signature
	for y in range(120):
		for x in range(120):
			nav.set_point_solid(Vector2i(x,y),int(q.layout.walkGrid[y*120+x]) == 0)
	for gate: Dictionary in q.layout.gates:
		var opened: bool = q.has_flag(gate.requires)
		(gates[gate.id] as Node3D).visible = not opened
		if not opened:
			for y in range(int(gate.bounds[1]),int(gate.bounds[3])+1):
				for x in range(int(gate.bounds[0]),int(gate.bounds[2])+1):
					nav.set_point_solid(Vector2i(x,y),true)

func _refresh() -> void:
	var step: Dictionary = q.current()
	chapter.text = "SCENE %02d / 08   ·   LANTERN REACH   ·   120 × 120" % int(step.scene)
	objective.text = step.objective
	hint.text = step.hint
	voice.text = step.voice
	toast.text = q.message
	status.text = "Health %d/%d     Food %d     Gold %d     Pickpoints %d     Pack %d/%d (draft units)" % [
		q.state.health,q.state.max_health,q.state.food,q.state.gold,q.state.points,q.weight(),q.state.capacity]
	marker.position = tile_position(_tile(q.target(step.target).approach))
	marker.visible = not q.has_flag("departed")
	for id: String in labels:
		var label: Label3D = labels[id]
		if id == "housing":
			label.text = "The restored beacon" if q.has_flag("lit") else "The dark beacon"
		label.modulate = Color("ffe0a1") if id == step.target else Color("b2c6c9")
		label.visible = not overview and (id != "bag" or q.has_flag("defeated") and not q.has_flag("looted"))
		if id == "boar":
			label.visible = not overview and not q.has_flag("defeated")
	boar_visual.visible = not q.has_flag("defeated")
	(get_node("Person_caldus") as Node3D).visible = not q.has_flag("lit")
	(get_node("Person_dock") as Node3D).visible = q.has_flag("lit")
	(player.get_node("Torch") as OmniLight3D).visible = q.has_flag("crafted") and q.count("inventory","Torch") > 0
	beacon_light.visible = q.has_flag("lit")
	beacon_flame.visible = q.has_flag("lit")
	beam.visible = q.has_flag("lit")
	sky.ambient_light_energy = .6 if q.has_flag("lit") else .35
	_refresh_nav()
	q.save()
	if window.visible and window_kind != "map":
		_rebuild_window()
	if is_instance_valid(map_canvas):
		map_canvas.queue_redraw()
	help_button.text = "Four Gates handoff" if q.has_flag("departed") else "Walk to the marker"

func _guide() -> void:
	if q.has_flag("departed"):
		_open("complete")
		return
	var id: String = q.current().id
	if id == "map":
		_open("map")
	elif id in ["sword","shield","food"]:
		_open("inventory")
	elif id == "attribute":
		_open("stats")
	else:
		_go_target(q.current().target)

func _go_target(id: String) -> void:
	var entry: Dictionary = q.target(id)
	if entry.is_empty():
		return
	pending_target = id
	_walk(_tile(entry.approach), false)

func _walk(destination: Vector2i, cancel := true) -> void:
	if cancel:
		pending_target = ""
		fighting = false
		harvest_item = ""
	if not nav.is_in_boundsv(destination) or nav.is_point_solid(destination):
		q.message = "Water, walls or a closed gate block that tile. Follow the open path."
		toast.text = q.message
		return
	var route: Array[Vector2i] = nav.get_id_path(_tile(q.state.tile),destination)
	if route.is_empty():
		q.message = "Nesh: Finish this part first. I'll open the way when we're ready."
		toast.text = q.message
		pending_target = ""
		return
	path = route
	if path.size() > 0:
		path.pop_front()
	if path.is_empty() and not pending_target.is_empty():
		var id := pending_target
		pending_target = ""
		_interact(id)

func _interact(id: String) -> void:
	if not q.near(id):
		return
	match id:
		"nesh":
			q.move_to(_tile(q.state.tile))
		"caldus": _open("caldus")
		"chart":
			q.act("chart")
			_open("chart")
		"reed", "quartz":
			harvest_item = "Reed" if id == "reed" else "Quartz"
			harvest_clock = .6
		"lower_cache", "upper_cache", "dock_cache": _open("storage")
		"bench": _open("craft")
		"boar":
			if q.can_attack():
				fighting = true
				combat_clock = .7
			else:
				q.message = "Nesh: Put on your Sword and Shield first."
				toast.text = q.message
				_open("inventory")
		"bag": q.act("loot")
		"rest":
			q.move_to(_tile(q.state.tile))
			_open("stats" if q.current().id == "attribute" else "inventory")
		"housing": _open("beacon")
		"dock": _open("trade")
		"ferry": _open("departure")

func _open(kind: String) -> void:
	window_kind = kind
	window.show()
	if kind == "map":
		q.act("map")
	_rebuild_window()

func _do(action: String, item := "", amount := 1) -> void:
	q.act(action,item,amount)
	if action == "depart":
		_open("complete")

func _rebuild_window() -> void:
	for child: Node in window_body.get_children():
		window_body.remove_child(child)
		child.queue_free()
	map_canvas = null
	window.size.y = 0
	var titles := {"map":"The keeper's chart", "inventory":"Your pack", "storage":"The keeper's cache",
		"craft":"Manufacturing", "stats":"Statistics", "journal":"Quest log", "caldus":"A hand in the dark",
		"chart":"The keeper's route", "beacon":"The last lantern", "trade":"Caldus's galley counter",
		"departure":"The road is yours", "complete":"Keeper of the First Light", "restart":"Start another draft playthrough?"}
	window_body.add_child(_text(titles.get(window_kind,window_kind),25))
	match window_kind:
		"map":
			map_canvas = MapCanvas.new()
			map_canvas.set("q",q)
			map_canvas.custom_minimum_size = Vector2(580,580)
			window_body.add_child(map_canvas)
			window_body.add_child(_text("Gold: current objective · White: you · Gates open as the rescue progresses",14))
		"inventory":
			window_body.add_child(_text("Equipped: " + ", ".join(q.state.equipment),16))
			for item: String in q.state.inventory:
				var name := item
				var row := HBoxContainer.new()
				window_body.add_child(row)
				var label := _text("%d × %s" % [q.count("inventory",item),item],17)
				label.custom_minimum_size.x = 300
				row.add_child(label)
				if item in ["Sword","Shield"]:
					_button("Equip",func(): _do("equip",name),row)
				elif item == "Bread":
					_button("Eat",func(): _do("eat"),row)
			var auto := CheckBox.new()
			auto.text = "Auto-gather defeated creatures' loot"
			auto.button_pressed = q.state.auto_gather
			auto.toggled.connect(func(value): q.state.auto_gather = value; q.save())
			window_body.add_child(auto)
		"storage":
			if not q.near_cache():
				window_body.add_child(_text("Walk to one of the marked caches to use storage."))
			else:
				window_body.add_child(_text("All keeper caches share these contents. Required supplies cannot be discarded in this draft.",15))
				for bag: String in ["inventory","storage"]:
					window_body.add_child(_text("IN YOUR PACK" if bag == "inventory" else "IN THE CACHE",14))
					for item: String in q.state[bag]:
						var name := item
						var amount: int = q.count(bag,item)
						var action := "deposit" if bag == "inventory" else "withdraw"
						_button("%s %d × %s" % ["Deposit" if bag == "inventory" else "Withdraw",amount,name],
							func(): _do(action,name,amount),window_body)
		"craft":
			window_body.add_child(_text("TORCH\n1 Wood Plank + 1 Cloth Roll\nTool: Hatchet (kept)\nFood cost: 1",19))
			window_body.add_child(_text("Nesh helps this first attempt succeed. This recipe matches the current game.",15))
			_button("Make one Torch",func(): _do("craft"),window_body)
		"stats":
			window_body.add_child(_text("Experience: %d · Available pickpoints: %d" % [q.state.xp,q.state.points],18))
			window_body.add_child(_text("Choose the kind of traveler you want to become. Either choice opens the upper climb.",17))
			_button("Matter — more health",func(): _do("spend","Matter"),window_body)
			_button("Carry — more pack capacity",func(): _do("spend","Carry"),window_body)
			window_body.add_child(_text("Draft values: +5 maximum health or +10 pack units. Final progression tuning is still open.",13))
		"journal":
			window_body.add_child(_text(q.current().objective,21))
			window_body.add_child(_text(q.current().hint,17))
			window_body.add_child(_text("Completed objectives: %d / %d\nThe storm has no failure timer. Your last checkpoint saves automatically." % [q.state.history.size(),q.quest.steps.size()],16))
		"caldus":
			window_body.add_child(_text("“That boat will follow our light. There isn't a light.”\n\nCaldus hands you Bread, a Pickaxe, a Sword and a Shield. He cannot make the climb.",18))
			if not q.has_flag("supplied"):
				_button("I'll get it burning.",func(): _do("supply"); window.hide(),window_body)
				_button("Tell me what to do.",func(): _do("supply"); q.message = "Nesh: Start with the chart. I'll show you each step."; toast.text = q.message; window.hide(),window_body)
		"chart":
			window_body.add_child(_text("Garden: gather Reed and Quartz.\nShed: store the repairs and make a Torch.\nCauseway: clear the climb.\nBeacon: bring back the light.\nEastern stair: return to the saved boat.",19))
			_button("Open the map",func(): _open("map"),window_body)
		"beacon":
			window_body.add_child(_text("The shutters rattle. A quartz socket stands empty. The approaching boat rings its bell.",18))
			if not q.has_flag("repaired"):
				_button("Repair housing — 3 Reed + 1 Quartz",func(): _do("repair"),window_body)
			elif not q.has_flag("lit"):
				_button("Light it with your Torch",func(): _do("light"); window.hide(),window_body)
			else:
				window_body.add_child(_text("Your light is guiding them home. The eastern return stair is open.",20))
		"trade":
			window_body.add_child(_text("“Fresh meat for the galley? Take bread for the crossing.”",18))
			_button("Sell 1 Raw Meat · receive 10 gold",func(): _do("sell"),window_body)
			_button("Buy 1 Bread · pay 8 gold",func(): _do("buy"),window_body)
			window_body.add_child(_text("One galley order per rescue. Bread uses the game's existing 8-gold shop price.",14))
			_button("Use the dock cache",func(): _go_target("dock_cache"); window.hide(),window_body)
		"departure":
			window_body.add_child(_text("The boat you guided past the reef offers you a crossing. The grounded ferry remains on the western beach.",18))
			_button("Ready for Four Gates",func(): _do("depart"),window_body)
			_button("One more look",func(): window.hide(),window_body)
		"complete":
			window_body.add_child(_text("You got them home.",30))
			window_body.add_child(_text("Next: Talk to Gate Warden Ilyon\n\nIlyon: “Caldus sent word. Four Gates owes you a safe arrival. Nesh — let me see that seal.”",19))
			window_body.add_child(_text("End of playable draft. The production handoff will carry your ordinary kit forward once and suppress the old introductory tutorial.",16))
			_button("Look back at the restored island",func(): overview = true; window.hide(),window_body)
		"restart":
			window_body.add_child(_text("This resets only this local draft's progress. No live character is connected.",18))
			_button("Restart this draft",func(): path.clear(); pending_target = ""; harvest_item = ""; fighting = false; q.reset(); player.position = tile_position(_tile(q.state.tile)); window.hide(),window_body)
	_button("Close · Esc",func(): window.hide(),window_body)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_ESCAPE: window.hide()
			KEY_TAB, KEY_M: _open("map")
			KEY_I: _open("inventory")
			KEY_C: _open("craft")
			KEY_P: _open("stats")
			KEY_J: _open("journal")
			KEY_O: overview = not overview; _refresh()
			KEY_E: _guide()
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		orbit -= event.relative.x*.006
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			zoom = maxf(18,zoom-2)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			zoom = minf(65,zoom+2)
		elif event.button_index == MOUSE_BUTTON_LEFT and not window.visible:
			var closest := ""
			var best := 30.0
			for entry: Dictionary in q.layout.targets:
				if entry.id == "boar" and q.has_flag("defeated") or entry.id == "bag" and (not q.has_flag("defeated") or q.has_flag("looted")):
					continue
				var screen := camera.unproject_position(tile_position(_tile(entry.tile))+Vector3(0,.8,0))
				var d: float = screen.distance_to(event.position)
				if d < best:
					best = d
					closest = entry.id
			if not closest.is_empty():
				_go_target(closest)
			else:
				var start := camera.project_ray_origin(event.position)
				var end := start + camera.project_ray_normal(event.position)*400
				var result := get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(start,end))
				if result.has("position"):
					var hit: Vector3 = result.position
					_walk(Vector2i(roundi(hit.x),roundi(-hit.z)))

func _update_camera(delta: float) -> void:
	var focus := Vector3(66,0,-60) if overview else player.position + Vector3(0,1.2,0)
	var offset := Vector3(sin(orbit)*38,46,cos(orbit)*38)
	var wanted := focus+offset
	camera.position = camera.position.lerp(wanted, minf(1,delta*8))
	camera.look_at(focus)
	camera.h_offset = -23 if overview else 0
	camera.size = lerpf(camera.size, 142.0 if overview else zoom, minf(1,delta*8))

func _process(delta: float) -> void:
	if player == null:
		return
	time += delta
	if not path.is_empty():
		var next := path[0]
		var direction := tile_position(next)-player.position
		if Vector2(direction.x,direction.z).length() > .01:
			player.rotation.y = lerp_angle(player.rotation.y,atan2(-direction.x,-direction.z),minf(1,delta*14))
		player.position = player.position.move_toward(tile_position(next),delta*8)
		if player.position.distance_to(tile_position(next)) < .06:
			path.pop_front()
			q.move_to(next)
			if path.is_empty() and not pending_target.is_empty():
				var id := pending_target
				pending_target = ""
				_interact(id)
	if not harvest_item.is_empty():
		harvest_clock -= delta
		if harvest_clock <= 0:
			harvest_clock = 1.2
			if not q.act("harvest",harvest_item):
				harvest_item = ""
			elif q.count("harvest",harvest_item) >= (3 if harvest_item == "Reed" else 1):
				harvest_item = ""
	if fighting:
		combat_clock -= delta
		if combat_clock <= 0:
			combat_clock = 1.0
			fighting = q.combat_round()
			if not fighting:
				player.position = tile_position(_tile(q.state.tile))
	Art.animate(player,"Sword_Attack" if fighting else ("Walk" if not path.is_empty() else "Idle_A"),1.35 if not path.is_empty() else 1.0)
	Art.animate(boar_visual,"Sword_Attack" if fighting else "Idle_A")
	marker.get_child(1).position.y = 3.5+sin(time*3)*.18
	beam.rotation.y = sin(time*.3)*.15
	if q.has_flag("lit"):
		boat.position = boat.position.move_toward(Vector3(110,-.5,-22),delta*4)
	else:
		boat.position = Vector3(117,-.5+sin(time)*.1,-70)
	_update_camera(delta)
	save_clock += delta
	if save_clock >= 3:
		save_clock = 0
		q.save()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		q.save()
