# Windows x64 rebuild

Build on Windows x64 using CPython 3.12 with Tcl/Tk. Target use requires no Python.
The editable application source is in `sources/AutoFoil-application-source.zip`.

1. Extract source, create `.venv`, install `requirements.txt` and
   `packaging/requirements-build.txt`.
2. Place these unchanged upstream archives in `build/portable/downloads/`:
   - https://github.com/su2code/SU2/releases/download/v8.5.0/SU2-v8.5.0-win64-omp.zip
   - https://github.com/su2code/SU2/archive/refs/tags/v8.5.0.zip
     (save as `SU2-v8.5.0-source.zip`)
   - https://gmsh.info/src/gmsh-4.15.2-source.tgz
   - https://raw.githubusercontent.com/tcltk/tcl/core-8-6-12/license.terms
     (save as `Tcl-8.6.12-license.terms`; use the matching notice if rebuilding with another Tcl version)
3. Run `python packaging/build_windows.py` from the source root.

Output: `portable_release/SU2_AutoFoil_Studio/` and its ZIP/SHA-256.
PyInstaller creates two entry points sharing `_internal`, rather than repeatedly
extracting the scientific stack to a temporary folder on every launch.
`AutoFoilStudio.exe` is windowed; `AutoFoilCLI.exe` is console/stdio capable and
also serves the private mesh worker command. `--mesh-worker` is internal, not API v1.

Build cache and downloads stay in `build/portable`; no existing CFD case is copied.
`--skip-freeze` only refreshes documentation/source/solver packaging and must not
be used after changing application code. Check `BUILD_MANIFEST.json` for versions
and SHA-256 checksums. This records the build, but byte-identical EXE reproducibility
across different toolchains is not promised.

Reference: https://pyinstaller.org/en/stable/runtime-information.html
and https://pyinstaller.org/en/stable/spec-files.html
