"""Meshy multi-image-to-3D for RL head reference targets.

Paid API. Without --submit this is a dry run: it reads the balance (free), prints
what would be sent and what it would cost, and submits nothing. --submit needs
the owner's explicit go-ahead in chat for that batch (see the meshy-api-access
memory and the rabbitlands-meshy-model-generation skill).

  python meshy_multi.py --job rowan_m71=meshy-7.1:front.png,side.png,back.png \
                        --job rowan_m6lite=meshy-6-lite:front.png,side.png,back.png \
                        --max-total-credits 45 [--submit]

Every accepted task id goes into the ledger (default ../../meshy/meshy_tasks.json)
before anything else happens; a re-run polls/downloads ledger tasks and never
resubmits a name the ledger already holds. --max-total-credits caps the sum of
expected credits over every ledger entry plus the new submissions. The key comes
from MESHY_API_KEY only and is never printed.
"""
import argparse, base64, datetime, hashlib, json, os, sys, time
from pathlib import Path

import requests

API = 'https://api.meshy.ai/openapi/v1'
# docs.meshy.ai/en/api/pricing, read 2026-10-27: multi-image-to-3d, 2K textures / mesh only
COST = {('meshy-7.1', True): 30, ('latest', True): 30, ('meshy-6', True): 30, ('meshy-6-lite', True): 15,
        ('meshy-7.1', False): 20, ('latest', False): 20, ('meshy-6', False): 20, ('meshy-6-lite', False): 5}
HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE.parent.parent / 'meshy' / 'meshy_tasks.json'
DEFAULT_OUT = HERE.parent.parent / 'meshy' / 'pilot'


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def data_uri(p):
    p = Path(p)
    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}[p.suffix.lower()]
    b = p.read_bytes()
    if len(b) > 20 * 1024 * 1024:
        raise SystemExit(f'{p} is over 20 MB')
    return f'data:{mime};base64,' + base64.b64encode(b).decode('ascii')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(tmp, path)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


class Client:
    def __init__(self, key):
        self.s = requests.Session()
        self.s.headers['Authorization'] = f'Bearer {key}'

    def call(self, method, path, **kw):
        for attempt in range(5):
            try:
                r = self.s.request(method, API + path, timeout=120, **kw)
            except requests.RequestException as e:
                print(f'  network error ({type(e).__name__}), retrying')
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f'{method} {path}: HTTP {r.status_code}: {r.text[:400]}')
            return r.json()
        raise RuntimeError(f'{method} {path}: gave up after retries')

    def balance(self):
        return self.call('GET', '/balance').get('balance')


def parse_job(s):
    name, rest = s.split('=', 1)
    model, imgs = rest.split(':', 1)
    return name, model, [Path(p) for p in imgs.split(',')]


def body_for(model, images, textured):
    body = {'ai_model': model, 'should_texture': textured, 'enable_pbr': False,
            'target_formats': ['glb'], 'should_remesh': False}
    if textured:
        body['texture_resolution'] = '2k'
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', action='append', default=[], help='name=model:img1,img2[,img3,img4]')
    ap.add_argument('--no-texture', action='store_true')
    ap.add_argument('--max-total-credits', type=int, required=True)
    ap.add_argument('--ledger', default=str(DEFAULT_LEDGER))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--submit', action='store_true', help='PAID: submit new jobs (owner go-ahead required)')
    ap.add_argument('--poll-timeout', type=float, default=3600)
    a = ap.parse_args()

    key = os.environ.get('MESHY_API_KEY', '').strip()
    if not key:
        raise SystemExit('MESHY_API_KEY is not set')
    c = Client(key)
    ledger = load(a.ledger)
    textured = not a.no_texture
    committed = sum(int(e.get('expected_credits', 0)) for e in ledger.values() if e.get('status') != 'FAILED')
    bal = c.balance()
    print(f'balance {bal} credits; ledger holds {len(ledger)} task(s), {committed} credits committed')

    plan = []
    for spec in a.job:
        name, model, imgs = parse_job(spec)
        if not 1 <= len(imgs) <= 4:
            raise SystemExit(f'{name}: 1-4 images')
        cost = COST[(model, textured)]
        state = ledger.get(name)
        print(f'\n{name}: {model}, textured={textured}, {len(imgs)} image(s), expected {cost} credits')
        for p in imgs:
            print(f'  {p}  {p.stat().st_size / 1e6:.2f} MB  sha256 {sha256(p)[:16]}')
        print(f'  body: {json.dumps(body_for(model, imgs, textured))} + image_urls')
        if state:
            print(f'  ledger: task {state["task_id"]} status {state.get("status")} - will not resubmit')
        else:
            plan.append((name, model, imgs, cost))

    new_cost = sum(p[3] for p in plan)
    print(f'\nnew submissions: {len(plan)}, {new_cost} credits; total with ledger {committed + new_cost} '
          f'of cap {a.max_total_credits}')
    if committed + new_cost > a.max_total_credits:
        raise SystemExit('over --max-total-credits: nothing submitted')
    if plan and bal is not None and bal < new_cost:
        raise SystemExit('balance too low: nothing submitted')

    if plan and not a.submit:
        print('\nDRY RUN: nothing submitted. Re-run with --submit only after the owner approves this batch.')
        return 0

    for name, model, imgs, cost in plan:
        body = body_for(model, imgs, textured)
        entry = {'ai_model': model, 'textured': textured, 'expected_credits': cost,
                 'images': [{'path': str(p), 'sha256': sha256(p)} for p in imgs],
                 'settings': body, 'endpoint': 'multi-image-to-3d'}
        body = dict(body, image_urls=[data_uri(p) for p in imgs])
        r = c.call('POST', '/multi-image-to-3d', json=body)
        entry.update(task_id=r['result'], status='SUBMITTED', submitted_at=now())
        ledger[name] = entry
        save(a.ledger, ledger)
        print(f'{name}: submitted, task {entry["task_id"]}')

    # poll and download everything the ledger holds that is not finished
    t0 = time.time()
    while True:
        pending = [n for n, e in ledger.items() if e.get('status') not in ('SUCCEEDED', 'FAILED', 'CANCELED')
                   or (e.get('status') == 'SUCCEEDED' and not e.get('files'))]
        if not pending:
            break
        if time.time() - t0 > a.poll_timeout:
            print('poll timeout: tasks are still running; re-run this command (it will not resubmit)')
            return 2
        for n in pending:
            e = ledger[n]
            t = c.call('GET', f'/multi-image-to-3d/{e["task_id"]}')
            e['status'] = t.get('status')
            e['progress'] = t.get('progress')
            if e['status'] == 'SUCCEEDED' and not e.get('files'):
                d = Path(a.out) / n
                d.mkdir(parents=True, exist_ok=True)
                files = {}
                urls = dict(t.get('model_urls') or {})
                tex = (t.get('texture_urls') or [{}])[0] or {}
                for kind, url in [('glb', urls.get('glb')), ('base_color', tex.get('base_color')),
                                  ('thumbnail', t.get('thumbnail_url'))]:
                    if not url:
                        continue
                    ext = '.glb' if kind == 'glb' else '.png'
                    dest = d / f'{n}_{kind}{ext}'
                    rr = requests.get(url, timeout=600)
                    rr.raise_for_status()
                    dest.write_bytes(rr.content)
                    files[kind] = {'path': str(dest), 'sha256': sha256(dest), 'bytes': dest.stat().st_size}
                e['files'] = files
                e['consumed_credits'] = t.get('consumed_credits')
                e['finished_at'] = now()
                print(f'{n}: SUCCEEDED, {t.get("consumed_credits")} credits, files {list(files)}')
            elif e['status'] in ('FAILED', 'CANCELED'):
                e['task_error'] = t.get('task_error')
                e['consumed_credits'] = t.get('consumed_credits')
                print(f'{n}: {e["status"]}: {t.get("task_error")}')
            else:
                print(f'{n}: {e["status"]} {e.get("progress")}%')
            save(a.ledger, ledger)
        time.sleep(15)
    print(f'balance now {c.balance()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
