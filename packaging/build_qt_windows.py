"""Build a relocatable Qt/VTK desktop folder with the required SU2 AD tools."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core_modules.runtime_paths import APP_VERSION  # noqa: E402
EXECUTABLES = ("SU2_CFD.exe", "SU2_CFD_AD.exe", "SU2_DOT_AD.exe", "SU2_DEF.exe")
RUNTIME_DLLS = ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validate_files(directory: Path, names: tuple[str, ...], label: str) -> None:
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{label} is missing: {', '.join(missing)} in {directory}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-freeze", action="store_true")
    parser.add_argument("--su2-bin", type=Path, required=True)
    parser.add_argument("--runtime-bin", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "portable_release" / "SU2_Airfoil_Studio_Qt")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()

    su2_bin = args.su2_bin.expanduser().resolve()
    runtime_bin = (args.runtime_bin or su2_bin).expanduser().resolve()
    _validate_files(su2_bin, EXECUTABLES, "SU2 AD bin")
    _validate_files(runtime_bin, RUNTIME_DLLS, "MinGW runtime bin")

    dist_root = ROOT / "build" / "qt_dist"
    frozen = dist_root / "SU2_Airfoil_Studio_Qt"
    if not args.skip_freeze:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--distpath",
                str(dist_root),
                "--workpath",
                str(ROOT / "build" / "qt_work"),
                str(ROOT / "packaging" / "qt_studio.spec"),
            ],
            cwd=ROOT,
            check=True,
        )
    if not (frozen / "SU2_Airfoil_Studio_Qt.exe").is_file():
        raise FileNotFoundError(f"Frozen Qt application not found: {frozen}")

    output = args.output.expanduser().resolve()
    manifest_path = output / "BUILD_MANIFEST.json"
    if output.exists() and not manifest_path.is_file():
        raise RuntimeError(f"Refusing to merge into an unrecognized directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('{"status": "build in progress"}', encoding="utf-8")
    # Replace the frozen runtime instead of merging it.  The solver folder is
    # intentionally kept because it may also be the selected SU2 source.
    frozen_runtime = output / "_internal"
    if frozen_runtime.is_dir():
        shutil.rmtree(frozen_runtime)
    for executable in ("SU2_Airfoil_Studio_Qt.exe", "AutoFoilCLI.exe"):
        (output / executable).unlink(missing_ok=True)
    shutil.copytree(frozen, output, dirs_exist_ok=True)
    # A previous merged build may retain Poppler's unversioned ICU 78 shim even
    # after the PyInstaller analysis excludes it.  It shadows the Windows ICU
    # shim and makes QtWidgets fail to load.  Remove both stale files from the
    # final folder; Qt uses the operating-system ICU implementation instead.
    for stale_icu in ("icuuc.dll", "icudt78.dll"):
        (output / "_internal" / stale_icu).unlink(missing_ok=True)

    solver_output = output / "solvers" / "SU2" / "bin"
    solver_output.mkdir(parents=True, exist_ok=True)
    for name in EXECUTABLES:
        source = su2_bin / name
        destination = solver_output / name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
    for name in RUNTIME_DLLS:
        source = runtime_bin / name
        destination = solver_output / name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)

    for source, destination in (
        (ROOT / "README.md", output / "README.md"),
        (ROOT / "docs" / "QT_MIGRATION.md", output / "QT_MIGRATION.md"),
        (ROOT / "THIRD_PARTY_NOTICES.md", output / "THIRD_PARTY_NOTICES.md"),
    ):
        if source.is_file():
            shutil.copy2(source, destination)
    if (ROOT / "docs").is_dir():
        if (output / "docs").is_dir():
            shutil.rmtree(output / "docs")
        shutil.copytree(ROOT / "docs", output / "docs")
    case_studies = ROOT / "examples" / "case_studies"
    if case_studies.is_dir():
        packaged_examples = output / "examples"
        if packaged_examples.is_dir():
            shutil.rmtree(packaged_examples)
        shutil.copytree(
            case_studies,
            packaged_examples / "case_studies",
        )

    license_root = output / "licenses" / "python_packages"
    for distribution_name in ("PySide6", "PySide6-Essentials", "shiboken6", "vtk"):
        distribution = metadata.distribution(distribution_name)
        for item in distribution.files or ():
            if "licenses" not in {part.lower() for part in item.parts}:
                continue
            source = Path(distribution.locate_file(item))
            if source.is_file():
                destination = license_root / distribution_name / Path(*item.parts[item.parts.index("licenses") + 1 :])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    project_license_root = ROOT / "packaging" / "licenses"
    if project_license_root.is_dir():
        shutil.copytree(
            project_license_root,
            output / "licenses" / "redistribution",
            dirs_exist_ok=True,
        )

    manifest = {
        "frontend": "Qt 6 + VTK",
        "version": APP_VERSION,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "su2_source": str(su2_bin),
        "runtime_source": str(runtime_bin),
        "files": {
            path.relative_to(output).as_posix(): _digest(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path != manifest_path
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_zip:
        archive = output.parent / f"SU2_Airfoil_Studio_V{APP_VERSION}_Windows_x64.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for source in sorted(output.rglob("*")):
                if source.is_file():
                    bundle.write(source, source.relative_to(output.parent).as_posix())
        (archive.with_suffix(archive.suffix + ".sha256")).write_text(
            f"{_digest(archive)}  {archive.name}\n", encoding="ascii"
        )
        print(f"Archive: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")
    print(f"Portable folder: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
