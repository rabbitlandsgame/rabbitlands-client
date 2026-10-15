"""Finger deformation and the weights-only player-body authoring contract."""
from __future__ import annotations
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import equipment_authoring as ea

FINGERS=('thumb','index','middle','ring','pinky')

def unique_skin_accessors(d):
 return {tuple(p['attributes'][k] for k in ('POSITION','JOINTS_0','WEIGHTS_0'))
         for m in d['meshes'] for p in m['primitives'] if 'JOINTS_0' in p['attributes']}

def immutable_digest(d,b):
 # Zero only the skin accessor bytes. Every position, normal, UV, index,
 # inverse bind and embedded texture byte, and the complete rig, stays pinned.
 masked=bytearray(b)
 for pi,ji,wi in unique_skin_accessors(d):
  for index in (ji,wi):
   a=d['accessors'][index];v=d['bufferViews'][a['bufferView']]
   width=ea.accessor_array(d,b,index).dtype.itemsize*4
   start=v.get('byteOffset',0)+a.get('byteOffset',0)
   for row in range(a['count']):
    offset=start+row*v.get('byteStride',width);masked[offset:offset+width]=bytes(width)
 metadata=copy.deepcopy(d)
 metadata.get('asset',{}).get('extras',{}).pop('sharedBodyShape',None)
 return hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()+masked).hexdigest()

def outside_hands_digest(d,b,hand_rows):
 h=hashlib.sha256()
 for pi,ji,wi in sorted(unique_skin_accessors(d)):
  p=ea.accessor_array(d,b,pi);outside=np.ones(len(p),bool)
  for start,end in hand_rows[f'{pi}:{ji}:{wi}']:outside[start:end]=False
  h.update(ea.accessor_array(d,b,ji)[outside].tobytes());h.update(ea.accessor_array(d,b,wi)[outside].tobytes())
 return h.hexdigest()

class HandSkinningTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.record=json.loads((ROOT/'eloria-assets/qa/held-hand-skinning.json').read_text())
  cls.library=ea.read_glb(ROOT/'godot-client/assets/actors/native/shared/Universal_Animation_Library.glb')

 def test_all_player_bodies_keep_their_geometry_rig_textures_and_other_skin(self):
  models=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())
  self.assertEqual(set(self.record['bodies']),{o['model'] for o in models['creationOptions']})
  for slug,pin in self.record['bodies'].items():
   with self.subTest(body=slug):
    path=ROOT/'godot-client/assets/actors/native/races'/f'{slug}.glb'
    d,b=ea.read_glb(path)
    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),pin['candidateSHA256'])
    self.assertEqual(immutable_digest(d,b),pin['immutablePayloadSHA256'])
    self.assertEqual(outside_hands_digest(d,b,pin['handRows']),pin['outsideHandsSkinSHA256'])
    names=[d['nodes'][i]['name'] for i in d['skins'][0]['joints']]
    counts={f'{finger}_{side}':0 for side in ('l','r') for finger in FINGERS}
    for pi,ji,wi in unique_skin_accessors(d):
     if pin['handRows'][f'{pi}:{ji}:{wi}']:
      self.assertEqual(d['accessors'][ji]['componentType'],5121,'hand joint storage must stay u8')
     # Separate head accessors retain their original u16 format, pinned by
     # immutable_digest above along with the full original accessor JSON.
     j=ea.accessor_array(d,b,ji);w=ea.accessor_array(d,b,wi)
     self.assertTrue(np.isfinite(w).all());self.assertGreaterEqual(float(w.min()),0)
     np.testing.assert_allclose(w.sum(1),1,atol=2e-4)
     for key in counts:
      finger,side=key.split('_');ids=[names.index(f'{finger}_{joint:02d}_{side}') for joint in (1,2,3)]
      counts[key]+=int((np.isin(j,ids)&(w>1e-4)).any(1).sum())
    for key,count in counts.items():self.assertGreater(count,20,f'{slug} {key} is still rigid')

 def test_authoring_tool_refuses_an_overwrite_or_a_second_skinning_pass(self):
  import reskin_human_hands as hs
  source=ROOT/'godot-client/assets/actors/native/races/luminous_female.glb'
  original=source.read_bytes()
  with self.assertRaisesRegex(ValueError,'separate output'):hs.reskin(source,source)
  with tempfile.TemporaryDirectory() as scratch:
   target=Path(scratch)/'twice.glb'
   with self.assertRaisesRegex(ValueError,'already has finger weights'):hs.reskin(source,target)
   self.assertFalse(target.exists())
  self.assertEqual(source.read_bytes(),original)

 def test_both_human_hands_deform_in_combat_and_the_regular_sword_cut(self):
  ld,lb=self.library
  for sex in ('male','female'):
   path=ROOT/'godot-client/assets/actors/native/races'/f'luminous_{sex}.glb'
   d,b=ea.read_glb(path);rig=ea.load_rig(path);rest=ea.global_matrices(d)
   edges=np.unique(np.sort(np.concatenate([rig.faces[:,[0,1]],rig.faces[:,[1,2]],rig.faces[:,[2,0]]]),axis=1),axis=0)
   rest_length=np.linalg.norm(rig.positions[edges[:,0]]-rig.positions[edges[:,1]],axis=1)
   hand_edges=(np.abs(rig.positions[edges,0])>.78).all(1)&(rest_length>.001)
   for clip in ('Fighting_Idle','Sword_Regular_A'):
    for time in (0.,.35,.65):
     posed=copy.deepcopy(d);sample=ea._sample_clip_rotations(ld,lb,clip,time)
     for node in posed['nodes']:
      name=node.get('name','')
      if name.startswith(tuple(f+'_' for f in FINGERS)):node['rotation']=sample[name]['rotation'].tolist()
     world=ea.global_matrices(posed)
     transforms=np.array([world[i]@np.linalg.inv(rest[i]) for i in d['skins'][0]['joints']])
     hp=np.column_stack((rig.positions,np.ones(len(rig.positions))))
     moved=np.einsum('nv,nvij,nj->ni',rig.weights,transforms[rig.joints],hp)[:,:3]
     with self.subTest(sex=sex,clip=clip,time=time):
      self.assertTrue(np.isfinite(moved).all())
      for side,sign in (('r',-1),('l',1)):
       hand=sign*rig.positions[:,0]>.82
       displacement=np.linalg.norm(moved[hand]-rig.positions[hand],axis=1)
       self.assertGreater(float(np.percentile(displacement,75)),.015,f'{side} fingers do not bend')
       self.assertLess(float(displacement.max()),.22,'finger flew away from the palm')
      length=np.linalg.norm(moved[edges[:,0]]-moved[edges[:,1]],axis=1)
      self.assertLess(float(np.percentile(length[hand_edges]/rest_length[hand_edges],99)),3.3,'knuckle/web deformation stretched excessively')

if __name__=='__main__':unittest.main()
