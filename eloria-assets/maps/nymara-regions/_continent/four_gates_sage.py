"""Four Gates tutorial Sage: keep the first harvest within reach of the arrival.

The compact Four Gates map kept its six Sage nodes 42 tiles from the spawn; the
continent's Four Gates site is 1.5x larger and its content scaled with it, so
the same nodes came to stand 76 tiles from the served arrival while the
tutorial (and ``test_nymara_vertical_slice``) expect the first harvest within
70. The six harvesting records are pinned here to open, dry ground beside the
plaza approach road, 48 tiles from the arrival, with their surveyed layout
kept. The contract placer still resolves each pin to actual standing ground.
Nothing else in Four Gates moves.
"""
from __future__ import annotations
import numpy as np

REGION='four_gates'
# harvesting.txt record (compact tile) -> global XZ metres on the composed
# continent. Layout offsets equal the compact patch (centroid 242.3, 110.0)
# moved to centroid (331, 115) in the published Four Gates frame
# (serverOrigin 310,164; translation 530,0,840): x = tile+.5-310+530,
# z = 164-tile-.5+840.
AUTHORED_POINTS={
    (240,110):(549.5,888.5),  # harvesting.txt:132:2506 Sage
    (245,118):(554.5,880.5),  # harvesting.txt:133:2507 Sage
    (236,116):(545.5,882.5),  # harvesting.txt:134:2508 Sage
    (246,108):(555.5,890.5),  # harvesting.txt:435:641 Sage
    (246,104):(555.5,894.5),  # harvesting.txt:436:642 Sage
    (241,104):(550.5,894.5)}  # harvesting.txt:437:643 Sage
MINIMUM_DRY_METRES=.8


def prepare_four_gates_sage(world,content):
    """Pin the six Sage records once retained content has been placed."""
    if REGION not in world.ids:return {}
    if not hasattr(content,'authored_server_points'):content.authored_server_points={}
    owner=world.ids.index(REGION);points={}
    for tile,(x,z) in AUTHORED_POINTS.items():
        if int(world.owner_at(x,z))!=owner:
            raise ValueError(f'{REGION}:{list(tile)}: authored Sage point lies outside its territory')
        height=float(world.height_at(x,z))
        if height<MINIMUM_DRY_METRES:
            raise ValueError(f'{REGION}:{list(tile)}: authored Sage point is not dry ground ({height:.2f} m)')
        point=np.array([x,height,z])
        content.authored_server_points[(REGION,tile)]=point;points[str(list(tile))]=point.tolist()
    world.four_gates_sage={'authoredPoints':points,
        'policy':'Six compact Sage records pinned 48 tiles from the arrival with their surveyed layout; placement resolves standing ground.'}
    return world.four_gates_sage


def refresh_four_gates_sage_heights(world,content):
    """Resolve the pinned points' heights from the final composed terrain."""
    if REGION not in world.ids:return
    for tile in AUTHORED_POINTS:
        point=content.authored_server_points[(REGION,tile)]
        point[1]=float(world.height_at(point[0],point[2]))
        if point[1]<MINIMUM_DRY_METRES:
            raise ValueError(f'{REGION}:{list(tile)}: final terrain under the Sage point is not dry ground')
        world.four_gates_sage['authoredPoints'][str(list(tile))]=point.tolist()
