# 运行与复现

验证平台为 Windows 11 x64、Python 3.12。所有命令均在仓库根目录运行；以下使用 PowerShell。无需激活虚拟环境，不需要修改系统执行策略。

## 1. 安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,display,camera]"
.venv\Scripts\python.exe -m pip check
```

`python --version` 应为 3.12。核心和无窗口演示可仅安装 `.[dev]`；窗口需要 `.[display]`，真实相机与 RGB-D 回放需要 `.[camera]`。不建议与已有 Anaconda 全局环境混用。

直接依赖版本固定在 `pyproject.toml`。当前组合为 NumPy 2.2.6、MediaPipe 0.10.32、Orbbec Python SDK 2.1.2、Open3D 0.19.0、OpenCV 4.11.0.86、pytest 8.3.5。SDK 的分发包名为 `pyorbbecsdk2`，导入名为 `pyorbbecsdk`。SDK 与 MediaPipe 分别声明 OpenCV 标准/扩展分发包，因此二者固定为相同版本；不要单独升级其中一个或混装 headless 变体。

## 2. 无摄像头演示

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo
```

打开三维场景和反馈面板。演示骨架为解析合成轨迹，不会读取电脑摄像头，不用于证明视觉检测精度。左右手交替击打，蓝色表示左手、橙色表示右手，绿色表示短时命中反馈，灰色球为待激活目标。

- `Space`：暂停/继续；合成或相机输入仍被读取，交互与回合计时暂停。
- `R`：清除得分并重新校准。
- `Q` / `Esc`：退出。关闭任一窗口也会退出并释放资源。
- 三维窗口可用鼠标调整视角；初始视角为斜前方观察。

无窗口运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 240
```

默认配置下，上述固定轨迹得到 **240 帧、6 次命中、60 分**。退出时输出 JSON 摘要；其中 `processing_s` 为当前软件会话耗时，不是相机端到端延迟。无窗口 demo/camera 默认限制为 600 帧，回放默认读取至文件结束或回合结束；窗口模式运行至 60 s 回合结束或用户退出。

## 3. Gemini 2 相机模式

显式下载模型：

```powershell
.venv\Scripts\python.exe scripts/download_pose_model.py
```

下载器使用 Google 官方固定版本地址，生成模型和 `.task.json` 来源摘要，不覆盖已有文件。模型缺失时程序只报错，不会后台下载。已有文件不需要重新下载；摘要见 [模型说明](../models/README.md)。

连接 Gemini 2 至 USB 3 端口，关闭 Orbbec Viewer 等占用设备的软件，然后运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source camera
```

相机路径已实现，当前环境 SDK 枚举为 0 台设备，**真实采集、对齐和人体击球尚未验收**。上述入口在当前无设备条件下会明确失败，不会替换为演示模式。

设备可用后：保持单人正面站立、双手收至肩部附近，稳定约 0.6 s 完成校准；目标出现后向相机方向做轻缓直拳。目标固定在相机空间，身体移动不会拖动目标。移动相机或改变站位后按 `R`。请留出活动空间，不击打屏幕、设备或实物，不将计分解释为真实力量或专业动作评价。

采集优先选择 RGB 640×480 / 30 fps，不支持时查询 SDK 支持的 RGB 配置；深度使用设备默认流，经软件 D2C 对齐，拒绝尺寸或时间不匹配帧。实际配置与固件信息进入录制元信息。轴向深度统一换算为米。

当前支持无畸变和标准 Brown–Conrady 标定。未知、修改型或反向畸变模型会拒绝处理，不能手动改名绕过验证。SDK 2.1.2 提供模型字段；旧版绑定缺失该字段且系数非零时，须先独立确认标定模型，才可在配置中指定 `legacy_sdk_distortion_model`。当前锁定环境不需要该兼容设置。

## 4. 录制与回放

三维轨迹录制，仅保存骨架、配置、控制操作和事件：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --headless --frames 240 --record recordings/demo.jsonl
.venv\Scripts\python.exe -m depthstrike --source replay --input recordings/demo.jsonl --headless
.venv\Scripts\python.exe -m depthstrike --source replay --input tests/fixtures/straight_punches.jsonl --headless
```

首两条得分与逐帧事件一致。随仓库提供的手工核对夹具得到 4 帧、2 次命中、20 分。回放默认采用记录中的配置；显式 `--config` 使用该配置文件及程序默认值替代记录配置，适合对比实验，但不再保证相同结果。

真实相机录制（仅在参与者同意后进行）：

```powershell
.venv\Scripts\python.exe -m depthstrike --source camera --record recordings/session.jsonl --record-rgbd recordings/rgbd-session
.venv\Scripts\python.exe -m depthstrike --source rgbd-replay --input recordings/rgbd-session
```

RGB-D 目录保存 `frames.jsonl` 和无对象 `.npy` 数组，回放会重新执行姿态模型与深度融合，而非直接读取骨架。此设备录制流程尚待真实设备验证；数组往返及合成 RGB-D 模型推理已单独测试。原始 RGB-D 体积较大，不宜长时间连续录制。

两类记录均拒绝覆盖已有目标。请每次使用新文件名/新目录。`recordings/`、`outputs/`、`models/` 权重及 SDK `Log/` 已忽略；私有仓库也不意味着可以未经同意上传人像。轨迹回放只验证交互规则，不能代替视觉链路验收。

## 5. 参数与测试

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/default.json
.venv\Scripts\python.exe -m pytest -q
```

配置为 JSON 对象，可仅填写需要覆盖的字段。完整字段与校验见 `src/depthstrike/config.py`。工程默认：手半径 0.06 m、目标半径 0.08 m、目标前伸 0.5 m、置信度阈值 0.6、最大轨迹间隔 0.2 s。它们尚非真实人体实验的最优参数。

真实显示测试需桌面会话，默认跳过：

```powershell
$env:DEPTHSTRIKE_GUI_TESTS = '1'
.venv\Scripts\python.exe -m pytest tests/test_app.py -q
Remove-Item Env:DEPTHSTRIKE_GUI_TESTS
```

## 6. 故障定位

| 现象 | 检查方向 |
| --- | --- |
| 无设备 | USB 3、供电、Viewer 占用、SDK/固件配套；先用官方 Viewer 核对，不自动升级固件 |
| 模型缺失 | 运行显式下载命令；中文目录已用内存加载方式兼容 |
| DLL 导入失败 | 核对 x64 Python、SDK 安装和 Windows VC++ 运行库 |
| 无显示/窗口失败 | 更新显卡驱动，或使用 `--headless --frames 240` |
| 连续无有效帧 | 超时期间取消攻击并保持窗口响应；连续 5 s 后报错并关闭资源 |
| 长时间停在校准 | 确认肩、肘、腕在视野内，双手收回并保持稳定；查看关键点与置信度 |
| 拳头接近但不计分 | 核对三维深度、当前激活手、前伸方向、速度及收拳复位，不以二维叠加为准 |

实际验收范围和已知限制见 [VERIFICATION.md](VERIFICATION.md)。
