# Aircraft-design workflow validation

Last run: 2026-11-24, Linux, Qt 6.9.2. This record separates software integration from aerodynamic validation. The cases below are local ignored build outputs and can be regenerated from the shown JSON requests. Do not use their coefficients for aircraft sizing.

## Scenario A: symmetric reference airfoil

Use NACA 0012 as a solver and visualization control at Mach 0.15 and 2° angle of attack. A 300-iteration Euler run completed and produced `mesh.su2`, `flow.vtu`, `history.csv`, `mesh_view.bin`, and `flow_view.bin`. The Qt 6 desktop reopened the case and drew the mesh and Mach contour in resizable widgets. The output dock displayed 300 iterations, CL 0.2287, CD 0.0594, and density residual log10 −2.684. The configured residual target was not met. The [flow screenshot](screenshots/flow-contour-linux.png) and [mesh screenshot](screenshots/mesh-linux.png) are from the actual desktop.

## Scenario B: cambered preliminary wing section

Choose analytic `builtin://naca2412`, Mach 0.22, 3° incidence, Euler solver, 100 surface points, and mesh refinement 0.1. The 120-iteration API request in `build/naca2412-request.json` produced a structured mesh, SU2 history, VTU data and both native view files. `ok=true`, but density residual log10 was −1.873, CL −0.2492, and CD −0.0892. A 600-iteration repeat in `build/naca2412-600-request.json` ended at residual −2.667, CL 0.2421, and CD 0.0216. The coefficient sign change shows that the 120-step force values were transient. Neither run met the residual target, so this case is **unsuitable for a design decision**. Continue convergence and mesh sensitivity checks before interpreting the forces.

The previously committed `airfoils/NACA2412.dat` failed the continuous-wall mesh geometry check, with source-point deviation 0.001528c and curve deviation 0.001568c. The failure is reproducible in `build/naca2412-design-case/api_result.json`. The analytic NACA four-digit option avoids that legacy coordinate file but does not validate its aerodynamic output.

## Scenario C: higher-camber low-speed candidate

Choose `builtin://naca4412`, Mach 0.12, 5° incidence, 100 surface points, and mesh refinement 0.15. `build/naca4412-request.json` generated `mesh.su2`, `mesh_view.bin`, and `case_request.json`; the Qt desktop reopened the result and restored NACA4412 and its operating conditions in the Properties panel. A separate automated desktop workflow selected NACA4412 through its menu, generated a mesh, selected Euler with 30 iterations, ran SU2, and verified the saved request, solver result, native mesh/flow views, history file, and enabled visualization tabs. This is an interface and integration check only: 30 iterations cannot establish convergence. A validated CFD comparison and optimization for this candidate remain open.

## Discrete-adjoint integration probe

`build/naca2412-adjoint-probe.json` reused the nonconverged 600-iteration NACA2412 state solely to exercise a one-attempt CST pipeline with shortened inner iteration limits. SU2_CFD_AD, SU2_DOT_AD, SU2_DEF, and SU2_CFD all ran. The trial raised CD from 0.02164 to 0.04784 and was correctly rejected; accepted steps were zero. This probe does not validate design optimization because its baseline and trial were unconverged. The public API and GUI require a direct case with `residual_target_met=true` before starting optimization. The [convergence screenshot](screenshots/naca2412-convergence-linux.png) shows why the 600-step baseline is not accepted.

## Acceptance still open

- The desktop needs interactive BCE constraints, undo, project persistence, result scalar selection, range and graph controls, file/report actions, and adjoint optimization parity.
- Run a converged direct case with mesh refinement study, then complete discrete-adjoint and geometry optimization tests on at least two cambered airfoils.
- Extend the real GUI workflow check to pause/resume and stop-after-save against live SU2, and verify exported geometry and results by reopening them.
- Build and test the Windows folder on Windows. No PR is to be submitted before user review and Windows adaptation.
- Write the English step-by-step PDF user guide with LaTeX theory, Times New Roman typography, and multiple validated aircraft-design use cases **after** these acceptance steps pass. Do not present an unvalidated scenario as a design recipe.
