"""Count unique physical GLB bytes by component; shared storage counted once."""
from pathlib import Path
import json,struct,collections,hashlib,sys,io
from PIL import Image
SIZES={5120:1,5121:1,5122:2,5123:2,5125:4,5126:4};WIDTH={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}
def inspect_glb(p):
 p=Path(p)
 raw=p.read_bytes();assert struct.unpack_from('<III',raw)==(0x46546c67,2,len(raw));pos=12;chunks=[]
 while pos<len(raw):
  n,t=struct.unpack_from('<II',raw,pos);chunks.append((t,raw[pos+8:pos+8+n]));pos+=8+n
 jb=next(v for t,v in chunks if t==0x4e4f534a);blob=next(v for t,v in chunks if t==0x004e4942);d=json.loads(jb);assert len(d['buffers'])==1
 refs=collections.defaultdict(set);cliprefs=collections.defaultdict(set)
 def ref(ai,label,clip=None):
  refs[ai].add(label)
  if clip is not None:cliprefs[ai].add(clip)
 for mesh in d.get('meshes',[]):
  for pr in mesh['primitives']:
   for k,ai in pr['attributes'].items():
    label=('skin.joint_indices'if k.startswith('JOINTS_')else'skin.weights'if k.startswith('WEIGHTS_')else'geometry.'+k)
    ref(ai,label)
   if 'indices'in pr:ref(pr['indices'],'geometry.indices')
   for target in pr.get('targets',[]):
    for k,ai in target.items():ref(ai,'corrective.'+k)
 for skin in d.get('skins',[]):
  if 'inverseBindMatrices'in skin:ref(skin['inverseBindMatrices'],'skin.inverse_bind_matrices')
 clipinfo=[]
 for i,a in enumerate(d.get('animations',[])):
  name=a.get('name',str(i));paths=collections.Counter()
  for c in a.get('channels',[]):
   s=a['samplers'][c['sampler']];path=c['target']['path'];ref(s['input'],'animation.times',name);ref(s['output'],'animation.'+path,name);paths[path]+=1
  clipinfo.append({'name':name,'channels':dict(paths),'samplers':len(a['samplers'])})
 events=collections.defaultdict(collections.Counter)
 def span(lo,hi,tags):
  assert 0<=lo<=hi<=len(blob),(lo,hi,len(blob))
  for tag in tags:events[lo][tag]+=1;events[hi][tag]-=1
 for ai,tags in refs.items():
  a=d['accessors'][ai];assert not a.get('sparse'),ai
  if 'bufferView'not in a:continue
  v=d['bufferViews'][a['bufferView']];assert v.get('buffer',0)==0 and not v.get('extensions');width=SIZES[a['componentType']]*WIDTH[a['type']];stride=v.get('byteStride',width);lo=v.get('byteOffset',0)+a.get('byteOffset',0);fulltags={'usage:'+t for t in tags}|{'clip:'+t for t in cliprefs[ai]}
  if stride==width:span(lo,lo+a['count']*width,fulltags)
  else:
   for row in range(a['count']):span(lo+row*stride,lo+row*stride+width,fulltags)
 images=[]
 for i,img in enumerate(d.get('images',[])):
  assert 'bufferView'in img and 'uri'not in img
  v=d['bufferViews'][img['bufferView']];lo=v.get('byteOffset',0);n=v['byteLength'];span(lo,lo+n,{'usage:textures','image:'+str(i)})
  im=Image.open(io.BytesIO(blob[lo:lo+n]));images.append({'image':i,'name':img.get('name'),'mime':img.get('mimeType'),'stored_bytes':n,'dimensions':list(im.size),'mode':im.mode,'material_uses':[]})
 def visit(x,path=''):
  if isinstance(x,dict):
   for k,v in x.items():
    if k.endswith('Texture')and isinstance(v,dict)and 'index'in v:
     ix=d['textures'][v['index']]['source'];images[ix]['material_uses'].append(path+'.'+k)
    else:visit(v,path+'.'+k)
  elif isinstance(x,list):
   for i,v in enumerate(x):visit(v,path+'.'+str(i))
 visit(d.get('materials',[]),'materials')
 events[0];events[len(blob)];active=collections.Counter();last=0;major=collections.Counter();detail=collections.Counter();clips=collections.Counter();shared=[]
 for at in sorted(events):
  n=at-last
  if n:
   usage=sorted(t[6:]for t,c in active.items()if c>0 and t.startswith('usage:'));groups={u.split('.')[0]for u in usage};key=next(iter(groups))if len(groups)==1 else('shared_between_categories'if groups else'unreferenced_binary_or_alignment');major[key]+=n;detail[' + '.join(usage)if usage else'unreferenced_binary_or_alignment']+=n
   cs=sorted(t[5:]for t,c in active.items()if c>0 and t.startswith('clip:'))
   if cs:clips[cs[0]if len(cs)==1 else'shared_between_clips']+=n
   if len(groups)>1:shared.append({'offset':last,'bytes':n,'usages':usage})
  active.update(events[at]);last=at
 overhead=len(raw)-len(blob);major['metadata_and_container']=overhead;assert sum(major.values())==len(raw)
 targets=[]
 for i,m in enumerate(d['meshes']):
  targets.append({'mesh':i,'name':m.get('name'),'vertices':sum(d['accessors'][pr['attributes']['POSITION']]['count']for pr in m['primitives']),'target_slots':[len(pr.get('targets',[]))for pr in m['primitives']]})
 for c in clipinfo:c['exclusive_physical_binary_bytes']=clips[c['name']]
 result={'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),'binary_bytes':len(blob),'json_chunk_bytes':len(jb),'container_bytes':overhead-len(jb),'major_physical_bytes':dict(major),'detailed_physical_bytes':dict(detail),'animation_clip_physical_bytes':dict(clips),'clips':clipinfo,'images':images,'meshes':targets,'joint_count':len({j for s in d.get('skins',[])for j in s['joints']}),'skin_count':len(d.get('skins',[])),'referenced_accessor_count':len(refs),'total_accessor_count':len(d['accessors']),'shared_cross_category_intervals':shared,'scope':'Exact raw-GLB physical byte attribution by referenced accessor element spans and embedded image spans. Overlapping/shared storage counted once. JSON metadata, chunk headers and padding separate. Not runtime memory or compressed-component attribution.'}
 return result
