extends SceneTree
const Protocol := preload("res://src/network/protocol.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
var failures := 0
var checks := 0
var main: Control
var window: PanelContainer
var state: Node
var requests: Array[Dictionary] = []

func _init() -> void: call_deferred("run")
func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)
func frames(count: int = 5) -> void:
	for _index: int in count: await process_frame

func sample() -> Dictionary:
	var essences := {}
	for family: String in ["Life","Death","Water","Magic","Fire","Frost","Earth","Wind"]:
		essences[family] = {"item": "Enriched " + family + " Essence", "favored_effects": []}
	return {"version":1,"enabled":true,"crafting_supported":true,"available":{"Life":100,"Death":100,"Water":100,"Magic":100,"Fire":100,"Frost":100,"Earth":100,"Wind":100},
		"rules":{"essences":essences,"initial":{"weights":[70,25,4,1],"max_essences":5},"promotion":{"costs":{"Enriched Magic Essence":10,"Enriched Life Essence":10}},"catalysts":["Fire","Frost","Earth","Wind"]},
		"items":[{"instance_id":501,"slot":0,"name":"Militia Arming Sword","image_id":374,"tier":"normal","quality":100,"durability":90,"max_durability":100,"effects":[],"effect_names":[]},
		{"instance_id":502,"slot":1,"name":"Militia Arming Sword","image_id":374,"tier":"magic","quality":100,"durability":96,"max_durability":100,"effects":["Brutal: +20 physical damage.","Flamebound: +10 heat damage."],"effect_names":["Brutal","Flamebound"]},
		{"instance_id":503,"slot":2,"name":"Phoenix Helm","image_id":182,"tier":"rare","quality":110,"durability":96,"max_durability":100,"effects":["Plated: +20 armor.","Vital: +50 maximum health.","Spellguard: +25% less incoming spell damage.","Restorative: +10 mana per normal regeneration tick."],"effect_names":["Plated","Vital","Spellguard","Restorative"]}],
		"quote":null,"error":"","message":"","result":null}

func receive(value: Dictionary) -> void:
	value["request_id"] = window.get("_serial")
	state.call("_on_packet",185,JSON.stringify(value).to_utf8_buffer())

func choose(action: String) -> void:
	for index: int in window.action_picker.item_count:
		if str(window.action_picker.get_item_metadata(index)) == action:
			window.action_picker.select(index)
			window.action_picker.item_selected.emit(index)
			return
	expect(false,"operation offered: " + action)

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	OS.set_environment("ELORIA_NO_MAP_CACHE","1")
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280,800)
	state = root.get_node("AppState")
	expect(Protocol.CLIENT_CAPABILITIES.has("equipment_enchanting_v1"),"enchanting capability advertised")
	expect(Protocol.decode_enchanting(JSON.stringify(sample()).to_utf8_buffer()).type == "enchanting","all-copy state decodes")
	var invalid := sample()
	invalid.items[0].tier = "magic"
	expect(Protocol.decode_enchanting(JSON.stringify(invalid).to_utf8_buffer()).type == "invalid","empty colored copy refused")
	var fixture := OS.get_environment("RL_ENCHANTING_WIRE_FIXTURE")
	if not fixture.is_empty():
		for raw: String in JSON.parse_string(FileAccess.get_file_as_string(fixture)):
			expect(Protocol.decode_server(185,raw.to_utf8_buffer()).type == "enchanting","actual server message decodes")
	var encoded := Protocol.mix_request(7,1,false,{"output":"Torch","ingredients":[{"name":"Militia Arming Sword","quantity":1}]},[502])
	expect(encoded.slice(encoded.size()-6,encoded.size()-1).get_string_from_utf8() == "[502]" and encoded[-1] == 0,"mix request includes exact equipment identities after recipe claim")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/equipment-enchanting/test.cfg"
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	state.set("authenticated",true)
	window = main.inventory_workspace.enchanting_window
	window.send_request = func(request: Dictionary) -> Error:
		requests.append(request.duplicate(true))
		return OK
	window.open(0)
	expect(not window.visible,"no entry to unsupported server")
	state.call("_on_packet",185,JSON.stringify(sample()).to_utf8_buffer())
	window.open(0)
	receive(sample())
	await frames()
	expect(window.visible and window.selected_id == 501,"plain copy preselected by inspection slot")
	expect(window.selected_title.text == "Militia Arming Sword","item name has no tier prefix")
	expect(window.action_picker.item_count == 1 and window.get("_action") == "enchant","plain gear offers first enchanting")
	expect(not window.confirm_button.disabled and window.quote.is_empty(),"Review is available before a quote; spending still needs the server token")
	expect((window.get("_odds") as HBoxContainer).visible,"enchantment odds stay visible next to the main action")
	expect(Rect2(Vector2.ZERO, Vector2(1184,712)).encloses(window.get_global_rect()),"plain enchanting with odds fits above the HUD")
	if OS.get_cmdline_user_args().has("--capture"): await capture("enchant-one")
	var primary: OptionButton = window.get("_primary_picker")
	primary.select(6)
	primary.item_selected.emit(6)
	expect((window.get("_families")["Earth"] as SpinBox).value == 1 and (window.get("_families")["Life"] as SpinBox).value == 0,"choosing a theme moves the selected essence amount")
	var requests_before := requests.size()
	window.call("_confirm")
	expect(requests.size() == requests_before,"no materials can be spent before review returns a token")
	for family: String in window.get("_families"):
		(window.get("_families")[family] as SpinBox).value = 0
	(window.get("_families")["Earth"] as SpinBox).value = 3
	(window.get("_families")["Wind"] as SpinBox).value = 2
	window.call("_review")
	expect(requests[-1].instance_id == 501 and requests[-1].essences == {"Earth":3,"Wind":2},"initial materials and exact copy sent")
	var data := sample()
	data.quote = {"token":"initial-token","action":"enchant","name":"Militia Arming Sword","summary":"Roll the count five times and keep the highest.","gold_fee":0,"chances":[{"count":1,"chance":.16807},{"count":2,"chance":.6057109375},{"count":3,"chance":.1772091124},{"count":4,"chance":.0490099501}],"inputs":[{"name":"Enriched Earth Essence","quantity":3},{"name":"Enriched Wind Essence","quantity":2}]}
	receive(data)
	expect(window.confirmation.visible,"Review automatically opens confirmation after the matching server quote")
	expect(not window.confirm_button.disabled and (window.get("_families")["Earth"] as SpinBox).value == 3,"preview preserves the chosen material controls")
	window.call("_ask_confirmation")
	expect(window.confirmation.dialog_text.contains("after confirmation") and window.confirmation.dialog_text.contains("3 Enriched Earth Essence"),"confirmation discloses random result and exact material spending")
	window.confirmation.hide()
	if OS.get_cmdline_user_args().has("--capture"): await capture("enchant")
	(window.get("_families")["Earth"] as SpinBox).value = 2
	expect(window.quote.is_empty() and not window.confirmation.visible,"changing essence count invalidates quote and closes review")
	(window.get("_families")["Earth"] as SpinBox).value = 5
	expect(window.confirm_button.disabled,"more than the configured total essence limit cannot be reviewed")
	(window.get("_families")["Earth"] as SpinBox).value = 2
	window.copies.select(1)
	window.copies.item_selected.emit(1)
	choose("promote")
	expect(window.explanation.text.contains("Both existing"),"promotion explains preservation")
	window.call("_preview")
	expect(requests[-1].action == "promote" and requests[-1].instance_id == 502,"promotion selects blue exact copy")
	receive(sample())
	window.copies.select(2)
	window.copies.item_selected.emit(2)
	expect(window.selected_title.get_theme_color("font_color") == Tiers.color("rare"),"yellow name conveys item tier")
	choose("values")
	window.dose.select(4)
	window.dose.item_selected.emit(4)
	window.call("_preview")
	expect(requests[-1].quantity == 5 and requests[-1].action == "values","five-Water numeric reroll request")
	receive(sample())
	choose("remove")
	window.target.select(2)
	window.target.item_selected.emit(2)
	window.call("_preview")
	expect(requests[-1].quantity == 3 and requests[-1].effect == "Vital","chosen Death removal uses three essences")
	receive(sample())
	choose("reroll")
	window.dose.select(2)
	window.dose.item_selected.emit(2)
	var locks: VBoxContainer = window.locks_body
	(locks.get_child(1) as CheckBox).button_pressed = true
	(locks.get_child(2) as CheckBox).button_pressed = true
	(window.get("_families")["Frost"] as SpinBox).value = 1
	window.call("_preview")
	expect(requests[-1].quantity == 5 and requests[-1].locks.size() == 2 and requests[-1].catalysts == {"Frost":1},"Magic locks and themed catalyst request")
	data = sample()
	data.quote = {"token":"reroll-token","action":"reroll","name":"Phoenix Helm","summary":"Preserve two chosen effects and reroll the rest.","gold_fee":0,"chances":[],"inputs":[{"name":"Enriched Magic Essence","quantity":5},{"name":"Enriched Frost Essence","quantity":1}]}
	receive(data)
	expect(window.dose.selected == 2 and window.get("_locks").size() == 2,"quote keeps locks and quantity controls")
	if OS.get_cmdline_user_args().has("--capture"): await capture("reroll")
	var inventory_before: Dictionary = state.inventory.duplicate(true)
	window.call("_confirm")
	expect(requests[-1].op == "confirm" and requests[-1].token == "reroll-token" and not requests[-1].has("effects"),"confirm sends only server token")
	expect(state.inventory == inventory_before,"client never optimistically changes materials or equipment")
	var serial: int = window.get("_serial")
	state.state_changed.emit(&"inventory")
	expect(int(window.get("_serial")) == serial,"inventory preceding receipt preserves pending request")
	receive(sample())
	var chosen_ids: Array = []
	window.choose_ingredients({"output":"Torch","equipmentIngredients":[{"name":"Militia Arming Sword","quantity":1}]},func(ids: Array) -> void: chosen_ids.assign(ids))
	receive(sample())
	expect(window.copies.item_count == 2 and window.confirm_button.disabled,"craft picker filters matching copies and needs explicit selection")
	window.copies.select(1,false)
	window.copies.multi_selected.emit(1,true)
	expect(not window.confirm_button.disabled,"exact equipment selection enables one crafting attempt")
	window.call("_ask_confirmation")
	expect(window.confirmation.dialog_text.contains("critical failure") and window.confirmation.dialog_text.contains("Flamebound"),"equipment consumption confirmation includes effects and failure rules")
	window.confirmation.hide()
	window.call("_confirm")
	expect(chosen_ids == [502],"crafting receives the selected copy only")
	var original_catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/manufacturing/recipes.json"))
	var equipment_input := {"name":"Militia Arming Sword","quantity":1,"imageId":374}
	main.manufacturing_catalog.configure({"recipes":[{"id":0,"output":"Torch","skill":"crafting","level":0,"experience":1,"food":1,"mana":0,"ingredients":[equipment_input],"equipmentIngredients":[equipment_input],"tools":[]}]})
	main.manufacturing_source.button_pressed = false
	main.call("_start_mix",0,3,-1)
	expect(window.visible and window.get("_craft_recipe").output == "Torch" and main.get("_mix_pending").is_empty(),"Mix Now opens exact-copy selection before any request")
	main.manufacturing_queue_running = true
	main.call("_start_mix",0,1,0)
	expect(not main.manufacturing_queue_running and main.get("_mix_pending").is_empty(),"automatic queue cannot select equipment copies")
	main.manufacturing_catalog.configure(original_catalog)
	window.open(2)
	receive(sample())
	root.size = Vector2i(1024,720)
	root.content_scale_size = Vector2i(1024,720)
	await frames()
	expect(Rect2(Vector2.ZERO,Vector2(928,632)).encloses(window.get_global_rect()),"enchanting window fits outside HUD at smaller viewport")
	window.copies.select(0)
	window.copies.item_selected.emit(0)
	await frames()
	expect(Rect2(Vector2.ZERO,Vector2(928,632)).encloses(window.get_global_rect()),"plain enchanting including its pinned odds fits the smaller viewport")
	if OS.get_cmdline_user_args().has("--capture"): await capture("enchant-narrow")
	state.set("enchanting_recovery_available",true)
	window.tabs.set_tab_disabled(1,false)
	window.tabs.current_tab = 1
	expect(not window.visible and main.inventory_workspace.recovery_window.visible and main.inventory_workspace.recovery_window.tabs.current_tab == 1,"shared Refine tab opens the refining window")
	main.inventory_workspace.recovery_window.hide()
	window.open(0)
	receive(sample())
	expect(window.tabs.current_tab == 2 and window.visible,"returning to enchanting restores the active tab")
	state.set("authenticated",false)
	state.state_changed.emit(&"connection")
	expect(not window.visible and window.quote.is_empty(),"disconnect closes and invalidates enchanting")
	print("Equipment enchanting: %d checks, %d failures" % [checks,failures])
	main.queue_free()
	await frames(2)
	quit(failures)

func capture(label: String) -> void:
	await frames(8)
	await RenderingServer.frame_post_draw
	var folder := "res://test-artifacts/equipment-enchanting"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	root.get_texture().get_image().save_png(folder + "/" + label + ".png")
