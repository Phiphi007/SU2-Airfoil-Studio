# Feature parity ledger

This is the acceptance checklist for replacing `qt_app/main_window.py` and `qt_app/airfoil_editor.py`. A menu entry or page title does not count as implementation. Each row requires a working C++ entry point and the indicated functional verification before the Python desktop can be retired.

| Original workflow | Current C++ state | Required acceptance test |
| --- | --- | --- |
| Open DAT, inspect coordinates | Working preview | Open a fixture, compare coordinate count and bounds |
| Edit BCE handles, constraints, undo/reset | Missing | Drag handles in each constraint mode; export and numerically compare coordinates with Python baseline |
| Export DAT | Implemented, pending round-trip test | Export, reopen, compare all coordinate pairs |
| Generate mesh and inspect mesh quality | C++ native mesh view works, with resize fit, wheel zoom and drag pan. Automated GUI test generates NACA4412 mesh; quality UI remains incomplete | Inspect cell counts, boundary markers, and quality in UI |
| Pause/resume, immediate stop, stop after save | Missing | Exercise all controls against a real SU2 solver process |
| CFD convergence and diagnostics | Native residual and CL/CD history plots work for completed cases. Automated GUI test runs a 30-step NACA4412 Euler case; live update, graph settings, and validated convergence missing | Run converged reference case; plot residual and force history; compare final metrics |
| Open SU2 mesh and VTU result | Completed API cases reopen in native C++ viewer; arbitrary mesh/VTU import, scalar selection and range controls missing | Open reference files and verify geometry, scalar selection, and range controls |
| Reports and result file browser | Case tree and summary are present; report and file actions missing | Load completed case, inspect reports and open output files |
| CST, D-BCE, hybrid, relay adjoint optimization | C++ Run menu and versioned backend endpoint exist; one CST low-iteration probe exercised AD, DOT, DEF, and direct solve and rejected a worse step. No converged study yet | Complete one reference optimization for each mode and compare objective/geometry history |
| English and Simplified Chinese | Partial Qt catalog | Every shipped C++ UI string translated via `tr()` and `.qm`; switch at runtime |
| Light and dark appearance | Preferences dialog, light default, persistent setting | Verify both palettes in every work page, restart persistence, contrast |
| User SU2/Gmsh paths | Settings fields present | Run mesh and CFD with explicit custom paths and path diagnostics |
| Agent control | MCP exposes info, schema, mesh, solve, report, and optimization requests; geometry editing and GUI control pending | MCP tool calls exercise geometry, mesh, solve, report, and optimization end to end |

The PySide6 application remains available while these rows are open. The current C++ application is not a feature-complete replacement.
