# Portable build validation — 2026-10-06

## 实测通过

- 65 项源代码回归测试通过，包含 GUI 布局、网格质量、多翼型、后处理和 8 项新增 API/打包路径测试。
- 将实际 EXE、运行库和求解器复制到一个含中文及空格的新目录，工作目录也不同于安装目录。
- 子进程 PATH 仅保留 Windows 和 System32；移除 Python、Tcl、SU2 等原有环境配置。
- `info` 确认使用新位置的内置求解器；`schema` 和无效请求 JSON/退出码正常。
- `doctor` 成功初始化 Tk 界面、内置翼型预览、Gmsh 4.15.2 DLL，启动 SU2 8.5.0。
- `SU2_Airfoil_Studio_Qt.exe --smoke-test` 正常初始化 PySide6 + VTK 图形界面并退出。
- API 实际生成 C-H 网格，以 2 个 OpenMP 线程运行 2 步 SU2，输出 CSV、VTU 与四张英文报告图。
- `report` 模式从上述原始结果生成四张中文报告图，没有重新运行求解。
- GUI 冻结版流程成功调用独立网格 EXE 子进程、运行 SU2，并生成实时曲线和报告。
- 标准库 Python 客户端成功获取信息并执行重绘报告请求。
- 扫描 154 个 EXE/DLL/PYD，未发现缺失的非系统导入；内置 SU2 仅导入 Windows 系统 DLL，
  没有 MPI 依赖。桌面 EXE 为 GUI 子系统，API EXE 为控制台子系统，求解器为 x64。

复查脚本：源码中的 `packaging/validate_portable.py`。
测试数据留在构建目录，不随最终包分发；包内不包含用户历史算例或本机虚拟环境。

## 验证边界

构建和上述测试在 Windows 11 x64 / Python 3.12 上完成。
尚未在另一台实体电脑或全新 Windows 虚拟机上验证，不能把同机迁移测试等同于所有电脑兼容性认证。
Windows 10/11 x64 是目标平台；实际运行还受图形驱动、系统完整性和安全软件策略影响。

两步试算只验证数据流程，不是收敛气动结果。API 正确标记残差未达标。
此版本未进行代码签名，发布包必须整体复制，不支持仅移动一个 EXE。
