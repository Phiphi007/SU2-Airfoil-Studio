"""Assemble the Linux desktop and frozen backend into an AppImage."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    parser.add_argument("--linuxdeploy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--qt-plugin", type=Path, required=True, help="Official linuxdeploy Qt plugin AppImage")
    parser.add_argument("--runtime-file", type=Path, help="AppImage type-2 runtime for offline builds")
    parser.add_argument("--qmake", type=Path, required=True, help="qmake from the same Qt SDK used for the C++ build")
    parser.add_argument("--offscreen-plugin", type=Path, help="Optional Qt offscreen platform plugin for headless smoke tests")
    parser.add_argument("--su2-bin", type=Path, required=True, help="SU2 build directory containing CFD, adjoint, DOT and deformation binaries")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("AppImage packaging is supported on Linux only")
    build = args.build_dir.resolve()
    executable = build / "studio-app/su2-airfoil-studio"
    backend = build / "studio-app/runtime/backend/studio-backend"
    translation = build / "studio-app/studio_zh_CN.qm"
    for required in (executable, backend / "studio-backend", translation):
        if not required.is_file():
            parser.error(f"Missing {required}; build studio-backend-bundle first")
    appdir = build / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    bindir = appdir / "usr/bin"
    bindir.mkdir(parents=True)
    shutil.copytree(backend, bindir / "runtime/backend/studio-backend", symlinks=True)
    shutil.copy2(translation, bindir / translation.name)
    solver_bin=args.su2_bin.resolve()
    names={"SU2_CFD": "SU2_CFD", "SU2_CFD_AD": "SU2_CFD", "SU2_DOT_AD": "SU2_DOT", "SU2_DEF": "SU2_DEF"}
    for name, folder in names.items():
        if not (solver_bin / folder / "src" / name).is_file():
            parser.error(f"Missing built solver: {solver_bin / folder / 'src' / name}")
    target=bindir / "solvers/SU2/bin"
    target.mkdir(parents=True)
    for name, folder in names.items():
        shutil.copy2(solver_bin / folder / "src" / name,target / name)
    licenses=appdir / "usr/share/licenses/su2-airfoil-studio"
    licenses.mkdir(parents=True)
    shutil.copy2(ROOT / "third_party/su2/COPYING", licenses / "SU2-COPYING")
    shutil.copy2(ROOT / "third_party/gmsh/LICENSE.txt", licenses / "Gmsh-LICENSE.txt")
    shutil.copy2(ROOT / "assets/fonts/OFL-JetBrainsMono.txt", licenses / "JetBrainsMono-OFL.txt")
    tools = args.linuxdeploy.resolve()
    if not tools.is_file():
        parser.error(f"linuxdeploy not found: {tools}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    qmake = args.qmake.resolve()
    if not qmake.is_file():
        parser.error(f"qmake not found: {qmake}")
    plugin = args.qt_plugin.resolve()
    if not plugin.is_file():
        parser.error(f"Qt deployment plugin not found: {plugin}")
    plugin_root = build / "qt-plugin"
    extracted = plugin_root / "squashfs-root"
    if not (extracted / "AppRun").is_file():
        if plugin_root.exists():
            shutil.rmtree(plugin_root)
        plugin_root.mkdir(parents=True)
        subprocess.run([str(plugin), "--appimage-extract"], cwd=plugin_root, check=True)
    toolbin = build / "appimage-tools"
    toolbin.mkdir(parents=True, exist_ok=True)
    wrapper = toolbin / "linuxdeploy-plugin-qt"
    wrapper.write_text(f'#!/bin/sh\nexec "{extracted / "AppRun"}" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    environment = os.environ.copy()
    environment["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    environment["QMAKE"] = str(qmake)
    environment["PATH"] = str(toolbin) + os.pathsep + environment.get("PATH", "")
    environment["OUTPUT"] = str(output / "SU2-Airfoil-Studio-x86_64.AppImage")
    if args.runtime_file:
        runtime_file = args.runtime_file.resolve()
        if not runtime_file.is_file():
            parser.error(f"AppImage runtime not found: {runtime_file}")
        environment["LDAI_RUNTIME_FILE"] = str(runtime_file)
    command = [str(tools), "--appdir", str(appdir), "--executable", str(executable),
               "--desktop-file", str(ROOT / "packaging/appimage/su2-airfoil-studio.desktop"),
               "--icon-file", str(ROOT / "assets/branding/su2-airfoil-studio.svg"),
               "--plugin", "qt", "--output", "appimage"]
    subprocess.run(command[:-2], env=environment, check=True)
    if args.offscreen_plugin:
        plugin = args.offscreen_plugin.resolve()
        if not plugin.is_file():
            parser.error(f"Offscreen plugin not found: {plugin}")
        platforms = appdir / "usr/plugins/platforms"
        platforms.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin, platforms / plugin.name)
    subprocess.run([str(tools), "--appdir", str(appdir), "--output", "appimage"], env=environment, check=True)
    artifact = Path(environment["OUTPUT"])
    if not artifact.is_file():
        raise RuntimeError(f"AppImage was not created: {artifact}")
    print(f"AppImage ready: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
