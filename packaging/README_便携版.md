# SU2 AutoFoil Studio 便携版

## 双击使用

1. 将整个 ZIP 解压到本地文件夹，例如 `D:\AutoFoil`。不要直接在压缩包里运行。
2. 双击 `AutoFoilStudio.exe`。
3. 导入翼型、生成网格，在求解设置页设置工况，再开始计算。

支持 Windows 10/11 **64 位 x64**。目标电脑不需要安装 Python、SU2、MPI，
也不需要修改 PATH。包内是 SU2 8.5.0 官方 Windows OpenMP 版，支持单机多线程，
不提供多机 MPI。此 EXE 不是 Linux/macOS/Windows ARM 原生程序。

必须保留 `_internal`、`solvers`、字体和其余配套文件，不能仅拷贝一个 EXE。
首次启动可能需要数秒。常规运行离线完成，启动时不会下载依赖或安装系统字体。

## 输出保存在哪里

默认保存在 `%LOCALAPPDATA%\SU2AutoFoilStudio`：

- `cases`：图形界面算例；
- `mesh_preview`：网格预览；
- `api_cases`：未指定目录的 API 算例；
- `desktop.log`、`gui_error.log`：运行与启动错误日志。

图形界面可以选择自己的结果目录。API 可以指定 `output_dir`。
也可通过 `SU2AUTOFOIL_DATA_DIR` 环境变量覆盖默认数据目录。
程序文件与计算数据分离，放在只读文件夹时仍可把结果写到用户目录。

## Python 调用

另一段 Python 程序调用 `AutoFoilCLI.exe`，不需要安装 NumPy 等计算依赖。
随包提供标准库客户端 `python_api/autofoil_client.py` 和完整的 [API 文档](API.md)。
调用方本身需要 Python 3.9+；仅双击使用界面则完全不需要 Python。

```python
import sys
sys.path.insert(0, r"D:\AutoFoil\python_api")
from autofoil_client import AutoFoilClient

client = AutoFoilClient(r"D:\AutoFoil\AutoFoilCLI.exe")
print(client.info())
result = client.run("builtin://naca0012", mode="mesh",
                    parameters={"global_refinement": 0.5})
print(result["files"]["mesh.su2"])
```

## 故障检查

在此文件夹中运行 `AutoFoilCLI.exe doctor`，检查图形组件、网格预览库和求解器。
不要把控制台入口 `AutoFoilCLI.exe` 误认为桌面入口；桌面入口是 `AutoFoilStudio.exe`。
若出现找不到 DLL，先确认 ZIP 完整解压，且安全软件没有隔离配套文件。
本包未做商业代码签名；请检查文件来源和 SHA-256，不要为运行它关闭系统安全保护。
详细实测范围见 [VALIDATION.md](VALIDATION.md)，重建步骤见 [BUILD.md](BUILD.md)。

计算成功不等于收敛或工程准确：仍需检查残差、气动力稳定性、Y+ 和网格无关性。
