"""Four Gates: surveyed civic island, working quarters and four usable roads.

Metres, Y up, -Z north. Architecture retains its native dimensions; parcels and
walking distances are replanned rather than applying a global model scale.
"""
from __future__ import annotations
import math
import numpy as np

REVISION = 'coastal-inhabited-396-v1'
SIZE = 396
SERVER_ORIGIN = (198, 198)
PLAZA_Y, DECK_Y, WATER_Y = 31., 23., 19.
PLAZA_R, WALL_R = 46., 120.
ARENAS = [
    {'id':'four-gates-40','cap':40,'bounds':[8,13,42,47],'centre':[-173,25,168]},
    {'id':'four-gates-60','cap':60,'bounds':[353,15,387,49],'centre':[172,24,166]},
]
TUTORIAL_ROUTE=[(198,151),(186,160),(161,194),(146,206),(128,213),(126,232)]
TUTORIAL_GARDENS=[(22,88),(33,92),(23,102)]
RESOURCE_POSTS={'2512':(20,86),'498':(30,87),'2506':(37,100),'2509':(20,101),
                '515':(-22,-91),'2503':(25,-84),'2501':(-36,-96),'2500':(36,-103)}

# Road stations carry actual survey elevations. The four surveyed neighbour
# decks begin at -42 m from their anchors and are owned by streaming_borders.
ROADS = {
    'north-avenue': [(0,31,-12),(0,31,-78),(.5,29,-112),(.5,25,-138),(.5,23,-153.5)],
    'west-avenue': [(-12,31,0),(-78,31,0),(-112,29,-.5),(-138,25,-.5),(-153.5,23,-.5)],
    'east-avenue': [(12,31,0),(78,31,0),(112,29,-.5),(138,25,-.5),(153.5,23,-.5)],
    'south-avenue': [(0,31,12),(0,31,78),(.5,29,112),(.5,25,138),(.5,23,153.5)],
    'sanctuary-road': [(.5,25,-138),(-30,26,-138),(-60,28,-143),(-88,34,-143),(-115,37,-143)],
    'orchard-road': [(145,23,0),(148,24,38),(152,24,81),(145,24,121),(139,24,147)],
    'western-shore': [(-141,24.5,-.5),(-150,25,43),(-157,25,85),(-151,25,123),(-147,25,151)],
    'north-pasture': [(145,23,0),(151,24,-42),(158,24,-84),(150,24,-121),(158,24,-149)],
    'southwest-practice': [(-147,25,145),(-152,25,154),(-166,25,159)],
    'southeast-practice': [(139,24,141),(151,24,144),(164,24,156)],
}

# Named shops have usable work yards and separate door/arrival posts. Values
# are centre X/Z, native shell facing yaw, width/depth; no house is miniaturised.
SHOPS = [
 ('four-gates-lantern-row','Lantern Row','agricultural','general goods',-35,84,math.pi,20,13),
 ('four-gates-reedworks','The Reedworks','agricultural','tailoring',64,83,math.pi,20,13),
 ('four-gates-stormglass-house','The Stormglass House','service','alchemy / glass',-55,-83,0,16,14),
 ('four-gates-mirrorsmith-forge',"Mirrorsmith's Forge",'service','smithing',55,-84,0,20,13),
 ('four-gates-ferrymans-rest',"The Ferryman's Rest",'service','inn / ferry office',-89,-39,math.pi/2,16,14),
 ('four-gates-deposit-four-keys','The Deposit of Four Keys','civic','storage / banking',-85,38,math.pi/2,20,14),
]

# Explicit exterior secrets: counterpart ids, room layouts, key requirements,
# reading/harvest effects remain in the shared four_gates_secrets design.
SECRET_POSTS = {
 'gates-civic-focus':(-17,24), 'gates-deposit-vault':(-74,48),
 'gates-drain-mouth':(-106,23), 'gates-ferry-butts':(-78,-25),
 'gates-lantern-cache':(-26,74), 'gates-mirrorsmith-well':(45,-73),
 'gates-otter-pit':(135,141), 'gates-plaza-spring':(18,18),
 'gates-reedworks-garden':(76,75), 'gates-sanctuary-reliquary':(-98,-143),
 'gates-stormglass-school':(-45,-72), 'gates-sunleaf-hollow':(86,44),
 'gates-wall-eyrie':(108,-30), 'gates-waystone':(9,66),
}

NPC_POSTS = {
 'Toran':(-23,18), 'Nima Vey':(25,18), 'Gate Warden Ilyon':(-9,-103),
 'Wayfinder Nesh':(-5,58), 'Tallykeeper Ysolde':(15,20),
 'Ferryman Caldus':(-73,-35), 'Scholar Meret':(-27,-39),
 'Lake Priest Olyra':(-107,-138), 'Sigil Keeper Ansa':(0,-23),
 'Cache Keeper Dellin':(-69,35), 'Register Clerk Hemmen':(-16,8),
 'Bettany Orl':(15,13), 'Toll-Reader Sarn Kesh':(-94,-8),
 'Banner-Rider Ashaia':(98,9), 'Cold Sister Nevet':(-10,-94),
 'Calibrator Yeshin Vol':(-71,19), 'Water-Clerk Ussa-Ren':(-70,-47),
 'Cairnwright Bodrum':(-15,65), 'Spore-Speaker Vell':(-58,-50),
 'Lamp-Trimmer Doric Ashen':(32,34), 'Quartermaster Perrin Lock':(-101,9),
 'Drover Anhu Tam':(138,-137),
}
SERVICE_POSTS = {'info':(4,56), 'storage':(-66,34), 'craft':(43,-62)}

def to_tile(x,z):
    return [math.floor(x+198),math.floor(198-z)]

def remap_world(x,z):
    """Fallback for unnamed old posts, protecting the immediate civic core.

    Named services, doorways, secrets and border triggers use authored overrides.
    This contracts distance between districts, never a building's local mesh.
    """
    r=math.hypot(x,z)
    if r < 1e-9:return (0.,0.)
    nr=float(np.interp(r,[0,45,90,180,280,360,700],[0,35,62,85,108,140,175]))
    return x*nr/r,z*nr/r

def smooth(v):
    q=np.clip(v,0,1);return q*q*(3-2*q)

def patch(t,x,z,width,depth,y,shoulder=6):
    d=np.maximum(np.abs(t.gx-x)-width/2,np.abs(t.gz-z)-depth/2)
    w=1-smooth(d/max(shoulder,.01))
    t.height=t.height*(1-w)+y*w

def grade(t,points,width=7,shoulder=5):
    """A cut road with an exact cross section and gently feathered shoulders."""
    best=np.full_like(t.height,np.inf);target=t.height.copy()
    for a,b in zip(points,points[1:]):
        a,b=np.asarray(a,float),np.asarray(b,float)
        dx,dz=b[0]-a[0],b[2]-a[2]
        q=np.clip(((t.gx-a[0])*dx+(t.gz-a[2])*dz)/max(dx*dx+dz*dz,.01),0,1)
        dist=np.hypot(t.gx-a[0]-q*dx,t.gz-a[2]-q*dz)
        take=dist<best;best=np.minimum(best,dist)
        target=np.where(take,a[1]+q*(b[1]-a[1]),target)
    w=1-smooth((best-width/2)/shoulder)
    t.height=t.height*(1-w)+target*w
    return best,width/2-best

def terrain(TER,cell=1.):
    t=TER.Terrain(-204,-204,408,408,cell=cell)
    x,z=t.gx,t.gz
    r=np.hypot(x,z)
    coast=133+3*np.sin(np.arctan2(z,x)*5)+2*np.sin(z*.038+x*.022)
    # A raised limestone civic island. The shoreline is uneven; the wall and
    # its street order were built on the island, not used to shape the lake.
    t.height=14+17*(1-smooth((r-112)/(coast-112)))
    for cx,cz,rx,rz,y in [(-176,-181,103,99,29),(184,-176,105,106,24),
                          (-184,187,108,106,25),(180,187,110,101,24)]:
        d=np.sqrt(((x-cx)/rx)**2+((z-cz)/rz)**2)
        d+=.12*np.sin(x*.044+z*.021)+.055*np.sin(z*.079-x*.039)
        land=14+(y-14)*(1-smooth((d-.62)/.6))
        t.height=np.maximum(t.height,land)
    texture=.55*np.sin(x*.047+z*.031)+.3*np.sin(z*.12-x*.07)
    t.height+=texture*smooth((r-108)/30)
    patch(t,-115,-162,68,51,37,13)
    for arena in ARENAS:
        ax,ay,az=arena['centre'];patch(t,ax,az,39,39,ay,6)
    # Native city parcels are practical flat yards, linked before dressing.
    for _,_,_,_,cx,cz,_,w,d in SHOPS:patch(t,cx,cz,w+9,d+9,31,5)
    road_masks=[]
    for name,points in ROADS.items():
        d,_=grade(t,points,9 if 'avenue' in name else 6,7)
        road_masks.append(d < (4.5 if 'avenue' in name else 3))
    # Ring street joins the four wards. Its centreline remains outside the
    # occupied porticos and inside the frontage parcels.
    rr=77.; distance=np.abs(r-rr)
    w=1-smooth((distance-3.5)/4)
    t.height=t.height*(1-w)+31*w
    road_masks.append(distance<3.5)
    patch(t,0,0,95,95,31,4)
    t.surface[:]=TER.MEADOW
    t.surface[t.height<20.2]=TER.SHORE
    dz,dx=np.gradient(t.height,t.cell)
    t.surface[np.hypot(dx,dz)>.75]=TER.ROCK
    for mask in road_masks:t.surface[mask]=TER.PAVING
    t.surface[r<46]=TER.PAVING
    t.water_depth=np.maximum(0,WATER_Y-t.height)
    t.tree_block=(r<132)|(t.height<WATER_Y+.7)
    return t

def content_layout(t):
    def p(xz):return [xz[0],round(float(t.height_at(*xz)),3),xz[1]]
    return {'arrival':[0,31.1,55],
      'services':[{'role':{'info':'information','storage':'storage','craft':'crafting_station'}[key],
                   'position':p(value)} for key,value in SERVICE_POSTS.items()],
      'primaryArrivalOnly':True, 'roadClearance':3., 'requireFullWildlife':True,
      'npcs':{key:p(value) for key,value in NPC_POSTS.items()},
      'resourcePosts':{key:p(value) for key,value in RESOURCE_POSTS.items()},
      'wildlife':{
          'mirrorfin_otter':[[-157,114,26],[150,115,28]],
          'riverglass_otter':[[-175,126,22]],
          'reedhorn_stag':[[175,-121,26],[181,-162,26]],
          'crown_antler_stag':[[177,-164,28],[-181,-112,19]]},
      'harvest':{
          'Reed':[[24,89,9]], 'Riverflax':[[32,90,10]],
          'Wheat':[[23,100,10]], 'Sage':[[38,99,9]],
          'Quartz':[[-25,-95,10]], 'Crystal':[[29,-99,10]],
          'Stormglass':[[-33,-88,10]], 'Seed':[[26,-85,9]]},
      'combatYards':ARENAS,
      'tutorial':{'spawn':[198,143],'plaza':[198,178],
                  'routeMarkers':TUTORIAL_ROUTE,'destinationNPC':'Ferryman Caldus'},
      'habitats':{'garden':[135,24,141],'pasture':[151,24,-137],
                  'shore':[-151,25,136],'cliff':[-163,29,-151]},
      'resources':{'mirror_reed':[-143,24,123], 'stormglass_shard':[-156,29,-137],
                   'resonant_crystal':[143,24,-143], 'sunmane_seed':[147,24,150]}}
