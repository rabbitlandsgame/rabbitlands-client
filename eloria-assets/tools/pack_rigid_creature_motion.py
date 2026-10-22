"""Pack rigid armor through anatomical skin ownership; verify reviewed surface motion."""
from pathlib import Path
import argparse,copy,json,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import accessor,read_glb,write_glb,digest
from video_motion.packing import compact
from video_motion.native_shapes import NativeShapeAsset
from video_motion.runtime_validation import surface_sampler

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--actor',required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--profile',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
 assert args.source.resolve()!=args.output.resolve(),'Keep the reviewed source immutable'
 p=json.loads(args.profile.read_text())[args.actor];a=NativeShapeAsset(args.source);d,b=copy.deepcopy(a.d),bytearray(a.b);pr=d['meshes'][0]['primitives'][0];assert len(d['meshes'])==len(d['meshes'][0]['primitives'])==1
 owners=np.full(len(a.vertices),-1,int)
 for piece in p['rigid_pieces']:
  ix=piece['vertices'];assert (owners[ix]<0).all();owners[ix]=piece['owner']
 assert (owners>=0).all();joints=d['skins'][0]['joints'];skin=np.array([joints.index(int(x)) for x in owners],dtype='<u2');joint=np.zeros((len(owners),4),dtype='<u2');joint[:,0]=skin;weight=np.zeros((len(owners),4),dtype='<f4');weight[:,0]=1
 def add(v,component):
  b.extend(b'\0'*(-len(b)%4));d['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':v.nbytes});b.extend(v.tobytes());d['accessors'].append({'bufferView':len(d['bufferViews'])-1,'componentType':component,'count':len(v),'type':'VEC4'});return len(d['accessors'])-1
 pr['attributes']['JOINTS_0']=add(joint,5123);pr['attributes']['WEIGHTS_0']=add(weight,5126)
 for k in ['JOINTS_1','WEIGHTS_1']:pr['attributes'].pop(k,None)
 for me in d['meshes']:
  me.pop('weights',None)
  if 'extras' in me:me['extras'].pop('targetNames',None)
  for primitive in me['primitives']:primitive.pop('targets',None)
 for node in d['nodes']:node.pop('weights',None)
 for an in d['animations']:
  an['channels']=[ch for ch in an['channels'] if ch['target']['path']!='weights'];kept=sorted({ch['sampler'] for ch in an['channels']});remap={ix:k for k,ix in enumerate(kept)};an['samplers']=[an['samplers'][ix] for ix in kept]
  for ch in an['channels']:ch['sampler']=remap[ch['sampler']]
 d['asset']['extras']['rabbitlands_rigid_skin_preparation']='Complete source sections assigned to their existing anatomical controls; reviewed corrective surfaces replaced by measured equivalent skin motion.'
 d,b,packing=compact(d,b);write_glb(args.output,d,b);final=NativeShapeAsset(args.output)
 assert np.linalg.norm(a.vertices-final.vertices,axis=1).max()/p['height']<1e-6 and np.array_equal(a.rest,final.rest) and a.d['materials']==final.d['materials'] and all(x['joints']==y['joints'] and np.array_equal(accessor(a.d,a.b,x['inverseBindMatrices']),accessor(final.d,final.b,y['inverseBindMatrices'])) for x,y in zip(a.d['skins'],final.d['skins']))
 for key,ix in a.d['meshes'][0]['primitives'][0]['attributes'].items():
  if not key.startswith(('JOINTS_','WEIGHTS_')):assert np.array_equal(accessor(a.d,a.b,ix),accessor(final.d,final.b,final.d['meshes'][0]['primitives'][0]['attributes'][key]))
 assert np.array_equal(accessor(a.d,a.b,a.d['meshes'][0]['primitives'][0]['indices']),accessor(final.d,final.b,final.d['meshes'][0]['primitives'][0]['indices']))
 for im,im2 in zip(a.d['images'],final.d['images']):
  v=a.d['bufferViews'][im['bufferView']];v2=final.d['bufferViews'][im2['bufferView']];assert a.b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]==final.b[v2.get('byteOffset',0):v2.get('byteOffset',0)+v2['byteLength']]
 oldsample=surface_sampler(a);newsample=surface_sampler(final);report={'passed':True,'reviewed_sha256':digest(args.source),'runtime_sha256':digest(args.output),'reviewed_bytes':args.source.stat().st_size,'runtime_bytes':args.output.stat().st_size,'geometry_topology_uv_normals_images_rest_bind_and_joint_curves_preserved':True,'skin_preparation':'Complete rigid component ownership; no texture downsampling or approximate curve reduction.','original_generic_skin_replaced':True,'corrective_targets_removed':True,'packing':packing,'clips':{}}
 for cl,an in a.animations.items():
  by={(ch['target']['node'],ch['target']['path']):ch for ch in final.animations[cl]['channels']};times=[]
  for ch in an['channels']:
   sm=an['samplers'][ch['sampler']];ts=accessor(a.d,a.b,sm['input']).ravel();times.extend(ts.tolist())
   if ch['target']['path']=='weights':continue
   fm=final.animations[cl]['samplers'][by[(ch['target']['node'],ch['target']['path'])]['sampler']]
   for field in ['input','output']:assert np.array_equal(accessor(a.d,a.b,sm[field]),accessor(final.d,final.b,fm[field]))
  times=np.unique(times);times=np.unique(np.r_[times,(times[:-1]+times[1:])/2]);maximum=0.
  t,q,scale,m=a.sample(cl,times)
  for k in range(len(times)):
   w=a.world(t[k],q[k],scale[k]);mm={n:v[k] for n,v in m.items()};error=float(np.linalg.norm(oldsample(w,mm)-newsample(w,{}),axis=1).max()/p['height']);maximum=max(maximum,error)
  assert maximum<.00015,(cl,maximum);report['clips'][cl]={'keys_and_between_key_samples':len(times),'all_vertex_maximum_review_surface_error_over_height':maximum};print(cl,report['clips'][cl],flush=True)
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n');print('RIGID_RUNTIME_PASS',args.output.stat().st_size,flush=True)
if __name__=='__main__':main()
