"""Retain the south customs arch after its old shared bridge moves east."""
from contextlib import contextmanager
import numpy as np


def prepare(terrain, plan, paving):
    # The previous crossing supplied this gate's 23m walking deck. The fixed
    # continent crossing now starts east of it, so the civic arch needs its
    # own permanent landing, rather than depending on a remote border mesh.
    plan.patch(terrain,.5,172.,54.,28.,23.,16.)
    plan.grade(terrain,[(.5,23.,153.5),(.5,23.,186.)],9.,8.)
    court=(np.abs(terrain.gx-.5)<=27.)&(np.abs(terrain.gz-172.)<=14.)
    path=(np.abs(terrain.gx-.5)<=4.5)&(terrain.gz>=153.5)&(terrain.gz<=186.)
    terrain.surface[court|path]=paving
    terrain.tree_block|=court|path


@contextmanager
def retain_footing_during_geography(build):
    # Geometry shaping already understands solid structure footprints. Feed
    # the arch's real bounds into that pass, then restore its authored
    # collision policy: only the two piers block players, never the passage.
    gate=next(p for p in build.placements if p.node=='Gate_South_Outer')
    original=gate.collides
    gate.collides=True
    try:
        yield
    finally:
        gate.collides=original

