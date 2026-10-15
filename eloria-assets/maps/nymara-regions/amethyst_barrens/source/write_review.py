"""Assemble annotated raw gameplay captures and a geometry-derived overview."""
import argparse
import base64
import html
import hashlib
import json
from pathlib import Path


def write(out):
    package=Path(__file__).resolve().parents[1]
    w=json.loads((package/'world.json').read_text())
    image=base64.b64encode((package/'minimap.webp').read_bytes()).decode()
    def point(x,z):return (x+116)/384*680+70,(z+268)/384*680+50
    markers=[]
    subjects=[('Assay outpost',24,16,'#ffc66e'),('Observatory',-54,-174,'#ffc66e'),
              ('Amethyst massif',134,-234,'#c3a6ff'),('Quiet basin',75,50,'#d8c5a0'),
              ('Worked seams',119,-15,'#c3a6ff')]
    subjects.extend((p['name'],p['position'][0],p['position'][2],'#8adacb') for p in w['portals'] if p['type']=='map-transition')
    for label,x,z,color in subjects:
        sx,sy=point(x,z)
        dx=-8 if sx>490 else 8
        anchor='end' if sx>490 else 'start'
        markers.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="5" fill="{color}" stroke="#111" stroke-width="2"/>'
                       f'<text x="{sx+dx:.1f}" y="{sy-9:.1f}" text-anchor="{anchor}" fill="{color}">{html.escape(label)}</text>')
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="820" height="820" viewBox="0 0 820 820">
<rect width="820" height="820" fill="#141418"/><style>text{{font:14px sans-serif;paint-order:stroke;stroke:#141418;stroke-width:3px;stroke-linejoin:round}}</style>
<text x="70" y="28" fill="#f2e8dc">AMETHYST BARRENS · 384 × 384 METRES</text>
<image href="data:image/webp;base64,{image}" x="70" y="50" width="680" height="680"/>
{''.join(markers)}<path d="M70 760h177" stroke="#f2e8dc" stroke-width="3"/><text x="70" y="785" fill="#f2e8dc">100 m</text>
<text x="750" y="785" text-anchor="end" fill="#f2e8dc">N ↑ · minimap rendered from final geometry</text></svg>'''
    (out/'overview.svg').write_text(svg,encoding='utf-8')
    entries=[
      ('07-outpost-life','A place to return to','Bunkhouse and cookhouse face the existing assay exchange. Dwellings keep their metre dimensions.',[(12,18,'Bunkhouse'),(73,18,'Cookhouse'),(69,72,'Assay exchange')]),
      ('01-assay-yard','The working court','A dusty court and readable cart routes replace the large luminous paving apron.',[(65,18,'Existing service shelter'),(42,55,'Open circulation')]),
      ('02-observatory','The Glasswarden seat','The protected survey retains the observatory stair, podium and forecourt at their original scale.',[(52,12,'Protected stair and terrace')]),
      ('03-basin-cut','A worked crystal seam','The quarry, its Measure House and its road remain one place; surrounding empty ground gives the encounter room.',[(16,73,'Worked seam'),(60,64,'Measure House')]),
      ('04-whitehorn-road','The Whitehorn approach','A broad 12m saddle continues the route into the reciprocal Whitehorn frame.',[(48,32,'Snowline approach')]),
      ('05-mirror-road','The Mirror Road shelf','The tower stands beside a continuous cart route, leaving the seven crossing lanes clear.',[(77,20,'Tower beside the road'),(34,38,'Open cart approach')]),
      ('06-crownwater-jetty','The packet landing','A 3.6m jetty follows its surveyed banks at the actual south-east inlet. The river still drains to the sea.',[(47,28,'Packet jetty')]),
    ]
    for identity, *_ in entries:
        for variant in ('baseline','after'):
            if not (out/variant/(identity+'.png')).is_file():
                raise FileNotFoundError(out/variant/(identity+'.png'))
    cards=[]
    for identity,title,description,tags in entries:
        labels=''.join(f'<span style="left:{x}%;top:{y}%">{html.escape(label)}</span>' for x,y,label in tags)
        cards.append(f'''<section id="{identity}"><h2>{title}</h2><p>{description}</p><div class="pair">
<figure><div class="frame"><img src="baseline/{identity}.png" alt="Before: {title}" loading="lazy"/></div><figcaption>Before · frozen 576m package</figcaption></figure>
<figure><div class="frame"><img src="after/{identity}.png" alt="After: {title}" loading="lazy"/><div class="tags">{labels}</div></div><figcaption>After · 384m authored package</figcaption></figure></div></section>''')
    detail=''
    if (out/'after-detail/08-packet-bank.png').is_file():
        detail='''<section><h2>On the new packet approach</h2><p>The matched shoreline view above keeps its original survey position, now below the relocated landing. This additional current view places the traveller on the connected jetty approach.</p><figure class="frame"><img src="after-detail/08-packet-bank.png" alt="Current gameplay camera on the packet landing approach" loading="lazy"/></figure></section>'''
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Amethyst Barrens · landscape review</title><style>
:root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#141418;color:#eee8e0}}body{{margin:0 auto;max-width:1700px;padding:36px 28px}}h1{{font-size:38px;line-height:1.1;margin-bottom:12px}}h2{{font-size:24px}}p{{max-width:1000px;color:#c9c2bc;line-height:1.6}}a{{color:#c9b7ff}}nav{{display:flex;gap:18px;flex-wrap:wrap;margin:26px 0}}.facts{{color:#f0d197}}section{{margin:40px 0 64px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}figure{{margin:0}}.frame{{position:relative}}img{{width:100%;display:block;cursor:zoom-in}}figcaption{{padding:10px 0;color:#b0aaa7}}.tags span{{position:absolute;transform:translate(-50%,-50%);background:#191422e8;border:1px solid #c9b7ff;padding:5px 8px;border-radius:3px;font-size:12px;white-space:nowrap;color:#fff}}.hide-tags .tags{{display:none}}.overview{{max-width:820px;cursor:default}}details{{padding:18px;border:1px solid #49434e;line-height:1.6}}dialog{{border:0;padding:0;max-width:96vw;max-height:96vh;background:#141418}}dialog::backdrop{{background:#000c}}dialog img{{max-height:94vh;width:auto;max-width:96vw}}@media(max-width:900px){{.pair{{grid-template-columns:1fr}}body{{padding:22px 16px}}}}
</style><h1>Amethyst Barrens</h1><p class="facts">384 × 384 metres · 11 retained portal IDs · 13 exterior secrets · 7 crystal bridges + the packet jetty</p>
<p>A sheltered Glasswarden outpost, an exposed crystal basin and shorter journeys between places. The observatory keeps its scale; roads and drainage retain their purpose. These are raw captures from the complete client with its gameplay camera, QA traveller and HUD. The after captures load the generated package from the new checkout.</p>
<nav><a href="#07-outpost-life">Outpost</a><a href="#02-observatory">Observatory</a><a href="#03-basin-cut">Workings</a><a href="#04-whitehorn-road">Approaches</a><a href="contracts.json">Geometry contracts</a><a href="walk-routes.json">Server walk fixture</a><label><input id="annotations" type="checkbox" checked> Show annotations</label></nav>
<img class="overview" src="overview.svg" alt="Annotated geometry-derived overview of Amethyst Barrens"/>
{''.join(cards)}{detail}<details open><summary>Evidence and limits</summary><p>Before and after use matching authored viewpoints, yaw and camera distance; the positions follow the compact survey. Click any gameplay frame to inspect the untouched capture. The minimap above is rendered from the exported geometry. <a href="survey-before.json">Before specification</a> · <a href="survey-after.json">After specification</a>.</p>
<p>The survey places a traveller for repeatable camera review. Authoritative server traversal is a separate integrated rollout check. Resident scene subsets increase package size while remaining hidden in the active region; dynamic actors still belong to the active server map. Frame-rate overlays were captured during concurrent development and are not a hardware performance benchmark.</p></details>
<dialog id="viewer"><img alt="Full-resolution gameplay capture"></dialog><script>
document.querySelector('#annotations').onchange=e=>document.body.classList.toggle('hide-tags',!e.target.checked);
const viewer=document.querySelector('#viewer');document.querySelectorAll('.frame img').forEach(img=>img.onclick=()=>{{viewer.querySelector('img').src=img.src;viewer.showModal()}});viewer.onclick=()=>viewer.close();
</script></html>'''
    (out/'review.html').write_text(page,encoding='utf-8')
    checks=json.loads((package/'verification-report.json').read_text())
    contracts=json.loads((out/'contracts.json').read_text())
    performance=w['performance']
    fingerprints={name:hashlib.sha256((package/name).read_bytes()).hexdigest()
                  for name in ('world.glb','world-lod2.glb','collision.bin','minimap.webp')}
    (out/'package-sha256.json').write_text(json.dumps(fingerprints,indent=2)+'\n')
    (out/'verification-report.json').write_text(json.dumps(checks,indent=2)+'\n')
    lane_note=''
    if (out/'border-lanes.json').is_file():
        lane_report=json.loads((out/'border-lanes.json').read_text())
        failed=sum(bool(l['blockedSamples'] or l['blockedSteps'])
                   for b in lane_report['borders'] for l in b['lanes'])
        lane_note=f"- Border lanes: {lane_report['samples']} samples across both seven-lane approaches, from trigger through 40m inland; {failed} lanes with blocked tiles or server steps. See `border-lanes.json`.\n"
    (out/'choices-and-checks.md').write_text(f'''# Amethyst Barrens review

The region is now 384m square with a sheltered working outpost, a protected
observatory, open crystal country and shorter routes. Two full-size dwellings
face the existing assay exchange. Debris follows the geology and dry growth
collects in lee pockets. Full-width surveyed crossings connect the basin.

- Preserved: 11 portal IDs, 13 exterior secret IDs, all legacy landmark IDs,
  seven Resonant Vault entrances and the existing interior geometry and lore.
- Revised navigation: Whitehorn saddle, Mirror Road shelf, southern ascent,
  Sour Cut footpath and a packet jetty tied into its actual bank height.
- Geometry checks: {len(checks['errors'])} errors; {checks['summary']['tilesSampled']:,} tiles sampled;
  {checks['summary']['groundingMisses']} grounding misses. One retained warning covers
  {checks['summary']['surfaceDiscontinuities']} adjacent height jumps at cliffs and bridge margins.
- Connectivity: all 11 conservative portal tiles open and connected to arrival;
  {contracts['primaryComponentTiles']:,} tiles in the main component. Every secret has connected
  adjacent ground within {max(s['distanceMetres'] for s in contracts['secretApproaches']):.2f}m of its marker.
- Package: {performance['glbBytes']/1e6:.2f}MB exterior and
  {performance['lod2']['glbBytes']/1e6:.2f}MB LOD; includes the actual reciprocal receiving scenery.
{lane_note}

Open `review.html` for seven annotated before/after pairs and `overview.svg`
for the geometry-derived region map. The PNGs are untouched gameplay-camera
captures from the complete client. `survey-before.json` and `survey-after.json`
record matching authored viewpoints. `package-sha256.json` identifies current
geometry; `capture-package-sha256.json` preserves the internal-view capture bake
before the coordinator's final shared border refinement.

The regional survey places a QA traveller for camera review. `walk-routes.json`
contains 14 routes for the rollout coordinator's authoritative server traversal.
The conservative connectivity audit does not prove server height-aware paths.
Frame-rate overlays were recorded amid concurrent development and do not form a
hardware performance benchmark. Interior scene dimensions were preserved.
''',encoding='utf-8')
    print(out/'review.html')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    write(ap.parse_args().out)
