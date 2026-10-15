#!/usr/bin/env python3
"""Torso garments cover the body, and the shoulder in particular.

Added 2026-08-29 for Eloria Client.  The defect this guards was reported as
"there are still gaps in the shoulder areas of the shirt", and it survived
several rounds of fixing because a shoulder seam that closes in the T-pose the
rig is authored in opens the moment the arm leaves it.  A bind-pose screenshot
cannot see that, so it is measured here instead, in the poses that show it.

The shoulder is asserted **separately** from the body total, deliberately.  A
torso garment claims eight hundred-odd vertices; fourteen of them coming through
at the deltoid is the whole complaint and rounds to nothing in a whole-body
figure.

What is checked, and why it is scoped the way it is: every part-5 mesh is asked
whether its shells are closed, which is cheap and catches the topology error
that made the old shells untestable at all.  Coverage is then measured on one
design of each of the four kinds, against every race that wears it, in every
clip the shoulder has to survive.  The exhaustive sweep over all sixty-four
designs is eloria-assets/tools/torso_audit.py - too slow for a test run, and its
results are committed beside it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
EQUIPMENT = CLIENT / "data" / "actors" / "equipment.json"
RACES = CLIENT / "assets" / "actors" / "native" / "races"
TOOLS = ROOT / "eloria-assets" / "tools"

#: One design of each kind, plus the two generic pieces most players will be
#: wearing.  Coverage is a property of the construction rather than of any one
#: design, so a representative of each construction is what a test needs.
SAMPLE = {
    "5:120": "coat",
    "5:128": "cuirass",
    "5:168": "shirt",
    "5:137": "robe",
    "5:0": "generic shirt",
    "5:16": "generic plate",
}

#: What else the wearer has on.  A torso hem finishes *inside* the trousers, so
#: the seam has to be judged with them on - and, separately, with them off.
TROUSERS = ("4:0",)


def _fit():
    sys.path.insert(0, str(TOOLS))
    import garment_coverage
    return garment_coverage


class TorsoShellTest(unittest.TestCase):
    """Every torso shell closes on itself.

    Enclosure is decided by ray parity, and parity needs a closed volume.  The
    shells this replaces were stacks of open tubes - not one of the sixteen
    torso meshes enclosed anything - so nothing about their coverage could be
    measured at all, which is how the gap survived.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(EQUIPMENT.read_text())

    def _scenes(self):
        for key, model in self.registry["models"].items():
            if not key.startswith("5:") or model.get("attach") != "skinned":
                continue
            yield key, CLIENT / str(model["scene"]).removeprefix("res://")
            for variant in (model.get("variants") or {}).values():
                yield key, CLIENT / str(variant["scene"]).removeprefix("res://")

    def test_every_torso_shell_is_closed_and_encloses_volume(self) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover - numpy is a build requirement
            self.skipTest("numpy is required to read garment geometry")
        fit = _fit()
        seen = 0
        for key, path in sorted(set(self._scenes()), key=lambda pair: pair[1]):
            with self.subTest(scene=path.name):
                self.assertTrue(path.is_file(), f"{path} missing")
                primitives, _rig, _names = fit.load(str(path))
                shells = [shell for primitive in primitives
                          for shell in fit.components(primitive.points,
                                                      primitive.triangles)]
                self.assertTrue(shells, f"{path.name} has no geometry")
                closed = [shell for shell in shells if shell.closed]
                self.assertTrue(
                    closed,
                    f"{path.name} ({key}) encloses nothing: none of its "
                    f"{len(shells)} shells is closed, so no body vertex can "
                    f"ever be inside it")
                for shell in closed:
                    self.assertGreater(
                        shell.volume, 0.0,
                        f"{path.name} has a closed shell wound inside out; the "
                        f"renderer culls the near wall and it goes transparent")
            seen += 1
        self.assertGreater(seen, 60, "no torso shells were checked")


class TorsoCoverageTest(unittest.TestCase):
    """No skin shows through a torso garment, at the shoulder least of all."""

    #: Body vertices a garment may leave showing over the region it covers.
    #: The full sweep - eighty meshes, sixteen races, seven clips, with trousers
    #: and without - reports 66 in total and a worst case of 3 on any one mesh,
    #: against 47,855 of 125,736 for the shells this replaces.
    MAX_EXPOSED = 4
    #: The shoulder gets its own budget.  This is the defect the work exists to
    #: close and it must not be able to hide inside a whole-body total.  Sixty
    #: five of the eighty meshes measure exactly zero and none reads more than
    #: 3, against 14,039 of 35,496 before.
    MAX_SHOULDER = 3

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("numpy is required to read garment geometry")
        cls.fit = _fit()
        cls.registry = json.loads(EQUIPMENT.read_text())
        cls.races = sorted(path.stem for path in RACES.glob("*.glb"))
        cls.library = (CLIENT / "assets/actors/native/shared"
                       / "Universal_Animation_Library.glb")

    def _measure(self, key: str, dressed: bool):
        fit = self.fit
        for race in self.races:
            scene, author = fit.resolve(self.registry, key, race)
            garment = CLIENT / scene.removeprefix("res://")
            also = fit.layers(CLIENT, self.registry,
                              TROUSERS if dressed else (), race)
            for clip, time in fit.POSE_CLIPS:
                yield fit.measure(garment, RACES / f"{race}.glb", self.registry,
                                  author_rig=author, clip=clip,
                                  library=self.library, time=time, also=also)

    def _assert_covered(self, key: str, kind: str, dressed: bool) -> None:
        worst_body = worst_shoulder = None
        for result in self._measure(key, dressed):
            if worst_body is None or result.exposed > worst_body.exposed:
                worst_body = result
            if (worst_shoulder is None
                    or result.shoulder_exposed > worst_shoulder.shoulder_exposed):
                worst_shoulder = result
            self.assertGreater(
                result.checked, 100,
                f"{key} claims only {result.checked} vertices on {result.rig}; "
                f"a garment that shrank away from the body would pass a "
                f"coverage check by covering nothing")
        with_legs = "with trousers" if dressed else "on bare legs"
        # The shoulder first, and on its own: this is the reported defect.
        self.assertLessEqual(
            worst_shoulder.shoulder_exposed, self.MAX_SHOULDER,
            f"{key} ({kind}, {with_legs}) leaves "
            f"{worst_shoulder.shoulder_exposed} shoulder vertices showing on "
            f"{worst_shoulder.rig} at {worst_shoulder.clip}")
        self.assertLessEqual(
            worst_body.exposed, self.MAX_EXPOSED,
            f"{key} ({kind}, {with_legs}) leaves {worst_body.exposed} of "
            f"{worst_body.checked} body vertices showing on {worst_body.rig} "
            f"at {worst_body.clip}")

    def test_torso_garments_cover_the_body_over_trousers(self) -> None:
        for key, kind in SAMPLE.items():
            with self.subTest(visual=key, kind=kind):
                self._assert_covered(key, kind, dressed=True)

    def test_torso_garments_cover_the_body_on_bare_legs(self) -> None:
        # The waist seam has to hold without the trousers as well: a hem long
        # enough only because something else is over it is not a hem.
        for key, kind in SAMPLE.items():
            with self.subTest(visual=key, kind=kind):
                self._assert_covered(key, kind, dressed=False)


class TorsoWaistDatumTest(unittest.TestCase):
    """The hem sits far enough inside the trousers, and owns no belt.

    The waist is shared with the leg-garment pipeline and is the one number the
    two sides have to agree on.  Expressed in world Y on the reference rig,
    because the torso pipeline works in absolute Y and the leg pipeline in bone
    fractions, and absolute Y is the language both can read.
    """

    #: World Y on luminous_male, and the numbers the *leg* pipeline works to.
    #: Taken from eloria-assets/tools/legwear_geometry.py rather than restated,
    #: so the two sides cannot drift apart silently: WAIST_TOP is the top of the
    #: trouser hip shell, BELT_Y the middle of the trouser belt, and the three
    #: standoffs are how far each layer is lofted off the body.
    HIGHEST_HEM = 1.0300
    #: Least of the hem that has to finish inside the trousers, in metres.
    MIN_TUCK = .045

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("numpy is required to read garment geometry")
        cls.fit = _fit()
        cls.registry = json.loads(EQUIPMENT.read_text())
        cls.races = sorted(path.stem for path in RACES.glob("*.glb"))

    #: What the leg pipeline works to, for a tree where it has not landed yet.
    #: These are the values in eloria-assets/tools/legwear_geometry.py; the test
    #: reads that module when it is present so the two cannot drift, and falls
    #: back to this copy so a torso-only checkout still checks the datum.
    FALLBACK = {"WAIST_TOP": 1.088, "BELT_Y": 1.048, "SHELL_STANDOFF": .032}

    @classmethod
    def _legwear(cls):
        sys.path.insert(0, str(TOOLS))
        try:
            import legwear_geometry
        except ImportError:
            from types import SimpleNamespace
            return SimpleNamespace(**cls.FALLBACK)
        return legwear_geometry

    def test_the_hem_finishes_inside_the_trousers(self) -> None:
        sys.path.insert(0, str(TOOLS))
        import equipment_authoring as authoring
        legs = self._legwear()
        for name, hem in (("shirt/cuirass", authoring.TORSO_HEM),
                          ("coat/robe", authoring.SKIRTED_HEM)):
            self.assertLessEqual(
                hem, self.HIGHEST_HEM,
                f"{name} hem at {hem} is above the datum both pipelines work to")
            self.assertGreaterEqual(
                legs.WAIST_TOP - hem, self.MIN_TUCK,
                f"{name} hem at {hem} leaves only "
                f"{(legs.WAIST_TOP - hem) * 1000:.0f} mm inside a trouser waist "
                f"that tops out at {legs.WAIST_TOP}")

    #: Heights the torso hem is genuinely *inside* the trousers, in world Y.
    #: Above this the shirt blouses over the waistband, which is what a tucked
    #: shirt does and not a defect.
    TUCK_ZONE = (1.024, 1.062)
    #: Garments to check the seam on: one of each construction.
    SEAM_SAMPLE = ("5:168", "5:128", "5:120", "5:0")

    def test_the_torso_layer_is_inside_the_trouser_layer(self) -> None:
        """Long enough is not sufficient: it has to be *under*, too.

        A hem that reaches inside the waistband but is cut wider than it pushes
        straight back out through it, and on screen that is indistinguishable
        from a gap.

        This used to compare two declared constants - the torso construction's
        ``thickness`` against the leg pipeline's ``SHELL_STANDOFF`` - and passed
        while the meshes failed by 30 mm.  Both pipelines size their rings from
        a slab that reaches the hips, so at the narrow waist both are hip-sized
        and the gap between them is nothing like the gap between the two
        numbers.  It now measures the built garments against the built trousers,
        per race, which is the only comparison that can see the defect.
        """
        import numpy as np
        fit = self.fit
        sides = 36

        def shells(key: str, race: str):
            """The garment's closed components, skinned onto this wearer."""
            scene, author = fit.resolve(self.registry, key, race)
            pieces, rig, _ = fit.load(str(CLIENT / scene.removeprefix("res://")))
            _body, wearer, _names = fit.load(str(RACES / f"{race}.glb"))
            binds = fit.bone_binds(rig, wearer,
                                   fit.girth_ratios(self.registry, author, race))
            matrices = {b: wearer.rest[b] @ binds[b] for b in binds if b in wearer.rest}
            out = []
            for piece in pieces:
                if piece.joints is None:
                    continue
                moved = fit.skin(piece.points, piece.joints, piece.weights,
                                 rig.names, matrices)
                out.extend(fit.components(moved, piece.triangles))
            return out

        def tucking(parts):
            """The one component that tucks in, chosen once for the garment.

            A coat's skirt and a cuirass's fauld are in here too, and both hang
            *outside* the trousers on purpose - a fauld is hip armour, it is
            meant to be seen.  The one that tucks is the body shell, and what
            separates them is that the shell carries on up to the collar while a
            skirt stops at the waist.

            Chosen once rather than per height: the shell's rings are 26 mm
            apart, so at some heights it has no vertices within a sampling
            window at all and a per-height choice silently picked the fauld -
            then reported the fauld's 21 mm as the shell's.
            """
            reaching = [s for s in parts
                        if s.points[:, 1].min() <= high
                        and s.points[:, 1].max() > 1.25]
            if not reaching:
                return None
            return max(reaching, key=lambda s: s.points[:, 1].max()).points

        def ring(points, height: float, window: float = .016):
            # Wide enough to catch a ring of the body shell, whose rows are
            # 26 mm apart; both layers are sampled the same way.
            here = points[np.abs(points[:, 1] - height) < window]
            if len(here) < sides // 3:
                return None
            angle = np.arctan2(here[:, 2], here[:, 0]) % (2 * np.pi)
            radius = np.hypot(here[:, 0], here[:, 2])
            slot = np.minimum((angle / (2 * np.pi) * sides).astype(int), sides - 1)
            out = np.full(sides, np.nan)
            for index in range(sides):
                found = radius[slot == index]
                if len(found):
                    out[index] = found.max()
            return out

        low, high = self.TUCK_ZONE
        heights = [low + (high - low) * step / 4 for step in range(5)]
        checked = 0
        for race in self.races:
            trouser_parts = shells("4:0", race)
            for key in self.SEAM_SAMPLE:
                torso = tucking(shells(key, race))
                if torso is None:
                    continue
                for height in heights:
                    # Against the *outermost* trouser surface, because the
                    # question is what a player can see.  The trousers are three
                    # layers here - hip shell at .032, waistband at .034, belt
                    # at .038 - and a hem that sits between two of them is
                    # covered by the outer one and invisible.  Measuring against
                    # the innermost instead failed a shirt by 3 mm for being
                    # under the waistband rather than under the shell.
                    trousers = [ring(s.points, height) for s in trouser_parts]
                    trousers = [r for r in trousers if r is not None]
                    if not trousers:
                        continue
                    outer = np.nanmax(np.vstack(trousers), axis=0)
                    inner = ring(torso, height)
                    if inner is None:
                        continue
                    proud = float(np.nanmax(inner - outer))
                    checked += 1
                    self.assertLess(
                        proud, .002,
                        f"{key} on {race} stands {proud * 1000:.1f} mm outside "
                        f"the trousers at y {height:.3f}; the torso garment is "
                        f"the inner layer through {low}-{high}")
        self.assertGreater(checked, 100, "the waist seam was barely sampled")

    def test_the_trousers_own_the_belt(self) -> None:
        """Two belts 52 mm apart on one waist is what players saw before.

        The torso garment no longer draws one by default.  Where a concept sheet
        draws a belt that is part of the garment, it has to sit clear of the
        band the trouser belt already occupies, high enough on the ribs to read
        as part of the garment rather than as a second waist.
        """
        sys.path.insert(0, str(TOOLS))
        import torso_designs
        legs = self._legwear()
        low, high = legs.BELT_Y - .026, legs.BELT_Y + .026
        belted = 0
        for slug, _label, _kind, _finish, _base, _accent, style in torso_designs.DESIGNS:
            if style.belt is None:
                continue
            belted += 1
            self.assertGreater(
                style.belt, high,
                f"{slug} puts a belt at {style.belt}, at or below the "
                f"{low:.3f}-{high:.3f} band the trouser belt occupies")
        self.assertLess(
            belted, len(torso_designs.DESIGNS) / 2,
            "most designs should carry no belt at all; the trousers own the waist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
