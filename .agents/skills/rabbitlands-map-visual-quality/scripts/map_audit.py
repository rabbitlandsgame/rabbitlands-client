"""Audit authored continent-v2 maps for the shapes that read as artificial.

Reads the saved authoring scenes (godot-client/world_authoring/regions/<map>/<map>.tscn)
and the published packages; changes nothing.

  python map_audit.py roads    [--maps ...] [--out DIR]   hairpins, zigzags, sharp corners
  python map_audit.py patches  [--maps ...] [--out DIR]   ground-region shapes and blends
  python map_audit.py drift    [--maps ...]               saved scene vs last published bake
  python map_audit.py overlay  [--maps ...] --out DIR      roads and findings over map-detail.webp

Default maps: every registry map with status continent-v2-served. Run from the
client checkout or pass --client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

# Godot 4.7 writes more attributes after the ones matched here (unique_id=NNN after
# parent=), so every header pattern allows a trailing remainder.
ROAD_NODE = re.compile(r'^\[node name="([^"]+)" type="Path3D" parent="Roads"(?: [^\n]*)?\]$', re.M)
REGION_NODE = re.compile(r'^\[node name="([^"]+)" type="Marker3D" parent="Ground/Regions"(?: [^\n]*)?\]$', re.M)
CURVE = re.compile(r'^\[sub_resource type="Curve3D"[^\n]*? id="([^"]+)"[^\n]*\]$', re.M)
RESOURCE = re.compile(r'^\[sub_resource type="Resource"[^\n]*? id="([^"]+)"[^\n]*\]$', re.M)
# Any node header under the two parents the audit reads, whatever its type or attributes.
CHILD_NODE = re.compile(r'^\[node [^\n]*? parent="(Roads|Ground/Regions)"[^\n]*\]$', re.M)

# A road's centreline should not turn tighter than this many road widths (radius),
# nor run out and back: over a stretch of DETOUR_WINDOW_WIDTHS widths the straight
# distance should stay above DETOUR_RATIO of the distance walked.
MIN_RADIUS_WIDTHS = 1.25
SHARP_CORNER_DEGREES = 50.0
DETOUR_WINDOW_WIDTHS = 3.0
DETOUR_RATIO = 0.55
# Ground regions: paving needs a blend of at least this to have room for an edge
# (the exporter samples weights on a 2 m lattice); a patch longer than this
# aspect reads as a ruled stripe from above.
MIN_PAVING_BLEND_METRES = 3.0
MAX_ASPECT = 3.0


def block_after(text: str, start: int) -> str:
    end = text.find('\n[', start)
    return text[start:end if end > 0 else len(text)]


def floats(text: str) -> list[float]:
    return [float(v) for v in re.findall(r'-?[0-9.]+(?:e[-+]?[0-9]+)?', text)]


class SceneFormatError(Exception):
    """The scene has content the header patterns did not read: an audit of it would report too little."""


def require_read(text: str, parent: str, pattern: re.Pattern) -> None:
    headers = [m.group(0) for m in CHILD_NODE.finditer(text) if m.group(1) == parent]
    unread = [h for h in headers if not pattern.match(h)]
    if unread:
        raise SceneFormatError(f'{len(unread)} of {len(headers)} nodes under {parent} were not read '
                               f'(the scene format changed?), first: {unread[0]}')


def scene_path(client: Path, map_id: str) -> Path:
    return client / 'godot-client/world_authoring/regions' / map_id / f'{map_id}.tscn'


def package_dir(client: Path, map_id: str) -> Path:
    return client / 'eloria-assets/maps/continent-v2' / map_id / 'client'


def served_maps(client: Path) -> list[str]:
    maps = json.loads((client / 'godot-client/data/maps/registry.json').read_text())['maps']
    return sorted(k for k, v in maps.items() if isinstance(v, dict) and v.get('status') == 'continent-v2-served')


def read(client: Path, map_id: str, reader):
    path = scene_path(client, map_id)
    try:
        return reader(path.read_text(encoding='utf-8'))
    except SceneFormatError as e:
        raise SceneFormatError(f'{path}: {e}') from None


def roads(text: str) -> list[dict]:
    require_read(text, 'Roads', ROAD_NODE)
    curves = {}
    for m in CURVE.finditer(text):
        pm = re.search(r'"points": PackedVector3Array\(([^)]*)\)', block_after(text, m.end()))
        if pm:
            v = floats(pm.group(1))
            curves[m.group(1)] = [(v[i + 6], v[i + 7], v[i + 8]) for i in range(0, len(v) - 8, 9)]
    out = []
    for m in ROAD_NODE.finditer(text):
        block = block_after(text, m.end())
        cm = re.search(r'curve = SubResource\("([^"]+)"\)', block)
        tm = re.search(r'^transform = Transform3D\(([^)]*)\)', block, re.M)
        wm = re.search(r'^default_width = ([0-9.]+)', block, re.M)
        if cm and cm.group(1) not in curves:
            raise SceneFormatError(f'road {m.group(1)} uses curve {cm.group(1)}, which was not read')
        # Transform3D(...) lists the basis ROWS, then the origin.
        t = floats(tm.group(1)) if tm else [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        points = [(t[0] * x + t[1] * y + t[2] * z + t[9], t[3] * x + t[4] * y + t[5] * z + t[10],
                   t[6] * x + t[7] * y + t[8] * z + t[11]) for x, y, z in curves.get(cm.group(1) if cm else '', [])]
        out.append({'name': m.group(1), 'width': float(wm.group(1)) if wm else 6.0, 'points': points})
    return out


def heading(a, b) -> float:
    return math.atan2(b[0] - a[0], -(b[2] - a[2]))


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def audit_road(road: dict) -> dict:
    pts = []
    for p in road['points']:
        if not pts or math.dist((p[0], p[2]), (pts[-1][0], pts[-1][2])) > 0.05:
            pts.append(p)
    n = len(pts)
    station = [0.0]
    for i in range(1, n):
        station.append(station[-1] + math.dist((pts[i][0], pts[i][2]), (pts[i - 1][0], pts[i - 1][2])))
    width = road['width']
    window = max(12.0, DETOUR_WINDOW_WIDTHS * width)
    issues = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and station[j + 1] - station[i] <= window:
            j += 1
        walked = station[j] - station[i]
        straight = math.dist((pts[i][0], pts[i][2]), (pts[j][0], pts[j][2])) if j > i else 0.0
        if j > i + 1 and walked > 4.0 and straight < DETOUR_RATIO * walked:
            k = max(range(i, j + 1), key=lambda q: math.dist((pts[i][0], pts[i][2]), (pts[q][0], pts[q][2])))
            turn = sum(abs(wrap(heading(pts[q], pts[q + 1]) - heading(pts[q - 1], pts[q]))) for q in range(i + 1, j))
            issues.append({'kind': 'doubles_back', 'at': [round(pts[k][0], 1), round(pts[k][2], 1)],
                           'station': round(station[k], 1), 'walked_m': round(walked, 1),
                           'straight_m': round(straight, 1), 'turn_deg': round(math.degrees(turn))})
            i = j
            continue
        i += 1
    for q in range(1, n - 1):
        turn = math.degrees(abs(wrap(heading(pts[q], pts[q + 1]) - heading(pts[q - 1], pts[q]))))
        if turn > SHARP_CORNER_DEGREES and not any(abs(station[q] - x['station']) < window for x in issues):
            issues.append({'kind': 'sharp_corner', 'at': [round(pts[q][0], 1), round(pts[q][2], 1)],
                           'station': round(station[q], 1), 'turn_deg': round(turn)})
    # Tightest turning radius over three-metre chords.
    tight = math.inf
    span = 3
    for q in range(span, n - span):
        a, b, c = pts[q - span], pts[q], pts[q + span]
        area2 = abs((b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]))
        if area2 > 1e-9 and station[q + span] - station[q - span] < 4 * span:
            radius = (math.dist((a[0], a[2]), (b[0], b[2])) * math.dist((b[0], b[2]), (c[0], c[2]))
                      * math.dist((a[0], a[2]), (c[0], c[2]))) / (2 * area2)
            tight = min(tight, radius)
    return {'name': road['name'], 'width': width, 'length_m': round(station[-1] if station else 0, 1),
            'min_radius_m': None if math.isinf(tight) else round(tight, 1),
            'radius_ok': math.isinf(tight) or tight >= MIN_RADIUS_WIDTHS * width, 'issues': issues}


def regions(text: str) -> list[dict]:
    require_read(text, 'Ground/Regions', REGION_NODE)
    presets = {}
    for m in RESOURCE.finditer(text):
        p = re.search(r'texture_preset = "([^"]+)"', block_after(text, m.end()))
        if p:
            presets[m.group(1)] = p.group(1)
    out = []
    for m in REGION_NODE.finditer(text):
        block = block_after(text, m.end())

        def field(name, default=''):
            f = re.search(rf'^{name} = (.+)$', block, re.M)
            return f.group(1) if f else default

        size = floats(field('size', 'Vector2(0, 0)').replace('Vector2', ''))
        transform = floats(field('transform'))
        surface = re.search(r'SubResource\("([^"]+)"\)', field('surface'))
        out.append({
            'node': m.group(1), 'shape': 'rectangle' if field('shape') == '1' else 'ellipse',
            'size': size, 'blend': float(field('blend_width', '0') or 0),
            'opacity': float(field('opacity', '1') or 1), 'enabled': field('enabled', 'true') == 'true',
            'preset': presets.get(surface.group(1), '?') if surface else '?',
            'at': [round(transform[9], 1), round(transform[11], 1)] if len(transform) >= 12 else None,
        })
    return out


def audit_region(region: dict) -> list[str]:
    findings = []
    size = [v for v in region['size'] if v > 0]
    paving = 'masonry' in region['preset'].lower() or 'paving' in region['preset'].lower()
    if paving and region['blend'] < MIN_PAVING_BLEND_METRES:
        findings.append(f'paving blend {region["blend"]} m < {MIN_PAVING_BLEND_METRES} m: its edge cannot soften')
    if len(size) == 2 and max(size) / min(size) > MAX_ASPECT:
        findings.append(f'aspect {max(size) / min(size):.1f} > {MAX_ASPECT}: reads as a ruled stripe')
    if region['shape'] == 'rectangle' and not paving:
        findings.append('a rectangle of natural ground: its sides read as ruled lines')
    if region['blend'] < 2.0 and not paving:
        findings.append(f'blend {region["blend"]} m: a hard edge on natural ground')
    return findings


def cmd_roads(client: Path, maps: list[str], out: Path | None) -> dict:
    report = {}
    for m in maps:
        report[m] = [audit_road(r) for r in read(client, m, roads)]
        issues = [i for r in report[m] for i in r['issues']]
        tight = [r['name'] for r in report[m] if not r['radius_ok']]
        print(f'{m:13s} roads={len(report[m]):2d} doubles_back={sum(i["kind"] == "doubles_back" for i in issues)} '
              f'sharp_corners={sum(i["kind"] == "sharp_corner" for i in issues)} tight_radius={len(tight)}')
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / 'roads.json').write_text(json.dumps(report, indent=1))
    return report


def cmd_patches(client: Path, maps: list[str], out: Path | None) -> dict:
    report = {}
    for m in maps:
        rows = read(client, m, regions)
        for row in rows:
            row['findings'] = audit_region(row) if row['enabled'] else []
        report[m] = rows
        shapes = {}
        for row in rows:
            shapes[row['shape']] = shapes.get(row['shape'], 0) + 1
        print(f'{m:13s} regions={len(rows):3d} {shapes} flagged={sum(bool(r["findings"]) for r in rows)}')
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / 'patches.json').write_text(json.dumps(report, indent=1))
    return report


def cmd_drift(client: Path, maps: list[str]) -> None:
    for m in maps:
        published = json.loads((package_dir(client, m) / 'publication.json').read_text())['snapshot'].get('sceneSha256')
        saved = hashlib.sha256(scene_path(client, m).read_bytes()).hexdigest()
        print(f'{m:13s} {"published" if published == saved else "DRIFT (saved scene not yet published)"}')


def cmd_overlay(client: Path, maps: list[str], out: Path) -> None:
    from PIL import Image, ImageDraw
    road_report = cmd_roads(client, maps, None)
    out.mkdir(parents=True, exist_ok=True)
    for m in maps:
        meta = json.loads((package_dir(client, m) / 'world.json').read_text())['minimap']
        lo, hi = meta['worldMin'], meta['worldMax']
        image = Image.open(package_dir(client, m) / 'map-detail.webp').convert('RGB')
        scale = image.size[0] / (hi[0] - lo[0])
        draw = ImageDraw.Draw(image)

        def px(x, z):
            return ((x - lo[0]) * scale, (z - lo[1]) * scale)

        for road in read(client, m, roads):
            if len(road['points']) > 1:
                draw.line([px(p[0], p[2]) for p in road['points']], fill=(255, 0, 0), width=3)
        for road in road_report[m]:
            for issue in road['issues']:
                x, y = px(*issue['at'])
                draw.ellipse([x - 30, y - 30, x + 30, y + 30], outline=(255, 255, 0), width=6)
        for row in read(client, m, regions):
            if row['enabled'] and row['at'] and audit_region(row):
                x, y = px(*row['at'])
                draw.rectangle([x - 14, y - 14, x + 14, y + 14], outline=(0, 255, 255), width=4)
        image.thumbnail((1600, 1600))
        image.save(out / f'{m}_audit.png')
        print('wrote', out / f'{m}_audit.png')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['roads', 'patches', 'drift', 'overlay'])
    parser.add_argument('--client', type=Path, default=Path.cwd())
    parser.add_argument('--maps', nargs='*')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    client = args.client.resolve()
    if not (client / 'godot-client/data/maps/registry.json').is_file():
        sys.exit(f'{client} is not a client checkout (pass --client)')
    maps = args.maps or served_maps(client)
    try:
        if args.command == 'roads':
            cmd_roads(client, maps, args.out)
        elif args.command == 'patches':
            cmd_patches(client, maps, args.out)
        elif args.command == 'drift':
            cmd_drift(client, maps)
        else:
            if not args.out:
                sys.exit('overlay needs --out')
            cmd_overlay(client, maps, args.out)
    except SceneFormatError as e:
        sys.exit(f'map_audit: {e}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
