extends "res://tests/playthrough.gd"

func button(text: String) -> Button:
	for b: Node in scene.window_body.find_children("*","Button",true,false):
		if b.text == text:
			return b as Button
	return null

func press(text: String) -> void:
	var b := button(text)
	expect(b != null,"button present: "+text)
	if b:
		b.pressed.emit()

func _run() -> void:
	root.size = Vector2i(1440,900)
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	q = scene.q
	q.reset()
	scene.player.position = scene.tile_position(Vector2i(q.state.tile[0],q.state.tile[1]))
	scene._go_target("nesh")
	for i in range(200):
		scene._process(.04)
		if scene.path.is_empty():
			break
	expect(q.current().id == "ask_caldus","guidance button actually walks and advances")
	go("caldus")
	scene._open("caldus")
	press("I'll get it burning.")
	expect(q.current().id == "chart","dialogue choice accepts supplies")
	scene._open("inventory")
	# Independent row callbacks must act on their own item, not the final loop value.
	var equip: Array[Node] = scene.window_body.find_children("*","Button",true,false)
	for b: Node in equip:
		if b.text == "Equip":
			b.pressed.emit()
			break
	expect("Sword" in q.state.equipment,"Sword row equips Sword")
	press("Equip")
	expect("Shield" in q.state.equipment,"Shield row equips Shield")
	press("Eat")
	expect(int(q.state.food) >= 35,"Eat button consumes Bread")
	go("chart")
	act("chart")
	scene._open("map")
	expect(q.current().id == "reeds","opening map updates quest")
	go("reed")
	scene._interact("reed")
	for i in range(6):
		scene._process(1.3)
	expect(q.count("harvest","Reed") == 3 and scene.harvest_item.is_empty(),"repeat harvest stops automatically")
	expect("3/3" in q.message,"harvest completion retains its success acknowledgement")
	go("quartz")
	act("harvest","Quartz")
	go("lower_cache")
	scene._open("storage")
	await process_frame
	expect(scene.window.position.y+scene.window.size.y < 880,"fully populated storage window fits screen")
	press("Deposit 3 × Reed")
	press("Deposit 1 × Quartz")
	press("Withdraw 1 × Wood Plank")
	press("Withdraw 1 × Cloth Roll")
	press("Withdraw 1 × Hatchet")
	expect(q.current().id == "torch","storage controls advance all five objectives")
	scene._open("craft")
	press("Make one Torch")
	expect(q.has_flag("crafted"),"manufacturing button crafts the actual recipe")
	for kind in ["inventory","storage","craft","stats","journal","map","beacon","trade","departure","complete","restart"]:
		scene._open(kind)
		await process_frame
		expect(scene.window.position.y+scene.window.size.y <= 900,"window fits: "+kind)
		press("Close · Esc")
		expect(not scene.window.visible,"window can close: "+kind)
	print("Lantern UI: %d checks, %d failures." % [checks,failures])
	quit(1 if failures else 0)
