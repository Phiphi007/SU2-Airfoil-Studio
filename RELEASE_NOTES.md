# V2.8.5 发布说明 / Release Notes

发布日期 / Release date: **2026-11-17**

## 2026-11-23 Qt-only production update

- Qt 手调 BCE 补齐最新约束交互：自由变形、锁定厚度、锁定弯度、红色控制点、固定预览范围、无效几何拦截，以及直接使用/D-BCE 重拟合双出口。The Qt BCE editor restores the latest constraint workflow: free, lock-thickness and lock-camber modes, red control points, stable view limits, invalid-geometry blocking and separate direct/D-BCE exits.
- 移除旧 Tk 启动/打包入口和 V1/V2 图标；生产入口统一为 `SU2_Airfoil_Studio_Qt.exe`。Removed obsolete Tk launch/package entry points and V1/V2 branding assets; the production entry is now the Qt executable.
- D-BCE 优化笔刷新增最小半宽与 CFD 壁面最少支撑点门槛。Added minimum half-width and CFD support-node gates for D-BCE optimization brushes.
- 新增可复现 NACA0012 固定升力案例：充分收敛基准上 CD 降低 0.603%，CL 误差 1.05×10⁻⁵，优化耗时 544.58 s；同时撤销由未收敛基准造成的 3.078% 初步结论。Added a reproducible fixed-lift NACA0012 case with CD −0.603%, CL error 1.05×10⁻⁵ and 544.58 s optimization time on a converged baseline; the preliminary 3.078% claim from an unconverged baseline is explicitly invalidated.
- 固定升力配平在首步后使用带符号和幅值保护的局部割线斜率，减少变形翼型与基准升力曲线不同导致的慢收敛。Fixed-lift trim now uses a sign- and magnitude-bounded local secant slope after the first correction, reducing slow convergence when the deformed lift curve differs from the baseline.
- README、案例教程和便携版构建说明全部更新为中英双语 Qt/VTK 工作流。Rewrote the README, case tutorial and portable-build guide for the bilingual Qt/VTK workflow.

## 主要修复 / Key fixes

- 大弯度翼型的上下表面按连续壁面拓扑拆分，修复几何图和 Cp 图的假高频震荡。Strongly cambered surfaces are split by continuous wall topology, removing false high-frequency oscillation in geometry and Cp plots.
- 已经闭合的用户/手调尖后缘保持原形，不再二次尾段拟合。Closed imported or manually edited sharp trailing edges are preserved without a second tail reconstruction.
- D-BCE 交接使用重叠紧支撑笔刷和曲率正则，零手调保持机器零误差。D-BCE handoff uses overlapping compact brushes and curvature regularization; zero edits remain exact.
- 网格、云图和翼型显示内嵌于工业深色界面；云图支持自动或自定义色阶。Mesh, contour and geometry views are embedded in the industrial dark UI; contour limits may be automatic or manual.
- 实时日志与实时收敛合并显示，网格和求解均有进度与暂停/继续/终止控制。Logs and convergence share one view, with progress and pause/resume/stop controls for meshing and solving.
- 可导入带外部边界标记的 `.su2` 网格。External `.su2` meshes with pre-defined markers can be imported.

## 验证 / Validation

- 关键几何、D-BCE 和报告回归 17/17 通过。Focused geometry, D-BCE and report regressions: 17/17 passed.
- NACA6409 强弯度结构化网格回归通过，实际耗时 274.611 s。Real NACA6409 structured-mesh regression passed in 274.611 s.
- 冻结版 GUI、Gmsh 4.15.2 和 SU2 8.5.0 自检通过。Frozen GUI, Gmsh 4.15.2 and SU2 8.5.0 doctor passed.
- 手调翼型冷启动与暖启动 RANS 代表算例通过所述残差/气动力窗口。Representative cold and warm RANS cases passed the stated residual/force windows.

完整条件和限制见 [`docs/TESTING.md`](docs/TESTING.md)。See [`docs/TESTING.md`](docs/TESTING.md) for conditions and limitations.

## 兼容性 / Compatibility

- Windows 10/11 x64;
- 便携版内置 Python 运行时、Gmsh 与 SU2 8.5.0 OpenMP；the portable build bundles the runtime, Gmsh and SU2;
- 源码模式支持 Python 3.11/3.12，并需要外部 SU2 8.x。Source mode supports Python 3.11/3.12 and requires external SU2 8.x.

## 发布文件 / Release assets

- `SU2_AutoFoil_Optimizer_Studio_Windows_x64_v285.zip` — 139.16 MiB;
- SHA-256: `ac2d0a045bdaf2342b82cacbf93172c481eeed6335f1b831a7f256b712b3a811`;
- 同名 `.sha256` 文件可用于下载后核对。Use the matching `.sha256` file to verify the download.

## 升级提醒 / Upgrade note

必须用新版完整文件夹替换旧版，不能只替换 EXE。旧算例目录可继续读取，但建议用 V2.8.5 重新生成报告以获得正确的强弯度表面拆分。Replace the complete application folder, not only the EXE. Old cases remain readable, but regenerate reports with V2.8.5 to obtain the corrected strong-camber surface split.
