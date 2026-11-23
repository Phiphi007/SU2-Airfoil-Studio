# flow5 interface reference decisions

Reviewed against [flow5 MainFrame](https://github.com/techwinder/flow5/blob/main/flow5-app/globals/mainframe.cpp), [XDirect airfoil workspace](https://github.com/techwinder/flow5/blob/main/flow5-app/modules/xdirect/xdirect.cpp), and the [flow5 repository structure](https://github.com/techwinder/flow5). This is a design review, not permission to copy GPL source or icons. Revisit each decision when the feature parity ledger changes.

| flow5 facility | Decision for this 2D SU2 studio | Implementation / acceptance |
| --- | --- | --- |
| Separate app, I/O, numerical libraries | Adopt | `studio-app`, `studio-io`, `studio-lib`; migrate algorithms without changing validated results |
| File actions and recent projects | Adopt | DAT import/export exists; project persistence, recent files, mesh/VTU open still required |
| Module switching for foil, plane, sail | Adapt | Switch among original airfoil, mesh, solver, results, and adjoint work pages; plane/sail modules are outside this application's scope |
| Preferences dialog under Options | Adopt | Options → Preferences now stores language, appearance, SU2 and Gmsh paths; expand into grouped pages as options grow |
| Restore toolbars and reset settings | Adopt when layouts become configurable | Test saved dock layout restoration and reset independently |
| OpenGL settings and diagnostics | Defer unless a hardware renderer is adopted | Native mesh and field views currently use QPainter. OpenGL options would have no effect. Revisit only if VTK/OpenGL becomes necessary; validate software-rendered Linux and native Windows first |
| Graph settings, legends and image export | Adopt with solver/result plots | Convergence and field visualizations need real plots before graph controls are meaningful |
| Log window and trace file | Adopt | Output dock exists; add per-run persistent log and open-log action |
| Online documentation, About, About Qt | Adopt selectively | About and About Qt exist; local workflow documentation and help links still needed |
| Built-in scripting/API | Adapt | Local stdio MCP adapter exists for mesh/solve/report; geometry and adjoint tool endpoints still needed |
| 3D plane/sail editor, stability controls | Exclude | The original product is a 2D airfoil and SU2 case workbench; no matching baseline workflow |

## XDirect airfoil workspace review

XDirect is the closest flow5 reference. Its source names separate foil editing dialogs (coordinates, camber, normalization, repaneling, scaling, flap, trailing-edge gap, interpolation), a foil explorer, polar definitions, operating-point graphs, and analysis controls. Those are interaction references. SU2 remains this project's solver; XFoil calculations and polar file formats are not silently substituted.

| XDirect capability | Decision | SU2 Studio work item and test |
| --- | --- | --- |
| Foil explorer with multiple named airfoils | Adopt | Case tree supports multiple DAT and generated variants, active selection, rename and remove; project round-trip test |
| Coordinate table and shape inspection | Adopt | Editable coordinates and validated DAT export; fixture round-trip test |
| Camber/thickness, normalization, repaneling, scale, flap, trailing-edge controls | Evaluate individually with existing BCE/D-BCE geometry model | Add a control only when it preserves geometry constraints and has a numerical baseline test; log accepted transformations in project history |
| Interpolate foils | Adopt as a geometry operation after M2 model exists | Blend two compatible profiles and validate upper/lower surfaces |
| Polar definition and operating points | Adapt to SU2 cases | Parameter sweep by Mach/Re/AoA; store each SU2 case and plot CL/CD/CM vs AoA with provenance |
| XFoil solve controls | Exclude solver implementation | Use SU2 CFD and adjoint processes; preserve run controls and convergence feedback concepts |
| Graph settings, legends, export | Adopt | Result and polar plots need axis selection, readable legend and image/CSV export |
| Context menus near foil and case objects | Adopt | Actions target the selected object and reflect state; keyboard/menu equivalents |

The [feature parity ledger](FEATURE_PARITY.md) is the release gate. A reference item marked “adopt” is complete only after its functional test passes.
