# Validation status

## Portable release — 2026-10-06

The full source suite passed 65 tests. The actual frozen desktop/CLI EXEs also
passed relocated-path tests with Python/SU2 removed from PATH, including a real
two-iteration solver workflow. See `packaging/VALIDATION.md` for the complete
checks and compatibility limits; no second physical computer has been tested.

## Previous source release

The packaged source was checked on Windows with Python 3.12 and SU2 8.5.

- The previous full-suite run passed 54 automated tests.
- The 2026-09-09 layout fix passed 17 targeted GUI tests, including three new
  layout regressions. These cover 1360x880, 1180x680 and 960x540 window sizes,
  English/Chinese switching, a 200% font-scale check at 960x600, fixed mesh
  actions, local wheel scrolling and keyboard focus revealing off-screen fields.
  This layout-only change did not rerun the full CFD/mesh suite.
- GUI construction and the built-in airfoil preview smoke test passed.
- A two-iteration GUI-to-SU2 workflow smoke test completed and produced live
  history plus all four aerodynamic report panels.
- Regression coverage includes sharp trailing-edge closure, all-quadrilateral
  topology, positive cell area, local leading/trailing-edge sizing, wake and
  global refinement, Y+ spacing, multiple NACA geometries, VTU parsing, contour
  display, bilingual switching and interrupted-result recovery.
- UI layout coverage verifies that the open-source font cannot clip the header
  subtitle, and contour coverage verifies symmetric quad display refinement
  without introducing new scalar extrema.

These checks verify software integration and mesh invariants. A short smoke run is
not a converged CFD result. Engineering use still requires residual and force
convergence checks, mesh independence, suitable farfield placement, Y+ assessment
and comparison with trusted experimental or numerical data.

## Leading-edge distribution — v2.6

The leading-edge regression checks at least 30 wall nodes per side inside the
first 5% chord, a maximum adjacent wall-spacing ratio of 1.10, and smooth
wall-normal direction changes. The default NACA0012 validation produced 37 nodes
per side, a 1.064 spacing ratio, 42.32 degree minimum cell angle, and 0.6688
minimum scaled Jacobian. A 150-step SU2 Euler smoke run completed and produced a
continuous pressure field; it is intentionally not treated as a converged
aerodynamic result.

## Coarse grids and domain scaling — v2.7

The global refinement range now extends down to 0.05. NACA0012 meshes at
0.05/0.10/0.25 contained 4,158/7,770/24,034 quadrilaterals and all retained
minimum angles above 43 degrees and minimum scaled Jacobians above 0.67. The
boundary-layer generator preserves the minimum radial count required to keep
the actual growth ratio at or below 2. Domain scales of 0.5 and 2.0 were also
generated successfully. Live count estimates were within 10% of generated
counts in the tested range (about 2% at the default setting).
