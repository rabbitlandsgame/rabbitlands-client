"""Evaluate the supported native TRS and corrective-shape GLBs for motion QA."""
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from .asset import read_glb, accessor

class NativeShapeAsset:
 def __init__(self,path):
  self.path=Path(path);self.d,self.b=read_glb(path);nodes=self.d['nodes'];self.n=len(nodes)
  self.names=[n.get('name',str(i)) for i,n in enumerate(nodes)];self.ids={n:i for i,n in enumerate(self.names)}
  self.parent=np.full(self.n,-1,int)
  for i,n in enumerate(nodes):
   for c in n.get('children',[]):self.parent[c]=i
  self.order=[]
  def visit(n):
   if n in self.order:return
   if self.parent[n]>=0:visit(self.parent[n])
   self.order.append(n)
  for n in range(self.n):visit(n)
  self.t=np.array([n.get('translation',[0,0,0]) for n in nodes],float);self.q=np.array([n.get('rotation',[0,0,0,1]) for n in nodes],float);self.s=np.array([n.get('scale',[1,1,1]) for n in nodes],float)
  for i,node in enumerate(nodes):
   if 'matrix' not in node:continue
   matrix=np.asarray(node['matrix'],float).reshape(4,4).T;scale=np.linalg.norm(matrix[:3,:3],axis=0)
   if np.any(scale<1e-12):raise ValueError('Singular rest matrix')
   if np.linalg.det(matrix[:3,:3])<0:scale[np.argmax(scale)]*=-1
   rotation=matrix[:3,:3]/scale[None,:]
   if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-7):raise ValueError('Sheared rest matrix')
   self.t[i]=matrix[:3,3];self.s[i]=scale;self.q[i]=Rotation.from_matrix(rotation).as_quat()
  self.joints=sorted({j for sk in self.d.get('skins',[]) for j in sk['joints']});self.parts=[];self.default_weights={}
  for ni,node in enumerate(nodes):
   if 'mesh' not in node:continue
   mesh=self.d['meshes'][node['mesh']];count=max([len(p.get('targets',[])) for p in mesh['primitives']],default=0)
   self.default_weights[ni]=np.array(node.get('weights',mesh.get('weights',[0.]*count)))
   for prim in mesh['primitives']:
    at=prim['attributes'];pos=accessor(self.d,self.b,at['POSITION']);p={'node':ni,'position':np.c_[pos,np.ones(len(pos))]}
    p['targets']=np.array([accessor(self.d,self.b,tr['POSITION']) if 'POSITION' in tr else np.zeros_like(pos) for tr in prim.get('targets',[])])
    if 'skin' in node:
     sk=self.d['skins'][node['skin']];sets=sorted(int(k.split('_')[1]) for k in at if k.startswith('JOINTS_'))
     p['joints']=np.concatenate([accessor(self.d,self.b,at[f'JOINTS_{k}']).astype(int) for k in sets],axis=1)
     p['weights']=np.concatenate([accessor(self.d,self.b,at[f'WEIGHTS_{k}']) for k in sets],axis=1)
     p['nodes']=np.array(sk['joints']);p['bind']=accessor(self.d,self.b,sk['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
     assert np.allclose(p['weights'].sum(1),1,atol=2e-4)
    self.parts.append(p)
  self.animations={a['name']:a for a in self.d['animations']};self.rest=self.world(self.t,self.q,self.s);self.vertices=self.skin(self.rest)
 def world(self,t,q,s=None):
  if s is None:s=self.s
  local=np.tile(np.eye(4),(self.n,1,1));local[:,:3,:3]=Rotation.from_quat(q).as_matrix()*s[:,None,:];local[:,:3,3]=t
  out=np.empty_like(local)
  for n in self.order:out[n]=local[n] if self.parent[n]<0 else out[self.parent[n]]@local[n]
  return out
 def skin(self,world,weights=None):
  result=[];weights=self.default_weights if weights is None else weights
  for p in self.parts:
   pos=p['position'].copy()
   if len(p['targets']):pos[:,:3]+=np.einsum('m,mvc->vc',weights.get(p['node'],self.default_weights[p['node']]),p['targets'])
   if 'joints' not in p:result.append((world[p['node']]@pos.T).T[:,:3]);continue
   transforms=world[p['nodes']]@p['bind'];v=np.zeros((len(pos),3))
   for k in range(p['joints'].shape[1]):v+=np.einsum('vab,vb->va',transforms[p['joints'][:,k],:3],pos)*p['weights'][:,k,None]
   result.append(v)
  return np.concatenate(result)
 def sample(self,clip,times):
  times=np.atleast_1d(times).astype(float);t=np.tile(self.t,(len(times),1,1));q=np.tile(self.q,(len(times),1,1));s=np.tile(self.s,(len(times),1,1));mw={n:np.tile(w,(len(times),1)) for n,w in self.default_weights.items()}
  for ch in self.animations[clip]['channels']:
   sm=self.animations[clip]['samplers'][ch['sampler']];ts=accessor(self.d,self.b,sm['input']).ravel();values=accessor(self.d,self.b,sm['output']);node=ch['target']['node'];kind=ch['target']['path'];mode=sm.get('interpolation','LINEAR')
   if kind=='weights':values=values.reshape(len(ts),-1)
   x=np.clip(times,ts[0],ts[-1])
   if len(ts)==1:res=np.tile(values[0],(len(times),1))
   elif mode=='STEP':res=values[np.clip(np.searchsorted(ts,x,side='right')-1,0,len(ts)-1)]
   elif mode=='LINEAR' and kind=='rotation':res=Slerp(ts,Rotation.from_quat(values))(x).as_quat()
   elif mode=='LINEAR':res=np.array([np.interp(x,ts,values[:,k]) for k in range(values.shape[1])]).T
   else:raise ValueError('Unsupported interpolation '+mode)
   if kind=='translation':t[:,node]=res
   elif kind=='rotation':q[:,node]=res
   elif kind=='scale':s[:,node]=res
   elif kind=='weights':mw[node]=res
   else:raise ValueError(kind)
  return t,q,s,mw
 def duration(self,clip):return float(max(accessor(self.d,self.b,sm['input'])[-1,0] for sm in self.animations[clip]['samplers']))
 def own(self,nodes):return np.concatenate([(p['weights']*np.isin(p['nodes'][p['joints']],nodes)).sum(1) if 'joints' in p else np.zeros(len(p['position'])) for p in self.parts])
