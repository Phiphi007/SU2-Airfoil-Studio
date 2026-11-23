# SU2 Airfoil Studio Qt 便携版 / Portable edition

## 使用 / Use

1. 完整解压 ZIP，不要直接在压缩包中运行。Fully extract the ZIP; do not run inside the archive.
2. 双击 `SU2_Airfoil_Studio_Qt.exe`。Launch `SU2_Airfoil_Studio_Qt.exe`.
3. 首先选择工作目录，然后按“翼型 → 网格 → 求解 → 结果 → 伴随优化”操作。Choose a workspace, then follow Airfoil → Mesh → Solver → Results → Adjoint Optimization.

支持 Windows 10/11 x64。目标电脑不需要安装 Python，但必须保留 `_internal`、`assets`、`solvers` 和字体目录。The package supports Windows 10/11 x64 and requires no host Python, but `_internal`, `assets`, `solvers` and font folders must remain beside the executable.

## 两个入口 / Two entry points

- `SU2_Airfoil_Studio_Qt.exe`：PySide6 + VTK 桌面程序 / desktop application.
- `AutoFoilCLI.exe`：本地 JSON API、诊断和后台工作进程 / local JSON API, diagnostics and workers.

```powershell
.\AutoFoilCLI.exe info
.\AutoFoilCLI.exe schema
.\AutoFoilCLI.exe doctor
```

## 输出 / Output

图形界面使用用户选择的工作目录；未指定目录的 API 请求默认写入 `%LOCALAPPDATA%\SU2AutoFoilStudio`。The GUI uses the selected workspace; API requests without an output path default to `%LOCALAPPDATA%\SU2AutoFoilStudio`.

每个算例保存 DAT、网格、配置、SU2 历史、VTK、报告和优化历史。Each case stores DAT geometry, meshes, configuration, SU2 histories, VTK output, reports and optimization history.

## 故障排查 / Troubleshooting

- DLL 错误：确认 ZIP 完整解压，`solvers\SU2\bin` 中含三个 MinGW DLL。For DLL errors, verify the archive and the three MinGW DLLs in `solvers\SU2\bin`.
- 伴随不可用：确认四个 SU2 可执行文件都存在。For unavailable adjoint controls, verify all four SU2 executables.
- 启动失败：查看 `%LOCALAPPDATA%\SU2AutoFoilStudio\qt_gui_error.log`。For startup failures, inspect the Qt GUI error log.
- 结果未收敛：增加迭代并检查残差、CL/CD 窗口、网格和边界，不要只看进程退出码。For unconverged results, inspect residuals, force windows, mesh and boundaries instead of relying on exit code.

构建说明见 [BUILD.md](BUILD.md)，接口见 [API.md](API.md)。See [BUILD.md](BUILD.md) and [API.md](API.md).
