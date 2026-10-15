import json, math, struct
from pathlib import Path
import numpy as np

P=Path('four-gates-city-package'); F=P/'four-gates-city.glb'; raw=F.read_bytes(); jl,_=struct.unpack_from('<I4s',raw,12); g=json.loads(raw[20:20+jl]); bo=20+jl; bl,_=struct.unpack_from('<I4s',raw,bo); buf=bytearray(raw[bo+8:bo+8+bl])
def align():
 while len(buf)%4:buf.append(0)
def view(data,target=None):
 align();o=len(buf);buf.extend(data);d={'buffer':0,'byteOffset':o,'byteLength':len(data)}
 if target:d['target']=target
 g['bufferViews'].append(d);return len(g['bufferViews'])-1
def acc(a,typ,comp=5126,target=34962):
 a=np.asarray(a,np.float32 if comp==5126 else np.uint32);d={'bufferView':view(a.tobytes(),target),'componentType':comp,'count':len(a),'type':typ,'min':a.min(0).tolist() if a.ndim>1 else [float(a.min())],'max':a.max(0).tolist() if a.ndim>1 else [float(a.max())]};g['accessors'].append(d);return len(g['accessors'])-1
nodes=g['nodes']; ni={n['name']:i for i,n in enumerate(nodes)}; mi={m['name']:i for i,m in enumerate(g['meshes'])}; mati={m['name']:i for i,m in enumerate(g['materials'])}
def ensure_mesh(name,prototype,material):
 if name in mi:return
 src=g['meshes'][mi[prototype]]; clone={'name':name,'primitives':[dict(src['primitives'][0])]};clone['primitives'][0]['attributes']=dict(src['primitives'][0]['attributes']);clone['primitives'][0]['material']=mati[material];g['meshes'].append(clone);mi[name]=len(g['meshes'])-1
ensure_mesh('cone_bronze','cone_roof','bronze')
def node(name,parent,mesh,pos,scale=(1,1,1),rot=None,extras=None):
 d={'name':name,'mesh':mesh,'translation':list(map(float,pos)),'scale':list(map(float,scale))}
 if rot:d['rotation']=rot
 if extras:d['extras']=extras
 nodes.append(d);nodes[ni[parent]].setdefault('children',[]).append(len(nodes)-1);return len(nodes)-1

# True thick pointed arch ring, centered at origin in XY and extruded in Z.
def arch_mesh(name,outer=38,inner=27,height=42,depth=9,segments=20,material='stone'):
 verts=[];uv=[];faces=[]
 # semicircular ring with slightly raised Gothic apex
 for z in [-depth/2,depth/2]:
  for r in [outer,inner]:
   for i in range(segments+1):
    a=math.pi*i/segments; x=r*math.cos(a); y=height+r*math.sin(a)+6*(1-abs(2*i/segments-1));verts.append([x,y,z]);uv.append([i/segments,0 if r==inner else 1])
 ring=segments+1
 for side in range(2):
  base=side*2*ring
  for i in range(segments):
   o0,o1=base+i,base+i+1;i0,i1=base+ring+i,base+ring+i+1;faces += [[o0,o1,i1],[o0,i1,i0]] if side else [[o0,i1,o1],[o0,i0,i1]]
 for band in range(2):
  for i in range(segments):
   a=band*2*ring+i;b=band*2*ring+i+1;c=(1-band)*2*ring+i+1;d=(1-band)*2*ring+i;faces += [[a,b,c],[a,c,d]]
 v=np.array(verts,np.float32); n=v.copy();n[:,1]=0;n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-6);t=np.cross(np.tile([0.,1.,0.],(len(n),1)),n);weak=np.linalg.norm(t,axis=1)<1e-5;t[weak]=[1,0,0];t/=np.maximum(np.linalg.norm(t,axis=1,keepdims=True),1e-6);t=np.column_stack((t,np.ones(len(t),np.float32)));p={'attributes':{'POSITION':acc(v,'VEC3'),'NORMAL':acc(n,'VEC3'),'TEXCOORD_0':acc(np.array(uv,np.float32),'VEC2'),'TANGENT':acc(t,'VEC4')},'indices':acc(np.array(faces,np.uint32).reshape(-1),'SCALAR',5125,34963),'material':mati[material]};g['meshes'].append({'name':name,'primitives':[p]});mi[name]=len(g['meshes'])-1;return mi[name]
arch=arch_mesh('landmark_pointed_arch')
arch_trim=arch_mesh('landmark_pointed_arch_bronze',40,36,42,10,20,'bronze')
gates={'Gate_South_Outer':(0,570,0,0.9),'Gate_South_Inner':(0,345,0,1.35),'Gate_North':(0,-345,0,1.25),'Gate_East':(345,0,math.pi/2,.9),'Gate_West':(-345,0,math.pi/2,.9)}
for parent,(x,z,ry,s) in gates.items():
 q=[0,math.sin(ry/2),0,math.cos(ry/2)];node(parent+'_Arch_LOD0',parent,arch,(x,30,z),(s,s,s),q);node(parent+'_Arch_Trim_LOD0',parent,arch_trim,(x,30,z),(s,s,s),q)
 # layered buttresses, finials and blue façade beacons
 for side in [-1,1]:
  off=49*s*side
  px,pz=(x+off,z) if ry==0 else (x,z+off)
  node(parent+f'_Buttress_{side:+}',parent,mi['cube_dark-stone'],(px,61,z if ry==0 else pz),(10*s,62*s,14*s) if ry==0 else (14*s,62*s,10*s))
  node(parent+f'_Finial_{side:+}',parent,mi['cone_bronze'],(px,104*s,z if ry==0 else pz),(5*s,20*s,5*s))
  node(parent+f'_Beacon_{side:+}',parent,mi['cone_blue-crystal'],(px,88*s,z if ry==0 else pz),(4*s,15*s,4*s),extras={'effect':'blue-energy','lod':'LOD0'})

# Sanctuary crown and central monument rings.
for a in range(0,360,30):
 r=65;rad=math.radians(a);x,z=r*math.sin(rad),-730+r*math.cos(rad);node(f'Sanctuary_Spire_{a:03}','Northern_Sanctuary',mi['cylinder_stone'],(x,82,z),(7,48,7));node(f'Sanctuary_Spire_Roof_{a:03}','Northern_Sanctuary',mi['cone_roof'],(x,112,z),(10,18,10));node(f'Sanctuary_Spire_Crystal_{a:03}','Northern_Sanctuary',mi['cone_blue-crystal'],(x,126,z),(4,12,4),extras={'effect':'blue-energy'})
for ring,r in enumerate([32,46,61]):
 for a in range(0,360,30):
  rad=math.radians(a);x,z=r*math.sin(rad),r*math.cos(rad);node(f'Plaza_Stair_{ring}_{a:03}','Central_Plaza',mi['cube_paving'],(x,31+ring*.8,z),(18,2,8),rot=[0,math.sin(rad/2),0,math.cos(rad/2)])

# Standard animations: gate portcullises and sanctuary/central energy pulse.
times=np.array([0,1.5,3],np.float32); ta=acc(times,'SCALAR',target=None); animations=[]
for parent in gates:
 target=ni[parent+'_Portcullis']; base=nodes[target]['translation']; vals=np.array([base,[base[0],base[1]+38,base[2]],base],np.float32); oa=acc(vals,'VEC3',target=None);animations.append({'name':parent+'_OpenClose','samplers':[{'input':ta,'output':oa,'interpolation':'LINEAR'}],'channels':[{'sampler':0,'target':{'node':target,'path':'translation'}}]})
for name in ['Sanctuary_Beacon','Plaza_Monument_Crystal']:
 vals=np.array([[1,1,1],[1.12,1.2,1.12],[1,1,1]],np.float32);oa=acc(vals,'VEC3',target=None);animations.append({'name':name+'_Pulse','samplers':[{'input':ta,'output':oa,'interpolation':'LINEAR'}],'channels':[{'sampler':0,'target':{'node':ni[name],'path':'scale'}}]})
g['animations']=animations;g['asset']['generator']='Eloria Four Gates production environment 0.3'
align();g['buffers'][0]['byteLength']=len(buf);jb=json.dumps(g,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);F.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(buf))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(buf),b'BIN\0')+buf)

m=json.loads((P/'four-gates-city.json').read_text());m['assetVersion']='0.3.0';m['animations']=[{'name':a['name'],'standard':'glTF-2.0','optional':True} for a in animations];m['navigation']['navmesh']={'format':'inline-convex-polygons-v1','coordinateSystem':'asset','agentRadius':0.6,'agentHeight':2.0,'maxSlopeDegrees':35,'polygons':[{'id':'plaza','vertices':[[-72,31,-72],[72,31,-72],[72,31,72],[-72,31,72]]},{'id':'south-axis','vertices':[[-13,31,0],[13,31,0],[13,31,620],[-13,31,620]]},{'id':'north-axis','vertices':[[-14,31,-690],[14,31,-690],[14,31,0],[-14,31,0]]},{'id':'east-axis','vertices':[[0,31,-13],[620,31,-13],[620,31,13],[0,31,13]]},{'id':'west-axis','vertices':[[-620,31,-13],[0,31,-13],[0,31,13],[-620,31,13]]}],'offMeshLinks':[{'id':'sanctuary-rise','start':[0,34,-620],'end':[0,55,-690],'bidirectional':True,'type':'ramp'}]};m['lodGroups'][0]={'id':'city-landmarks','strategy':'node-suffix','levels':[{'id':'LOD0','suffix':'_LOD0','screenCoverage':0.35},{'id':'LOD1','suffix':None,'screenCoverage':0.08},{'id':'LOD2','proposedSibling':'four-gates-city-lod2.glb','screenCoverage':0.0}],'fallback':'LOD1'};m['knownLimitations']=[x for x in m['knownLimitations'] if 'Navigation is path' not in x];m['knownLimitations'].append('Inline navmesh covers principal axes and plaza; district alley polygons remain to be baked from final collision geometry.');(P/'four-gates-city.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'assetVersion':'0.3.0','nodes':len(nodes),'meshes':len(g['meshes']),'animations':len(animations),'glbBytes':F.stat().st_size},indent=2))
