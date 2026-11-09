extends SceneTree
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Scenes := preload("res://src/world/campaign_scene.gd")
var checks:=0
var failures:=0
func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
	checks+=1
	if not ok:
		failures+=1
		push_error(message)
func run()->void:
	var path:="C:/rabbitlands/work-output/shelves-author-revision-20261108/native-basics.json"
	var records:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
	expect(records is Array and records.size()>=12,"real server states cover all three supply assignments")
	for row:Dictionary in records:
		var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(row).to_utf8_buffer())
		expect(decoded.type=="campaign","native revised opening decodes: "+str(decoded.get("error","")))
	var definitions:=Scenes.scene_definitions()
	for key:String in ["offer","accepted_fire","accepted_water","gathered","mixing_life","mixing_fire","mixing_water","missing","delivery","trainer","heal","fire","ether","spar","retry","victory"]:
		var definition:Dictionary=definitions.get("measure.shelves.basics."+key,{})
		expect(not definition.is_empty() and definition.get("required_actors",[])==["mentor"],key+" uses an NPC portrait actor")
		expect(definition.get("live_camera","")=="gameplay" and (definition.get("shots",[]) as Array).is_empty(),key+" holds the player's established camera")
	var state:Dictionary=records[0].duplicate(true)
	state.travel={"map":"landfall","tile":[63,250],"route":"Gather herbs","markers":[
		{"map":"landfall","tile":[63,250],"label":"Sage"},
		{"map":"landfall","tile":[156,379],"label":"Hearthroot"}],
		"via":[{"map":"landfall_town","tile":[175,21],"label":"Leave the shop"}]}
	expect(Guidance.navigation_targets(state,"landfall",true).size()==2,"both herb patches appear together")
	expect(Guidance.navigation_targets(state,"landfall_town",true)[0].tile==[175,21],"the shop shows its exit")
	expect(Guidance.navigation_targets(state,"landfall",false).is_empty(),"untrack hides all new resource markers")
	state.travel.markers[0].tile=[-1,250]
	expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type=="invalid","invalid resource-marker coordinates are rejected")
	var choice:Dictionary={"id":"shelves_basics","title":"Can you help?","owner":"Learner","owner_is_you":true,"selected":"basics_accept","can_choose":false,"response":"Gather the herbs.","options":[
		{"id":"basics_accept","label":"What do you need?","detail":"Help"},
		{"id":"basics_defer","label":"Not now","detail":"Later"}]}
	expect(EloriaProtocol.campaign_scene_choice_valid(choice),"replay retains both options and the selected answer")
	print("Revised basics client: %d checks; %d failures"%[checks,failures])
	quit(1 if failures else 0)
