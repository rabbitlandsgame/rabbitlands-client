"""Preserved identity and actual exported surface regressions for Verdant."""
from pathlib import Path
import sys,json,math,unittest
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[1]/'_toolkit')]
import region as R
import landscape_plan as PLAN
import verify_runtime as G
import glb_reader as GLB

class LandscapeContract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=json.loads((HERE.parent/'world.json').read_text())
  cls.contract=json.loads((HERE/'preservation-contract.json').read_text())
  doc,binary=G.load_glb(HERE.parent/'world.glb')
  triangles,_=G.collect_triangles(doc,binary,lambda n:n.startswith(('Terrain_','Walk_')))
  cls.nav=G.VerticalRayIndex(triangles)
 def test_original_landmarks_portals_and_returns_remain(self):
  for name,expected in self.contract.items():self.assertEqual(sorted(e['id'] for e in self.m[name]),expected,name)
 def test_full_width_six_flights_have_continuous_real_ground(self):
  for name,(a,b,width) in R.STAIR_RUNS.items():
   a,b=np.array(a),np.array(b);d=b[[0,2]]-a[[0,2]];length=np.linalg.norm(d);side=np.array([-d[1],d[0]])/length
   for lane in np.linspace(-width/2+1,width/2-1,7):
    heights=[]
    for t in np.linspace(0,1,math.ceil(length/.45)+1):
     x,z=a[[0,2]]+t*d+lane*side;h=self.nav.top_hit(x,z)
     self.assertIsNotNone(h,(name,lane,t));heights.append(h)
    self.assertLess(max(abs(np.diff(heights))),.9,(name,lane,max(abs(np.diff(heights)))))
    self.assertLess(abs(heights[0]-a[1]),.6,(name,'foot',heights[0],a[1]))
    self.assertLess(abs(heights[-1]-b[1]),.6,(name,'head',heights[-1],b[1]))
 def test_locked_exits_keep_the_exact_shared_datum(self):
  for s in self.m['streamingBorders']:
   p=next(p for p in self.m['portals'] if p['id']==s['portal']);a=np.array(s['anchor']);a[[0,2]]+=np.array(s['outward'])
   np.testing.assert_allclose(p['position'],a,atol=.001)
   self.assertAlmostEqual(self.nav.top_hit(a[0],a[2]),a[1],delta=.03)
 def test_resident_posts_reproduce_source_and_leave_doors_clear(self):
  posts=self.m['contentLayout']['npcs']
  self.assertEqual(set(posts),set(R.CONTENT_LAYOUT['npcs']))
  for name,position in posts.items():
   self.assertEqual(position[::2],R.CONTENT_LAYOUT['npcs'][name][::2],name)
  self.assertEqual(len(posts),13)
  ox,oy=self.m['coordinateTransform']['serverOrigin']
  for name,position in posts.items():
   tile=(round(position[0]+ox),round(oy-position[2]))
   for portal in self.m['portals']:
    self.assertGreater(max(abs(a-b) for a,b in zip(tile,portal['serverTile'])),3,(name,portal['id']))
   height=self.nav.top_hit(tile[0]-ox+.5,oy-tile[1]-.5)
   self.assertIsNotNone(height,name)
   self.assertAlmostEqual(height,position[1],delta=.02,msg=name)
 def test_pool_cannot_fill_a_separate_lower_terrace_across_a_dry_rim(self):
  class TwoCatchments:
   def height_at(self,x,z):
    basin=(x*x+z*z)<16
    other=x>6
    return np.where(basin|other,0.,3.)
  pool=PLAN.pool_water(TwoCatchments(),1.,0.,0.,12.,'water_cenote')
  self.assertGreater(pool.triangle_count,0)
  self.assertLess(pool.positions[:,0].max(),5)
 def test_main_flights_are_above_all_actual_pool_and_stream_water(self):
  doc,binary=G.load_glb(HERE.parent/'world.glb')
  triangles,_=G.collect_triangles(doc,binary,lambda n:n.startswith('Water_'))
  water=G.VerticalRayIndex(triangles)
  for name,(a,b,width) in R.STAIR_RUNS.items():
   a,b=np.array(a),np.array(b);d=b[[0,2]]-a[[0,2]];length=np.linalg.norm(d);side=np.array([-d[1],d[0]])/length
   for lane in np.linspace(-width/2+1,width/2-1,7):
    for t in np.linspace(0,1,math.ceil(length)+1):
     x,z=a[[0,2]]+t*d+lane*side;ground=self.nav.top_hit(x,z);wet=water.top_hit(x,z)
     if wet is not None:self.assertGreaterEqual(ground,wet-.25,(name,lane,t,ground,wet))
 def test_guarded_actor_landing_tiles_keep_all_seven_lanes(self):
  grid,_=GLB.read_grid(HERE.parent)
  ox,oy=self.m['coordinateTransform']['serverOrigin']
  for name,(a,b,width) in R.STAIR_RUNS.items():
   a,b=np.array(a),np.array(b);d=b[[0,2]]-a[[0,2]];side=np.array([-d[1],d[0]])/np.linalg.norm(d)
   for lane in np.linspace(-width/2+1,width/2-1,7):
    for point in (a,b):
     x,z=point[[0,2]]+lane*side;tx,ty=round(x+ox),round(oy-z)
     self.assertTrue(np.all(grid[ty*2-1:ty*2+1,tx*2-1:tx*2+1]>0),(name,lane,tx,ty))

if __name__=='__main__':unittest.main()
