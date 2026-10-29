"""Publishing-only policy preservation; no runtime assets, importer or GPU required."""
import copy
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import shared_meshes as S
spec=importlib.util.spec_from_file_location('canonicalize_policy_workflow',ROOT/'eloria-assets/tools/canonicalize_map_images.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

def relative(path,base):return os.path.relpath(path,base).replace('\\','/')

class PublishingPolicy(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.maps=self.root/'eloria-assets/maps';self.pool=self.maps/'_shared/meshes';self.pool.mkdir(parents=True)
  self.image=self.maps/'_shared/images/pixel.png';self.image.parent.mkdir();self.image.write_bytes(b'unchanged encoded image bytes')
  self.original=self.maps/'old-policies/with-no-raw-files';self.original.mkdir(parents=True)
  for name,value in [('MAPS',self.maps),('POOL',self.pool),('INDEX',self.pool/'index.json')]:
   p=mock.patch.object(S,name,value);p.start();self.addCleanup(p.stop)
 def document(self,owner):
  return {'asset':{'version':'2.0'},'buffers':[{'byteLength':36}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36}],
   'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'}],
   'images':[{'uri':relative(self.image,owner.parent),'extras':{'keep':'original',S.POLICY_DIRECTORY_EXTRA:relative(self.original,owner.parent)}}],
   'textures':[{'source':0}],'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}],
   'meshes':[{'primitives':[{'attributes':{'POSITION':0},'material':0}]}]}
 def body(self):return struct.pack('<9f',0,0,0,1,0,0,0,0,1)
 def prototype(self):
  owner=self.pool/'prop.glb';doc=self.document(owner);data=S.write_glb(doc,self.body());owner.write_bytes(data);return owner,doc,data
 def test_index_entry_keeps_original_policy_and_exact_uri_spelling(self):
  owner,doc,data=self.prototype();doc['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]+='/.'
  entry=S._index_entry(doc,data);uri=doc['images'][0]['uri'];self.assertEqual(entry['imagePolicies'],{uri:[doc['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]]});self.assertEqual(entry['images'],{uri:S.sha256(self.image.read_bytes())})
 def test_collect_and_merge_rebase_policy_with_pixels_without_mutating_source(self):
  owner=self.maps/'territory/client/world.glb';doc=self.document(owner);original=copy.deepcopy(doc);out,body=S._collect(doc,self.body(),0,owner)
  image=out['images'][0];self.assertEqual((self.pool/image['uri']).resolve(),self.image.resolve());self.assertEqual((self.pool/image['extras'][S.POLICY_DIRECTORY_EXTRA]).resolve(),self.original.resolve());self.assertEqual(doc,original)
  destination=self.maps/'another/chunks/00/world.glb';merged={};S._merge(destination,merged,bytearray(),out,body);image=merged['images'][0];self.assertEqual((destination.parent/image['uri']).resolve(),self.image.resolve());self.assertEqual((destination.parent/image['extras'][S.POLICY_DIRECTORY_EXTRA]).resolve(),self.original.resolve());self.assertEqual(image['extras']['keep'],'original')
 def test_reconcile_repairs_missing_index_collection_and_preserves_newlines(self):
  owner,doc,data=self.prototype();entry=S._index_entry(doc,data);entry.pop('imagePolicies');entry['keep']='publisher metadata';raw=(json.dumps({'prototypes':{'prop':entry}},indent=1)+'\n').replace('\n','\r\n').encode();S.INDEX.write_bytes(raw)
  changed=S.reconcile(prototypes={'prop'},manifests=[]);self.assertTrue(changed);fixed=json.loads(S.INDEX.read_bytes());self.assertEqual(fixed['prototypes']['prop']['imagePolicies'],S.image_policy_collections(doc));self.assertEqual(fixed['prototypes']['prop']['keep'],'publisher metadata');self.assertEqual(owner.read_bytes(),data);self.assertNotIn(b'\r\r\n',S.INDEX.read_bytes());self.assertIn(b'\r\n',S.INDEX.read_bytes());self.assertEqual(S.reconcile(prototypes={'prop'},manifests=[]),[])
 def test_metadata_without_descriptors_is_not_silently_erased(self):
  owner,doc,data=self.prototype();entry=S._index_entry(doc,data);doc['images'][0]['extras'].pop(S.POLICY_DIRECTORY_EXTRA);data=S.write_glb(doc,self.body());owner.write_bytes(data);S.INDEX.write_text(json.dumps({'prototypes':{'prop':entry}}))
  with self.assertRaisesRegex(ValueError,'restore original policy extras'):S.reconcile(prototypes={'prop'},manifests=[])
 def test_mixed_explicit_and_implicit_identical_uri_fails_closed(self):
  owner,doc,data=self.prototype();image=copy.deepcopy(doc['images'][0]);image.pop('extras');doc['images'].append(image)
  with self.assertRaisesRegex(ValueError,'ambiguous original policy'):S._index_entry(doc,data)
 def test_unsafe_policy_is_rejected_before_indexing(self):
  owner,doc,data=self.prototype()
  for value in ['../../../../../../escape','%2e%2e','C:/outside','..\\outside','']:
   doc['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=value
   with self.subTest(value=value),self.assertRaises(ValueError):S._index_entry(doc,data)
 def test_existing_prototype_policy_guard_preserves_ids_and_legacy_reuse(self):
  source=self.maps/'region/world.glb';source.parent.mkdir();incoming=self.document(source);incoming['nodes']=[{'mesh':0}];body=self.body();identity=S.mesh_identity(incoming,body,0,source,{})[0];prototype,packed=S._collect(incoming,body,0,source);target=self.pool/(identity+'.glb');target.write_bytes(S.write_glb(prototype,packed));source.write_bytes(S.write_glb(incoming,body));index={identity:S._index_entry(prototype,target.read_bytes())}
  self.assertEqual(S.apply_to_file(source,{identity:{}},index,True)['moved'],1)
  other=self.maps/'different-policy';other.mkdir();incoming['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=relative(other,source.parent);self.assertEqual(S.mesh_identity(incoming,body,0,source,{})[0],identity);source.write_bytes(S.write_glb(incoming,body))
  with self.assertRaisesRegex(ValueError,'original texture policy differs'):S.apply_to_file(source,{identity:{}},index,True)
  # One explicit side also guards an unannotated URI's implied directory.
  incoming['images'][0]['extras'].pop(S.POLICY_DIRECTORY_EXTRA);source.write_bytes(S.write_glb(incoming,body))
  with self.assertRaisesRegex(ValueError,'original texture policy differs'):S.apply_to_file(source,{identity:{}},index,True)
  # Both legacy sides retain their historical identity/sharing behavior.
  prototype['images'][0]['extras'].pop(S.POLICY_DIRECTORY_EXTRA);target.write_bytes(S.write_glb(prototype,packed));self.assertEqual(S.apply_to_file(source,{identity:{}},index,True)['moved'],1)
 def test_embedded_incoming_reuses_matching_annotated_published_policy(self):
  source=self.maps/'region/world.glb';source.parent.mkdir();incoming=self.document(source);pixels=self.image.read_bytes();body=self.body()+pixels;incoming['nodes']=[{'mesh':0}];incoming['buffers'][0]['byteLength']=len(body);incoming['bufferViews'].append({'buffer':0,'byteOffset':36,'byteLength':len(pixels)});incoming['images']=[{'bufferView':1,'mimeType':'image/png'}]
  identity=S.mesh_identity(incoming,body,0,source,{})[0];target=self.pool/(identity+'.glb');published=self.document(target);published['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=relative(self.image.parent,target.parent);self.assertEqual(S.mesh_identity(published,self.body(),0,target,{})[0],identity);target.write_bytes(S.write_glb(published,self.body()));source.write_bytes(S.write_glb(incoming,body));index={identity:S._index_entry(published,target.read_bytes())};before_source=source.read_bytes();before_target=target.read_bytes()
  self.assertEqual(S.apply_to_file(source,{identity:{}},index,True)['moved'],1);self.assertEqual(source.read_bytes(),before_source);self.assertEqual(target.read_bytes(),before_target)
  # A genuinely different original published directory still cannot be reused.
  published['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=relative(self.original,target.parent);target.write_bytes(S.write_glb(published,self.body()))
  with self.assertRaisesRegex(ValueError,'original texture policy differs'):S.apply_to_file(source,{identity:{}},index,True)
 def test_inline_data_uri_does_not_invent_global_external_policy(self):
  source=self.maps/'region/world.glb';incoming=self.document(source);incoming['images']=[{'uri':'data:image/png;base64,cGl4ZWxz'}];target,published,_=self.prototype();published['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=relative(self.image.parent,target.parent)
  with self.assertRaisesRegex(ValueError,'original texture policy differs'):S._check_prototype_policy(incoming,0,source,published,target)
 def test_identical_effective_directory_can_mix_explicit_and_legacy(self):
  target,existing,_=self.prototype();source=self.maps/'region/world.glb';incoming=self.document(source);incoming['images'][0].pop('extras');existing['images'][0]['extras'][S.POLICY_DIRECTORY_EXTRA]=relative(self.image.parent,target.parent);S._check_prototype_policy(incoming,0,source,existing,target)
 def test_legacy_entries_keep_legacy_shape(self):
  owner,doc,data=self.prototype();doc['images'][0].pop('extras');self.assertNotIn('imagePolicies',S._index_entry(doc,data))
 def test_canonicalizer_repairs_owner_local_and_road_collections_without_aliases(self):
  owner='eloria-assets/maps/region/roads.json';image={'uri':'../canonical.png','extras':{C.POLICY_DIRECTORY_EXTRA:'../original'}}
  document={'resources':{'../canonical.png':'a'*64},'styles':[{'material_document':{'images':[image]}}]};fixed=C.rewrite_document(owner,document,{});self.assertEqual(fixed[C.POLICY_COLLECTION],{'../canonical.png':['../original']});self.assertEqual(C.rewrite_document(owner,fixed,{}),fixed)
  local={'images':[image],'externalResources':{'../canonical.png':'a'*64}};fixed=C.rewrite_document(owner,local,{});self.assertEqual(fixed[C.POLICY_COLLECTION],{'../canonical.png':['../original']})
 def test_canonicalizer_missing_world_collection_fails_with_repair_hint(self):
  owner=self.maps/'region/world.glb';owner.parent.mkdir();doc=self.document(owner);owner.write_bytes(S.write_glb(doc,self.body()));world=owner.with_name('world.json');world.write_text(json.dumps({'asset':{'glb':'world.glb'},'externalResources':{doc['images'][0]['uri']:S.sha256(self.image.read_bytes())}}))
  files=[p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()]
  with mock.patch.object(C,'tracked_files',return_value=files),self.assertRaisesRegex(C.CanonicalizationError,'refusing to infer original policy'):
   C.make_plan(self.root,self.root/'.local/plan.json',files=files,images=[self.image.relative_to(self.root).as_posix()])
  self.assertFalse((self.root/'.local/plan.json').exists());self.assertEqual(self.image.read_bytes(),b'unchanged encoded image bytes')
 def test_canonicalizer_mixed_descriptor_repair_is_ambiguous(self):
  explicit={'uri':'../canonical.png','extras':{C.POLICY_DIRECTORY_EXTRA:'../original'}}
  doc={'images':[explicit,{'uri':'../canonical.png'}]}
  with self.assertRaisesRegex(C.CanonicalizationError,'restore missing descriptor extras'):C.rewrite_document('eloria-assets/maps/region/world.gltf',doc,{})

if __name__=='__main__':unittest.main()
