# SU2 Airfoil Studio

[简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

SU2 Airfoil Studio is a desktop workspace for two-dimensional airfoil studies. Its new desktop uses C++17 and Qt 6 Widgets. A private frozen Python backend runs Gmsh and locally built SU2 executables. English is the source language; Simplified Chinese GUI text uses Qt Linguist.

![Qt 6 desktop with an interactive Mach contour from a local SU2 run](docs/screenshots/flow-contour-linux.png)

The contour is drawn by a Qt widget from mesh and VTU data, not embedded as a plot image. The [mesh view](docs/screenshots/mesh-linux.png) and contour adapt to the window size. Use the wheel to zoom and drag with the left or middle button to pan. This NACA 0012 Euler integration case ran 300 iterations at Mach 0.15 and 2° angle of attack. Its density residual target was **not met**; the image demonstrates the workflow and viewer, not validated aerodynamic accuracy.

## Current scope

The C++ desktop can open and export DAT airfoils, generate analytic four-digit NACA sections, generate a structured Gmsh mesh, run SU2 CFD, reopen cases, inspect native mesh, Mach, and [convergence views](docs/screenshots/naca2412-convergence-linux.png), and send pause, resume, immediate stop, and stop-after-save commands. A discrete-adjoint optimization entry accepts converged CFD cases and offers CST, BCE, hybrid, and relay parameterizations. Preferences contain language, light or dark theme, and custom SU2 and Gmsh paths. Light is the default. The Output panel bundles JetBrains Mono.

Interactive BCE editing and richer optimization and result controls in the original Python desktop are still being migrated. One low-iteration CST adjoint integration probe completed, but no converged optimization study has been validated. The [feature parity checklist](docs/FEATURE_PARITY.md) tracks acceptance. The C++ desktop is not yet a complete replacement.

## Build on Linux

Use an installed Qt 6 SDK with Widgets and LinguistTools, CMake 3.16+, a C++17 compiler, and Python for the build process. Qt Online Installer is unnecessary when a compatible Qt 6 SDK is already installed.

```sh
git submodule update --init --recursive
cmake -S . -B build/qt6 -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/path/to/Qt/6.9.2/gcc_64 \
  -DSTUDIO_BOOTSTRAP_PYTHON=/path/to/python
cmake --build build/qt6 --parallel
cmake --build build/qt6 --target studio-backend-bundle
cmake --build build/qt6 --target studio-su2
```

The backend target creates a build-local virtual environment and freezes the numerical code. End users do not need system Python or Conda. Developer overrides are `SU2_STUDIO_PYTHON` and `SU2_STUDIO_ROOT`. Gmsh and SU2 source checkouts live in `third_party/`; external installations can be selected in Preferences.

Linux AppImage packaging options are in the [handoff](docs/HANDOFF.md); the output is `dist/SU2-Airfoil-Studio-x86_64.AppImage`. The planned Windows release is a folder compiled on Windows with a double-clickable EXE and private dependencies. Windows validation has not started.

## Automation and project structure

The versioned JSON backend is `portable_api.py`. It sends one response to stdout and progress to stderr. Query `info` and `schema`, then run each mesh or solve request in a new output directory. An [MCP adapter](agent_toolkit/mcp_server.py) and [agent workflow](agent_toolkit/skills/su2-airfoil-studio/SKILL.md) expose mesh, solve, report, and optimization requests. Solver exit alone does not establish convergence; inspect residuals, forces, near-wall resolution, and mesh independence before design decisions.

| Directory | Purpose |
| --- | --- |
| `studio-app/` | Qt desktop, actions, docks, preferences, process control |
| `studio-lib/` | Native airfoil, mesh, and field viewers |
| `studio-io/` | Backend request encoding |
| `core_modules/`, `parametric_adjoint/` | Geometry, mesh, solver, and optimization backend |
| `translations/` | Qt Linguist catalogs |
| `agent_toolkit/` | MCP adapter and agent instructions |
| `third_party/` | Pinned Gmsh and SU2 submodules |

The architecture draws on [flow5](https://github.com/techwinder/flow5). flow5 is GPL-3.0, so its source and icons are not copied into this MIT-licensed repository. See the [refactor plan](docs/REFACTOR_PLAN.md), [flow5 decisions](docs/FLOW5_REFERENCE_CHECKLIST.md), and [maintainer handoff](docs/HANDOFF.md).
