# V2.8.5 发布说明 / Release Notes

发布日期 / Release date: **2026-11-17**

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
