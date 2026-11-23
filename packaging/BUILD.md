# Qt Windows x64 便携版构建 / Qt Windows x64 portable build

当前唯一生产打包目标是 PySide6 + VTK 版本。旧 Tk 打包脚本已经移除；`gui_app.py` 仅作为兼容数值后端和回归夹具保留。

The only production packaging target is the PySide6 + VTK application. Legacy Tk packaging scripts have been removed; `gui_app.py` remains only as a compatibility numerical backend and regression fixture.

## 依赖 / Prerequisites

- Windows x64, CPython 3.12;
- `requirements.txt` and `packaging/requirements-build.txt`;
- a SU2 AD directory containing `SU2_CFD.exe`, `SU2_CFD_AD.exe`, `SU2_DOT_AD.exe`, `SU2_DEF.exe`;
- `libgcc_s_seh-1.dll`, `libstdc++-6.dll`, `libwinpthread-1.dll` in the same directory or a separate runtime directory.

## 构建 / Build

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
.\.venv\Scripts\python.exe packaging\build_qt_windows.py `
  --su2-bin "D:\SU2-AD\bin" `
  --runtime-bin "D:\SU2-AD\bin"
```

输出 / Output:

```text
portable_release/SU2_Airfoil_Studio_Qt/
portable_release/SU2_Airfoil_Studio_Qt.zip
```

`SU2_Airfoil_Studio_Qt.exe` 是无控制台桌面入口，`AutoFoilCLI.exe` 是 JSON/stdio 和私有工作进程入口。二者共享 `_internal`、`assets` 与 `solvers`，不能只复制单个 EXE。

`SU2_Airfoil_Studio_Qt.exe` is the windowed entry point and `AutoFoilCLI.exe` provides JSON/stdio and private worker commands. They share `_internal`, `assets` and `solvers`; do not copy a single EXE alone.

## 发布验证 / Release verification

```powershell
.\portable_release\SU2_Airfoil_Studio_Qt\AutoFoilCLI.exe info
.\portable_release\SU2_Airfoil_Studio_Qt\AutoFoilCLI.exe doctor
.\portable_release\SU2_Airfoil_Studio_Qt\SU2_Airfoil_Studio_Qt.exe --smoke-test
```

正式发布还应运行核心回归、Qt 回归、真实网格和至少一个 SU2 正问题/伴随案例。A production release must also pass core regressions, Qt regressions, a real mesh case and at least one SU2 direct/adjoint case.
