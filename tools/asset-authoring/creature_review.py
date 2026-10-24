"""Local, resumable creature animation review. Standard library only.
Media stays local; comments are stored under the ignored authoring workspace.
"""
from __future__ import annotations
import argparse, hashlib, http.server, json, mimetypes, os, re, secrets, threading, time, urllib.parse, urllib.request, webbrowser
from contextlib import contextmanager
from pathlib import Path

VIEWS = ('side','game','front','rear','opposite','rear_quarter')
LABELS = {'Walk':'Walk / slow travel','Jog':'Run / fast travel','Sword_Attack':'Attack','Death_A':'Death','Idle_A':'Idle','Fighting_Idle':'Alert','Hit_Chest':'Flinch','Fly':'Flight'}
ORDER = {name:i for i,name in enumerate(LABELS)}
APP = 'rabbitlands-creature-animation-review-v1'

def read(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (FileNotFoundError, json.JSONDecodeError): return default

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+secrets.token_hex(5)+'.tmp')
    try:
        with temp.open('x',encoding='utf-8',newline='\n') as f:
            json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def embedded_motions(page):
    """Decode JSON literals only; never execute old review-page JavaScript."""
    text=page.read_text(encoding='utf-8-sig');decoder=json.JSONDecoder()
    for match in re.finditer(r'(?:const|let|var)\s+(?:motions|MOTIONS|clips|CLIPS|metadata|meta|timings)\s*=\s*',text):
        try: data,_=decoder.raw_decode(text[match.end():])
        except json.JSONDecodeError: continue
        if isinstance(data,dict) and any(isinstance(v,dict) and isinstance(v.get('videos'),dict) for v in data.values()):return data
    return {}

class Catalog:
    def __init__(self,root):
        self.root=Path(root).resolve();self.archive=self.root/'.local/asset-authoring';self.work=self.archive/'working';self.state=self.work/'animation-review';self.media={};self.actors=[];self.warnings=[];self.last_refresh=0;self.hashes={};self.lock=threading.RLock();self.known_versions=set();self.refresh()
    def file_hash(self,path):
        path=Path(path);s=path.stat();key=(str(path),s.st_size,s.st_mtime_ns)
        if key not in self.hashes:self.hashes[key]=digest(path)
        return self.hashes[key]
    def asset(self,path):
        path=Path(path).resolve()
        if not path.is_relative_to(self.archive.resolve()) or not path.is_file():return None
        if path.suffix.lower() not in {'.mp4','.jpg','.jpeg','.png','.webp'}:return None
        ident=hashlib.sha256(str(path).encode()).hexdigest()[:24];self.media[ident]=path
        return '/media/'+ident+'/'+urllib.parse.quote(path.name)
    def package(self,family,entry):
        page=Path(entry['review']).resolve();base=page.parent;manifest_path=base/'manifest.json';manifest=read(manifest_path,{})
        if not page.is_file():self.warnings.append(f'{family}: review page missing');return
        pin=entry.get('manifest_sha256')
        if pin and digest(manifest_path)!=pin:self.warnings.append(f'{family}: selected manifest changed; not indexed');return
        ids=entry.get('completed_draft_actors') or list(entry.get('selected_sources',{})) or list(manifest.get('actors',{})) or [manifest.get('pilot')]
        timing=read(base/'timing.json',{});files=list(manifest.get('files',{}))
        for actor in filter(None,ids):
            info=manifest.get('actors',{});info=info.get(actor,{}) if isinstance(info,dict) else {}
            candidates=[base/info.get('review','__absent__'),base/'actors'/actor/'review.html',base/actor/'review.html']
            ap=next((p for p in candidates if p.is_file()),page);motions=embedded_motions(ap)
            if not motions:
                for rel in files:
                    parts=Path(rel).parts
                    if actor not in parts or not rel.endswith('.mp4'):continue
                    stem=Path(rel).stem
                    for view in sorted(VIEWS,key=len,reverse=True):
                        suffix='-'+view
                        if stem.endswith(suffix):
                            clip=stem[:-len(suffix)];motions.setdefault(clip,{'videos':{}})['videos'][view]=os.path.relpath(base/rel,ap.parent);break
            rowtiming=timing.get(actor,{}).get('timings',{})
            normalized={}
            for clip,spec in motions.items():
                if not isinstance(spec,dict) or not isinstance(spec.get('videos'),dict):continue
                videos={view:self.asset(ap.parent/path) for view,path in spec['videos'].items() if isinstance(path,str)};videos={k:v for k,v in videos.items() if v}
                if not videos:continue
                tm=rowtiming.get(clip,spec);pose=spec.get('pose_sheet')
                posepath=ap.parent/pose if pose else next((p for p in [base/'media'/actor/(clip+'-poses.jpg'),ap.parent/'media'/(clip+'-poses.jpg')] if p.exists()),None)
                normalized[clip]={'label':spec.get('label',LABELS.get(clip,clip.replace('_',' '))),'videos':videos,'duration':tm.get('duration'),'playback_duration':tm.get('playback_duration'),'loop':bool(tm.get('loop',clip in ('Walk','Jog','Idle_A','Fighting_Idle','Fly'))),'pose_sheet':self.asset(posepath) if posepath else None,'fps':tm.get('fps',24)}
                media_hashes={view:self.file_hash(ap.parent/spec['videos'][view]) for view in videos}
                normalized[clip]['version']=hashlib.sha256(json.dumps([actor,clip,media_hashes,normalized[clip]['loop']],sort_keys=True).encode()).hexdigest()
            if not normalized:self.warnings.append(f'{family}/{actor}: no indexed motion videos');continue
            model_hash=info.get('sha256') or info.get('model_sha256') or manifest.get('model_sha256')
            if isinstance(model_hash,dict):model_hash=model_hash.get(actor)
            source=manifest.get('selected_sources',{}).get(actor,{})
            if isinstance(source,dict):model_hash=model_hash or source.get('model_sha256') or source.get('sha256')
            if entry.get('runtime_model_sha256'):model_hash=entry['runtime_model_sha256']
            version=digest(manifest_path);name=info.get('name',actor.replace('_',' ').title());concept=info.get('concept',{}) or timing.get(actor,{}).get('concept',{})
            self.actors.append({'id':actor,'name':name,'family':info.get('family_name',family.replace('_',' ').title()),'version':version,'model_sha256':model_hash,'runtime_installed':bool(entry.get('runtime_installed')),'concept':concept,'motions':dict(sorted(normalized.items(),key=lambda kv:ORDER.get(kv[0],99))),'review_source':str(ap.relative_to(self.archive)),'agent_followups':entry.get('agent_followups',{}),'qualification':{'client_strict_passed':info.get('client_strict_passed'),'motion_checks_passed':info.get('motion_checks_passed')}})
    def refresh(self):
        with self.lock:self._refresh()
    def _refresh(self):
        self.actors=[];self.warnings=[]
        queue=read(self.work/'memory/animation-review-queue.json',{'families':{}})
        for family,entry in queue.get('families',{}).items():
            if entry.get('human_approved') is True:continue
            if entry.get('review'):self.package(family,entry)
        human=self.work/'humanoid-draft-batch-20261019/delivery-v10/review.html'
        if human.exists():
            m=read(human.parent/'manifest.json',{})
            self.package('humanoid_baseline',{'review':str(human),'completed_draft_actors':list(m.get('actors',{})),'runtime_installed':True})
        extra=read(self.work/'creature-completion-20261023/review-selections.json',{'creatures':{}})
        existing={a['id'] for a in self.actors}
        for actor,entry in extra.get('creatures',{}).items():
            if entry.get('human_approved') is not True:
                self.actors=[a for a in self.actors if a['id']!=actor];self.package(entry.get('family','New drafts'),{**entry,'completed_draft_actors':[actor]})
        # The original two wolf pilots share comparison footage; the UI makes
        # that explicit while keeping separate per-creature comments.
        legacy=self.archive/'workspace/generate_models/wolf_action_motion_pilot/delivery-v2'
        lm=legacy/'delivery-manifest.json'
        if lm.exists():
            for actor in ('dire_wolf','moorland_dire_wolf'):
                motions={}
                for clip,folder in [('Sword_Attack','attack'),('Death_A','death')]:
                    videos={v:self.asset(legacy/folder/(v+'-comparison.mp4')) for v in ('side','game','front','rear','other_side','tail_view','top','travel') if (legacy/folder/(v+'-comparison.mp4')).exists()}
                    if videos:
                        version=hashlib.sha256(json.dumps([actor,clip,{v:self.file_hash(legacy/folder/(v+'-comparison.mp4')) for v in videos}],sort_keys=True).encode()).hexdigest()
                        motions[clip]={'label':LABELS[clip],'videos':videos,'duration':None,'playback_duration':None,'loop':False,'pose_sheet':None,'fps':30,'version':version}
                if motions:self.actors.append({'id':actor,'name':actor.replace('_',' ').title(),'family':'Wolf source pilots','version':digest(lm),'model_sha256':None,'runtime_installed':False,'concept':{'movement':'Shared comparison footage shows both original wolves. Comments here apply to the selected creature. Their accepted walk is not marked as unreviewed.'},'motions':motions,'review_source':str((legacy/'review.html').relative_to(self.archive)),'qualification':{},'comparison_media':True})
        # Installation is independent of the reviewed media version. Keep each
        # existing comment key and rendered-model hash intact after promotion.
        installed=read(self.state/'runtime-installations.json',{}).get('actors',{})
        for actor in self.actors:
            if actor['id'] in installed:
                actor['runtime_installed']=True
                actor['runtime_model_sha256']=installed[actor['id']]['sha256']
        # Shared family reviews may describe two overlapping queues.
        unique={a['id']:a for a in self.actors};self.actors=sorted(unique.values(),key=lambda a:(a['family'],a['name']));self.known_versions.update((a['id'],c,m['version']) for a in self.actors for c,m in a['motions'].items());self.last_refresh=time.monotonic()
    def snapshot(self):
        with self.lock:
            if time.monotonic()-self.last_refresh>10:self._refresh()
            progress=read(self.work/'creature-completion-20261023/progress.json',{})
            return {'actors':self.actors,'warnings':self.warnings,'progress':progress,'comment_file':str(self.state/'comments.json')}
    def current(self,actor,clip,version):
        with self.lock:return self._current(actor,clip,version)
    def _current(self,actor,clip,version):
        item=next((a for a in self.actors if a['id']==actor),None)
        if item is None or clip not in item['motions']:raise ValueError('Unknown creature or animation')
        if item['motions'][clip]['version']!=version and (actor,clip,version) not in self.known_versions:raise RuntimeError('A newer draft is available; reload before saving')
        return item

@contextmanager
def comment_file_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if f.seek(0,2)==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

class ReviewStore:
    def __init__(self,path):self.path=Path(path);self.lock=threading.Lock()
    def load(self):
        if not self.path.exists():return {'schema':1,'records':{}}
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('records'),dict):raise ValueError('Comment file is invalid; preserving it for recovery')
        return data
    def save(self,item):
        if item.get('status') not in ('unreviewed','needs_changes','approved'):raise ValueError('Invalid status')
        text=item.get('comment','')
        if not isinstance(text,str) or len(text)>20000:raise ValueError('Comment exceeds 20,000 characters')
        key='|'.join(item[k] for k in ('actor','version','clip'))
        with self.lock,comment_file_lock(self.path.with_suffix('.lock')):
            data=self.load();old=data['records'].get(key,{});revision=old.get('revision',0)
            if item.get('revision',0)!=revision:raise RuntimeError('This comment changed in another window; reload to retain both edits')
            record={k:item[k] for k in ('actor','version','clip','status')};record.update(comment=text,revision=revision+1,updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
            history=data.setdefault('history',[]);history.append(record.copy());data['records'][key]=record;atomic_json(self.path,data);return record

def make_handler(catalog,store,token):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):pass
        def authorized_host(self):
            host=self.headers.get('Host','').split(':')[0].lower();return host in ('127.0.0.1','localhost')
        def respond(self,status,value):
            blob=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(blob)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(blob)
        def do_GET(self):
            if not self.authorized_host():self.respond(403,{'error':'Local host required'});return
            url=urllib.parse.urlsplit(self.path);route=url.path
            if route=='/api/health':self.respond(200,{'app':APP,'root':hashlib.sha256(str(catalog.root).encode()).hexdigest()});return
            if route=='/api/catalog':self.respond(200,catalog.snapshot());return
            if route in ('/api/reviews','/api/export'):self.respond(200,store.load());return
            if route=='/':
                text=Path(__file__).with_name('creature_review_ui.html').read_text(encoding='utf-8').replace('__TOKEN__',token);blob=text.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(blob)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(blob);return
            if route.startswith('/media/'):
                ident=route.split('/')[2]
                with catalog.lock:path=catalog.media.get(ident)
                if path is None:self.respond(404,{'error':'Media not in the current review catalog'});return
                size=path.stat().st_size;start=0;end=size-1;partial=False;request=self.headers.get('Range')
                if request:
                    match=re.fullmatch(r'bytes=(\d*)-(\d*)',request)
                    if not match or not any(match.groups()):self.respond(416,{'error':'Invalid media range'});return
                    first,last=match.groups()
                    if first:start=int(first);end=min(int(last),size-1) if last else size-1
                    else:start=max(0,size-int(last))
                    if start>=size or end<start:self.respond(416,{'error':'Range outside media'});return
                    partial=True
                self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('X-Content-Type-Options','nosniff')
                if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                try:
                    with path.open('rb') as f:
                        f.seek(start);left=end-start+1
                        while left:
                            chunk=f.read(min(256*1024,left))
                            if not chunk:break
                            self.wfile.write(chunk);left-=len(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            self.respond(404,{'error':'Unknown review route'})
        def do_POST(self):
            expected='http://'+self.headers.get('Host','')
            if not self.authorized_host() or self.headers.get('X-Review-Token')!=token or self.headers.get('Origin')!=expected:self.respond(403,{'error':'Review session token and local origin required'});return
            if self.path!='/api/review':self.respond(404,{'error':'Unknown review route'});return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise ValueError('Invalid comment size')
                item=json.loads(self.rfile.read(size));catalog.current(item['actor'],item['clip'],item['version']);result=store.save(item);self.respond(200,result)
            except RuntimeError as exc:self.respond(409,{'error':str(exc)})
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:self.respond(400,{'error':str(exc)})
    return Handler

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--port',type=int,default=8773);ap.add_argument('--open',action='store_true');ap.add_argument('--catalog-only',action='store_true');args=ap.parse_args();catalog=Catalog(args.root)
    if args.catalog_only:
        atomic_json(catalog.state/'catalog.json',catalog.snapshot());print('REVIEW_CATALOG',len(catalog.actors),'creatures',sum(len(a['motions']) for a in catalog.actors),'animations','warnings',catalog.warnings);return
    root_hash=hashlib.sha256(str(catalog.root).encode()).hexdigest()
    for port in range(args.port,args.port+10):
        try:
            existing=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.3))
            if existing.get('app')==APP and existing.get('root')==root_hash:
                if args.open:webbrowser.open(f'http://127.0.0.1:{port}/')
                print('Existing review:',f'http://127.0.0.1:{port}/');return
        except Exception:pass
        try:server=http.server.ThreadingHTTPServer(('127.0.0.1',port),make_handler(catalog,ReviewStore(catalog.state/'comments.json'),secrets.token_urlsafe(32)));break
        except OSError:continue
    else:raise SystemExit('No free local review port; close an older review window and retry')
    url=f'http://127.0.0.1:{server.server_port}/';print('Creature animation review:',url,flush=True);print('Comments:',catalog.state/'comments.json',flush=True);print('Keep this window open. Ctrl+C stops the review server.',flush=True)
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
