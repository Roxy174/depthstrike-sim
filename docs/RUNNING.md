# 运行说明

所有命令在项目根目录的 PowerShell 中执行。Python 使用 3.12，下面用 `$py` 指定解释器。

## 环境

本机已有 `depthstrike` Conda 环境，直接设置：

```powershell
$py = "$env:USERPROFILE\.conda\envs\depthstrike\python.exe"
```

新电脑可建立独立环境，安装图形界面与 Astra 依赖：

```powershell
python -m venv .venv
$py = (Resolve-Path .venv\Scripts\python.exe).Path
& $py -m pip install -e ".[dev,display,astra]"
& $py -m pip check
& $py scripts/download_pose_model.py
```

模型仅在缺失时下载，已有模型及来源文件不会覆盖。依赖版本统一见 [pyproject.toml](../pyproject.toml)。仅做无窗口合成演示和规则测试可安装 `.[dev]`；Gemini SDK 采集另安装 `.[camera]`。

界面默认中文。Windows 使用微软雅黑或黑体；其他系统安装中文字体，或设置 `DEPTHSTRIKE_FONT` 为字体文件路径。

## Astra 摄像头

```powershell
& $py -m depthstrike --source astra-camera --config configs/adaptive.json
```

本入口适配已确认的旧款 Astra：深度 USB `2bc5:060f`，独立彩色接口 `2bc5:050f`。本机已安装驱动和运行库；其他电脑还需要：

1. 安装适配设备的 [Orbbec 官方 Astra 驱动](https://www.orbbec.com/developers/openni-sdk/)。本机使用版本 4.3.0.22。
2. 下载同一官方页面的 **OpenNI SDK 2.3.0.86 beta6，Win64**，将 `Win64-Release/sdk/libs/` 内容放入 `.cache/openni2/`，保留以下结构。

```text
.cache/openni2/
├── OpenNI2.dll
└── OpenNI2/Drivers/
    ├── orbbec.dll
    └── orbbec.ini
```

也可在启动命令后加 `--openni-dir PATH`。程序检查运行库版本、设备型号、640×480 帧格式和出厂配准状态，不在启动时安装驱动或更新固件。

彩色与深度使用独立接口，主机读取时间差检查不能证明曝光同步；画面保留“奥比中光相机体验”标记。实际定位精度与真人稳定性需另行测量。

## 演示和操作

```powershell
& $py -m depthstrike --source demo --config configs/adaptive.json
& $py -m depthstrike --source demo --config configs/adaptive.json --view dual
& $py -m depthstrike --source demo --headless --frames 600
```

演示使用合成骨架，不读取相机。默认配置的 600 帧演示为 9 次正式命中、90 分。

校准顺序为收拳、左右舒适前伸与收回、左右各试击一次、倒计时，再进入回合。空格暂停／继续，`R` 清分并重新校准，`Q` / `Esc` 或关闭窗口退出。增加 `--sound` 可启用 Windows 提示音。

`adaptive.json` 启用逐侧校准、跳变抑制和 0.20 秒的短暂丢点恢复。“追踪恢复中”时保持姿势，进度暂时冻结；持续缺失、明显移位或暂停会重置当前采样段。灰色空心预测点和“预览”目标只用于显示。

正式目标在校准后固定，改变站位或移动相机后按 `R`。查看“表面间距”“深度差”和“横向偏差”判断空间关系；二维圆圈重叠不直接计分。

## 其他输入

| 输入 | 命令参数 | 用途 |
| --- | --- | --- |
| Gemini SDK | `--source camera` | 使用设备时间戳、标定及软件对齐；需 `.[camera]` |
| OpenCV 体验 | `--source opencv-camera` | 主机计时、近似内参；不作为同步或精度验证 |
| 骨架回放 | `--source replay --input FILE.jsonl` | 重算校准与计分，无需相机 |
| 彩色与深度回放 | `--source rgbd-replay --input DIRECTORY` | 重新执行姿态检测和深度融合；需 MediaPipe |

Gemini SDK 若报告零设备时间戳，需按 SDK 官方说明注册 UVC 元数据并重新插拔设备；这涉及系统设置。旧的排查过程保留在 [相机检查记录](archive/HISTORY.md#docs-camera-smoke-2026-10-23-md)。采集失败会明确报错。

## 录制与回放

每次使用新的输出文件名或目录，已有输出会拒绝覆盖：

```powershell
& $py -m depthstrike --source demo --headless --frames 600 --record recordings/demo.jsonl
& $py -m depthstrike --source replay --input recordings/demo.jsonl
& $py -m depthstrike --source astra-camera --config configs/adaptive.json --record recordings/pose.jsonl --record-rgbd recordings/rgbd
& $py -m depthstrike --source rgbd-replay --input recordings/rgbd
```

默认不保存图像或人体轨迹。骨架记录保存配置、关节、操作和事件；RGB-D 记录还包含图像、米制深度与标定。真人录制前取得参与者同意，原始人像和模型默认不纳入 Git。

## 动作关卡与复盘

以下示例均使用新输出路径：

```powershell
& $py -m depthstrike.studio demo --output outputs/studio-try
& $py -m depthstrike.studio demo --output outputs/studio-batch --headless
& $py -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2
& $py -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2 --image outputs/review.png
```

合成示例生成九靶关卡，预设六次命中和三次空间未命中。复盘窗口用 `A / D` 或左右箭头切换靶位，空格播放／暂停，`R` 重播当前轨迹，`Q / Esc` 关闭。`--trial` 从 1 开始。

自己的完整 guided 骨架录制可转为关卡，再用骨架回放或相机挑战：

```powershell
& $py -m depthstrike.studio author --input recordings/pose.jsonl --output outputs/my-challenge.json
& $py -m depthstrike --source replay --input recordings/pose.jsonl --challenge outputs/my-challenge.json --review-output outputs/my-review.json
```

输入须包括完整校准、试击和正式阶段的有效出拳与收回。挑战回放的 `R` 不倒带原始录制，需从头体验时重新启动。复盘的紫色线段表示满足约束的局部空间修正；观测不足和未完成窗口不推断动作错误。

## 耗时统计

```powershell
& $py -m depthstrike --source demo --headless --frames 600 --metrics outputs/demo-metrics.json
```

统计包含采集、推理、融合、模拟与显示等软件阶段。`read` 已包含子阶段，不能重复相加；`frame_total` 排除回放等待，每阶段保留最近 4096 条样本计算分位数。它们不代表曝光到显示的延迟。测试和对比实验见 [开发与测试](DEVELOPMENT.md)。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 找到 0 个 Astra 深度设备 | 检查 USB、供电和驱动，确认设备管理器中 `ORBBEC Depth Sensor` 在线，关闭占用相机的程序 |
| 骨架或目标跳动 | 使用 `configs/adaptive.json`；保持光照和单人正面取景，双肩双肘双手入镜；移动后按 `R` |
| 校准反复停住 | 看当前引导，短暂恢复时保持姿势；持续缺失则调整取景和站位 |
| 看似碰到但没计分 | 检查深度差、活动手、出拳速度及是否收拳复位 |
| 模型缺失或 DLL 失败 | 核对 Python x64、依赖与运行库，缺模型时运行下载脚本 |
| 中文字体或三维窗口失败 | 设置 `DEPTHSTRIKE_FONT`；显示问题可用 `--view overlay` 或 `--headless` 排查 |
| 输出已存在 | 使用新文件名或目录 |
