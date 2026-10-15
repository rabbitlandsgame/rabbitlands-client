"""Repair source-space weights before the canonical fit bakes in folds."""
import numpy as np
from fit_character_appearance import weld, average


def smoothstep(x, lo, hi):
    t = np.clip((x-lo)/(hi-lo), 0, 1)
    return t*t*(3-2*t)


def repair(positions, dense, names, source_joints):
    x, y, z = positions.T
    labels = weld(positions)
    dense = average(dense, labels)
    # Continuous pelvis/thigh transitions replace the donor's abrupt jumps
    # between adjacent trouser faces. The centre blends both thighs softly.
    hip = source_joints['Hips'][1]
    thigh = .5*(source_joints['LeftUpLeg'][1]+source_joints['RightUpLeg'][1])
    pelvis = smoothstep(y, thigh-.13, hip-.035)
    left = smoothstep(x, -.055, .055)
    target = np.zeros_like(dense)
    target[:, names.index('Hips')] = pelvis
    target[:, names.index('LeftUpLeg')] = (1-pelvis)*left
    target[:, names.index('RightUpLeg')] = (1-pelvis)*(1-left)
    region = (smoothstep(y, thigh-.26, thigh-.17)
              * (1-smoothstep(y, hip+.015, hip+.085))
              * (1-smoothstep(abs(x), .16, .24)))
    dense = dense*(1-region[:, None])+target*region[:, None]
    # Central back cloth follows the thorax, fading into neck and shoulders.
    # Alternating clavicle/Head influences here fold the canonical rest mesh.
    neck_y = source_joints['neck'][1]
    neck = smoothstep(y, neck_y-.10, neck_y+.015) * (1-smoothstep(abs(x), .065, .13))
    target = np.zeros_like(dense)
    target[:, names.index('Spine')] = 1-neck
    target[:, names.index('neck')] = neck
    region = (smoothstep(y, neck_y-.25, neck_y-.13)
              * (1-smoothstep(y, neck_y+.015, neck_y+.06))
              * (1-smoothstep(abs(x), .10, .23))
              * (1-smoothstep(z, -.03, .025)))
    dense = dense*(1-region[:, None])+target*region[:, None]
    # Height alone captures the T-pose shoulders and sleeves as well as Head.
    # Keep the rigid face transition inside the actual head/neck column.
    column = np.maximum(1-smoothstep(abs(x), .095, .16), smoothstep(y, 1.47, 1.50))
    head = smoothstep(y, 1.410, 1.455) * column
    dense *= 1-head[:, None]
    dense[:, names.index('Head')] += head
    return average(dense, labels)
