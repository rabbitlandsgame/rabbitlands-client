"""Workshop art cannot strand a learner or disagree with harvest coordinates."""
from collections import deque
from pathlib import Path
import gzip
import json
import struct
import unittest

CLIENT=Path(__file__).resolve().parents[1]
PACKAGE=CLIENT/'eloria-assets/maps/cinderbank'


class CinderbankMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=json.loads((PACKAGE/'layout.json').read_text(encoding='utf-8'))
        cls.manifest=json.loads((PACKAGE/'world.json').read_text(encoding='utf-8'))

    def test_art_and_server_interactions_share_tiles_and_pick_volumes(self):
        targets={t['id']:t for t in self.layout['targets']}
        for obj in self.manifest['interactives']:
            with self.subTest(id=obj['id']):
                target=targets[obj['id']]
                self.assertEqual(obj['serverTile'],target['tile'])
                self.assertEqual(obj['approachTile'],target['approach'])
                self.assertEqual(obj['position'],[target['tile'][0],.4,-target['tile'][1]])
                self.assertIn(str(obj['objectId']),self.layout['presentation']['pickShapes'])
        self.assertEqual(targets['ore']['tile'],[50,98])
        self.assertEqual(targets['coal']['tile'],[70,98])

    def test_client_collision_and_prop_footprints_match_layout(self):
        raw=(PACKAGE/'collision.bin').read_bytes()
        size=self.layout['size'];grid=self.layout['walkGrid']
        self.assertEqual(struct.unpack('<4sHHII',raw[:16]),(b'EWCG',2,0,size*2,size*2))
        fine=bytes(v for y in range(size) for _ in range(2) for x in range(size) for v in (grid[y*size+x],)*2)
        self.assertEqual(raw[16:],fine)
        for prop in self.layout['blockers']:
            x0,y0,x1,y1=prop['bounds']
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):self.assertEqual(grid[y*size+x],0,prop['id'])
        server=CLIENT.parent/'dev-server'
        if server.exists():
            self.assertEqual(json.loads((server/'config/eloria/cinderbank.json').read_text(encoding='utf-8')),self.layout)
            packed=gzip.decompress((server/'tools/collision/cinderbank.escg.gz').read_bytes())
            self.assertEqual(packed,struct.pack('<4sHHI',b'ESCG',1,200,size)+bytes(grid))

    def test_every_unlocked_approach_is_reachable_and_closed_courts_stay_closed(self):
        size=self.layout['size']
        for phase in range(1,5):
            grid=list(self.layout['walkGrid'])
            closed=set()
            for index,gate in enumerate(self.layout['gates'],1):
                if index<=phase:continue
                for x0,y0,x1,y1 in (gate['bounds'],self.layout['rooms'][index]):
                    for y in range(y0,y1+1):
                        for x in range(x0,x1+1):grid[y*size+x]=0;closed.add((x,y))
            seen={tuple(self.layout['spawn'])};queue=deque(seen)
            while queue:
                x,y=queue.popleft()
                for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    xx,yy=p
                    if 0<=xx<size and 0<=yy<size and grid[yy*size+xx] and p not in seen:
                        seen.add(p);queue.append(p)
            self.assertFalse(seen & closed)
            for target in self.layout['targets']:
                approach=tuple(target['approach'])
                if approach not in closed:
                    self.assertIn(approach,seen,(phase,target['id']))


if __name__=='__main__':unittest.main()
