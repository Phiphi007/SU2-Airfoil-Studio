# External source dependencies

These are Git submodules pinned to release tags:

- [SU2](https://github.com/su2code/SU2), `v8.5.0`, source in `third_party/su2/`.
- [Gmsh](https://gitlab.onelab.info/gmsh/gmsh), `gmsh_4_15_0`, source in `third_party/gmsh/`.

Clone with `git clone --recurse-submodules` or, after cloning, run `git submodule update --init --recursive`. The `studio-su2` CMake target builds the SU2 direct and adjoint executables from the pinned source. Gmsh's matching 4.15.0 Python wheel is installed into the private build runtime and frozen into the release backend; the Gmsh source submodule is retained for reproducibility and source review. The GUI accepts custom solver and Gmsh paths in Options → Preferences.

The AppImage packaging step now requires the four SU2 solver executables used for direct and discrete-adjoint workflows. The private Python backend pins the Gmsh wheel to 4.15.0, matching the source tag, and freezes its binding and library. The previous AppImage is stale until rebuilt with these solver binaries. Upstream licenses apply to each submodule and redistributed binary; package their notices with the final release.
