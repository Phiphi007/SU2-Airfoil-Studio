"""SU2 AutoFoil 核心模块包。

模块边界见 ``docs/ARCHITECTURE.md``：

- ``geo_surgeon`` / ``cosine_resampler`` / ``airfoil_processor``：几何处理。
- ``yplus_calc``：目标 Y+ 对应的首层高度。
- ``mesh_architect`` / ``mesh_worker``：Pointwise 风格多块 C-H 全结构化四边形网格。
- ``su2_driver``：配置生成与 SU2_CFD 子进程。
- ``post_analyzer``：CSV 报告。
- ``field_visualizer``：flow.vtu 解析与云图渲染。
"""
