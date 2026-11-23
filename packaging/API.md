# AutoFoil Portable API v1

## 1. 接口形式

这是本地 **EXE 子进程 + UTF-8 JSON** 接口，不是 HTTP 服务，不监听端口。
桌面端为 `SU2_Airfoil_Studio_Qt.exe`；自动化端为同一文件夹内的 `AutoFoilCLI.exe`。
二者使用同一套网格、求解、后处理核心。复制时保留整个发布文件夹。

```powershell
.\AutoFoilCLI.exe info
.\AutoFoilCLI.exe schema
.\AutoFoilCLI.exe doctor
.\AutoFoilCLI.exe run --request request.json
```

- `info`：版本、资源/数据目录和发现的求解器路径，不执行 CFD；
- `schema`：支持的参数名、类型、默认值和枚举；
- `doctor`：实际初始化 GUI、内置翼型和 Gmsh DLL，并执行 SU2 `--help`；
- `run`：同步执行一次任务，`--request -` 或省略 `--request` 时从 stdin 读 JSON。

前三个命令及 `run` 的正常处理结果：**stdout 恰好一个 JSON 对象**；进度与 SU2 日志
在 stderr。`--help` 输出普通帮助文本；非法命令行语法输出 argparse 错误，不保证 JSON。
所有路径都可以包含空格和中文。相对路径基于调用进程的当前目录，不是 JSON 文件目录。
建议 Python 调用时使用绝对路径。每次调用独立进程，批量任务逐次调用即可。

## 2. Python 快速开始

调用方 Python 3.9+；仅使用 Python 标准库。无需安装本程序的计算依赖。

```python
from pathlib import Path
import sys

APP = Path(r"D:\AutoFoil")  # 改成实际解压后包含两个 EXE 的文件夹
sys.path.insert(0, str(APP / "python_api"))
from autofoil_client import AutoFoilClient, AutoFoilError

client = AutoFoilClient(APP / "AutoFoilCLI.exe")
print(client.doctor())

try:
    result = client.run(
        "builtin://naca2412",    # 或 r"D:\Airfoils\my_airfoil.dat"
        mode="solve",
        # 省略 output_dir 自动新建算例；指定时必须是尚不存在的新目录
        parameters={"mach": 0.15, "aoa": 2.0, "reynolds": 3e6,
                    "iterations": 1000, "threads": 2,
                    "global_refinement": 1.0, "wake_refinement": 2.0,
                    "y_plus": 1.0, "language": "zh"},
    )
    print(result["output_dir"])
    print(result["last_values"])  # 原始 SU2 CSV 最后有效行的有限数值
    print(result["residual_target_met"])
    print(result["files"].get("Aerodynamic_Report/02_Surface_Pressure.png"))
except AutoFoilError as exc:
    print(exc.returncode, exc.result)
    print(exc.logs)               # stderr，可辅助定位质量门槛或求解失败
```

客户端方法：`info()`、`schema()`、`doctor()` 返回字典；
`run(airfoil="builtin://naca0012", *, mode="mesh", output_dir=None, parameters=None)`
返回结果字典，非零退出码或 `ok=false` 抛 `AutoFoilError`。
异常字段为 `.result`、`.returncode`、`.logs`。

客户端是**同步阻塞**接口，不提供暂停/继续、硬超时或远程取消。
GUI 的暂停/继续/终止功能仍然保留。不要只强杀 API 主进程：这可能遗留 SU2 子进程。
对于自建进程管理器，应管理整个进程树，并为每个并发任务使用不同目录与合理线程数。

不使用客户端也可以直接调用：

```python
import json
import subprocess

request = {"api_version": 1, "mode": "mesh", "airfoil": "builtin://naca0012",
           "parameters": {"global_refinement": 0.5}}
p = subprocess.run(
    [r"D:\AutoFoil\AutoFoilCLI.exe", "run", "--request", "-"],
    input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
)
response = json.loads(p.stdout)
if p.returncode:
    raise RuntimeError(response.get("error"), p.stderr)
print(response["files"]["mesh.su2"])
```

## 3. 请求

```json
{
  "api_version": 1,
  "mode": "mesh",
  "airfoil": "builtin://naca0012",
  "output_dir": "D:/Cases/new_case_001",
  "parameters": {
    "global_refinement": 0.5,
    "wake_refinement": 2.0,
    "mach": 0.15,
    "aoa": 2.0,
    "reynolds": 3000000,
    "y_plus": 1.0,
    "language": "zh"
  }
}
```

顶层字段：

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `api_version` | `1` | 仅接受整数 1 |
| `mode` | `mesh` | `mesh` 仅网格/配置；`solve` 网格+SU2+报告；`report` 对已有结果重绘报告 |
| `airfoil` | `builtin://naca0012` | Selig 顺序 DAT 路径，或任意有效四位 NACA，例如 `builtin://naca2412` |
| `output_dir` | 自动生成唯一算例目录 | `mesh`/`solve` 必须尚不存在，避免覆盖；`report` 必须指定含 history.csv 和 surface_flow.csv 的现有目录 |
| `parameters` | `{}` | 下表参数；未知字段/拼写错误会拒绝，不会静默忽略 |

`report` 会更新既有目录中的报告图、api_run.log、api_result.json，不修改原始 SU2 CSV/VTU。
重绘时传 `parameters={"language":"en"}` 可改变报告语言；其他计算参数不重新求解。

## 4. parameters

使用 JSON 数值/布尔值，不要用数字字符串。数值必须有限，不接受 NaN/Infinity。
几何单位按输入坐标解释；若使用 SI 工况，翼型坐标应为米，默认内置翼型弦长 1 m。

| 参数 | 默认 | 说明 |
| --- | ---: | --- |
| `surface_points` | 100 | 每侧几何采样点，整数 ≥8 |
| `global_refinement` | 1.0 | 全局加密，0.05–10；小于 1 生成粗网格 |
| `leading_edge_size` | 0.0015 | 前缘尺寸/弦长，(0,0.05] |
| `trailing_upper_size` | 0.0015 | 上后缘尺寸/弦长，(0,0.05] |
| `trailing_lower_size` | 0.0015 | 下后缘尺寸/弦长，(0,0.05] |
| `wake_refinement` | 2.0 | 尾迹加密，1–12 |
| `y_plus` | 1.0 | 正数，估算首层高度目标，不是求解后 Y+ 保证值 |
| `farfield` | 20.0 | 正数，远场半径/弦长 |
| `domain_scale` | 1.0 | 流场域缩放系数，0.25–10，与 farfield 相乘 |
| `growth_ratio` | 1.15 | 附面层参考扩张比，必须满足网格内核限制 |
| `boundary_layer_thickness` | 0.08 | 附面层总厚度/弦长，(0,0.5] |
| `farfield_size` | 0.4 | 正数，远场目标尺寸/弦长 |
| `wall_size` | 0.008 | 旧版兼容参数，切向密度实际由全局加密控制 |
| `mach` | 0.15 | 正数，来流 Mach |
| `aoa` | 2.0 | 攻角，度，可负 |
| `reynolds` | 3000000 | 正数，以处理后弦长为参考 |
| `temperature` | 288.15 | 正数，来流 K |
| `velocity` | 未设置 | 正数 m/s，仅覆盖首层高度估算的速度；默认由 Mach 和温度计算 |
| `nu` | 未设置 | 正数 m²/s，仅覆盖首层高度估算的运动黏度；默认由速度、弦长、Re 反算 |
| `solver` | `RANS` | `RANS` 或 `EULER`；RANS 为绝热无滑移壁面，EULER 为滑移壁面 |
| `turbulence` | `SA` | RANS 用 `SA` 或 `SST`；EULER 自动使用 NONE |
| `iterations` | 1000 | 最大迭代步，正整数 |
| `threads` | 1 | OpenMP 线程数，正整数；非 MPI 进程数 |
| `cfl` | 5.0 | 正数，初始 CFL；模板启用自适应 CFL |
| `residual_min` | -8.0 | log10 密度残差目标 |
| `skip_report` | false | `solve` 后跳过报告图，不影响 SU2 原始输出 |
| `language` | `zh` | `zh` / `en`，报告语言 |

API v1 不开放任意 SU2 配置文本注入，也不覆盖 GUI 全部高级边界/数值选项。
非默认等温壁面、入口出口边界等请通过 GUI 设置。
合法参数也可能因特定翼型无法达到网格质量门槛而失败；不会为了完成请求导出折叠网格。
CLI 不自动弹出 Gmsh 预览；需要交互预览请使用 GUI。

## 5. 响应和错误

```json
{
  "api_version": 1,
  "version": "1.0.0-portable",
  "ok": true,
  "status": "completed",
  "mode": "mesh",
  "output_dir": "D:/Cases/new_case_001",
  "report": null,
  "last_values": {},
  "residual_target_met": null,
  "files": {
    "mesh.su2": "D:/Cases/new_case_001/mesh.su2",
    "mesh_quality.json": "D:/Cases/new_case_001/mesh_quality.json",
    "api_result.json": "D:/Cases/new_case_001/api_result.json"
  },
  "convergence_note": "Process completion is not CFD validation; check residuals, forces, Y+ and mesh independence."
}
```

`files` 只列实际存在的文件，键为算例目录内相对路径，值为绝对路径。
`report` 是第一张报告图的路径，全部报告通过 `files` 中的 `Aerodynamic_Report/` 查找。
`last_values` 保留原始 SU2 CSV 的列名，例如 `Inner_Iter`、`rms[Rho]`、`CL`、`CD`；
列缺失时不能假设存在。`residual_target_met` 仅在 solve 有密度残差时为布尔值，其他情况为 null。
它只比较最后残差与目标，不表示气动力稳定、网格无关或工程验证已完成。

| 退出码 | 含义 |
| --- | --- |
| 0 | 请求成功处理；不代表 CFD 收敛 |
| 1 | 运行错误：缺少文件/依赖、网格质量失败、SU2/后处理失败等 |
| 2 | JSON 请求/参数无效，或命令行语法错误 |

运行错误为 `ok=false`，包含 `error.type` 和 `error.message`。
已开始的算例保留已有文件、`api_run.log` 和 `api_result.json`；可以检查部分结果。
在读取请求/创建目录前失败，或磁盘不可写时，不保证能落盘结果文件。

## 6. 数据、版本与替换求解器

默认数据根目录 `%LOCALAPPDATA%\SU2AutoFoilStudio`；
`SU2AUTOFOIL_DATA_DIR` 可改变数据根目录。
求解器优先用 `solvers/SU2/bin/SU2_CFD.exe`；
`SU2AUTOFOIL_SU2_EXECUTABLE` 可指定外部 SU2 完整路径，覆盖内置版本。
外部版本的 DLL、兼容性和 MPI 安装由调用者负责。
API v1 接口版本与 SU2 版本不同；当前包携带 SU2 8.5.0 OpenMP。
