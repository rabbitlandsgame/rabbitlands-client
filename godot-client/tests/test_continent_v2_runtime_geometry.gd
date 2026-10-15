extends SceneTree
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
var failures := 0
func _initialize() -> void:
	call_deferred("_run")
func _run() -> void:
	var rings: Array = [ [[0,0],[2,0],[2,2],[0,2]], [[5,0],[7,0],[7,2],[5,2]] ]
	var main_script := load("res://src/app/main.gd") as GDScript
	if main_script == null or not main_script.can_instantiate():
		push_error("Runtime cartography consumer did not compile.")
		quit(1)
		return
	var root_view: Control = main_script.new()
	root_view.cartography_regions = [ {"continentPolygons": rings}, {"continentPolygon":rings[0]} ]
	var components: Array[PackedVector2Array] = root_view.call("_region_polygon_components",0)
	_expect(components.size() == 2 and GEOMETRY.contains(Vector2(6,1),components),"runtime cartography includes second component")
	_expect(not GEOMETRY.contains(Vector2(3,1),components),"runtime cartography excludes intervening gap")
	_expect((root_view.call("_region_polygon_components",1) as Array).size() == 1,"legacy cartography single-ring schema remains valid")
	root_view.free()
	LookBorders.define({"west":rings,"east":[[7,0],[9,0],[9,2],[7,2]]}, {"west":"continent-v2","east":"continent-v2"})
	_expect(LookBorders.neighbours_of("west").has("east"),"look discovers shared border on second component")
	var selection := LookBorders.near("west",Rect2(6,0,2,2),1)
	_expect(selection.segments.size() == 1,"disconnected components create no connecting border")
	LookBorders.define({"west":[[0,0],[10,0],[5,10]],"east":[[10,0],[15,10],[5,10]]}, {"west":"continent-v2","east":"continent-v2"})
	var a := LookBorders.near("west",Rect2(4,0,7,10),2)
	var b := LookBorders.near("east",Rect2(4,0,7,10),2)
	_expect(a.segments.size() == 1 and b.segments.size() == 1,"angled border is intersected exactly")
	_expect(absf(LookBorders.weights(Vector2(7.5,5),a,2)[0]-0.5) < 0.0001 and absf(LookBorders.weights(Vector2(7.5,5),b,2)[0]-0.5) < 0.0001,"angled border has reciprocal half blend")
	print("continent-v2 runtime geometry: ",failures," failures")
	quit(1 if failures else 0)
func _expect(ok: bool,message: String) -> void:
	print("PASS: " if ok else "FAIL: ",message)
	if not ok:
		failures += 1
