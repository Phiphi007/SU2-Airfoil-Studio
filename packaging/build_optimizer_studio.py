"""Build the unified SU2 AutoFoil Optimizer Studio portable release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--su2-bin", type=Path, required=True)
    parser.add_argument("--runtime-bin", type=Path, required=True)
    parser.add_argument("--su2-license", type=Path, required=True)
    parser.add_argument(
        "--replace", action="store_true",
        help="Replace a release previously created by this build script.",
    )
    args = parser.parse_args()
    su2_bin = args.su2_bin.expanduser().resolve()
    runtime_bin = args.runtime_bin.expanduser().resolve()
    su2_license = args.su2_license.expanduser().resolve()
    executables = ("SU2_CFD.exe", "SU2_CFD_AD.exe", "SU2_DOT_AD.exe", "SU2_DEF.exe")
    runtime_dlls = ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")
    missing = [str(su2_bin / name) for name in executables if not (su2_bin / name).is_file()]
    missing += [str(runtime_bin / name) for name in runtime_dlls if not (runtime_bin / name).is_file()]
    if not su2_license.is_file():
        missing.append(str(su2_license))
    if missing:
        raise FileNotFoundError("Missing build inputs:\n" + "\n".join(missing))

    build = ROOT / "build" / "optimizer_studio"
    frozen_parent = build / "frozen"
    release_parent = ROOT / "portable_release"
    app = release_parent / "SU2_AutoFoil_Optimizer_Studio"
    if app.exists():
        if not args.replace:
            raise FileExistsError(f"Refusing to overwrite an existing release: {app}")
        if not (app / "BUILD_MANIFEST.json").is_file():
            raise RuntimeError(f"Refusing to replace an unrecognized directory: {app}")
        shutil.rmtree(app)
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(build / "pyinstaller_cache")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(frozen_parent),
            "--workpath",
            str(build / "work"),
            str(ROOT / "packaging" / "optimizer_studio.spec"),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    shutil.copytree(frozen_parent / "SU2_AutoFoil_Optimizer_Studio", app)
    solver = app / "solvers" / "SU2" / "bin"
    solver.mkdir(parents=True)
    for name in executables:
        shutil.copy2(su2_bin / name, solver / name)
    for name in runtime_dlls:
        shutil.copy2(runtime_bin / name, solver / name)

    licenses = app / "licenses"
    licenses.mkdir()
    shutil.copy2(su2_license, licenses / "SU2-LICENSE.md")
    font_license = ROOT / "assets" / "fonts" / "OFL.txt"
    if font_license.is_file():
        shutil.copy2(font_license, licenses / "Noto-OFL.txt")
    for folder in ("airfoils", "python_api", "docs"):
        shutil.copytree(
            ROOT / folder,
            app / folder,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ("README.md", "使用手册.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, app / name)
    (app / "双击启动.cmd").write_text(
        "@echo off\r\nstart \"\" \"%~dp0SU2_AutoFoil_Optimizer_Studio.exe\"\r\n",
        encoding="utf-8-sig",
    )
    (app / "首次使用.txt").write_text(
        "这是 D-BCE 变形、网格、正问题、后处理和离散伴随优化的一体化版本。\n"
        "双击 SU2_AutoFoil_Optimizer_Studio.exe。\n"
        "启动时先选择工作目录；可拖动旧 BCE 的 h、alpha、beta 三条贝塞尔曲线控制点手动设计。\n"
        "手调结果可直接导出 DAT、精确送入网格，或用紧支撑 D-BCE 重拟合后进入优化。\n"
        "完成正问题后进入“伴随优化”，输入 Mach、Re、攻角及安全约束。\n"
        "优化完成后可导出 final_airfoil.dat，或只丢弃候选翼型并保留数值日志。\n"
        "整个文件夹必须一起保留，不能只复制 EXE。\n",
        encoding="utf-8-sig",
    )
    manifest = {
        "name": "SU2 AutoFoil Optimizer Studio",
        "version": "2.8.5",
        "python": sys.version,
        "bundled_su2": "8.5.0 local discrete-AD build",
        "features": [
            "stable-scale legacy h-alpha-beta Bezier editor",
            "adaptive non-jittering BCE preview", "0.35x/0.8x/1.5x drag controls",
            "curvature-regularized compact D-BCE refit", "undo controls",
            "dense uniform leading-edge structured mesh",
            "wall-spacing and radial-direction quality diagnostics",
            "0.05x extra-coarse structured meshes",
            "live mesh-count estimate and flow-domain scaling",
            "direct CFD", "anti-aliased post-processing", "CST", "D-BCE",
            "topology-safe strong-camber surface reports",
            "shape-preserving imported sharp trailing edges",
            "hybrid", "relay", "bounded-AoA discrete adjoint", "DAT export",
        ],
        "files": {
            path.relative_to(app).as_posix(): digest(path)
            for path in sorted(app.rglob("*")) if path.is_file()
        },
    }
    (app / "BUILD_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    package = release_parent / "SU2_AutoFoil_Optimizer_Studio_Windows_x64.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(release_parent).as_posix())
    checksum = digest(package)
    (release_parent / f"{package.name}.sha256").write_text(
        f"{checksum}  {package.name}\n", encoding="ascii"
    )
    print(f"Portable folder: {app}")
    print(f"ZIP: {package}")
    print(f"SHA256: {checksum}")


if __name__ == "__main__":
    main()
