# C++ migration plan

Status: **in progress**. This file is the durable plan for maintainers and future Codex sessions. Update it in the same change as each milestone. Do not describe the migration as complete until the acceptance gates below pass.

## Product goal

Make the C++/Qt desktop the primary, cross-platform interface for airfoil design, structured meshing, SU2 solving, optimization, and result inspection. Keep English as the source language. Add Simplified Chinese only through Qt Linguist (`tr()`, `.ts`, compiled `.qm`). Preserve numerical behavior against the current regression cases while moving Python algorithms behind a stable API or replacing them with tested C++ modules.

flow5 is a structural and interaction reference: separate application, numerical, and I/O libraries, with a dense engineering workspace. No flow5 source or icons are copied because flow5 is GPL-3.0 and this repository is MIT.

## Current state

- `studio-app/`: C++17 Qt Widgets shell; project, properties, output docks; DAT preview; mesh and CFD actions.
- The default palette is light, with a persistent dark option. DAT export is present. See `docs/FEATURE_PARITY.md` for the authoritative workflow inventory.
- `studio-lib/`: geometry preview and DAT coordinate parser.
- `studio-lib/` now also has native resizable mesh and Mach field widgets with wheel zoom and drag pan. Analytic four-digit NACA selection is available in the C++ File menu.
- `studio-io/`: versioned JSON request encoder.
- `portable_api.py`: Python numerical boundary; geometry, mesh, SU2, and reporting remain there.
- `third_party/su2` and `third_party/gmsh`: pinned upstream source submodules. Release packaging now requires four SU2 executables built from the pinned source and freezes a Gmsh 4.15.0 wheel matching the source tag.
- `qt_app/`: the existing feature-rich PySide6 interface, retained during migration. The C++ app has **not** reached feature parity.

## Milestones and acceptance gates

### M1 — Reproducible workspace and dependencies

1. CI must build the Qt 6.8+ C++ app on Linux and Windows; add macOS when a runner is available. Linux releases are AppImage files. Windows releases are self-contained directories with a double-clickable EXE, staged on Windows with `windeployqt`.
2. Document pinned upstream submodule revisions, licenses, source build commands, and supported tested binaries.
3. Resolve SU2 executable in this order: explicit user setting, project-local built executable, legacy bundled executable, `PATH`. Resolve Gmsh Python bindings through explicit user path or the active Python environment. Show the resolved paths and versions in a GUI diagnostics panel.
4. Add a noninteractive environment check that reports each dependency independently.
5. Ensure installed app can locate resources without a build-tree path and can start from arbitrary working directories. Freeze the Python backend for distribution and verify it does not use host Conda or system Python.

Gate: clean clone with `--recurse-submodules`, CMake build, launch, dependency diagnosis, and a small mesh run on Linux and Windows.

### M2 — C++ geometry and project model

1. Define airfoil, design parameters, case, mesh settings, solver settings, and result types in `studio-lib/`, independent of Qt Widgets.
2. Move DAT import/export and project persistence into `studio-io/` with versioned formats and validation.
3. Implement undoable control-point editing and geometry constraints in the C++ UI.
4. Build the five original work pages and their menu/toolbar entry points around real workflows, not placeholder panels.
5. Compare exported coordinates against existing NACA and BCE regression fixtures.

Gate: open/edit/save/reopen an airfoil with identical coordinates; no UI dependency in the geometry library.

### M3 — Mesh and solver workflow

1. Replace Python-specific process assumptions with a typed job controller that exposes progress, cancel, errors, and output paths.
2. Preserve the existing mesh and SU2 config results while moving modules to C++ incrementally.
3. Add mesh quality visualization, convergence plots, result files, and field inspection.
4. Keep one versioned backend protocol during coexistence, with compatibility tests on Linux and Windows.

Gate: mesh generation and a converged reference SU2 case produce comparable geometry, cells, config, and force history to the recorded baseline.

### M4 — Optimization, translation, and retirement

1. Bring CST/D-BCE/adjoint controls and monitoring to the C++ desktop.
2. Remove all hardcoded Chinese from shipped source UI and English documentation; translate through Qt `.ts` catalogs.
3. Retire `qt_app/` and the Tk entry point only after feature and regression parity is demonstrated.
4. Review dependency licensing and packaging separately for source submodules and redistributed binaries.

Gate: all supported workflows are reachable in C++; English and Simplified Chinese UI pass a translation audit; regression and packaging checks pass on both platforms.

### M5 — Validated design cases and user manual

1. Validate end-to-end desktop workflows with a symmetric reference and multiple cambered aircraft wing sections. Include geometry changes, mesh quality, converged direct CFD, adjoint optimization, exports, and reopening. Record inputs, versions, convergence, and mesh sensitivity. The live [validation ledger](END_TO_END_VALIDATION.md) distinguishes integration tests from valid aerodynamic results.
2. Build an English step-by-step PDF user guide after the functions pass. Use a simple paper layout with Times New Roman and LaTeX typesetting for NACA geometry, governing equations, nondimensional coefficients, mesh resolution, and discrete-adjoint theory. Include multiple real aircraft-design use cases, not only NACA 0012.
3. Maintain the default English README and its linked Simplified and Traditional Chinese reading versions. GUI translations remain Qt Linguist catalogs.

Gate: a new user can reproduce the documented cases in the release build and verify every reported result from packaged outputs.

## Rules for future changes

- Keep each PR within a milestone with measured regression evidence.
- Never replace a validated numerical routine solely to change implementation language.
- Treat the Python API as a compatibility boundary until its users are migrated.
- Add tests for calculations and protocol boundaries, not screenshots of UI structure.
- Update `docs/HANDOFF.md` with exact verification results and blockers before handing work to another agent.
