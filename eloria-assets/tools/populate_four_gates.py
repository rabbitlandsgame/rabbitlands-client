import json, math, random, struct
from pathlib import Path

P=Path('four-gates-city-package'); F=P/'four-gates-city.glb'; random.seed(406)
raw=F.read_bytes();jl,_=struct.unpack_from('<I4s',raw,12);g=json.loads(raw[20:20+jl]);bo=20+jl;bl,_=struct.unpack_from('<I4s',raw,bo);buf=raw[bo+8:bo+8+bl]
nodes=g['nodes']; ni={n['name']:i for i,n in enumerate(nodes)}; mi={m['name']:i for i,m in enumerate(g['meshes'])}
mati={m['name']:i for i,m in enumerate(g['materials'])}
def ensure_mesh(name,prototype,material):
 if name in mi:return
 src=g['meshes'][mi[prototype]];clone={'name':name,'primitives':[dict(src['primitives'][0])]};clone['primitives'][0]['attributes']=dict(src['primitives'][0]['attributes']);clone['primitives'][0]['material']=mati[material];g['meshes'].append(clone);mi[name]=len(g['meshes'])-1
ensure_mesh('cylinder_wood','cylinder_stone','wood');ensure_mesh('cube_water','cube_waterfall','water')
def add(name,parent,mesh,pos,scale,rot=None,extras=None):
 d={'name':name,'mesh':mi[mesh],'translation':list(map(float,pos)),'scale':list(map(float,scale))}
 if rot:d['rotation']=rot
 if extras:d['extras']=extras
 nodes.append(d);nodes[ni[parent]].setdefault('children',[]).append(len(nodes)-1);return len(nodes)-1
def cyl(name,parent,pos,scale,mat='stone'):return add(name,parent,'cylinder_'+mat,pos,scale)
def cube(name,parent,pos,scale,mat='plaster',rot=None,extras=None):return add(name,parent,'cube_'+mat,pos,scale,rot,extras)
def cone(name,parent,pos,scale,mat='roof'):return add(name,parent,'cone_'+mat,pos,scale)
def gable(name,parent,pos,scale,rot=None):return add(name,parent,'gable_roof',pos,scale,rot)

# Civic district: arcaded halls, domed council annexes and service courts.
for i,a in enumerate(range(200,321,20)):
 rad=math.radians(a);r=145+(i%2)*38;x,z=r*math.sin(rad),r*math.cos(rad);h=30+(i%3)*8
 cube(f'Civic_Hall_{i}_Body','District_Civic',(x,30+h/2,z),(42,h,28),'stone')
 for bay in [-14,0,14]:
  cube(f'Civic_Hall_{i}_Arcade_{bay:+}','District_Civic',(x+bay,43,z+15),(9,18,4),'dark-stone')
 cyl(f'Civic_Hall_{i}_Cupola','District_Civic',(x,30+h+12,z),(18,20,18));cone(f'Civic_Hall_{i}_Dome','District_Civic',(x,30+h+29,z),(22,18,22))
 cube(f'Civic_Hall_{i}_Service_Court','District_Civic',(x,31,z-23),(48,2,16),'paving',extras={'walkable':True})

# Residential neighborhoods: façades, entrances, chimneys and walled courtyards.
for i,a in enumerate(range(15,196,15)):
 rad=math.radians(a);r=235+(i%3)*28;x,z=r*math.sin(rad),r*math.cos(rad);h=22+(i%4)*5;ry=rad;q=[0,math.sin(ry/2),0,math.cos(ry/2)]
 width=24+(i%2)*7;depth=19+(i%3)*3
 cube(f'Residence_{i}_Body','District_Residential',(x,30+h/2,z),(width,h,depth),'plaster',q)
 gable(f'Residence_{i}_Roof','District_Residential',(x,30+h+6,z),(width+5,12,depth+5),q)
 fx,fz=math.sin(rad),math.cos(rad);cube(f'Residence_{i}_Door','District_Residential',(x+fx*(depth*.5+.5),35,z+fz*(depth*.5+.5)),(4,9,1),'wood',q)
 for floor in range(1,1+int(h//10)):
  side=-7;wx=x+math.cos(rad)*side+fx*(depth*.5+.7);wz=z-math.sin(rad)*side+fz*(depth*.5+.7)
  cube(f'Residence_{i}_Window_{floor}','District_Residential',(wx,34+floor*8,wz),(4,5,.6),'blue-crystal',q,{'emissiveWindow':True})
 cx=x+math.cos(rad)*8-fx*4;cz=z-math.sin(rad)*8-fz*4;cyl(f'Residence_{i}_Chimney','District_Residential',(cx,30+h+10,cz),(2.4,14,2.4),'dark-stone')
 cube(f'Residence_{i}_Courtyard','District_Residential',(x-fx*(depth*.5+8),31,z-fz*(depth*.5+8)),(width+6,1,14),'paving',q,{'walkable':True})

# Agricultural/service district: farmhouses, granaries, irrigation and docks.
for i,x in enumerate(range(-260,261,65)):
 z=255+(i%2)*35;farm_rot=[0,0,0,1];cube(f'Farmhouse_{i}','District_Agricultural',(x,41,z),(30,22,22),'plaster',farm_rot);gable(f'Farmhouse_{i}_Roof','District_Agricultural',(x,59,z),(35,14,27),farm_rot);cyl(f'Granary_{i}','District_Agricultural',(x+22,43,z-20),(15,26,15),'wood');cone(f'Granary_{i}_Roof','District_Agricultural',(x+22,62,z-20),(18,12,18),'roof')
 cube(f'Irrigation_Channel_{i}','District_Agricultural',(x,30.3,225),(50,.6,4),'water',extras={'effect':'irrigation-water'})
for i,x in enumerate([-170,-95,95,170]):
 cube(f'Service_Dock_{i}','District_Service',(x,3,390),(48,5,16),'wood');cyl(f'Service_Crane_Post_{i}','District_Service',(x,19,390),(3,28,3),'wood');cube(f'Service_Crane_Boom_{i}','District_Service',(x+8,31,390),(20,2,2),'wood')

# Street-scale detail and vegetation, leaving all principal paths clear.
for i,a in enumerate(range(0,360,10)):
 rad=math.radians(a);r=195;x,z=r*math.sin(rad),r*math.cos(rad)
 cyl(f'Ring_Lamp_{i}','Props',(x,40,z),(1,16,1),'bronze');cone(f'Ring_Lamp_Crystal_{i}','Props',(x,50,z),(3.5,7,3.5),'blue-crystal')
 if i%2==0:cube(f'Ring_Banner_{i}','Props',(x,47,z),(1,15,7),'blue-crystal',extras={'effect':'banner-sway'})
for i in range(180):
 a=random.random()*math.tau;r=random.uniform(105,330);x,z=r*math.sin(a),r*math.cos(a)
 if abs(x)<35 or abs(z)<35:continue
 h=random.uniform(13,28);cyl(f'Vegetation_Trunk_{i}','Vegetation',(x,32+h*.25,z),(2,h*.5,2),'wood');cone(f'Vegetation_Crown_{i}','Vegetation',(x,32+h*.75,z),(10+h*.15,h,10+h*.15),'vegetation')

g['asset']['generator']='Eloria Four Gates production environment 0.4'
def write_glb(path,doc,binary):
 jb=json.dumps(doc,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);binary=bytearray(binary)
 while len(binary)%4:binary.append(0)
 doc['buffers'][0]['byteLength']=len(binary);jb=json.dumps(doc,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(binary))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
write_glb(F,g,buf)

# Real reduced-node LOD2 sibling: preserves landmark silhouettes, roads, terrain,
# water and walls while removing close props, overlays, vegetation and animation.
drop=('Battlement_','Plaza_Bench_','Plaza_Lamp_','Market_','Farm_Fence_','Residence_','Civic_Hall_','Farmhouse_','Granary_','Irrigation_','Service_','Ring_','Vegetation_')
keep=[]
for i,n in enumerate(nodes):
 name=n.get('name','');keep.append(not name.endswith('_LOD0') and not name.startswith(drop))
remap={old:new for new,old in enumerate(i for i,k in enumerate(keep) if k)};lodnodes=[]
for old,k in enumerate(keep):
 if not k:continue
 n=dict(nodes[old]);
 if 'children'in n:n['children']=[remap[c] for c in n['children'] if c in remap]
 lodnodes.append(n)
lod=dict(g);lod['nodes']=lodnodes;lod['scenes']=[{'name':'Four Gates City LOD2','nodes':[remap[0]]}];lod.pop('animations',None);lod['asset']=dict(g['asset']);lod['asset']['generator']='Eloria Four Gates reduced-node LOD2 0.4';write_glb(P/'four-gates-city-lod2.glb',lod,buf)

m=json.loads((P/'four-gates-city.json').read_text());m['assetVersion']='0.4.0';nav=m['navigation']['navmesh']['polygons']
for q,(x0,x1,z0,z1) in enumerate([(-330,-35,-330,-35),(35,330,-330,-35),(-330,-35,35,330),(35,330,35,330),(-300,300,205,315)]):nav.append({'id':f'district-walkable-{q}','vertices':[[x0,31,z0],[x1,31,z0],[x1,31,z1],[x0,31,z1]],'tags':['district','alley-courtyard']})
m['navigation']['navmesh']['exclusions']=[{'id':'central-monument','shape':'cylinder','center':[0,31,0],'radius':18},{'id':'city-wall','shape':'outside-circle','center':[0,31,0],'radius':350}]
m['lodGroups'][0]['levels'][2]={'id':'LOD2','glb':'four-gates-city-lod2.glb','screenCoverage':0.0,'nodeCount':len(lodnodes),'animations':0};m['districtDetail']={'civic':{'families':['arcaded-hall','domed-annex','service-court']},'residential':{'families':['pitched-residence','courtyard','chimney']},'agricultural':{'families':['farmhouse','granary','irrigation']},'service':{'families':['dock','crane']}};m['knownLimitations']=[x for x in m['knownLimitations'] if 'district-alley' not in x and 'authored LOD2' not in x];m['knownLimitations'].append('District navmesh uses conservative convex coverage; final blockers should be rebaked after hand-authored building placement.');(P/'four-gates-city.json').write_text(json.dumps(m,indent=2)+'\n')
lm=json.loads(json.dumps(m));lm['asset']['glb']='four-gates-city-lod2.glb';lm['assetVersion']='0.4.0-lod2';lm['animations']=[];(P/'four-gates-city-lod2.json').write_text(json.dumps(lm,indent=2)+'\n')
print(json.dumps({'assetVersion':'0.4.0','lod1Nodes':len(nodes),'lod2Nodes':len(lodnodes),'lod1Bytes':F.stat().st_size,'lod2Bytes':(P/'four-gates-city-lod2.glb').stat().st_size,'navPolygons':len(nav)},indent=2))
