"""Survey instruments and a terraced observatory, with region-supplied materials."""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M, stonework as SW, noise as N, routecraft as RC, architecture as ARCH

def observatory(seed: int = 0, stone="amethyst_pale_stone",
                roof="amethyst_verdigris", brass="amethyst_brass",
                crystal="amethyst_crystal") -> SW.MeshGroup:
    """The Glasswarden Observatory, panel 2.

    A domed hall on a walkable podium, ringed by balustrades and pinnacles, with
    the great brass armillary sphere standing on the dome. The podium deck is a
    walk surface; everything else is structure, so the grounding ray cannot put
    an actor on the roof.
    """
    STONE, ROOF, BRASS, CRYSTAL = stone, roof, brass, crystal
    rng = N.Rng(seed)
    out = SW.MeshGroup()

    half_x, half_z = 13.0, 10.5
    podium_h = 2.6

    # -- podium, and the deck a player can stand on
    body = M.box((half_x*2-0.4,podium_h+0.3,half_z*2-0.4),
                 center=(0,(podium_h+0.3)/2,0),uv_scale=0.5,material=STONE)
    faces=body.indices.reshape(-1,3)
    top=np.all(body.positions[faces][:,:,1]>podium_h+0.29,axis=1)
    body.indices=faces[~top].reshape(-1)
    out.add(body)
    # Four non-overlapping walking strips surround the closed drum. The core
    # has a structural floor, so the walk opener cannot reopen its interior.
    top = podium_h + 0.3
    for x0,x1,z0,z1 in [(-12.8,12.8,6.5,10.3),(-12.8,12.8,-10.3,-6.5),
                         (-12.8,-6.5,-6.5,6.5),(6.5,12.8,-6.5,6.5)]:
        out.add_walk(M.quad([(x0,top,z0),(x0,top,z1),(x1,top,z1),(x1,top,z0)],
                            uv_scale=0.5,material=STONE))
    core_floor=M.quad([(-6.5,top,-6.5),(-6.5,top,6.5),(6.5,top,6.5),(6.5,top,-6.5)],material=STONE)
    out.add(core_floor)
    steps = RC.stair_flight(7.0,top,8.0,14,material=STONE)
    out.add_walk(steps.rotate_y(math.pi).translate(0,0,18.3))

    # -- balustrade around the deck
    for sign in (-1.0, 1.0):
        lengths = [(0,half_x*2-1.2)] if sign < 0 else [(-8.3,8.2),(8.3,8.2)]
        for x,length in lengths:
            out.add(SW.balustrade(length,1.05,material=STONE)
                    .translate(x,podium_h+0.30,sign*(half_z-0.6)))
        side = SW.balustrade(half_z * 2 - 1.2, 1.05, material=STONE)
        side.rotate_y(math.pi * 0.5)
        out.add(side.translate(sign * (half_x - 0.6), podium_h + 0.30, 0.0))

    # -- the drum and dome
    drum_r, drum_h = 6.4, 7.2
    # The lower front sector is a real doorway, rather than a door plate on a
    # closed cylinder. The existing upper drum and dome keep their silhouette.
    lower=M.cylinder(drum_r,drum_r*0.982,3.3,20,uv_scale=0.6,material=STONE)
    faces=lower.indices.reshape(-1,3)
    centre=lower.positions[faces].mean(axis=1)
    caps=np.all(lower.positions[faces][:,:,1]>3.299,axis=1)
    lower.indices=faces[~(caps|((centre[:,2]>5.9)&(np.abs(centre[:,0])<2.1)))].reshape(-1)
    out.add(lower.translate(0,podium_h+0.3,0))
    upper=M.cylinder(drum_r*0.982,drum_r*0.96,drum_h-3.3,20,uv_scale=0.6,material=STONE)
    faces=upper.indices.reshape(-1,3)
    bottom=np.all(upper.positions[faces][:,:,1]<0.001,axis=1)
    upper.indices=faces[~bottom].reshape(-1)
    out.add(upper.translate(0,podium_h+3.6,0))
    out.add(M.box((3.48,0.20,0.42),center=(0,podium_h+3.5,6.03),material=STONE))
    for side in (-1,1):
        out.add(M.box((0.40,3.3,0.50),center=(side*1.94,podium_h+1.95,6.1),material=STONE))
    out.add(ARCH.door(3.46,3.1,material=ROOF).translate(0,podium_h+0.3,6.03))
    # a moulded cornice
    cornice = M.cylinder(drum_r * 1.10, drum_r * 1.02, 0.55, 20, uv_scale=0.6,
                         material=STONE)
    out.add(cornice.translate(0.0, podium_h + drum_h + 0.05, 0.0))

    dome_profile = [(drum_r * 0.99, 0.0)]
    for index in range(1, 13):
        t = index / 12.0
        dome_profile.append((drum_r * math.cos(t * math.pi * 0.5) * 0.99,
                             drum_r * 0.86 * math.sin(t * math.pi * 0.5)))
    dome = M.lathe(dome_profile, segments=22, material=ROOF)
    out.add(dome.translate(0.0, podium_h + drum_h + 0.55, 0.0))

    # tall arched windows around the drum, cut as recessed panels
    for index in range(1,10):
        angle = 2.0 * math.pi * index / 10.0
        panel = M.box((1.5, 3.4, 0.4), center=(0.0, 0.0, 0.0), uv_scale=0.7,
                      material=ROOF)
        panel.rotate_y(angle)
        out.add(panel.translate(math.sin(angle) * drum_r * 0.99,
                                podium_h + 3.1,
                                math.cos(angle) * drum_r * 0.99))

    # -- corner pinnacles with verdigris caps
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            x, z = sx * (half_x - 1.5), sz * (half_z - 1.5)
            shaft = M.cylinder(0.85, 0.62, 8.5, 10, uv_scale=0.7, material=STONE)
            out.add(shaft.translate(x, podium_h + 0.3, z))
            cap = M.cylinder(0.86, 0.02, 3.2, 10, uv_scale=0.7, material=ROOF)
            out.add(cap.translate(x, podium_h + 8.8, z))
            lamp = M.icosphere(0.34, subdivisions=1, material=CRYSTAL)
            out.add(lamp.translate(x, podium_h + 12.2, z))

    # -- the armillary sphere on the dome, panel 2's silhouette
    sphere_y = podium_h + drum_h + 0.55 + drum_r * 0.86
    out.add(armillary(radius=4.3, seed=seed + 7, brass=BRASS, crystal=CRYSTAL).translate(0.0, sphere_y + 4.4, 0.0))

    # a brass mounting yoke
    for sign in (-1.0, 1.0):
        leg = M.cylinder(0.30, 0.24, 4.6, 8, uv_scale=0.6, material=BRASS)
        leg.rotate_z(sign * 0.16)
        out.add(leg.translate(sign * 1.5, sphere_y, 0.0))

    # The podium owns this plane. Remove the concealed seating faces of the
    # drum, pinnacles, door and balustrades instead of stacking caps on it.
    for part in out.parts:
        if part is core_floor:
            continue
        faces=part.indices.reshape(-1,3)
        seated=np.all(np.abs(part.positions[faces][:,:,1]-top)<1e-5,axis=1)
        part.indices=faces[~seated].reshape(-1)
    return out


def armillary(radius: float = 4.0, seed: int = 0,
              brass="amethyst_brass", crystal="amethyst_crystal") -> M.Mesh:
    """The brass orrery: three great rings, a globe and a pointer arm."""
    BRASS, CRYSTAL = brass, crystal
    parts = []
    segments = 40

    def ring(tilt_x: float, tilt_z: float, r: float, thickness: float) -> M.Mesh:
        angles = np.linspace(0.0, 2.0 * math.pi, segments + 1)
        path = np.stack([np.cos(angles) * r,
                         np.zeros_like(angles),
                         np.sin(angles) * r], axis=-1)
        piece = M.tube(path, np.full(len(path), thickness), segments=7,
                       material=BRASS)
        piece.rotate_x(tilt_x)
        piece.rotate_z(tilt_z)
        return piece

    parts.append(ring(0.0, 0.0, radius, radius * 0.052))
    parts.append(ring(math.pi * 0.5, 0.0, radius * 0.94, radius * 0.046))
    parts.append(ring(math.pi * 0.5, math.pi * 0.5, radius * 0.88, radius * 0.042))
    parts.append(ring(0.42, 0.0, radius * 0.72, radius * 0.038))

    globe = M.icosphere(radius * 0.42, subdivisions=2, material=CRYSTAL)
    parts.append(globe)

    # the long pointer arm that the lightning strikes in the concept
    arm = M.cylinder(radius * 0.045, radius * 0.018, radius * 2.5, 8,
                     uv_scale=0.6, material=BRASS)
    arm.rotate_z(math.pi * 0.5)
    arm.rotate_y(0.6)
    parts.append(arm.translate(0.0, radius * 0.15, 0.0))

    # polar axis
    axis = M.cylinder(radius * 0.05, radius * 0.05, radius * 2.35, 8,
                      uv_scale=0.6, material=BRASS)
    parts.append(axis.translate(0.0, -radius * 1.18, 0.0))
    return M.merge(parts, material=BRASS)
