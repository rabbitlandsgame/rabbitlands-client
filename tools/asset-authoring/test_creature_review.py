import importlib.util,json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('creature_review',Path(__file__).with_name('creature_review.py'));app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'comments.json';self.store=app.ReviewStore(self.path)
 def tearDown(self):self.temp.cleanup()
 def item(self,**changes):return {'actor':'test_creature','clip':'Walk','version':'v1','revision':0,'status':'needs_changes','comment':'[0.31s / side] Keep the heel down.',**changes}
 def test_comments_survive_reopening_and_keep_history(self):
  one=self.store.save(self.item());self.assertEqual(one['revision'],1);two=app.ReviewStore(self.path).save(self.item(revision=1,status='approved',comment='Fixed.'));self.assertEqual(two['revision'],2);d=self.store.load();self.assertEqual(len(d['history']),2);self.assertEqual(d['records']['test_creature|v1|Walk']['status'],'approved')
 def test_stale_save_preserves_the_other_window(self):
  self.store.save(self.item())
  with self.assertRaises(RuntimeError):self.store.save(self.item(comment='Stale overwrite'))
  self.assertEqual(self.store.load()['records']['test_creature|v1|Walk']['comment'],self.item()['comment'])
 def test_new_media_has_separate_review_state(self):
  self.store.save(self.item(status='approved'));self.store.save(self.item(version='v2',comment='A new issue'))
  self.assertEqual(len(self.store.load()['records']),2)
 def test_invalid_status_and_oversized_comment_do_not_write(self):
  for item in [self.item(status='publish'),self.item(comment='x'*20001)]:
   with self.assertRaises(ValueError):self.store.save(item)
  self.assertFalse(self.path.exists())
 def test_read_is_not_a_mutation(self):self.assertEqual(self.store.load()['records'],{});self.assertFalse(self.path.exists())
 def test_json_extractor_does_not_execute_scripts(self):
  page=self.root/'test.html';page.write_text('<script>const motions={"Walk":{"videos":{"side":"media/Walk-side.mp4"}}};throw new Error("must not execute")</script>');self.assertEqual(app.embedded_motions(page)['Walk']['videos']['side'],'media/Walk-side.mp4')

class HttpTests(ReviewTests):
 def setUp(self):
  super().setUp();video=self.root/'test.mp4';video.write_bytes(bytes(range(100)));root=self.root
  class Mini:
   lock=threading.RLock();media={'valid':video}
   def snapshot(self):return {'actors':[{'id':'test_creature'}]}
   def current(self,actor,clip,version):
    if (actor,clip)!=('test_creature','Walk'):raise ValueError('unknown clip')
    if version!='v1':raise RuntimeError('unknown media version')
  self.catalog=Mini();self.catalog.root=root;self.server=app.http.server.ThreadingHTTPServer(('127.0.0.1',0),app.make_handler(self.catalog,self.store,'token'));self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
 def request(self,route='/',data=None,headers=None):
  h={'Origin':self.url,'X-Review-Token':'token','Content-Type':'application/json'};h.update(headers or {});req=urllib.request.Request(self.url+route,json.dumps(data).encode() if data is not None else None,h)
  try:
   with urllib.request.urlopen(req,timeout=3) as response:return response.status,response.headers,response.read()
  except urllib.error.HTTPError as exc:return exc.code,exc.headers,exc.read()
 def test_comment_api_roundtrip_and_conflicts(self):
  code,_,blob=self.request('/api/review',self.item());self.assertEqual(code,200);self.assertEqual(json.loads(blob)['revision'],1);self.assertEqual(self.request('/api/review',self.item())[0],409);self.assertEqual(self.request('/api/review',self.item(version='arbitrary'))[0],409)
 def test_cross_origin_or_missing_token_rejected(self):
  for headers in [{'Origin':'https://external.example'},{'X-Review-Token':'bad'},{'Host':'external.example'}]:self.assertEqual(self.request('/api/review',self.item(),headers)[0],403)
  self.assertFalse(self.path.exists())
 def test_media_ranges_and_unknown_paths(self):
  code,h,b=self.request('/media/valid/test.mp4',headers={'Range':'bytes=10-19'});self.assertEqual((code,b),(206,bytes(range(10,20))));self.assertEqual(h['Content-Range'],'bytes 10-19/100');self.assertEqual(self.request('/media/valid/test.mp4',headers={'Range':'bytes=-3'})[2],bytes([97,98,99]));self.assertEqual(self.request('/media/valid/test.mp4',headers={'Range':'bytes=200-'})[0],416);self.assertEqual(self.request('/media/../../comments.json')[0],404)
 def test_page_and_catalog_are_read_only(self):
  code,_,html=self.request();self.assertEqual(code,200);self.assertNotIn(b'__TOKEN__',html);self.assertEqual(self.request('/api/catalog')[0],200);self.assertFalse(self.path.exists())

class InstallationTests(unittest.TestCase):
 def test_installation_keeps_media_and_comment_versions(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);work=root/'.local/asset-authoring/working'
   app.atomic_json(work/'memory/animation-review-queue.json',{'families':{'test':{'review':'unused','human_approved':False}}})
   app.atomic_json(work/'animation-review/runtime-installations.json',{'actors':{'test_creature':{'sha256':'installed-runtime'}}})
   def package(catalog,*args):catalog.actors.append({'id':'test_creature','family':'Test','name':'Test Creature','version':'review-v1','model_sha256':'rendered-source','runtime_installed':False,'motions':{'Walk':{'version':'motion-v1'}}})
   with patch.object(app.Catalog,'package',package):catalog=app.Catalog(root)
   actor=catalog.snapshot()['actors'][0]
   self.assertTrue(actor['runtime_installed']);self.assertEqual(actor['runtime_model_sha256'],'installed-runtime');self.assertEqual(actor['model_sha256'],'rendered-source');self.assertEqual(actor['version'],'review-v1');self.assertEqual(actor['motions']['Walk']['version'],'motion-v1')
   self.assertFalse((work/'animation-review/comments.json').exists())

if __name__=='__main__':unittest.main()
