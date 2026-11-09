extends SceneTree
const Supplies:=preload("res://tests/test_campaign_shelves.gd")
var failures:=0
var checks:=0

func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
	checks+=1
	if not ok:failures+=1;push_error(message)

func fixture()->Dictionary:
	var s:=Supplies.snapshot()
	s.scene={};s.key="life";s.title="A Harvest Worth Defending";s.stage="work";s.targets=[]
	s.shelves.chapter="life";s.shelves.phase="work";s.shelves.unlocked=[]
	s.shelves.growers={"field":"sage","stored":{"sage":1000,"root":0},"carried":200,"wave":4,"raid":false,"workers":[]}
	for i:int in range(4):
		s.shelves.growers.workers.append({"actor_id":100+i,"name":"Worker "+str(i),"health":80,"max_health":80,
			"downed":false,"cargo":50,"activity":"return","harvesting":false})
	return s

func run()->void:
	var s:=fixture()
	expect(EloriaProtocol.decode_campaign(JSON.stringify(s).to_utf8_buffer()).type=="campaign","new crew ledger passes production validation")
	var path:=OS.get_environment("RL_GROWERS_EVIDENCE")
	if not path.is_empty():
		var evidence:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
		expect(evidence is Array and evidence.size()>10,"native journey includes both fields, healing, retry and mine scenes")
		for row:Dictionary in evidence:
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(row.snapshot).to_utf8_buffer())
			expect(decoded.type=="campaign","native "+str(row.snapshot.title)+" / "+str(row.snapshot.stage)+": "+str(decoded.get("error","valid")))
	var bad:=s.duplicate(true);bad.shelves.growers.workers[1].actor_id=100
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","duplicate workers are rejected")
	bad=s.duplicate(true);bad.shelves.growers.workers[0].cargo=251
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","worker bags have the native capacity limit")
	bad=s.duplicate(true);bad.shelves.growers.stored.sage=10001
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","out-of-range shipment progress is rejected")
	var app:=root.get_node("AppState");app.authenticated=true;app.current_map="landfall";app.campaign=s
	app.actors={}
	for worker:Dictionary in s.shelves.growers.workers:app.actors[int(worker.actor_id)]={"kind":2,"name":worker.name,"health":worker.health,"max_health":80,"actor_type":0}
	var main=(load("res://src/app/main.gd") as Script).new()
	for worker:Dictionary in s.shelves.growers.workers:
		expect(main._overhead_health_for(int(worker.actor_id),app.actors[int(worker.actor_id)],-1),"every crew worker gets an overhead health bar")
		expect(not main._is_attackable_actor(int(worker.actor_id),app.actors[int(worker.actor_id)]),"crew members remain friendly")
	var extension=(load("res://src/ui/extension_windows.gd") as Script).new()
	var crew:Array=extension._quest_party_members()
	expect(crew.size()==4 and crew.all(func(row:Dictionary)->bool:return bool(row.gathering_worker)),"four native villagers appear beside the human party")
	s.shelves.growers.workers[0].downed=true
	crew=extension._quest_party_members()
	expect(crew[0].health==0,"a downed worker is clearly shown as down in the party roster")
	var hud:Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	hud.apply_state(s,Vector2i(64,249),"landfall")
	expect(hud._shelves.text.contains("gathered: 1200") and hud._shelves.text.contains("In bags: 200") and hud._shelves.text.contains("In crew storage: 1000"),"the quest window distinguishes gathered, carried and deposited stock")
	expect(hud._shelves.text.contains("DOWNED") and hud._shelves.text.contains("Heal Target"),"the ledger explains how to revive a worker")
	app.current_map="landfall_town"
	expect(extension._quest_party_members().is_empty(),"leaving the field removes the crew from the local party view")
	expect(not main._overhead_health_for(100,app.actors[100],-1),"a stale field snapshot cannot expose a public NPC's health")
	var scenes:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/campaign/shelves_scenes.json")).scenes
	for key:String in ["brief_crew","sage_entry","sage_done","root_entry","root_done","report_crew","brief_raid","raid_entry","boss","raid_done","report_raid","retry"]:
		var film:Dictionary=scenes["measure.shelves.growers."+key]
		expect((film.get("shots",[]) as Array).size()<=1 and not (film.get("lines",[]) as Array).is_empty(),key+" keeps one conversation camera with portrait dialogue")
	expect(bool(scenes["measure.shelves.growers.report_crew"].handoff.keep_dialogue),"Ilka's reward stays in dialogue for the mine assignment")
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model:Dictionary=registry.models[registry.actorTypes["0"]]
	var equipment:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var worker_dto:Dictionary={"actor_id":100,"kind":2,"actor_type":0,"name":"Fenna Ash","x":64,"y":249,"rotation":0,
		"health":80,"max_health":80,"alive":true,"appearance":{"skin":1,"hair":107,"shirt":5,"pants":4,"boots":1,"head":0,"eyes":2}}
	var worker_actor:=ReplicatedActor3D.new();worker_actor.apply_render_quality(1,true);root.add_child(worker_actor)
	var errors:=worker_actor.configure(worker_dto,main.adapter,model,main._animation_for_model(model),equipment)
	expect(errors.is_empty() and worker_actor.get_node_or_null("NativeModel")!=null,"the crew uses a real native body")
	var works:Node3D=load("res://src/world/campaign_shelves_works.gd").new();root.add_child(works)
	s.shelves.growers.workers[0].downed=false
	works.apply_workers(s,{100:worker_actor});works._process(0.1)
	expect(is_instance_valid(works.props.get("bag_100")),"a carried shipment has a visible approved sack model")
	s.shelves.growers.workers[0].cargo=0;s.shelves.growers.workers[0].harvesting=true
	works.apply_workers(s,{100:worker_actor})
	expect(not works.props.has("bag_100") and worker_actor.current_action==&"harvest"
		and worker_actor.animation_player.has_animation(worker_actor.resolver.clip_for_action(&"harvest")),"unloading removes the bag and the actual harvest clip plays")
	works.clear();works.free();worker_actor.free()
	app.authenticated=false;app.campaign={};app.actors={}
	hud.queue_free();extension.free()
	var freed:Dictionary={}
	for property:Dictionary in main.get_property_list():
		if (int(property.get("usage",0)) & PROPERTY_USAGE_SCRIPT_VARIABLE)==0:continue
		var value:Variant=main.get(str(property.name))
		if value is Node and is_instance_valid(value) and value!=main and value.get_parent()==null and not freed.has(value.get_instance_id()):
			freed[value.get_instance_id()]=true;value.free()
	main.free()
	NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Grower quest client: %d checks, %d failures" % [checks,failures])
	quit(1 if failures else 0)
