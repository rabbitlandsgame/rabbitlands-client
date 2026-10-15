"""Seat geographic paint and soften only the inland northern mineral wash.

The shared paint algorithm stays frozen. This explicit regional opt-in uses
its unchanged implementation, while the final three metres keep the original
mineral material, UVs and coverage. Only visual paint copies may change.
"""
from pathlib import Path
import sys
import numpy as np

REGIONS=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(REGIONS/n) for n in ('_toolkit','_northern','_color')]
import streaming_borders as SB
import terrain_paint as C
from road_profiles import _clip_scalar

REGION='sunmane_steppe'
CONNECTION='amethyst-sunmane'
EDGE_METRES=3.0
FADE_METRES=10.0
RECEIVING_EDGE_LIFT=.012
SOFT_SUFFIX='_InlandSoft'


def smooth(value):
    value=np.clip(value,0.,1.)
    return value*value*(3.-2.*value)


def inland_coverage(alpha,depth,covered=None):
    """Fade a mineral wash through its existing mask, without new soil faces.

    The cutout's discarded half of the mask approaches zero coverage; high
    coverage becomes a restrained wash over grass farther from the border.
    """
    weight=smooth((-np.asarray(depth)-EDGE_METRES)/FADE_METRES)
    alpha=np.asarray(alpha)
    soft=smooth((alpha-.35)/.65)*.70
    binary=(alpha>=.5).astype(float) if covered is None else np.full_like(alpha,float(covered))
    return binary*(1.-weight)+soft*weight


def receiving_edge_lift(depth):
    """Match Amethyst's .014/.016/.018 paint stack at the common line.

    Its northern finish uses a .012 higher slot for this third connection.
    The physical soil is already identical. Carry only that visual lift
    across the shared strip, then return to this region's ordered stack.
    """
    return RECEIVING_EDGE_LIFT*(1.-smooth((-np.asarray(depth)-EDGE_METRES)/FADE_METRES))


def apply(build):
    previous=getattr(build,'sun_north_paint',None)
    if previous is not None:return previous
    # Native builders run in separate processes. Temporarily enrolling this
    # one region avoids changing the frozen helper or any other region's
    # source certificate; restore its curated default even on failure.
    supported=C.REGIONS
    try:
        C.REGIONS=tuple(dict.fromkeys((*supported,REGION)))
        seating=C.apply(build,REGION)
    finally:
        C.REGIONS=supported
    frame=next(f for f in build.streaming_borders if f['id']==CONNECTION)
    edge=np.asarray(frame['anchor'])[[0,2]];outward=np.asarray(frame['outward'])
    softened=[]
    for name,mesh in list(build.terrain_meshes.items()):
        if f'_StreamCollar_{CONNECTION}_Frost' not in name or not mesh.triangle_count:continue
        # Exact complementary clips preserve the shared strip and avoid a
        # second coincident copy. Every attribute is interpolated by SB.
        shared=SB.clip_plane(mesh,edge,-outward,EDGE_METRES)
        inland=SB.clip_plane(mesh,edge,outward,-EDGE_METRES)
        if not inland.triangle_count:continue
        # MASK tests alpha after interpolation. Split its literal .5 contour
        # before storing binary endpoint coverage, so a vertex-only threshold
        # cannot displace the old contour or create a straight -3m seam.
        high=_clip_scalar(inland,.5-inland.colors[:,3])
        low=_clip_scalar(inland,inland.colors[:,3]-.5)
        faces=low.indices.reshape(-1,3)
        low.indices=faces[low.colors[faces,3].min(axis=1)<.5-1e-9].ravel()
        parts=[]
        for suffix,part,covered in (('High',high,True),('Low',low,False)):
            if not part.triangle_count:continue
            depth=(part.positions[:,[0,2]]-edge)@outward
            part.colors[:,3]=inland_coverage(part.colors[:,3],depth,covered)
            part.material='amethyst_barrens_dust_soft_ground'
            soft_name=name+SOFT_SUFFIX+suffix
            build.terrain_meshes[soft_name]=part;parts.append(soft_name)
        if shared.triangle_count:build.terrain_meshes[name]=shared
        else:del build.terrain_meshes[name]
        for border in build.streaming_borders:
            if name in border.get('sceneNodes',[]):
                border['sceneNodes'].extend(n for n in parts if n not in border['sceneNodes'])
                if not shared.triangle_count:border['sceneNodes'].remove(name)
        softened.append(dict(source=name,soft=parts,sharedTriangles=shared.triangle_count,
            inlandTriangles=inland.triangle_count))
    # The two region recipes previously exposed a 12mm purple substrate slit
    # when viewed obliquely across the common boundary. Match corresponding
    # paint levels without raising soil, changing coverage, or filling water.
    # Apply after clipping so newly inserted shared-strip vertices also keep
    # the full receiving level rather than interpolating from inland knots.
    lifted=[]
    for name,mesh in build.terrain_meshes.items():
        if f'_StreamCollar_{CONNECTION}_' not in name or not mesh.triangle_count:continue
        depth=(mesh.positions[:,[0,2]]-edge)@outward
        mesh.positions[:,1]+=receiving_edge_lift(depth)
        mesh.recompute_normals(180)
        lifted.append(name)
    report=dict(version=1,region=REGION,seating=seating,sharedStripMetres=EDGE_METRES,
        inlandFadeMetres=FADE_METRES,maximumInlandMineralCoverage=.70,softened=softened,
        receivingEdgeLift=RECEIVING_EDGE_LIFT,liftedPaint=lifted,physicalMeshesChanged=0)
    build.sun_north_paint=report
    build.notes.append('The northern mineral wash follows the final soil with ordered paint layers; its inland edge uses stable fine coverage while the shared three-metre palette remains exact.')
    return report
