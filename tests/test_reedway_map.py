"""Caravan art, native picking and companion-sized routes share one layout."""
from collections import deque
from pathlib import Path
import gzip
import json
import struct
import unittest

CLIENT=Path(__file__).resolve().parents[1]
PACKAGE=CLIENT/'eloria-assets/maps/reedway'


class ReedwayMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=json.loads((PACKAGE/'layout.json').read_text(encoding='utf-8'))
        cls.manifest=json.loads((PACKAGE/'world.json').read_text(encoding='utf-8'))

    def flood(self,grid,start,radius=0):
        size=self.layout['size']
        def fits(x,y):
            return all(0<=x+dx<size and 0<=y+dy<size and grid[(y+dy)*size+x+dx]
                for dx in range(-radius,radius+1) for dy in range(-radius,radius+1))
        seen={start};queue=deque([start]);distances={start:0}
        while queue:
            x,y=queue.popleft()
            for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if p not in seen and fits(*p):
                    seen.add(p);distances[p]=distances[(x,y)]+1;queue.append(p)
        return distances

    def test_collision_and_interaction_parity(self):
        size=self.layout['size'];grid=self.layout['walkGrid']
        raw=(PACKAGE/'collision.bin').read_bytes()
        fine=bytes(v for y in range(size) for _ in range(2) for x in range(size) for v in (grid[y*size+x],)*2)
        self.assertEqual(raw,struct.pack('<4sHHII',b'EWCG',2,0,size*2,size*2)+fine)
        server=CLIENT.parent/'dev-server'
        if server.exists():
            self.assertEqual(json.loads((server/'config/eloria/reedway.json').read_text(encoding='utf-8')),self.layout)
            self.assertEqual(gzip.decompress((server/'tools/collision/reedway.escg.gz').read_bytes()),
                struct.pack('<4sHHI',b'ESCG',1,200,size)+bytes(grid))
        targets={v['id']:v for v in self.layout['targets']}
        self.assertNotIn('ore',targets);self.assertNotIn('waystone',targets)
        for obj in self.manifest['interactives']:
            t=targets[obj['id']]
            self.assertEqual(obj['serverTile'],t['tile'])
            self.assertEqual(obj['approachTile'],t['approach'])
            self.assertEqual(obj['position'],[t['tile'][0],.4,-t['tile'][1]])
            self.assertIn(str(obj['objectId']),self.layout['presentation']['pickShapes'])

    def test_open_targets_and_closed_gates(self):
        size=self.layout['size']
        for phase in range(1,5):
            grid=list(self.layout['walkGrid']);closed=set()
            for index,gate in enumerate(self.layout['gates'],1):
                if index<=phase:continue
                for x0,y0,x1,y1 in (gate['bounds'],self.layout['rooms'][index]):
                    for y in range(y0,y1+1):
                        for x in range(x0,x1+1):grid[y*size+x]=0;closed.add((x,y))
            reached=self.flood(grid,tuple(self.layout['spawn']))
            self.assertFalse(set(reached)&closed)
            for target in self.layout['targets']:
                p=tuple(target['approach'])
                if p not in closed:self.assertIn(p,reached,(phase,target['id']))

    def test_companion_clearance_and_west_alternatives(self):
        grid=self.layout['walkGrid'];size=self.layout['size']
        reached=self.flood(grid,(60,90),radius=1)
        self.assertIn((60,104),reached,'The companion course supports a three-tile-wide body')
        self.assertLessEqual(reached[(60,104)],24,'Pre-summon staging keeps the walk short')
        west=list(grid)
        for y in range(size):
            for x in range(size):
                if not (5<=x<=31 and 43<=y<=77):west[y*size+x]=0
        # Close either side of the trunk; the other must reach a companion stand-off.
        # The player can approach one tile closer to the berth's low front rail.
        for close_top in (True,False):
            trial=list(west)
            for y in (range(61,78) if close_top else range(43,60)):
                for x in range(17,22):trial[y*size+x]=0
            self.assertTrue((12,53) in self.flood(trial,(27,60),radius=1),
                f'Companion route blocked with close_top={close_top}')
        for points in self.layout['encounters'].values():
            for x,y in points:
                self.assertTrue(all(grid[(y+dy)*size+x+dx] for dx in (-1,0,1) for dy in (-1,0,1)),(x,y))


if __name__=='__main__':unittest.main()
