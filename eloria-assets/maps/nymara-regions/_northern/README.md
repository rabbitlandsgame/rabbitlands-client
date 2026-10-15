# Northern continent landscape finish

The Whitehorn, Mirrorhold and Amethyst source builders call this regional
finish after the shared continent border pass. Install its build dependencies
with `python -m pip install -r eloria-assets/maps/nymara-regions/_northern/requirements.txt`.
SciPy supplies the HiGHS linear solver used to bound the gradients of the
actual road triangles. Shapely 2.1.2 and its bundled GEOS provide robust
polygon unions and constrained triangulation for continent bridge decks.
These are offline build dependencies only.

The deterministic finish preserves the native structural footings and common
border contours. It replaces disconnected road quads with a continuous bed,
solves the interior face gradients, seats terrain from that exact bed, and
adds the visible grotto arch and grounded abutments. A small bend away from the footing
keeps Mirrorhold's road clear of the existing Orrery slab. Paint follows the
refined final terrain. Native walk meshes are not modified.
