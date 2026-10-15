#!/usr/bin/env python3
"""Does a leg garment actually cover the leg it is worn on?

The parity mathematics, the connected-component split and the runtime refit all
live elsewhere - in ``garment_fit`` and ``footwear_refit``, written for the
footwear rebuild - and are imported rather than copied, so the two briefs cannot
drift apart on the arithmetic that decides whether a seam is closed.

What is added here is the one thing a leg garment needs and a boot does not: the
region it is answerable for has a *floor* as well as a ceiling.  A boot is open
at the top and closed at the bottom, so everything below its rim is its problem.
A trouser is open at both ends.  Below its hem the leg belongs to the footwear,
and measuring a trouser against the ankles it deliberately does not reach counts
the boot's job as the trouser's failure.  The region therefore runs from the hem
up to the waist and stops at both.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from garment_fit import (Component, FitReport, body_points, check,
                         covered_region, garment_components)
from footwear_refit import skeleton, skinned_primitives, worn_geometry

#: How far under the hem the garment stops being answerable, in metres.  The hem
#: is a knife edge whose own vertices sit exactly on the surface.
HEM_MARGIN = .001


def leg_region(body: np.ndarray, shells: list[Component]) -> np.ndarray:
    """Body vertices a leg garment must contain: the band between hem and waist.

    Deliberately *not* ``covered_region``.  That masks against each shell's own
    bounding box, which is right for a boot: a boot is answerable for the foot
    beneath it and for nothing else in the same horizontal slice.  A leg garment
    spans the whole body at every height it covers, so the plan mask can only
    ever be a no-op or a way of quietly excusing a gap - and a mask that moves
    when the garment moves is one that cannot be tuned against, because widening
    a hem would widen the box and change the population being counted.

    Measured on this cast the two definitions agree exactly, so this is not a
    correction of any number: it is the same answer expressed in terms that
    cannot drift.

    The region is therefore defined by the *body* and the garment's two
    horizontal edges, and by nothing else that geometry can move.  Between the
    hem and the top of the waistband a humanoid body is legs, seat and hips and
    nothing else - the arms rest at Y 1.41 on every rig in the cast, well clear
    of the 1.09 the waistband reaches - so no plan mask is needed to exclude
    them.  This is the stricter reading as well as the stable one: everything
    between the two edges is the garment's problem, with nowhere to hide.
    """
    closed = [s for s in shells if s.closed]
    pool = closed or shells
    flat = [s.vertices().reshape(-1, 3) for s in pool]
    hem = min(float(v[:, 1].min()) for v in flat)
    top = max(float(v[:, 1].max()) for v in flat)
    return (body[:, 1] >= hem + HEM_MARGIN) & (body[:, 1] <= top - HEM_MARGIN)


def worn_shells(piece: Path, wearer: Path, registry: dict,
                author_rig: str) -> list[Component]:
    """The garment's components as the wearer will really see them."""
    if Path(wearer).stem == author_rig:
        return garment_components(piece)
    shells: list[Component] = []
    for points, triangles in worn_geometry(piece, wearer, registry, author_rig):
        from garment_fit import components
        shells.extend(components(points, triangles))
    return shells


def measure(piece: Path, wearer: Path, registry: dict,
            author_rig: str) -> FitReport:
    shells = worn_shells(piece, wearer, registry, author_rig)
    body = body_points(wearer)
    return check(piece, wearer, shells=shells, body=body,
                 region=leg_region(body, shells))


def hem_of(shells: list[Component]) -> float:
    closed = [s for s in shells if s.closed]
    pool = closed or shells
    return min(float(s.vertices().reshape(-1, 3)[:, 1].min()) for s in pool)
