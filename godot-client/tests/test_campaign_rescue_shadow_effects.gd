extends SceneTree
## Film-only arrival and fire survive hidden/dissolving cast, then relinquish
## their light/material resources on rewind, Skip, map exit and disconnect.
const Presentation := preload("res://src/world/campaign_rescue_presentation.gd")
const ARRIVAL := {"id":"lich-arrival","type":"teleport","actor":"lich","at":3.0,"until":7.0}
const FIRE := {"id":"corpse-burn","type":"corpse_fire","actor":"goblin_boss","at":20.0,"until":32.0}
const ASHES := {"id":"corpse-ashes","type":"dissolve","actor":"goblin_boss","at":26.0,"until":40.0,"duration":6.0}
var checks := 0
var failures := 0

class Corpse extends Node3D:
	var health := 0
	var current_action := &"death"
	var _corpse_transparency := 0.0

func _init() -> void: run.call_deferred()
func expect(value: bool, message: String) -> void:
	checks += 1
	if value: print("PASS: ",message)
	else: failures += 1;push_error(message)

func state(time: float, cast: Dictionary, replay := false) -> Dictionary:
	var events: Array = []
	for event: Dictionary in [ARRIVAL,FIRE,ASHES]:
		if time >= float(event.at) and time <= float(event.until): events.append(event.duplicate(true))
	return {"id":"measure.rescue.shadow","run_id":"effects-run","token":"shadow-token",
		"elapsed":time,"playing":true,"returning":false,"replaying":replay,"actors":cast,"events":events}

func bind(presenter: Node3D) -> void:
	presenter._identity = "effects-run:landfall_insides"
	presenter._map = "landfall_insides"
	presenter._snapshot = {"run_id":"effects-run","rescue":{"mother":{"downed":false},"proofs":[],"experience":0}}

func run() -> void:
	root.get_node("Network").call("block_for_hud_preview")
	var presenter := Presentation.new();root.add_child(presenter);bind(presenter)
	var lich := Node3D.new();root.add_child(lich);lich.position=Vector3(3,0,1);lich.hide()
	var corpse := Corpse.new();root.add_child(corpse);corpse.position=Vector3(1,0,2)
	var body := MeshInstance3D.new();body.mesh=BoxMesh.new();corpse.add_child(body)
	var original := StandardMaterial3D.new();original.albedo_color=Color(0.3,0.2,0.1)
	body.material_override=original
	var cast := {"lich":lich,"goblin_boss":corpse}
	var original_snapshot := JSON.stringify(presenter._snapshot)
	var original_pose := corpse.global_transform
	presenter.apply_cinematic(state(2.9,cast),cast)
	expect(presenter._arrival_effects.is_empty(),"the arrival is absent before its authored beat")
	presenter.apply_cinematic(state(4.8,cast),cast)
	var arrival: Dictionary=presenter._arrival_effects.get("lich-arrival",{})
	expect(not arrival.is_empty(),"the lich's arrival is drawn before his reveal")
	if not arrival.is_empty():
		expect(arrival.root.get_parent()==presenter and arrival.root.is_visible_in_tree() and not lich.visible,
			"arrival runes remain visible while the server-owned lich is hidden")
		expect(arrival.root.global_position.distance_to(lich.global_position)<0.1 and arrival.light.light_energy>3.0,
			"the pulse and its local chamber light mark the actual bound lich position")
		var clock:float=arrival.spell.elapsed
		var energy:float=arrival.light.light_energy
		presenter.apply_cinematic(state(4.8,cast),cast)
		expect(is_equal_approx(arrival.spell.elapsed,clock) and is_equal_approx(arrival.light.light_energy,energy),
			"manual reading time does not advance the arrival's sampled clock")
	lich.show();presenter.apply_cinematic(state(5.2,cast),cast)
	expect(not presenter._arrival_effects.is_empty(),"the visible lich emerges inside the still-active arrival")
	presenter.apply_cinematic(state(7.0,cast),cast)
	expect(presenter._arrival_effects.is_empty(),"the arrival light and rune roots leave at the authored end")
	presenter.apply_cinematic(state(20.5,cast),cast)
	expect(not presenter._corpse_fires.is_empty() and presenter._dissolves.is_empty(),
		"ignition is visible while the boss body is still solid")
	presenter.apply_cinematic(state(24.0,cast),cast)
	var fire: Dictionary=presenter._corpse_fires.get("corpse-burn",{})
	expect(not fire.is_empty() and presenter._dissolves.is_empty() and body.material_override==original,
		"full engulfing fire precedes any corpse material dissolution")
	if not fire.is_empty():
		expect(fire.mesh.get_aabb().size.y>1.7 and fire.light.light_energy>5.0,
			"rising flames surround the body and illuminate the dark chamber")
		var bounds:AABB=fire.mesh.get_aabb()
		presenter.apply_cinematic(state(24.0,cast),cast)
		expect(fire.mesh.get_aabb()==bounds,"manual dialogue holds preserve the same burning stage")
	presenter.apply_cinematic(state(29.0,cast),cast)
	expect(not presenter._corpse_fires.is_empty() and is_equal_approx(float(presenter._dissolve_progress.get("corpse-ashes",-1)),0.5),
		"fire and its own light persist while the existing corpse dissolve progresses")
	presenter.apply_cinematic(state(32.0,cast),cast)
	expect(presenter._corpse_fires.is_empty() and is_equal_approx(float(presenter._dissolve_progress.get("corpse-ashes",-1)),1.0),
		"flames end after consumption while the body stays fully dissolved")
	presenter.apply_cinematic(state(4.8,cast,true),cast)
	expect(not presenter._arrival_effects.is_empty() and presenter._corpse_fires.is_empty()
		and body.material_override==original and body.get_surface_override_material(0)==null,
		"rewinding for read-only replay reconstructs arrival and restores the original corpse material")
	presenter.apply_cinematic(state(24.0,cast,true),cast)
	var returning:=state(24.0,cast,true);returning.returning=true;returning.return_reason="skipped"
	presenter.apply_cinematic(returning,cast)
	expect(presenter._arrival_effects.is_empty() and presenter._corpse_fires.is_empty(),
		"Skip during replay removes local flame and arrival lights immediately")
	presenter.apply_cinematic(state(24.0,cast),cast)
	presenter.apply_cinematic(state(24.0,{}),{})
	expect(presenter._corpse_fires.is_empty(),"a removed bound corpse cannot leave an orphaned fire")
	presenter.apply_cinematic(state(24.0,cast),cast)
	presenter.apply_snapshot({},CoordinateAdapter.new(),"landfall_insides",func(_point:Vector3)->float:return 0.0)
	expect(presenter._corpse_fires.is_empty() and presenter._arrival_effects.is_empty(),
		"disconnect clears all film-only lights and effects")
	bind(presenter);presenter.apply_cinematic(state(24.0,cast),cast)
	presenter.apply_snapshot({"active":true,"kind":"rescue","run_id":"effects-run","map":"boarsend"},
		CoordinateAdapter.new(),"boarsend",func(_point:Vector3)->float:return 0.0)
	expect(presenter._corpse_fires.is_empty() and presenter._arrival_effects.is_empty(),
		"leaving the rescue map relinquishes every fire and arrival root")
	expect(corpse.health==0 and corpse.current_action==&"death" and corpse.global_transform==original_pose
		and original.albedo_color==Color(0.3,0.2,0.1),"the effects change neither native death/position nor the shared source material")
	bind(presenter)
	expect(JSON.stringify(presenter._snapshot)==original_snapshot,"visual events never add quest proof or experience")
	presenter.clear();presenter.queue_free();lich.queue_free();corpse.queue_free()
	await process_frame;await process_frame
	print("Rescue shadow effects: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
