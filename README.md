# PCB Agent · Flow Studio 2.0

> **离线可运行的四层 PCB 自动设计流程 Demo**：自然语言设计约束 + KiCad 原理图/网表 → 器件自动布局 → 自动布线、换层和过孔 → 内置几何与电气连通检查 → 导出工程文件。
>
> **An offline, constrained PCB-design workflow showcase.** It is not a general-purpose autorouter or manufacturing sign-off tool.

![Flow Studio PCB 工作区预览](docs/preview.png)

## ⭐ 先运行起来 / Quick start

**只想演示（无需安装依赖）：** 直接用 Edge/Chrome 打开仓库根目录的 [`OPEN_DEMO.html`](OPEN_DEMO.html)，保留默认输入，点 **“开始完整流程”**。网页已经打包了所需 JS/CSS；无需 API Key、Node、Python 或联网。录屏可在界面开启“录屏节奏”。

**要在本机调用 KiCad 原生 DRC：** 需要 Python **3.10+** 和另外安装的 KiCad CLI（推荐与项目实验版本一致的 10.x）。本地 Python 服务仅绑定 `127.0.0.1`：

```powershell
# 在 VS Code 打开当前仓库目录，终端执行：
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_studio.ps1
```

启动后浏览器通常自动打开；否则访问 `http://127.0.0.1:8765/`。本地服务默认查找 PATH 和已安装的 KiCad，也可明确指定：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_studio.ps1 `
  -KiCadCli "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
```

Windows 也可以双击 `START_WINDOWS.cmd`（该脚本与 PowerShell 启动器会优先查找仓库自身或上级目录的 `.venv`，不再要求固定安装到 `C:\pcb_agent`）。其他平台可运行 `python3 server.py`，或 `sh start.sh`。

> `OPEN_DEMO.html` 的离线页面可做内部检查；**只有启动本地服务并实际调用 KiCad CLI**，才能得到独立的原生 DRC 报告。无 CLI 时不会冒充 DRC 成功。

## 🧩 功能 / Features

- **受限自然语言约束识别**：板尺寸、4 铜层、通道数、部分安装面约束、线宽、间距、过孔。这里是规则解析器，**并未使用大模型**。
- **原理图与网表读取**：随包 KiCad `.kicad_sch`、KiCad XML `.net`、内部 JSON 网表；读取器件引脚及网络关系。层次原理图需先导出网表；不支持任意截图/PDF。
- **自动布局与四层布线**：双面器件、4 个铜层（`F.Cu / In1.Cu / In2.Cu / B.Cu`）、有障碍路径搜索、多网络分支和过孔换层。
- **自动检查与故障演示**：包括网络连通、异网短路、铜间距、板框、同面器件重叠、安装面、线宽、过孔和换层连接等；可人工删除一段线，检出断路并重布线复检。
- **交互可视化**：原理图、PCB 视图、铜层分解、缩放及检查报告。
- **工程导出**：生成 `.kicad_pcb`、`.kicad_sch`、BOM、网表、设计规则/工程文件、运行日志和检查 JSON；本地服务可对生成的副本执行 KiCad DRC。

## 📈 自带样板 / Built-in 12-channel AFE sample

| 项目 | 演示样板结果 |
|---|---:|
| 板尺寸 | 160 × 110 mm |
| 元件 | 204（电阻、电容、电感、OPA197、连接器） |
| 网络 / 焊盘 | 120 / 456 |
| 铜层 | 4 |
| 铜走线段 | 1,513 |
| 过孔 | 276 |
| 内置检查 | 12/12 通过 |

信号链示例：无源电阻分压衰减 → RC 滤波 → OPA197 同相放大 → 输出滤波；该电路是参考公开拓扑自行组织的**样例工程**，非厂商经过设计验证的参考板。可切换 4/8/12/16 通道；样板、封装和预生成 PCB 位于 `examples/`、`outputs/`。供验收讲解的功能范围请见 [`docs/VALIDATION.md`](docs/VALIDATION.md)。

**重要区分：** 内置 12 项检查通过、独立铜几何复核通过，**不等于 KiCad 原生 DRC/ERC、SI/PI、模拟电路实测、可制造性验证通过**。本仓库没有用户真实 RP2350 PCB，也不会把演示生成结果写进真实工程。

## 🗂️ 仓库目录 / Structure

```text
app/               核心 JS 引擎、原理图解析、网页界面
examples/          原理图、网表、输入、配套封装库
outputs/           一个可复现的只读演示参考 PCB 和必要的 KiCad 项目文件
docs/              架构、来源、验证范围、录屏讲稿、GitHub 上传步骤
legacy/model.py    用于导出板的独立审计的旧解析器
server.py          本地 Python HTTP 服务 + 可选 KiCad CLI 桥接
build.py           从 app/ 重新生成单文件 OPEN_DEMO.html
tests/             JS / Python 回归测试以及可选浏览器与几何审计
.github/workflows/ci.yml  每次 push / PR 的基础自动测试
```

> `runs/`、测试截图、反馈 ZIP、视频和个人绝对路径不随源码仓库发布。所有新生成的运行数据由 `.gitignore` 排除；仓库保留一套必要的、能复现的参考 PCB。

## 🧪 开发与测试 / Tests

安装 **Node.js 22+**（仅引擎测试需要）和 **Python 3.10+**（本机服务和重建离线网页需要），在仓库根目录执行：

```powershell
node --test tests/engine.test.js
python -m unittest discover -s tests -p test_server.py
python build.py
```

另外的独立 PCB 几何审计和浏览器检查需要可选依赖：

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tests/independent_audit.py
python tests/browser_checks.py
```

基础测试会在 GitHub Actions 中运行；**CI 通过不代表本机 KiCad 原生 DRC 通过**。改变 `app/` 中的 JS/CSS/HTML 后，记得执行 `python build.py` 更新离线包。

## 📌 当前边界与下一步

- 定位：**有具体输入范围的 Demo / showcase**，不是任意原理图通用 PCB 自动设计器。
- 当前自检主要验证特定几何与网络关系；硬件可靠性、实际元器件选型、封装制造限制需要后续工程验证。
- 后续优先加入 KiCad 10.x 实机 DRC 回归、真正可编辑的输入适配器、布局约束扩展和更一般的路由能力。
- 真实工程必须保持只读；在独立 sandbox 中做修改并记录证据。

详细 GitHub 新建仓库与上传流程见 **[`docs/GITHUB_UPLOAD_GUIDE.md`](docs/GITHUB_UPLOAD_GUIDE.md)**。

## ⚖️ 版权与授权

本仓库来自项目演示交付文件，不自动附加 MIT、Apache 等开源许可证；**公开发布前由项目所有者确认源代码、样例和参考素材的发布权**。如涉及甲方保密要求，建议先建 **Private** 仓库。`docs/SOURCES.md` 记载了参考电路和数据表来源。
