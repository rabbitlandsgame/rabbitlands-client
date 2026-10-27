class_name PortraitHairLocks
extends RefCounted
## Explicitly authored opaque clump curves, sampled once into the existing hair
## surface. The imported cap, bind/rest data and all source files stay intact.
const GROOM := preload("res://src/actors/portrait_groom.gd")
const PATH := "res://data/actors/hair_high/hero-locks.json"
const SIDES := 6
const SAMPLES := 10
static var _data: Dictionary = {}
static func clear() -> void:
	_data.clear()
static func curves(sex: String, style: int, detail: int) -> Array:
	if _data.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
		if parsed is Dictionary: _data = parsed
	return _data.get("styles",{}).get("%s:%d:%d" % [sex,style,detail],[])
static func binding(skin: Skin, skeleton: Skeleton3D, name: StringName) -> int:
	if skin == null: return -1
	var bone := skeleton.find_bone(name)
	for index: int in skin.get_bind_count():
		if skin.get_bind_name(index) == name or (bone >= 0 and skin.get_bind_bone(index) == bone): return index
	return -1
static func _bezier(p: Array[Vector3], segment: int, t: float) -> Vector3:
	var a := segment*3
	var u := 1.0-t
	return p[a]*u*u*u+p[a+1]*3.0*u*u*t+p[a+2]*3.0*u*t*t+p[a+3]*t*t*t
static func append(arrays: Array, from_head: Transform3D, sex: String, style: int, detail: int,
		head_bind: int, neck_bind: int, eye_y: float, length: int, volume: int) -> Dictionary:
	var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
	var colors := PackedColorArray()
	colors.resize(points.size())
	var to_head:=from_head.affine_inverse()
	for index: int in points.size(): colors[index]=Color(0,0,clampf(((to_head*points[index]).y-eye_y)/0.13,0.0,1.0),1)
	arrays[Mesh.ARRAY_COLOR]=colors
	var definitions := curves(sex,style,detail)
	if definitions.is_empty() or head_bind < 0: return {"arrays":arrays,"added_indices":PackedInt32Array()}
	var influences: int = arrays[Mesh.ARRAY_BONES].size()/points.size() if arrays[Mesh.ARRAY_BONES] != null else 0
	if influences not in [4,8]: return {"arrays":arrays,"added_indices":PackedInt32Array()}
	var vertex := PackedVector3Array()
	var normal := PackedVector3Array()
	var uv := PackedVector2Array()
	var color := PackedColorArray()
	var tangent := PackedFloat32Array()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	var indices := PackedInt32Array()
	var normal_from_head := from_head.basis.inverse().transposed()
	for definition: Dictionary in definitions:
		for mirror: int in (2 if bool(definition.get("mirror",false)) else 1):
			var control: Array[Vector3]=[]
			for value: Array in definition.points:
				control.append(Vector3(float(value[0])*(-1.0 if mirror else 1.0),float(value[1]),float(value[2])))
			var segments: int=(control.size()-1)/3
			var fitted: Array=definition.get("samples",[])
			var fitted_normals: Array=definition.get("normals",[])
			var rings:=fitted.size() if not fitted.is_empty() else segments*SAMPLES+1
			var start:=vertex.size()
			var width:=float(definition.width)*(1.0+float(volume-50)*0.004)
			var depth:=float(definition.get("depth",0.28))
			var seed:=float(definition.get("seed",0.5))+(0.09 if mirror else 0.0)
			for ring: int in rings:
				var progress:=float(ring)/float(rings-1)
				var scaled:=progress*segments
				var segment:=mini(int(scaled),segments-1)
				var t:=scaled-segment
				var centre:=_bezier(control,segment,t)
				var next:=_bezier(control,segment,minf(t+0.001,1.0))
				var previous:=_bezier(control,segment,maxf(t-0.001,0.0))
				if not fitted.is_empty():
					centre=Vector3(fitted[ring][0],fitted[ring][1],fitted[ring][2])
					var ni:=mini(ring+1,rings-1)
					var pi:=maxi(ring-1,0)
					next=Vector3(fitted[ni][0],fitted[ni][1],fitted[ni][2])
					previous=Vector3(fitted[pi][0],fitted[pi][1],fitted[pi][2])
				var size_j:=GROOM._size_hair_jacobian(centre,eye_y,length,volume)
				centre=GROOM._size_hair_point(centre,eye_y,length,volume)
				next=GROOM._size_hair_point(next,eye_y,length,volume)
				previous=GROOM._size_hair_point(previous,eye_y,length,volume)
				var direction: Vector3=(next-previous).normalized()
				var outward:=Vector3(centre.x/0.085,(centre.y-0.08)/0.11,(centre.z+0.025)/0.10).normalized()
				if not fitted_normals.is_empty():
					outward=Vector3(fitted_normals[ring][0],fitted_normals[ring][1],fitted_normals[ring][2])
					outward=(size_j.inverse().transposed()*outward).normalized()
				var across:=direction.cross(outward).normalized()
				if across.length_squared()<0.1: across=Vector3.RIGHT
				var raised:=across.cross(direction).normalized()
				if raised.dot(outward)<0.0:
					raised=-raised
					across=-across
				var radius:=maxf(width*(0.55*(1.0-progress)+0.65*sin(progress*PI)),0.00004)
				for side: int in SIDES+1:
					var u:=float(side)/SIDES
					var angle:=u*TAU
					var p:=centre+across*cos(angle)*radius+raised*sin(angle)*radius*depth
					vertex.append(from_head*p)
					var n:Vector3=(across*cos(angle)+raised*sin(angle)/depth).normalized()
					normal.append((normal_from_head*n).normalized())
					var tang:Vector3=(from_head.basis*(-across*sin(angle)+raised*cos(angle)*depth)).normalized()
					tangent.append_array(PackedFloat32Array([tang.x,tang.y,tang.z,1.0]))
					uv.append(Vector2(u,progress))
					color.append(Color(1,seed,progress,1))
					var neck_weight:=0.20*(1.0-smoothstep(-0.08,0.025,p.y))*(1.0-smoothstep(-0.03,0.025,p.z)) if neck_bind>=0 else 0.0
					for influence: int in influences:
						bones.append(head_bind if influence!=1 else neck_bind if neck_bind>=0 else head_bind)
						weights.append((1.0-neck_weight) if influence==0 else neck_weight if influence==1 else 0.0)
				if ring>0:
					for side: int in SIDES:
						var a:=start+(ring-1)*(SIDES+1)+side
						var b:=a+SIDES+1
						indices.append_array(PackedInt32Array([a,a+1,b+1,a,b+1,b]))
	# Append streams once, avoiding a copy of the imported arrays per new ring.
	var offset:=points.size()
	points.append_array(vertex)
	arrays[Mesh.ARRAY_VERTEX]=points
	var n:PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
	n.append_array(normal)
	arrays[Mesh.ARRAY_NORMAL]=n
	var tex:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV]
	tex.append_array(uv)
	arrays[Mesh.ARRAY_TEX_UV]=tex
	colors.append_array(color)
	arrays[Mesh.ARRAY_COLOR]=colors
	if arrays[Mesh.ARRAY_TANGENT]!=null:
		var t:PackedFloat32Array=arrays[Mesh.ARRAY_TANGENT]
		t.append_array(tangent)
		arrays[Mesh.ARRAY_TANGENT]=t
	if arrays[Mesh.ARRAY_TEX_UV2]!=null:
		var uv2:PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV2]
		uv2.resize(points.size())
		arrays[Mesh.ARRAY_TEX_UV2]=uv2
	var skin_bones:PackedInt32Array=arrays[Mesh.ARRAY_BONES]
	var skin_weights:PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS]
	skin_bones.append_array(bones)
	skin_weights.append_array(weights)
	arrays[Mesh.ARRAY_BONES]=skin_bones
	arrays[Mesh.ARRAY_WEIGHTS]=skin_weights
	for index: int in indices.size(): indices[index]+=offset
	var full:PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
	full.append_array(indices)
	arrays[Mesh.ARRAY_INDEX]=full
	return {"arrays":arrays,"added_indices":indices}
