# Maintainer and Codex handoff

Last updated: 2026-11-24 (Asia/Shanghai). Branch: local working tree; **do not submit a PR until Linux work and later Windows adaptation have been reviewed by the user**.

## What changed in this working tree

- The mesh and Mach result tabs now use native interactive Qt widgets fed by actual mesh/VTU-derived binary data. They fit window size, support wheel zoom and drag pan, and clip the visible field. Completed API cases reopen in the C++ desktop.
- Added analytic four-digit NACA selection to the C++ File menu, including cambered presets by designation. The backend already supported `builtin://nacaNNNN`; the C++ preview now calculates the same family. Case requests are persisted in `case_request.json` so the desktop can restore the airfoil and operating conditions.
- Rewrote the default English README with real desktop screenshots and linked Simplified and Traditional Chinese versions. The screenshot explicitly identifies the unmet CFD residual target. `docs/END_TO_END_VALIDATION.md` records multi-airfoil scenarios and remaining acceptance work.

- Created a three-target C++17/Qt Widgets build: `studio-app`, `studio-lib`, and `studio-io`.
- Added a restrained engineering workspace with DAT preview, meshing, CFD launch, project tree, properties, and output log.
- Added a default light palette, persistent dark option in an Options → Preferences dialog, and DAT export. Language and solver paths also live in Preferences; the toolbar language selector was removed. `docs/FEATURE_PARITY.md` tracks the original five-page UI and each missing acceptance test.
- The Output dock uses bundled JetBrains Mono 2.304 loaded through Qt resources; its OFL notice is included in Linux and Windows packages.
- Added `agent_toolkit/mcp_server.py` and a project skill for the existing mesh/solve/report backend. `docs/FLOW5_REFERENCE_CHECKLIST.md` records flow5 panel and menu decisions, including OpenGL deferral until native VTK rendering is available.
- Corrected the release contract: AppImage and Windows staging now require all four SU2 direct/adjoint/deformation binaries. The `studio-su2` CMake target and `scripts/build_su2.py` build them. The private Python runtime pins Gmsh 4.15.0 to the checked-out source tag. SU2 native Meson build completed with reverse autodiff enabled and MPI disabled under `build/su2-native`.
- Added Qt Linguist Simplified Chinese catalog; C++ source strings are English.
- Added user settings for SU2 executable and Gmsh Python bindings path. `SU2_STUDIO_PYTHON` selects the backend interpreter; `SU2_STUDIO_ROOT` selects the source checkout. The existing SU2 override environment variable remains supported.
- Added official source submodules: SU2 `v8.5.0` at `12eb826f049ef7f67df974dfcb44cf36ee07c0f8` and Gmsh `gmsh_4_15_0` at `1ea7346b3f749cc20726b31eeeba11323b9f7898`.
- Added Linux/Windows CMake CI workflow. The C++ GUI now requires Qt 6.8+.
- Added a build-time private Python venv and PyInstaller backend bundle. Linux AppImage packaging is implemented; Windows self-contained folder staging is scripted but not yet tested on Windows.

## Verified locally

- Current Qt 6.9.2 C++ build and `ctest --test-dir build/qt6-local --output-on-failure` pass (3 tests). The native field-view test checks actual image changes after wheel zoom and mouse drag and verifies resize behavior. The GUI integration test selects analytic NACA4412, generates a mesh, runs a 30-iteration Euler case, and checks native view files, history, and saved solver parameters. Python API/driver tests: 16 passed, 20 subtests passed. All 97 Qt Simplified Chinese strings are translated.
- The AppImage was rebuilt after the native viewer, history chart, optimizer endpoint, and GUI workflow changes. `dist/SU2-Airfoil-Studio-x86_64.AppImage` opens a case offscreen and saves a 1440×900 screenshot. SHA-256: `4e4a04322ccd4b0ff1148dc6649eada8a93ab26323c74f7dac9863f40a97a094`. The bundled frozen backend reports Gmsh 4.15.0 and supports mesh, solve, report, and optimize modes. Earlier bundled smoke tests resolved all four SU2 executables and generated analytic NACA4412 mesh artifacts.
- Analytic NACA2412 completed a 120-iteration Euler solve and generated VTU/native view data; residual and force results are **not validated**. Analytic NACA4412 passed mesh generation and Qt case reopen with restored case settings. See [the end-to-end record](END_TO_END_VALIDATION.md).

- `cmake -S . -B build/qt6 -DCMAKE_PREFIX_PATH=build/qt-sdk/6.8.3/gcc_64` and `cmake --build build/qt6 -j2`: pass with the user-installed Qt 6.9.2 SDK at `/home/laneing/Qt/6.9.2/gcc_64` and GCC 11.4. A separately downloaded Qt 6.8.3 SDK under ignored `build/` was used earlier but is not required.
- Qt 6 executable launches offscreen. An earlier AppImage launch check used `APPIMAGE_EXTRACT_AND_RUN=1`; FUSE mounting is unavailable in this sandbox. The current AppImage additionally completed a case-open screenshot run.
- Frozen backend `info` passes, and its `mesh` mode generated `mesh.su2` with 17,658 quadrilaterals for NACA0012 at 100 surface points and 0.1 global refinement. A source-backend probe verified `SU2_STUDIO_GMSH_PYTHON_PATH` overrides the module location.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg ... python -m pytest tests/test_qt_frontend.py -q`: 6 passed in the private environment.
- After the Preferences and DAT export edits: C++ build passed; offscreen app remained alive for 3 seconds; focused portable API, parameterization, optimizer, and Qt tests passed (22 tests, 20 subtests); MCP initialize/tools/list/studio_info requests returned JSON-RPC responses; portable API unittest suite passed (8 tests).
- Frozen backend rebuilt with Gmsh 4.15.0 and completed a NACA0012 mesh smoke run: 17,658 quadrilateral elements, minimum angle 52.03°, minimum scaled Jacobian 0.7867. Sixteen portable API, bridge and SU2 driver unit tests passed after solver discovery changes.
- All four SU2 executables compiled locally. The frozen backend completed a 20-iteration Euler CFD smoke case in `build/cfd-smoke-native`, producing 12 output files including `history.csv`. This is an integration test only: `residual_target_met` is false, and no adjoint or optimization case has been validated yet.
- The C++ Run menu now sends pause, resume, immediate stop, and stop-after-save commands through the backend's solver-control file. These controls compile but still need a live GUI integration test against a long-running case.
- The rebuilt AppDir contains all four SU2 binaries, and the frozen backend `info` resolves their paths plus Gmsh 4.15.0 without environment overrides. Focused Python tests after the C++ request fix: 15 passed, 20 subtests passed. The C++ executable rebuilt successfully.
- `python3 portable_api.py info`: works; reports no SU2 executable until one is built or configured.
- The first system-Python test run had 98 tests and 23 errors from incompatible NumPy/Matplotlib packages. The private environment ran 105 tests with 21 errors from Tk requiring a display plus one missing pytest import. Pytest is now installed in the local private build runtime; the focused Qt suite passes. Full legacy GUI tests still need a working Xvfb display or a real desktop test session.

## Known gaps

- The native contour uses per-cell colors and currently exposes Mach only. Scalar choice, limits, smooth interpolation, axes and quantitative probe tools remain open. This is a live Qt widget, not a static image.
- `airfoils/NACA2412.dat` fails wall-continuity validation. Analytic `builtin://naca2412` generates and solves, but its 120-iteration force coefficients are anomalous and residual target is unmet. Do not use those values for design; see `docs/END_TO_END_VALIDATION.md`.
- A step-by-step English PDF user guide with LaTeX theory and Times New Roman, plus multiple validated aircraft-design use cases, is required after full feature verification. It has not yet been written because the workflows are not all validated.

- The C++ desktop is an initial migration slice, not feature equivalent to the PySide6 desktop. The source tree and AppImage are prepared for Linux review; Windows adaptation remains deferred until the user switches to Windows. It lacks interactive BCE, a dedicated optimization monitor, arbitrary VTK scalar selection, and full solver monitoring. Completed CFD cases do have native VTU Mach contours and convergence charts.
- The current theme, DAT export, native viewers, history chart, analytic NACA entry, solver selection, and optimization action are in the rebuilt AppImage. The full original menu and five work pages are not yet migrated.
- The pinned Gmsh 4.15.0 wheel is included in the frozen private backend. The SU2 source submodule is built by the `studio-su2` packaging dependency, with an upstream FSI include fix applied from `patches/su2/`.
- Source checkout fallback still uses a compile-time path, but the frozen backend in the AppImage runs from its own resources. Set `SU2_STUDIO_ROOT` when using the source backend from a relocated installation.
- The legacy Python GUI, comments, and older documentation still contain hardcoded Chinese. M4 tracks their conversion or retirement.
- Dynamic status and geometry messages should be audited in both languages as workflows migrate.
- A short CFD workflow now runs on this machine; converged CFD and adjoint optimization remain unverified. The bundled Gmsh Python package works for mesh generation.
- The AppImage embeds SU2 and Gmsh, but older distribution compatibility is not yet verified; CI should build on a defined baseline runner. Windows folder staging is planned and not tested. A fresh CMake `studio-backend-bundle` target run could not provision a second venv because the sandbox could not resolve PyPI; the existing validated `build/studio-app/runtime/python` venv successfully rebuilt the frozen backend manually.

## Next actions

1. Run a converged reference CFD case through the C++ GUI, compare output with existing fixtures, then validate an adjoint case.
2. Make the private runtime build reuse cached wheels or document a deterministic offline dependency source for restricted build hosts.
3. Make resource and translation loading relocatable, including Windows multi-config and macOS bundle layouts.
4. Complete M1 acceptance gates, then continue M2 through M4 in the plan.
5. Request user review. Create a PR only after explicit satisfaction/approval.
