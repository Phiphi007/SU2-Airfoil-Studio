# Third-party components and editable sources

This portable package includes original third-party binaries and their notices.
Keep `licenses/` and `sources/` with redistributions. The application source and
build recipe are included in `sources/AutoFoil-application-source.zip`.

- SU2 **8.5.0**, official Windows x64 OpenMP build (unmodified). Its versioned
  LGPL-2.1 license and embedded third-party notices are in `licenses/SU2-LICENSE.md`.
  Corresponding upstream source is in `sources/SU2-v8.5.0-source.zip`.
  Binary: https://github.com/su2code/SU2/releases/tag/v8.5.0
  Source: https://github.com/su2code/SU2/tree/v8.5.0
- Gmsh **4.15.2**, original Python API and Windows library. License and exceptions
  are in `licenses/Gmsh-LICENSE.txt`; upstream source is in
  `sources/gmsh-4.15.2-source.tgz`. https://gmsh.info/
- CPython 3.12, Tcl/Tk, NumPy, pandas, Matplotlib, Pillow and their runtime
  dependencies: notices available in `licenses/` and bundled metadata.
  Exact installed build versions are recorded in `BUILD_MANIFEST.json`.
- PyInstaller bootloader: its distribution exception and other notices are
  copied to `licenses/python_packages/pyinstaller/`.
- Noto Sans CJK SC Regular/Bold: SIL Open Font License 1.1 in
  `licenses/Noto-OFL.txt` and `_internal/assets/fonts/OFL.txt`.

No Microsoft MPI runtime is bundled or required by this OpenMP solver build.
The code is unsigned. No third-party license is replaced by this notice.
Before a public redistribution, retain all applicable source, license, copyright
and attribution files and review the combined distribution's licensing.
