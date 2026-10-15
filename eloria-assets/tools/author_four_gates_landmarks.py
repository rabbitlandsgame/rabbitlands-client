import json, math, random, struct
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

P=Path('four-gates-city-package');F=P/'four-gates-city.glb';T=P/'textures';T.mkdir(exist_ok=True)
raw=F.read_bytes();jl,_=struct.unpack_from('<I4s',raw,12);g=json.loads(raw[20:20+jl]);bo=20+jl;bl,_=struct.unpack_from('<I4s',raw,bo);buf=bytearray(raw[bo+8:bo+8+bl])
def align():
 while len(buf)%4:buf.append(0)
def view(data,target=None):
 align();o=len(buf);buf.extend(data);d={'buffer':0,'byteOffset':o,'byteLength':len(data)}
 if target:d['target']=target
 g['bufferViews'].append(d);return len(g['bufferViews'])-1
def acc(a,typ,comp=5126,target=34962):
 a=np.asarray(a,np.float32 if comp==5126 else np.uint32);d={'bufferView':view(a.tobytes(),target),'componentType':comp,'count':len(a),'type':typ,'min':a.min(0).tolist() if a.ndim>1 else [float(a.min())],'max':a.max(0).tolist() if a.ndim>1 else [float(a.max())]};g['accessors'].append(d);return len(g['accessors'])-1
def mesh(name,v,f,n,uv,mat):
 n=np.asarray(n,np.float32);t=np.cross(np.tile([0.,1.,0.],(len(n),1)),n);weak=np.linalg.norm(t,axis=1)<1e-5;t[weak]=[1,0,0];t/=np.maximum(np.linalg.norm(t,axis=1,keepdims=True),1e-6);t=np.column_stack((t,np.ones(len(t),np.float32)));p={'attributes':{'POSITION':acc(v,'VEC3'),'NORMAL':acc(n,'VEC3'),'TEXCOORD_0':acc(uv,'VEC2'),'TANGENT':acc(t,'VEC4')},'indices':acc(np.asarray(f,np.uint32).reshape(-1),'SCALAR',5125,34963),'material':mat};g['meshes'].append({'name':name,'primitives':[p]});return len(g['meshes'])-1
def write(path,doc,binary):
 align();doc['buffers'][0]['byteLength']=len(binary);jb=json.dumps(doc,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(binary))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(binary),b'BIN\0')+binary)

def normalize_atlas(image,grid):
 image=image.convert('RGB');w,h=image.size;tile=1024//grid;result=Image.new('RGB',(1024,1024))
 for row in range(grid):
  for col in range(grid):
   box=(round(col*w/grid),round(row*h/grid),round((col+1)*w/grid),round((row+1)*h/grid))
   result.paste(image.crop(box).resize((tile,tile),Image.Resampling.LANCZOS),(col*tile,row*tile))
 return result

def normal_atlas(image,grid,strength):
 source=np.asarray(image.convert('L'),np.float32)/255.;result=np.empty((1024,1024,3),np.uint8);tile=1024//grid
 for row in range(grid):
  for col in range(grid):
   y0,y1=row*tile,(row+1)*tile;x0,x1=col*tile,(col+1)*tile;gray=source[y0:y1,x0:x1]
   gy,gx=np.gradient(gray);normal=np.dstack((-gx*strength,-gy*strength,np.ones_like(gray)));normal/=np.maximum(np.linalg.norm(normal,axis=2,keepdims=True),1e-6)
   result[y0:y1,x0:x1]=((normal*.5+.5)*255).astype(np.uint8)
 return Image.fromarray(result)

# Dedicated landmark texture family.  The restrained charcoal-and-gold value
# hierarchy keeps the blue inlays legible without turning whole façades cyan.
def paint_landmark_atlas(path):
 quadrants=[(76,76,74),(147,101,35),(55,58,59),(31,91,166)]
 rng=np.random.default_rng(407);image=Image.new('RGB',(1024,1024));draw=ImageDraw.Draw(image)
 for tile,color in enumerate(quadrants):
  x=(tile%2)*512;y=(tile//2)*512
  noise=rng.normal(0,3.4,(512,512,1));base=np.asarray(color,dtype=np.float32)[None,None,:]
  patch=Image.fromarray(np.clip(base+noise,0,255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(.7));image.paste(patch,(x,y))
  dark=tuple(max(0,c-14) for c in color);light=tuple(min(255,c+13) for c in color)
  if tile in (0,2):
   for row in range(0,512,52):
    draw.line((x,y+row,x+511,y+row),fill=dark,width=3)
    offset=43 if (row//52)%2 else 0
    for col in range(-offset,512,86):draw.line((x+col,y+row,x+col,y+min(51+row,511)),fill=dark,width=3)
  elif tile==1:
   for line in range(14,512,30):draw.line((x+line,y,x+line,y+511),fill=light,width=3)
  else:
   for line in range(-420,900,60):draw.line((x+line,y+511,x+line+260,y),fill=light,width=5)
 image.save(path,optimize=True);return image
src=paint_landmark_atlas(T/'four-gates-landmark-trims-source.png');src.save(T/'four-gates-landmark-basecolor.png',optimize=True)
normal_atlas(src,2,.58).save(T/'four-gates-landmark-normal.png',optimize=True)
orm=np.zeros((1024,1024,3),np.uint8);orm[:,:,0]=238;orm[:,:,1]=210;orm[:512,512:,1]=96;orm[:512,512:,2]=220;orm[512:,512:,1]=105;orm[512:,512:,2]=25;Image.fromarray(orm).save(T/'four-gates-landmark-orm.png',optimize=True)
em=np.zeros((1024,1024,3),np.uint8);em[512:,512:]=np.asarray(src)[512:,512:];Image.fromarray(em).save(T/'four-gates-landmark-emissive.png',optimize=True)
start_tex=len(g.get('textures',[]));ivs=[]
for fn in ['four-gates-landmark-basecolor.png','four-gates-landmark-normal.png','four-gates-landmark-orm.png','four-gates-landmark-emissive.png']:ivs.append(view((T/fn).read_bytes()))
g.setdefault('images',[]).extend([{'name':n,'bufferView':v,'mimeType':'image/png'} for n,v in zip(['landmark-basecolor','landmark-normal','landmark-orm','landmark-emissive'],ivs)])
source0=len(g['images'])-4;g.setdefault('textures',[]).extend([{'sampler':0,'source':source0+i} for i in range(4)])
def ti(idx,c,r):return {'index':start_tex+idx,'extensions':{'KHR_texture_transform':{'offset':[c*.5,(1-r)*.5],'scale':[.5,.5]}}}
mat0=len(g['materials'])
for name,c,r,metal,rough,emissive in [('landmark-stone',0,0,0,.72,False),('landmark-bronze',1,0,1,.38,False),('landmark-foundation',0,1,0,.9,False),('landmark-energy',1,1,.5,.22,True)]:
 d={'name':name,'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':1,'roughnessFactor':1,'baseColorTexture':ti(0,c,r),'metallicRoughnessTexture':ti(2,c,r)},'normalTexture':ti(1,c,r),'occlusionTexture':ti(2,c,r)}
 if emissive:d['emissiveFactor']=[.05,.24,.72];d['emissiveTexture']=ti(3,c,r)
 g['materials'].append(d)

# Authored multi-ring tower shaft.
seg=32;rings=[(-.5,.52),(-.34,.58),(-.30,.48),(.18,.46),(.22,.55),(.38,.43),(.5,.38)];v=[];n=[];uv=[]
for ri,(y,r) in enumerate(rings):
 for i in range(seg):
  a=math.tau*i/seg;v.append([r*math.cos(a),y,r*math.sin(a)]);n.append([math.cos(a),0,math.sin(a)]);uv.append([i/seg,ri/(len(rings)-1)])
f=[]
for q in range(len(rings)-1):
 for i in range(seg):j=(i+1)%seg;a=q*seg+i;b=q*seg+j;c=(q+1)*seg+j;d=(q+1)*seg+i;f += [[a,b,c],[a,c,d]]
tower_mesh=mesh('authored_landmark_tower',v,f,n,uv,mat0)

# Ribbed dome/cupola mesh.
lat=14;seg=32;v=[];n=[];uv=[]
for j in range(lat+1):
 p=(math.pi/2)*j/lat;y=math.sin(p)*.55;rr=math.cos(p)*(.5-.08*j/lat)
 for i in range(seg):
  a=math.tau*i/seg;v.append([rr*math.cos(a),y-.5,rr*math.sin(a)]);nn=[math.cos(a)*math.cos(p),math.sin(p),math.sin(a)*math.cos(p)];n.append(nn);uv.append([i/seg,j/lat])
f=[]
for j in range(lat):
 for i in range(seg):k=(i+1)%seg;a=j*seg+i;b=j*seg+k;c=(j+1)*seg+k;d=(j+1)*seg+i;f += [[a,b,c],[a,c,d]]
dome_mesh=mesh('authored_landmark_dome',v,f,n,uv,mat0+1)

# Thick bridge arch module with proper extruded faces.
seg=28;v=[];n=[];uv=[]
for z in [-.5,.5]:
 for r in [.5,.34]:
  for i in range(seg+1):
   a=math.pi*i/seg;v.append([r*math.cos(a),r*math.sin(a)-.5,z]);n.append([0,0,-1 if z<0 else 1]);uv.append([i/seg,1 if r>.4 else 0])
f=[];ring=seg+1
for side in range(2):
 b=side*2*ring
 for i in range(seg):f += [[b+i,b+i+1,b+ring+i+1],[b+i,b+ring+i+1,b+ring+i]]
bridge_arch=mesh('authored_bridge_arch',v,f,n,uv,mat0+2)

# Irregular, subdivided cliff face module.
random.seed(505);cols,rows=10,6;v=[];n=[];uv=[]
for y in range(rows+1):
 for x in range(cols+1):
  xx=x/cols-.5;yy=y/rows-.5;zz=random.uniform(-.09,.09)+(1-abs(yy*2))*.06;v.append([xx,yy,zz]);n.append([0,0,1]);uv.append([x/cols,y/rows])
f=[]
for y in range(rows):
 for x in range(cols):a=y*(cols+1)+x;b=a+1;c=a+cols+2;d=a+cols+1;f += [[a,b,c],[a,c,d]]
cliff_mesh=mesh('authored_cliff_face',v,f,n,uv,mat0+2)
# Thin emissive façade inlay panel.
v=np.array([[-.5,-.5,0],[.5,-.5,0],[.5,.5,0],[-.5,.5,0]],np.float32);f=np.array([[0,1,2],[0,2,3]],np.uint32);n=np.tile([0,0,1],(4,1)).astype(np.float32);uv=np.array([[0,0],[1,0],[1,1],[0,1]],np.float32);energy_panel=mesh('authored_energy_inlay',v,f,n,uv,mat0+3)

nodes=g['nodes'];names={n['name']:i for i,n in enumerate(nodes)}
# Replace landmark tower shafts and domes without changing stable node names.
for n in nodes:
 name=n.get('name','')
 if name.endswith('_Base') and ('Gate_' in name or 'Crystal_Tower' in name):n['mesh']=tower_mesh;n.setdefault('extras',{})['authoredGeometry']='0.5'
 if name.endswith('_Roof') and ('Gate_' in name or 'Crystal_Tower' in name):n['mesh']=dome_mesh;n.setdefault('extras',{})['authoredGeometry']='0.5'
 if name.startswith('Cliff_') and name[6:].isdigit():n['mesh']=cliff_mesh;n.setdefault('extras',{})['authoredGeometry']='0.5'

def add(name,parent,meshidx,pos,scale,rot=None,extras=None):
 d={'name':name,'mesh':meshidx,'translation':list(map(float,pos)),'scale':list(map(float,scale))}
 if rot:d['rotation']=rot
 if extras:d['extras']=extras
 nodes.append(d);nodes[names[parent]].setdefault('children',[]).append(len(nodes)-1)
# Repeated structural bridge arches and landmark façade energy inlays.
for bridge,axis,vals in [('Bridge_South','z',[405,455,505,545]),('Bridge_North','z',[-610,-555,-500,-445]),('Bridge_East','x',[405,455,505,545]),('Bridge_West','x',[-545,-495,-445,-395])]:
 for k,val in enumerate(vals):
  pos=(0,28,val) if axis=='z' else (val,28,0);rot=None if axis=='z' else [0,math.sin(math.pi/4),0,math.cos(math.pi/4)];add(f'{bridge}_Authored_Arch_{k}',bridge,bridge_arch,pos,(38,55,8),rot,{'lod':'LOD0','structural':True})
for gate,(x,z,ry) in {'Gate_South_Outer':(0,570,0),'Gate_South_Inner':(0,345,0),'Gate_North':(0,-345,0),'Gate_East':(345,0,math.pi/2),'Gate_West':(-345,0,math.pi/2)}.items():
 for side in [-1,1]:
  off=55*side;px,pz=(x+off,z) if ry==0 else (x,z+off);rot=[0,math.sin(ry/2),0,math.cos(ry/2)];add(f'{gate}_Energy_Inlay_{side:+}',gate,energy_panel,(px,75,pz),(8,38,1),rot,{'effect':'blue-energy','materialFamily':'landmark-energy'})

g['asset']['generator']='Eloria Four Gates authored landmark and terrain pass 0.5';write(F,g,buf)
m=json.loads((P/'four-gates-city.json').read_text());m['assetVersion']='0.5.0';m['materials']['landmarkAtlas']={'resolution':[1024,1024],'maps':['landmark-basecolor','landmark-normal','landmark-orm','landmark-emissive'],'families':['landmark-stone','landmark-bronze','landmark-foundation','landmark-energy']};m['authoredGeometry']={'gateTowerMesh':'authored_landmark_tower','domeMesh':'authored_landmark_dome','bridgeArchMesh':'authored_bridge_arch','cliffMesh':'authored_cliff_face','replacedStableNodes':True};obs=[]
for n in nodes:
 if n.get('name','').startswith(('Residence_','Civic_Hall_','Farmhouse_','Granary_')) and n.get('name','').endswith(('Body','_0','_1','_2','_3','_4','_5','_6','_7','_8')) and 'translation'in n:obs.append({'node':n['name'],'center':n['translation'],'halfExtents':[x*.5 for x in n.get('scale',[1,1,1])]})
m['navigation']['navmesh']['obstacles']=obs[:96];m['knownLimitations']=[x for x in m['knownLimitations'] if 'Atlas UVs are procedural' not in x];m['knownLimitations'].append('General district assets retain shared atlas projection; major gate towers, domes, bridge arches, and cliffs use authored modular UVs.');(P/'four-gates-city.json').write_text(json.dumps(m,indent=2)+'\n')
# Refresh the distant sibling against the authored 0.5 source while stripping
# close overlays, props, vegetation, animations, and bridge-arch inspection detail.
drop=('Battlement_','Plaza_Bench_','Plaza_Lamp_','Market_','Farm_Fence_','Residence_','Civic_Hall_','Farmhouse_','Granary_','Irrigation_','Service_','Ring_','Vegetation_')
keep=[not n.get('name','').endswith('_LOD0') and not n.get('name','').startswith(drop) and '_Authored_Arch_' not in n.get('name','') and '_Energy_Inlay_' not in n.get('name','') for n in nodes]
remap={old:new for new,old in enumerate(i for i,k in enumerate(keep) if k)};lodnodes=[]
for old,k in enumerate(keep):
 if not k:continue
 d=dict(nodes[old]);
 if 'children'in d:d['children']=[remap[c] for c in d['children'] if c in remap]
 lodnodes.append(d)
lod=dict(g);lod['nodes']=lodnodes;lod['scenes']=[{'name':'Four Gates City LOD2','nodes':[remap[0]]}];lod.pop('animations',None);lod['asset']=dict(g['asset']);lod['asset']['generator']='Eloria Four Gates authored reduced-node LOD2 0.5';write(P/'four-gates-city-lod2.glb',lod,buf)
m['lodGroups'][0]['levels'][2].update({'glb':'four-gates-city-lod2.glb','nodeCount':len(lodnodes),'animations':0});(P/'four-gates-city.json').write_text(json.dumps(m,indent=2)+'\n');lm=json.loads(json.dumps(m));lm['asset']['glb']='four-gates-city-lod2.glb';lm['assetVersion']='0.5.0-lod2';lm['animations']=[];(P/'four-gates-city-lod2.json').write_text(json.dumps(lm,indent=2)+'\n')
print(json.dumps({'assetVersion':'0.5.0','nodes':len(nodes),'meshes':len(g['meshes']),'materials':len(g['materials']),'images':len(g['images']),'glbBytes':F.stat().st_size,'navObstacles':len(obs[:96])},indent=2))
