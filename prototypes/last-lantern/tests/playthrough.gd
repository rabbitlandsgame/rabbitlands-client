extends SceneTree

var scene
var q
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("_run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: "+label)

func go(id: String) -> void:
	var target: Dictionary = q.target(id)
	var destination := Vector2i(target.approach[0],target.approach[1])
	var start := Vector2i(q.state.tile[0],q.state.tile[1])
	var route: Array[Vector2i] = scene.nav.get_id_path(start,destination)
	expect(not route.is_empty(),"reachable target: "+id+" at "+str(q.current().id))
	for tile: Vector2i in route:
		q.move_to(tile)
	expect(q.near(id),"in interaction range: "+id)

func act(action: String, item := "", quantity := 1) -> void:
	expect(q.act(action,item,quantity),action+" "+item+": "+q.message)

func blocked(id: String) -> bool:
	var target: Dictionary = q.target(id)
	var route: Array[Vector2i] = scene.nav.get_id_path(Vector2i(q.state.tile[0],q.state.tile[1]),
		Vector2i(target.approach[0],target.approach[1]))
	return route.is_empty()

func roundtrip() -> void:
	var before: String = JSON.stringify(q.state)
	q.save("user://checkpoint-test.json")
	expect(q.restore("user://checkpoint-test.json"),"checkpoint loads")
	expect(q.state == JSON.parse_string(before),"checkpoint preserves exact progress and inventory")

func play(auto: bool, attribute: String, early: bool) -> void:
	q.reset()
	q.state.auto_gather = auto
	expect(blocked("boar"),"causeway closed before crafting")
	expect(blocked("housing"),"beacon climb closed before preparation")
	expect(blocked("dock"),"shortcut cannot bypass the quest")
	expect(not q.act("supply"),"supplies cannot be taken remotely")
	go("nesh")
	go("caldus")
	act("supply")
	expect(not q.act("supply"),"starter kit granted once")
	if early:
		act("eat")
		act("equip","Sword")
		act("equip","Shield")
	go("chart")
	act("chart")
	act("map")
	go("reed")
	for i in range(3):
		act("harvest","Reed")
		roundtrip()
	expect(not q.act("harvest","Reed"),"Reed stops at quota")
	go("quartz")
	act("harvest","Quartz")
	expect(not q.act("harvest","Quartz"),"Quartz stops at quota")
	go("lower_cache")
	act("deposit","Reed",3)
	act("deposit","Quartz")
	act("withdraw","Wood Plank")
	act("withdraw","Cloth Roll")
	act("withdraw","Hatchet")
	go("bench")
	act("craft")
	expect(q.count("inventory","Torch") == 1 and q.count("inventory","Hatchet") == 1,"Torch uses ingredients and keeps tool")
	expect(not q.act("craft"),"assisted Torch cannot be farmed")
	expect(not blocked("boar"),"crafting opens causeway")
	if not early:
		act("equip","Sword")
		act("equip","Shield")
	go("boar")
	# Exercise the novice rescue and repeat attempt with all supplies retained.
	q.state.health = 2
	var items: Dictionary = q.state.inventory.duplicate(true)
	expect(not q.combat_round(),"Nesh interrupts a losing attempt")
	expect(int(q.state.health) == int(q.state.max_health),"retry restores health")
	expect(items == q.state.inventory and not q.has_flag("defeated"),"retry preserves supplies and requires a real victory")
	go("boar")
	for i in range(4):
		q.combat_round()
	expect(q.has_flag("defeated"),"boar can be defeated")
	if not auto:
		expect(q.current().id == "loot","manual loot keeps bag objective")
		go("bag")
		act("loot")
	expect(q.has_flag("looted") and q.count("inventory","Raw Meat") == 1,"both loot settings advance exactly once")
	expect(not q.act("loot"),"bag cannot duplicate supplies")
	if early:
		act("spend",attribute)
	go("rest")
	if not early:
		act("eat")
		act("spend",attribute)
	expect(q.has_flag("prepared"),"either build choice opens upper climb")
	roundtrip()
	go("upper_cache")
	act("withdraw","Reed",3)
	act("withdraw","Quartz")
	go("housing")
	expect(not q.act("light"),"lighting requires repairs")
	act("repair")
	expect(not q.act("repair"),"repair materials consumed once")
	act("light")
	expect(q.count("inventory","Reed") == 0 and q.count("inventory","Quartz") == 0,"beacon consumes the actual gathered supplies")
	roundtrip()
	expect(not blocked("dock"),"lighting unlocks direct return route")
	go("dock")
	# Recover quest supplies stored early, without walking back up the island.
	go("dock_cache")
	act("deposit","Raw Meat")
	act("withdraw","Raw Meat")
	go("dock")
	act("sell")
	expect(not q.act("sell"),"galley offer paid once")
	act("buy")
	expect(int(q.state.gold) == 2,"trade is affordable and leaves two gold")
	go("ferry")
	act("depart")
	expect(q.has_flag("rewarded") and q.current().id == "complete","rescue reaches Four Gates handoff")
	expect(not q.act("depart"),"reward cannot be duplicated")
	expect(q.state.history.size() == q.quest.steps.size(),"every objective completed")
	roundtrip()

func _run() -> void:
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	q = scene.q
	for auto in [true,false]:
		for attribute in ["Matter","Carry"]:
			for early in [true,false]:
				play(auto,attribute,early)
	print("Lantern Reach playthrough: %d checks, %d failures (8 full routes)." % [checks,failures])
	quit(1 if failures else 0)
