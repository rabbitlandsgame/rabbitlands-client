"""CPU-only contracts for byte-identical image canonicalization. No Godot/import/GPU."""
import copy
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('canonicalize_map_images',ROOT/'eloria-assets/tools/canonicalize_map_images.py')
C=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(C)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def uri(path,owner):return __import__('os').path.relpath(path,owner.parent).replace('\\','/')
def write_glb(path,image,role='normal',tail=b'\x04\0\0\0BIN\0\x12\x34\x56\x78'):
 material={'normalTexture':{'index':0}} if role=='normal' else {'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}
 document={'asset':{'version':'2.0'},'images':[{'uri':uri(image,path)}],'textures':[{'source':0}],'materials':[material],
           'buffers':[{'byteLength':4},{'byteLength':16,'uri':'unchanged.part0.bin'}],
           'accessors':[{'componentType':5126,'count':7,'type':'VEC3','extras':{'sentinel':[3.25,-9,55]}}]}
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(C.glb_bytes(document,tail));return document,tail


class CanonicalImages(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.maps=self.root/'eloria-assets/maps'
 def image(self,name,raw=b'identical encoded source pixels'):
  p=self.maps/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return p
 def files(self):return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file() and '.local' not in p.relative_to(self.root).parts)
 def simple(self):
  first=self.image('a/images/pixel.png');second=self.image('b/images/duplicate.png')
  for name,image in [('a',first),('b',second)]:
   glb=self.maps/name/'world.glb';write_glb(glb,image)
   write_json(glb.with_name('world.json'),{'asset':{'glb':'world.glb'},'externalResources':{uri(image,glb):sha(image.read_bytes())},'performance':{'glbBytes':glb.stat().st_size}})
  return first,second
 def plan(self,policies=None):
  return C.make_plan(self.root,self.root/'.local/plan.json',files=self.files(),images=[name for name in self.files() if Path(name).suffix in C.IMAGE_SUFFIXES],policies=policies)
 def test_complete_rewrite_preserves_glb_binary_and_integrity_links(self):
  first,second=self.simple();old_bytes=second.read_bytes();digest=sha(old_bytes)
  proto=self.maps/'_shared/meshes/prop.glb';_,tail=write_glb(proto,second);old_proto_sha=sha(proto.read_bytes())
  write_json(proto.with_name('index.json'),{'prototypes':{'prop':{'sha256':old_proto_sha,'bytes':proto.stat().st_size,'images':{uri(second,proto):digest}}}})
  world=self.maps/'b/world.json';doc=json.loads(world.read_text());doc['externalMeshes']={uri(proto,world):old_proto_sha}
  roads=self.maps/'b/roads.json';road_doc={'resources':{uri(second,roads):digest},'styles':[{'material_document':{'images':[{'uri':uri(second,roads)}]},'externalResources':{uri(second,roads):digest}}],
   'source_glb_sha256':'f'*64,'source_manifest_sha256':'e'*64}
  write_json(roads,road_doc);doc['roadGround']={'metadata':'roads.json','sha256':sha(roads.read_bytes())};write_json(world,doc)
  code=self.root/'godot-client/src/use.gd';code.parent.mkdir(parents=True);code.write_text('const T = "res://../'+second.relative_to(self.root).as_posix()+'"\n')
  policies=C.policy_inventory(self.root);plan=self.plan(policies);self.assertEqual(plan['summary']['safeDuplicateBytes'],len(old_bytes));self.assertEqual(len(plan['deletes']),1)
  self.assertTrue(second.exists(),'plan must not modify source');C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery')
  self.assertFalse(second.exists());self.assertEqual(first.read_bytes(),old_bytes);after_doc,after_tail=C.glb_parts(proto);self.assertEqual(after_tail,tail)
  self.assertEqual(after_doc['accessors'][0]['extras']['sentinel'],[3.25,-9,55]);self.assertEqual(after_doc['buffers'][1]['uri'],'unchanged.part0.bin')
  index=json.loads(proto.with_name('index.json').read_text())['prototypes']['prop'];self.assertEqual(index['sha256'],sha(proto.read_bytes()));self.assertEqual(index['bytes'],proto.stat().st_size)
  current=json.loads(world.read_text());self.assertEqual(list(current['externalMeshes'].values()),[sha(proto.read_bytes())]);self.assertEqual(current['roadGround']['sha256'],sha(roads.read_bytes()))
  rd=json.loads(roads.read_text());self.assertEqual(rd['source_glb_sha256'],'f'*64);self.assertEqual(rd['source_manifest_sha256'],'e'*64)
  self.assertIn(first.relative_to(self.root).as_posix(),code.read_text());self.assertEqual((self.root/'.local/recovery'/second.relative_to(self.root)).read_bytes(),old_bytes)
  self.assertEqual(C.policy_inventory(self.root),{k:{**v,'source':plan['aliases'].get(v['source'],v['source'])} for k,v in policies.items()})
 def test_original_raw_and_compressed_policies_survive_one_pixel_file(self):
  first=self.image('_shared/images/a.png');second=self.image('nymara-regions/_continent/shared-assets/b.png')
  for name,image in [('first',first),('second',second)]:
   glb=self.maps/name/'world.glb';write_glb(glb,image);write_json(glb.with_name('world.json'),{'asset':{'glb':'world.glb'},'externalResources':{uri(image,glb):sha(image.read_bytes())}})
  before=C.policy_inventory(self.root);self.assertEqual({v['reason'] for v in before.values()},{'','excluded_by_caller'})
  plan=self.plan(before);self.assertEqual(plan['summary']['safeDuplicateFiles'],1)
  C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery')
  after=C.policy_inventory(self.root);self.assertEqual(after,{key:{**value,'source':plan['aliases'].get(value['source'],value['source'])} for key,value in before.items()})
  self.assertFalse(first.exists());doc,_=C.glb_parts(self.maps/'first/world.glb');self.assertIn(C.POLICY_DIRECTORY_EXTRA,doc['images'][0]['extras'])
  self.assertEqual((self.maps/'first'/doc['images'][0]['uri']).resolve(),second.resolve())
 def test_unsafe_policy_cannot_escape_map_asset_tree(self):
  self.simple();glb=self.maps/'a/world.glb';doc,tail=C.glb_parts(glb);doc['images'][0]['extras']={C.POLICY_DIRECTORY_EXTRA:'../../../../outside'};glb.write_bytes(C.glb_bytes(doc,tail))
  with self.assertRaises((C.CanonicalizationError,C.vram.BuildError)):self.plan()
 def test_raw_unplanned_copies_can_merge_without_enabling_sidecars(self):
  first=self.image('x/a.png');second=self.image('y/b.png');p=self.plan({});self.assertEqual(len(p['deletes']),1);C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery');self.assertEqual(C.policy_inventory(self.root),{})
 def test_stale_consolidated_geometry_refuses_apply(self):
  self.simple();plan=self.plan();world=self.maps/'b/world.glb';world.write_bytes(world.read_bytes()+b'new geometry after planning')
  with self.assertRaisesRegex(C.CanonicalizationError,'stale plan input'):C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery')
  self.assertTrue((self.maps/'b/images/duplicate.png').exists());self.assertFalse((self.root/'.local/recovery').exists())
 def test_corrupt_stage_refuses_before_source_writes(self):
  self.simple();plan=self.plan();change=plan['changes'][0];(Path(plan['stage'])/change['path']).write_bytes(b'bad stage')
  with self.assertRaisesRegex(C.CanonicalizationError,'corrupt staged file'):C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery')
  self.assertTrue((self.maps/'b/images/duplicate.png').exists())
 def test_policy_verification_failure_restores_exact_originals(self):
  self.simple();self.plan();before={name:(self.root/name).read_bytes() for name in self.files()}
  with mock.patch.object(C,'policy_inventory',return_value={}):
   with self.assertRaisesRegex(C.CanonicalizationError,'texture policy changed'):C.apply_plan(self.root,self.root/'.local/plan.json',self.root/'.local/recovery')
  self.assertEqual({name:(self.root/name).read_bytes() for name in before},before)
 def test_plan_never_overwrites_previous_plan(self):
  self.simple();self.plan()
  with self.assertRaisesRegex(C.CanonicalizationError,'fresh plan'):self.plan()
 def test_existing_recovery_is_never_overwritten(self):
  self.simple();self.plan();recovery=self.root/'.local/recovery';recovery.mkdir();(recovery/'keep').write_bytes(b'keep')
  with self.assertRaisesRegex(C.CanonicalizationError,'fresh recovery'):C.apply_plan(self.root,self.root/'.local/plan.json',recovery)
  self.assertEqual((recovery/'keep').read_bytes(),b'keep')
 def test_nested_glb_external_resources_rebase_from_glb_directory(self):
  first=self.image('a/images/copy.png');second=self.image('b/data/images/duplicate.png');glb=self.maps/'b/data/world.glb';write_glb(glb,second)
  owner='eloria-assets/maps/b/world.json';doc={'asset':{'glb':'data/world.glb'},'externalResources':{'images/duplicate.png':sha(second.read_bytes())}}
  old=second.relative_to(self.root).as_posix();new=first.relative_to(self.root).as_posix();out=C.rewrite_document(owner,doc,{old:new});target=next(iter(out['externalResources']));self.assertEqual(C.resolve_reference(owner,target,C.document_base(owner,out))[0],new)
 def test_both_res_forms_and_root_relative_paths(self):
  old='eloria-assets/maps/b/a.png';new='eloria-assets/maps/a/b.png';aliases={old:new};owner='godot-client/src/test.gd'
  for literal in ['res://../'+old,old]:self.assertEqual(C.resolve_reference(owner,C.rebase(owner,literal,aliases))[0],new)
  old='godot-client/assets/a.png';new='eloria-assets/maps/a/b.png';self.assertEqual(C.rebase(owner,'res://assets/a.png',{old:new}),'res://../'+new)
 def test_default_candidates_exclude_fixed_ui_and_coverage(self):
  self.assertFalse(C.candidate_image('eloria-assets/maps/continent-v2/suncoil/client/map-detail.webp'))
  self.assertFalse(C.candidate_image('eloria-assets/maps/continent-v2/suncoil/client/minimap.webp'))
  self.assertFalse(C.candidate_image('eloria-assets/maps/continent-v2/suncoil/client/chunks/06_09/coverage.png'))
  self.assertTrue(C.candidate_image('eloria-assets/maps/_shared/images/source.png'))
 def test_path_escape_is_refused(self):
  with self.assertRaisesRegex(C.CanonicalizationError,'escapes'):C.inside(self.root,'../outside')
 def test_rebase_conflicting_hashes_is_fatal(self):
  owner='eloria-assets/maps/test/world.json';doc={'externalResources':{'a.png':'a'*64,'b.png':'b'*64}}
  with self.assertRaisesRegex(C.CanonicalizationError,'conflicting'):C.rewrite_document(owner,doc,{'eloria-assets/maps/test/a.png':'eloria-assets/maps/test/b.png'})
 def test_glb_parser_refuses_invalid_header(self):
  p=self.maps/'bad.glb';p.parent.mkdir(parents=True);p.write_bytes(b'not a glb')
  with self.assertRaises(C.CanonicalizationError):C.glb_parts(p)
 def test_live_prototype_stale_hash_is_not_silently_restamped(self):
  owner='eloria-assets/maps/world.json';doc={'externalMeshes':{'prop.glb':'f'*64}};target='eloria-assets/maps/prop.glb'
  with self.assertRaisesRegex(C.CanonicalizationError,'stale file hash'):C.refresh_hash_links(owner,doc,{target:'b'*64},{target:20},{target:'a'*64})
 def test_retirement_binding_changes_only_sha(self):
  target='eloria-assets/maps/world.glb';doc={'mapMeshCopies':{target:{'sha256':'a'*64,'meshes':[2,17,99]}}}
  out=C.refresh_hash_links('godot-client/data/assets/retired.json',doc,{target:'b'*64},{target:20},{target:'a'*64});self.assertEqual(out['mapMeshCopies'][target],{'sha256':'b'*64,'meshes':[2,17,99]})
 def test_historical_source_hashes_remain_historical(self):
  doc={'source_glb_sha256':'a'*64,'provenance':{'sha256':'z'*64,'path':'world.glb'}};owner='eloria-assets/maps/world.json';target='eloria-assets/maps/world.glb'
  self.assertEqual(C.refresh_hash_links(owner,doc,{target:'b'*64},{target:20},{target:'a'*64}),doc)


class DeliveryPolicy(unittest.TestCase):
 def record(self):return {'roles':{('normal','MASK')},'cutoffs':set(),'maps':{'region/chunks/00'}}
 def test_release_skipped_shared_copy_stays_excluded(self):
  p=C.vram.delivery_policy(self.record(),Path('/maps/_shared/images'),C.RELEASE_SKIP,C.RELEASE_UNSKIP);self.assertIsNone(p['recipe']);self.assertEqual(p['reason'],'excluded_by_caller');self.assertEqual(p['roles'],['normal'])
 def test_town_unskip_keeps_its_existing_recipe(self):
  record=self.record();record['maps']={'continent-v2/landfall_town/chunks/00'};p=C.vram.delivery_policy(record,Path('/maps/_shared/images'),C.RELEASE_SKIP,C.RELEASE_UNSKIP);self.assertEqual(p['recipe'],'normal')
 def test_normal_enabled_copy_is_not_affected_by_folder_rebasing(self):
  p=C.vram.delivery_policy(self.record(),Path('/maps/nymara-regions/_continent/shared-assets'),C.RELEASE_SKIP,C.RELEASE_UNSKIP);self.assertEqual(p['recipe'],'normal');self.assertEqual(p['rolePairs'],[['normal','MASK']])
 def test_role_conflict_still_falls_back(self):
  r=self.record();r['roles'].add(('base','OPAQUE'));p=C.vram.delivery_policy(r,Path('/maps/enabled'));self.assertIsNone(p['recipe']);self.assertTrue(p['reason'].startswith('role_conflict'))


if __name__=='__main__':unittest.main()
