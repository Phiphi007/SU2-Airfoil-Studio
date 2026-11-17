# Architecture

## Processing pipeline

1. `airfoil_processor.py`, `geo_surgeon.py` and `cosine_resampler.py` read a
   Selig-order airfoil, resample both surfaces and rebuild a shared sharp
   trailing edge.
2. `yplus_calc.py` estimates the first wall-normal spacing from the target Y+.
3. `mesh_architect.py` constructs the conformal all-quadrilateral C-H topology;
   `mesh_worker.py` runs this work outside the GUI process.
4. `su2_driver.py` writes the case configuration and controls `SU2_CFD`, including
   pause, resume and termination.
5. `post_analyzer.py` and `field_visualizer.py` generate the four report panels and
   interactive field contours from SU2 output.

## Mesh invariants

- The volume mesh contains SU2 element type 9 quadrilaterals only.
- Imported finite-thickness or open trailing edges are fitted to one mathematical
  sharp point. Upper and lower logical trailing-edge ends remain distinct.
- The leading edge is continuous and is not split into separate upper/lower points.
- Wall, boundary-layer, farfield and wake density respond to global refinement;
  upper/lower trailing-edge sizes and wake refinement remain independently tunable.
- The first wall-normal height equals the value obtained from the Y+ estimate.
- Candidate grids with non-positive area are rejected. Export also requires a
  minimum angle of 30 degrees and a minimum scaled Jacobian of 0.40.
- SU2 boundary names are `airfoil`, `farfield_inlet` and `farfield_outlet`.

## Output policy

Every GUI calculation uses its own case directory under `output_results/`. Results,
meshes and solver restart files are generated data and are intentionally excluded
from version control. The program never smooths the saved SU2 numerical values;
smoothing is limited to display copies used by plots.
